# Copyright 2026 mp3monster.org
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Reusable mixins for OpAMP client server-handling and runtime lifecycle logic."""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from codecs import decode as byte_value
from typing import TYPE_CHECKING

import httpx
from google.protobuf import text_format

from opamp_consumer.custom_handlers import build_factory_lookup, create_handler
from opamp_consumer.exceptions import AgentException
from opamp_consumer.proto import opamp_pb2
from opamp_consumer.reporting_flag import ReportingFlag
from shared.opamp_config import (
    PB_FIELD_AGENT_IDENTIFICATION,
    PB_FIELD_COMMAND,
    PB_FIELD_CONNECTION_SETTINGS,
    PB_FIELD_CUSTOM_CAPABILITIES,
    PB_FIELD_CUSTOM_MESSAGE,
    PB_FIELD_ERROR_RESPONSE,
    PB_FIELD_INSTANCE_UID,
    PB_FIELD_PACKAGES_AVAILABLE,
    PB_FIELD_REMOTE_CONFIG,
    PB_FIELD_RETRY_INFO,
    PB_FLAG_REPORT_FULL_STATE,
)

if TYPE_CHECKING:
    from pathlib import Path

    from opamp_consumer.abstract_client import OpAMPClientData
    from opamp_consumer.config import ConsumerConfig


class ServerMessageHandlingMixin:
    """ServerToAgent message dispatch and handler implementations."""

    data: OpAMPClientData
    config: ConsumerConfig
    _custom_handler_folder: Path
    _custom_handler_lookup: dict[str, object]

    def restart_agent_process(self) -> bool:
        """Restart the managed agent process.

        Concrete implementations are expected to provide this behavior.
        """
        raise NotImplementedError

    def _handle_server_to_agent(self, reply: opamp_pb2.ServerToAgent) -> bool:
        """Process ServerToAgent fields and dispatch each populated payload section.

        Args:
            reply: ServerToAgent payload received from the provider.

        Returns:
            True when message processing completed without critical handling errors.
        """
        logger = logging.getLogger(__name__)
        logger.debug("_handle_server_to_agent called")
        successful_message = True

        logger.debug("Handling Server to agent payload:%s", reply)
        if reply is None:
            logger.error("Been given None response")
            return False

        try:
            if not self._validate_reply_instance_uid(reply):
                successful_message = False
        except ValueError as val_err:
            logger.error("Error processing svr instance uid %s", val_err)
            successful_message = False

        try:
            if reply.HasField(PB_FIELD_ERROR_RESPONSE):
                self.data.set_all_reporting_flags()
                self.handle_error_response(error_response=reply.error_response)
            if reply.HasField(PB_FIELD_REMOTE_CONFIG):
                self.handle_remote_config(reply.remote_config)
            if reply.HasField(PB_FIELD_CONNECTION_SETTINGS):
                self.handle_connection_settings(reply.connection_settings)
            if reply.HasField(PB_FIELD_PACKAGES_AVAILABLE):
                self.handle_packages_available(reply.packages_available)
            if reply.flags:
                self.handle_flags(reply.flags)
            if reply.capabilities:
                self.handle_capabilities(reply.capabilities)
            if reply.HasField(PB_FIELD_AGENT_IDENTIFICATION):
                self.handle_agent_identification(reply.agent_identification)
            if reply.HasField(PB_FIELD_COMMAND):
                self.handle_command(reply.command)
            if reply.HasField(PB_FIELD_CUSTOM_CAPABILITIES):
                self.handle_custom_capabilities(reply.custom_capabilities)
            if reply.HasField(PB_FIELD_CUSTOM_MESSAGE):
                self.handle_custom_message(reply.custom_message)

        except AgentException as agent_err:
            logger.error("Agent Error received - %s", agent_err)
            successful_message = False
        return successful_message

    def _validate_reply_instance_uid(self, reply: opamp_pb2.ServerToAgent) -> bool:
        """Validate that a reply contains and matches the expected instance UID.

        Args:
            reply: Incoming ServerToAgent payload.

        Returns:
            True if the payload instance UID is present and matches this client.
        """
        logger = logging.getLogger(__name__)
        # `instance_uid` is a proto3 scalar bytes field and does not support HasField().
        if reply.instance_uid:
            logger.debug(
                "reply target is %s",
                byte_value(reply.instance_uid, errors="replace"),
            )
            if reply.instance_uid == self.data.uid_instance:
                return True
            logger.error(
                "Message doesn't have an instance uid or doesn't match our "
                "service instance id %s",
                byte_value(reply.instance_uid, errors="replace"),
            )
            return False
        logger.error(
            "Server didn't share instance_uid, my instance uid is %s",
            byte_value(self.data.uid_instance or b"", errors="replace"),
        )
        return False

    def handle_error_response(
        self, error_response: opamp_pb2.ServerErrorResponse
    ) -> None:
        """Log details from a ServerErrorResponse.

        Args:
            error_response: Server error payload to inspect and log.
        """
        logger = logging.getLogger(__name__)
        logger.warning("server error_response type=%s", error_response.type)
        if error_response.error_message:
            logger.warning(
                "*******/n server error_response message=%s/n*******",
                error_response.error_message,
            )
        if error_response.HasField(PB_FIELD_RETRY_INFO):
            logger.warning(
                "server error_response retry_after_nanoseconds=%s",
                error_response.retry_info.retry_after_nanoseconds,
            )

    def handle_remote_config(self, remote_config: opamp_pb2.AgentRemoteConfig) -> None:
        """Log the remote-config payload received from the provider.

        Args:
            remote_config: Remote configuration payload from ServerToAgent.
        """
        logging.getLogger(__name__).info(
            "server remote_config:\n%s", text_format.MessageToString(remote_config)
        )

    def handle_connection_settings(
        self, connection_settings: opamp_pb2.ConnectionSettingsOffers
    ) -> None:
        """Log provider connection-settings offers for diagnostics and visibility.

        Args:
            connection_settings: Connection settings offered by the provider.
        """
        logging.getLogger(__name__).info(
            "server connection_settings:\n%s",
            text_format.MessageToString(connection_settings),
        )

    def handle_packages_available(
        self, packages_available: opamp_pb2.PackagesAvailable
    ) -> None:
        """Log package offers sent by the provider.

        Args:
            packages_available: Package availability payload from ServerToAgent.
        """
        logging.getLogger(__name__).info(
            "server packages_available:\n%s",
            text_format.MessageToString(packages_available),
        )

    def handle_flags(self, flags: int) -> None:
        """Log raw server flag bitmask values from ServerToAgent.

        Args:
            flags: Integer bitmask from `ServerToAgent.flags`.
        """
        logger = logging.getLogger(__name__)
        flag_names: list[str] = []
        for enum_value in opamp_pb2.ServerToAgentFlags.DESCRIPTOR.values:
            if enum_value.number == 0:
                continue
            if flags & enum_value.number:
                name = enum_value.name
                if name.startswith("ServerToAgentFlags_"):
                    name = name[len("ServerToAgentFlags_") :]
                flag_names.append(name)

        if PB_FLAG_REPORT_FULL_STATE in flag_names:
            self.data.set_all_reporting_flags(True)
            logger.info(
                "server flags include ReportFullState; set all reporting flags true"
            )

        if flag_names:
            logger.info("server flags: %s (%s)", flags, ", ".join(flag_names))
        else:
            logger.info("server flags: %s", flags)

    def handle_capabilities(self, capabilities: int) -> None:
        """Log raw server capability bitmask values from ServerToAgent.

        Args:
            capabilities: Integer bitmask from `ServerToAgent.capabilities`.
        """
        logging.getLogger(__name__).debug("server capabilities: %s", capabilities)

    def handle_command(self, command: opamp_pb2.ServerToAgentCommand) -> None:
        """Handle ServerToAgent command payloads.

        Args:
            command: Command payload from the provider.
        """
        logger = logging.getLogger(__name__)
        if command is None:
            return
        logger.info("server command:\n%s", text_format.MessageToString(command))
        match command.type:
            case opamp_pb2.CommandType.CommandType_Restart:
                logger.info("server command to restart recognized")
                self.restart_agent_process()
            case _:
                raise AgentException(f"Unknown command type: {command.type}")

    def handle_agent_identification(
        self, agent_identification: opamp_pb2.AgentIdentification
    ) -> None:
        """Update local instance UID when the server sends AgentIdentification.

        Args:
            agent_identification: AgentIdentification payload with replacement UID.
        """
        logging.getLogger(__name__).info(
            "server agent_identification:\n%s",
            text_format.MessageToString(agent_identification),
        )
        self.data.uid_instance = agent_identification.new_instance_uid

    def handle_custom_capabilities(
        self, custom_capabilities: opamp_pb2.CustomCapabilities
    ) -> None:
        """Log custom capability declarations received from the provider.

        Args:
            custom_capabilities: Custom capability list reported by the provider.
        """
        logging.getLogger(__name__).info(
            "notified of server custom_capabilities: %s",
            text_format.MessageToString(custom_capabilities),
        )

    def handle_custom_message(self, custom_message: opamp_pb2.CustomMessage) -> None:
        """Route a custom message to its handler and execute it against this client.

        Args:
            custom_message: Custom message payload containing capability and data.
        """
        logger = logging.getLogger(__name__)
        logger.info(
            "server custom_message: %s", text_format.MessageToString(custom_message)
        )
        if custom_message is None:
            return

        # Resolve handler factories from the concrete client module for test patch points.
        client_module = sys.modules.get(self.__class__.__module__)

        create_handler_fn = create_handler
        build_factory_lookup_fn = build_factory_lookup
        if client_module is not None:
            create_handler_fn = getattr(client_module, "create_handler", create_handler)
            build_factory_lookup_fn = getattr(
                client_module, "build_factory_lookup", build_factory_lookup
            )

        capability = str(custom_message.capability or "").strip()
        if not capability:
            raise AgentException("CustomMessage capability is missing")
        logger.debug(
            "handling custom message capability=%s type=%s data_len=%s",
            capability,
            str(custom_message.type or ""),
            len(bytes(custom_message.data or b"")),
        )

        handler = create_handler_fn(
            capability,
            self._custom_handler_folder,
            client_data=self.data,
            factory_lookup=self._custom_handler_lookup,
            allow_custom_capabilities=bool(self.config.allow_custom_capabilities),
        )
        logger.debug(
            "custom handler lookup initial capability=%s found=%s",
            capability,
            handler.__class__.__name__ if handler is not None else None,
        )
        if handler is None:
            self._custom_handler_lookup = build_factory_lookup_fn(
                self._custom_handler_folder,
                client_data=self.data,
            )
            handler = create_handler_fn(
                capability,
                self._custom_handler_folder,
                client_data=self.data,
                factory_lookup=self._custom_handler_lookup,
                allow_custom_capabilities=bool(self.config.allow_custom_capabilities),
            )
            logger.debug(
                "custom handler lookup after refresh capability=%s found=%s",
                capability,
                handler.__class__.__name__ if handler is not None else None,
            )
        if handler is None:
            raise AgentException(
                f"No command handler registered for capability: {capability}"
            )

        handler.set_custom_message_handler(custom_message)
        logger.debug(
            "executing custom handler capability=%s handler=%s",
            capability,
            handler.__class__.__name__,
        )
        command_error = handler.execute(self)
        if command_error is not None:
            raise AgentException(str(command_error))


class ClientRuntimeMixin:
    """Agent process lifecycle and heartbeat polling behavior."""

    data: OpAMPClientData
    config: ConsumerConfig

    async def send(self) -> opamp_pb2.ServerToAgent | None:
        """Send AgentToServer payloads and return the provider response."""
        raise NotImplementedError

    _runtime_agent_command = "agent"
    _runtime_config_flag = "-c"
    _heartbeat_paths = ("/health",)
    _localhost_base = "http://localhost"
    _http_timeout_seconds = 5.0
    _error_prefix = "error: "
    _error_status = "error"
    _heartbeat_skew_seconds = 1
    _semaphore_filename = "OpAMPSupervisor.signal"
    _key_agent_version = "version"
    _key_agent_edition = "edition"
    _json_key_agent = "agent"
    _json_key_agent_fallback: str | None = None
    _json_key_version = "version"
    _json_key_edition = "edition"
    _value_agent_type = "Agent"

    def launch_agent_process(self) -> bool:
        """Launch the configured agent process using runtime command metadata."""
        logger = logging.getLogger(__name__)
        command = [
            self._runtime_agent_command,
            *(self.config.agent_additional_params or []),
            self._runtime_config_flag,
            self.config.agent_config_path,
        ]
        logger.debug(
            "About to start agent process with config %s and command %s",
            self.config.agent_config_path,
            command,
        )
        try:
            with self.data.process_lock:
                process_response: subprocess.Popen[bytes] = subprocess.Popen(command)
                self.data.agent_process = process_response
                self.data.launched_at = time.time_ns()
        except FileNotFoundError as file_error:
            logger.error(
                "Agent launch failed because command was not found (%s): %s",
                self._runtime_agent_command,
                file_error,
            )
            return False
        except Exception as launch_error:  # pragma: no cover - env-dependent
            logger.exception("Agent launch failed for command %s", command)
            logger.debug("Agent launch exception detail: %s", launch_error)
            return False
        logger.info("Launch result = %s", process_response)
        return True

    def terminate_agent_process(self) -> None:
        """Terminate the launched Agent process if available."""
        logger = logging.getLogger(__name__)
        with self.data.process_lock:
            process = self.data.agent_process
            self.data.allow_heartbeat = False
            if process is None:
                return
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Agent did not terminate in time; killing process")
                print("Agent did not terminate in time; killing process")
                process.kill()
                process.wait(timeout=5)
            self.data.agent_process = None

    def restart_agent_process(self) -> bool:
        """Stop the current agent process and start a new instance."""
        logger = logging.getLogger(__name__)
        logger.info("Restarting agent process")
        lock_acquired = self.data.process_lock.acquire(timeout=30)
        if not lock_acquired:
            raise AgentException(
                "Timed out waiting for process lock while restarting agent process"
            )
        try:
            self.terminate_agent_process()
            relaunched = self.launch_agent_process()
        finally:
            self.data.process_lock.release()
        if not relaunched:
            raise AgentException("Failed to restart agent process")
        logger.info("Agent process restarted")
        return relaunched

    def _populate_disconnect(
        self, msg: opamp_pb2.AgentToServer
    ) -> opamp_pb2.AgentToServer:
        """Populate disconnect data and ensure instance UID is set."""
        if self.data.uid_instance is not None:
            msg.instance_uid = self.data.uid_instance
            logging.getLogger(__name__).warning(
                "Set disconnect message instance UID to %s", self.data.uid_instance
            )
        msg.agent_disconnect.SetInParent()
        return msg

    async def send_disconnect(self) -> None:
        """Implements `OpAMPClientInterface.send_disconnect` with best-effort send."""
        msg = self._populate_disconnect(opamp_pb2.AgentToServer())
        logging.getLogger(__name__).debug("Built disconnect message")

        try:
            await self.send(msg, send_as_is=True)
            self.data.allow_heartbeat = False
        except Exception as err:  # pragma: no cover - error path varies by env
            logging.getLogger(__name__).warning(
                "Failed to send disconnect message - %s", err
            )

    async def _send_disconnect_with_timeout(self, timeout_seconds: float = 1.0) -> None:
        """Best-effort disconnect send with a short timeout."""
        try:
            logging.getLogger(__name__).warning("_send_disconnect_with_timeout exiting")
            await asyncio.wait_for(self.send_disconnect(), timeout=timeout_seconds)
        except Exception as err:  # pragma: no cover - error path varies by env
            logging.getLogger(__name__).error("Disconnect send timed out-- %s", err)

        logging.getLogger(__name__).warning("_send_disconnect_with_timeout exiting")

    def finalize(self) -> None:
        """Implements `OpAMPClientInterface.finalize` with async-loop fallback."""
        try:
            loop = asyncio.get_running_loop()
            logging.getLogger(__name__).debug("finalize - got loop")
        except RuntimeError:

            def _runner() -> None:
                """Run best-effort async disconnect send inside a dedicated thread."""
                try:
                    logging.getLogger(__name__).debug(
                        "About to send disconnect message"
                    )
                    asyncio.run(self._send_disconnect_with_timeout())
                except Exception as err:
                    logging.getLogger(__name__).error(
                        "Failed to send disconnect message, error is:\n %s", err
                    )
                    return

            thread = threading.Thread(target=_runner, daemon=True)
            thread.start()
        else:
            loop.create_task(self._send_disconnect_with_timeout())

    def __del__(self) -> None:
        """Attempt graceful disconnect/finalize during object destruction."""
        print("FINALIZER triggered")
        self.finalize()

    def _heartbeat_key(self, path: str) -> str:
        """Return the last URL path component as the dictionary key."""
        return path.rstrip("/").split("/")[-1]

    def poll_local_status_with_codes(
        self, port: int
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Poll local health endpoints and collect response bodies and status codes.

        Args:
            port: Local agent HTTP status port to query.

        Returns:
            Tuple of `(results, codes)` maps keyed by heartbeat endpoint name.
        """
        results: dict[str, str] = {}
        codes: dict[str, str] = {}
        for path in self._heartbeat_paths:
            url = f"{self._localhost_base}:{port}{path}"
            key = self._heartbeat_key(path)
            try:
                response = httpx.get(url, timeout=self._http_timeout_seconds)
                results[key] = response.text
                codes[key] = str(response.status_code)
                response.raise_for_status()
                if (response.status_code < 200) or (response.status_code > 299):
                    self.data.reporting_flags[ReportingFlag.REPORT_HEALTH] = True
                    results[key] = f"{path}={response.status_code}"
                    logging.getLogger(__name__).warning(
                        "Err checking status using %s got code %s",
                        path,
                        response.status_code,
                    )
            except Exception as error:  # pragma: no cover - error path varies by env
                results[key] = f"{self._error_prefix}{error}"
                codes[key] = self._error_status
                self.data.reporting_flags[ReportingFlag.REPORT_HEALTH] = True
                logging.getLogger(__name__).warning(
                    "Err checking status using %s got error %s", path, error
                )
        return results, codes

    def add_agent_version(self, port: int) -> None:
        """Fetch Fluent Bit version endpoint and store in client runtime metadata.

        Args:
            port: Local agent HTTP status port used for version endpoint calls.
        """
        url = f"{self._localhost_base}:{port}"
        try:
            response = httpx.get(url, timeout=self._http_timeout_seconds)
            response.raise_for_status()
            value = response.text
            try:
                data = response.json()
                version = None
                edition = None
                if isinstance(data, dict):
                    version = data.get(self._key_agent_version)
                    edition = data.get(self._key_agent_edition)
                    agent_payload = data.get(self._json_key_agent)
                    if (
                        agent_payload is None
                        and self._json_key_agent_fallback is not None
                    ):
                        agent_payload = data.get(self._json_key_agent_fallback)
                    if isinstance(agent_payload, dict):
                        self.data.agent_type_name = self._value_agent_type
                        version = version or agent_payload.get(
                            self._json_key_version
                        )
                        edition = edition or agent_payload.get(
                            self._json_key_edition
                        )
                if version or edition:
                    if version and edition:
                        value = f"{version} ({edition})"
                    else:
                        value = version or edition
                self.data.agent_version = value
            except ValueError as parse_error:
                logging.getLogger(__name__).warning(
                    "failed to parse Agent version response: %s", parse_error
                )
        except Exception as error:  # pragma: no cover - error path varies by env
            logging.getLogger(__name__).warning(
                "failed to parse Agent version response: %s", error
            )

    def check_semaphore(self) -> bool:
        """Return True when the supervisor semaphore file exists on local disk."""
        if os.path.isfile(self._semaphore_filename):
            logging.getLogger(__name__).warning("Spotted Semaphore file")
            return True
        return False

    async def _heartbeat_loop(self, port: int) -> None:
        """Run a periodic polling loop that updates last heartbeat results.

        Args:
            port: Local agent HTTP status port used for heartbeat polling.
        """
        logger = logging.getLogger(__name__)
        interval = max(
            0, int(self.config.heartbeat_frequency) - self._heartbeat_skew_seconds
        )
        logger.debug("Heartbeat cycle start - checking every %s", interval)
        try:
            while self.data.allow_heartbeat:
                await asyncio.sleep(interval)
                if self.check_semaphore():
                    await self._send_disconnect_with_timeout()
                    self.data.allow_heartbeat = False
                try:
                    with self.data.process_lock:
                        results, codes = self.poll_local_status_with_codes(port)
                        self.data.last_heartbeat_results.clear()
                        self.data.last_heartbeat_results.update(results)
                        self.add_agent_version(port)
                        self.data.last_heartbeat_http_codes = codes
                    if self.config.log_agent_api_responses and self.data.logFLB:
                        logger.debug("Heartbeat outcome --> %s", results)

                    logger.info("Heartbeat response codes: %s", codes)

                except KeyboardInterrupt as keyboard_interrupt:
                    logger.error(
                        "Error - a disturbance in the force\n %s", keyboard_interrupt
                    )
                    self.data.allow_heartbeat = False
                    await self._send_disconnect_with_timeout()
                    break
                except Exception as error:  # pylint: disable=broad-exception-caught
                    logger.error(
                        "Something stumbled - we catch and carry on\n %s", error
                    )
                    self.data.last_heartbeat_results = None
                    self.data.last_heartbeat_http_codes = None

                self._handle_server_to_agent(await self.send())
        except BaseException as base_error:  # pylint: disable=broad-exception-caught
            await self._send_disconnect_with_timeout()
            logger.error(
                "heartbeat outer error trap triggered by:\n%s\n %s",
                base_error,
                traceback.format_exc(),
            )
            print("...ouch, bye")
