"""OpAMP client skeleton for HTTP and WebSocket transports."""

from __future__ import annotations

import argparse
import logging
import re
import pathlib
import subprocess
import threading
import time
from typing import Optional

import httpx
import websockets

from opamp_consumer import config as consumer_config
from opamp_consumer.config import CFG_FLUENTBIT_CONFIG_PATH, CONFIG
from opamp_consumer.proto import opamp_pb2
from opamp_consumer.transport import decode_message, encode_message
from shared.opamp_config import (
    OPAMP_HTTP_PATH,
    OPAMP_TRANSPORT_HEADER_NONE,
    UTF8_ENCODING,
)

HTTP_TIMEOUT_SECONDS = 5.0  # Timeout for local HTTP calls.
HEARTBEAT_SKEW_SECONDS = 1  # Sleep interval is heartbeat_frequency minus this value.
LOCALHOST_BASE = "http://localhost"  # Base URL for local Fluent Bit endpoints.
CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Transport header error text.
ERR_PREFIX = "error: "  # Prefix for error values stored in results.
FLUENTBIT_CMD = "fluentbit"  # Fluent Bit executable name.
FLUENTBIT_CONFIG_FLAG = "-c"  # Fluent Bit config flag.
KEY_FLUENTBIT_VERSION = "fluentbit_version"  # Result key for version response.
KEY_AGENT_DESCRIPTION = "agent_description"  # Comment key for agent description.
KEY_INSTANCE_UID = "instance_uid"  # Comment key for instance UID.
KEY_HTTP_PORT = "http_port"  # Fluent Bit HTTP port config key.
KEY_HTTP_LISTEN = "http_listen"  # Fluent Bit HTTP listen config key.
KEY_HTTP_SERVER = "http_server"  # Fluent Bit HTTP server config key.
KEY_HTTP_SERVER_ON = "on"  # Expected value token when HTTP server is enabled.
LOG_INVALID_HTTP_PORT = "invalid http_port value: %s"  # Log format for bad ports.
LOG_HTTP_SERVER_DISABLED = (
    "http_server is not enabled: %s"  # Log format for disabled HTTP.
)
OPAMP_HEADER_NONE = OPAMP_TRANSPORT_HEADER_NONE  # Expected transport header value.

_HEARTBEAT_PATHS = (  # Local endpoints polled per heartbeat.
    "/api/v1/uptime",
    "/api/v1/health",
    "/api/v2/metrics/prometheus",
)


class OpAMPClient:
    """Minimal OpAMP client supporting HTTP and WebSocket transports."""

    def __init__(self, base_url: str) -> None:
        """Create a client bound to a base URL."""
        self.base_url = base_url.rstrip("/")
        self.last_heartbeat_results: dict[str, str] = {}

    async def send_http(self, msg: opamp_pb2.AgentToServer) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message via HTTP and return the response."""
        # TODO(opamp): Populate AgentToServer with per-operation fields before sending:
        # - agent_description, capabilities
        # - health, effective_config, remote_config_status
        # - package_statuses
        # - connection_settings_request / connection_settings_status
        # - custom_capabilities / custom_message / available_components
        url = f"{self.base_url}{OPAMP_HTTP_PATH}"
        payload = msg.SerializeToString()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                content=payload,
                headers={"Content-Type": CONTENT_TYPE_PROTO},
            )
            resp.raise_for_status()
            reply = opamp_pb2.ServerToAgent()
            reply.ParseFromString(resp.content)
            # TODO(opamp): Handle per-operation ServerToAgent fields:
            # - error_response
            # - remote_config, connection_settings, packages_available
            # - capabilities, agent_identification, command
            # - custom_capabilities / custom_message
            return reply

    async def send_ws(self, msg: opamp_pb2.AgentToServer) -> opamp_pb2.ServerToAgent:
        """Send an AgentToServer message via WebSocket and return the response."""
        # TODO(opamp): Populate AgentToServer with per-operation fields before sending:
        # - agent_description, capabilities
        # - health, effective_config, remote_config_status
        # - package_statuses
        # - connection_settings_request / connection_settings_status
        # - custom_capabilities / custom_message / available_components
        url = f"{self.base_url}{OPAMP_HTTP_PATH}"
        async with websockets.connect(url) as ws:
            await ws.send(encode_message(msg.SerializeToString()))
            data = await ws.recv()
        if isinstance(data, str):
            data = data.encode(UTF8_ENCODING)
        header, payload = decode_message(data)
        if header != OPAMP_HEADER_NONE:
            raise ValueError(ERR_UNSUPPORTED_HEADER)
        reply = opamp_pb2.ServerToAgent()
        reply.ParseFromString(payload)
        # TODO(opamp): Handle per-operation ServerToAgent fields:
        # - error_response
        # - remote_config, connection_settings, packages_available
        # - capabilities, agent_identification, command
        # - custom_capabilities / custom_message
        return reply

    def launch_fluent_bit(self) -> "subprocess.Popen[bytes]":
        """Launch the Fluent Bit process using configured params."""
        cmd = [
            FLUENTBIT_CMD,
            *CONFIG.additional_fluent_bit_params,
            FLUENTBIT_CONFIG_FLAG,
            CONFIG.fluentbit_config_path,
        ]
        return subprocess.Popen(cmd)

    def _heartbeat_key(self, path: str) -> str:
        """Return the last URL path component as the dictionary key."""
        return path.rstrip("/").split("/")[-1]

    def poll_local_status(self, port: int) -> dict[str, str]:
        """Poll local health endpoints and return a map of key to response text."""
        results: dict[str, str] = {}
        for path in _HEARTBEAT_PATHS:
            url = f"{LOCALHOST_BASE}:{port}{path}"
            try:
                resp = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS)
                resp.raise_for_status()
                results[self._heartbeat_key(path)] = resp.text
            except Exception as exc:  # pragma: no cover - error path varies by env
                results[self._heartbeat_key(path)] = f"{ERR_PREFIX}{exc}"
        return results

    def add_fluentbit_version(self, port: int) -> None:
        """Fetch Fluent Bit version endpoint and store in last heartbeat results."""
        url = f"{LOCALHOST_BASE}:{port}"
        try:
            resp = httpx.get(url, timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            value = resp.text
        except Exception as exc:  # pragma: no cover - error path varies by env
            value = f"{ERR_PREFIX}{exc}"
        self.last_heartbeat_results[KEY_FLUENTBIT_VERSION] = value

    def _heartbeat_loop(self, port: int) -> None:
        """Run a periodic polling loop that updates last heartbeat results."""
        interval = max(0, int(CONFIG.heartbeat_frequency) - HEARTBEAT_SKEW_SECONDS)
        logger = logging.getLogger(__name__)
        logger.debug(f"Heartbeat cycle start - checking every {interval}")
        while True:
            time.sleep(interval)
            results = self.poll_local_status(port)
            self.last_heartbeat_results.clear()
            self.last_heartbeat_results.update(results)
            logger.debug(f"Heartbeat outcome --> {results}")

    def start_heartbeat_thread(self, port: int) -> "threading.Thread":
        """Start a daemon thread to poll local status endpoints."""
        thread = threading.Thread(
            target=self._heartbeat_loop, args=(port,), daemon=True
        )
        thread.start()
        logging.getLogger(__name__).debug(f"Heatbeat thread launched")

        return thread


def load_fluentbit_config(config: consumer_config.ConsumerConfig) -> ConsumerConfig:
    """Load Fluent Bit config values and agent metadata into the config object."""
    logger = logging.getLogger(__name__)
    logger.warning(f"All config is {config}")
    path = config.fluentbit_config_path
    if not path:
        raise ValueError(f"{CFG_FLUENTBIT_CONFIG_PATH} is not set")

    comment_kv = re.compile(
        r"^\s*#\s*(?P<key>agent_description|instance_uid)\s*[:=]\s*(?P<value>.+?)\s*$",
        re.IGNORECASE,
    )
    config_kv = re.compile(
        r"^\s*(?P<key>http_port|http_listen|http_server|http_server)\s*[:=]\s*(?P<value>\S.*)$",
        re.IGNORECASE,
    )
    section_header = re.compile(r"^\s*\[.*\]\s*$")

    with open(path, "r", encoding=UTF8_ENCODING) as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.__sizeof__() > 0:
                comment_match = comment_kv.match(raw_line)
                if comment_match:
                    key = comment_match.group("key").lower()
                    value = comment_match.group("value")
                    try:
                        config[key] = value
                        logger.info(f"located >{key}< with value >{value}<")
                        continue
                    except KeyError:
                        logger.error(f"barfed with comment match {key} --> {value}")
                        continue

                config_match = config_kv.match(raw_line)
                if config_match:
                    key = config_match.group("key").lower()
                    value = config_match.group("value").strip()
                    try:
                        config[key] = value
                        logger.info(f"located >{key}< with value >{value}<")
                        continue
                    except KeyError:
                        logger.error(f"barfed with config match {key} --> {value}")
                        continue

                logger.debug(f"No matches for >>{line}<<")
    return config


def build_minimal_agent(
    instance_uid: Optional[bytes] = None,
) -> opamp_pb2.AgentToServer:
    """Create a minimal AgentToServer message with configured capabilities."""
    msg = opamp_pb2.AgentToServer()
    if instance_uid is not None:
        msg.instance_uid = instance_uid
    # Capabilities are read from config/opamp.json at startup.
    msg.capabilities = CONFIG.agent_capabilities
    return msg


def main() -> None:
    """Load config, read Fluent Bit settings, launch Fluent Bit, start heartbeat."""
    logger = logging.getLogger(__name__)

    logger.debug("prepping CLI parser")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-path", type=str)
    parser.add_argument("--server-url", type=str)
    parser.add_argument("--server-port", type=int)
    parser.add_argument("--fluentbit-config-path", type=str)
    parser.add_argument("--additional-fluent-bit-params", nargs="*")
    parser.add_argument("--heartbeat-frequency", type=int)
    args = parser.parse_args()

    logger.debug("about to load with CLI overrides")
    config = consumer_config.load_config_with_overrides(
        config_path=pathlib.Path(args.config_path) if args.config_path else None,
        server_url=args.server_url,
        server_port=args.server_port,
        fluentbit_config_path=args.fluentbit_config_path,
        additional_fluent_bit_params=args.additional_fluent_bit_params,
        heartbeat_frequency=args.heartbeat_frequency,
    )

    logger.warning("setting config")
    consumer_config.set_config(config)

    logger.warning("about to process FLB config")
    config = load_fluentbit_config(config)

    if config.http_port is None:
        raise ValueError("http_port not found in Fluent Bit config")

    logger.debug(msg="setting up OpAMP")
    client = OpAMPClient(config.server_url)

    # client.start_heartbeat_thread(config.http_port)
    client._heartbeat_loop(config.http_port)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    main()
