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

"""Fluentd-specific OpAMP consumer implementation."""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import re
import sys
import time
import traceback
import tracemalloc
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from opamp_consumer import config as consumer_config
from opamp_consumer.abstract_client import (
    KEY_HEALTH,
    KEY_SERVICE_INSTANCE_ID_COMMENT,
    KEY_SERVICE_TYPE,
    LOCALHOST_BASE,
    AbstractOpAMPClient,
    _config_parameters_payload,
    resolve_service_instance_id_template,
)
from opamp_consumer.client_bootstrap import (
    build_common_cli_parser,
    configure_logging_for_config,
    load_config_from_cli_args,
    maybe_print_config_help,
    run_client,
    validate_runtime_server_config,
)
from opamp_consumer.config import CFG_AGENT_CONFIG_PATH, ConsumerConfig
from opamp_consumer.proto import opamp_pb2
from opamp_consumer.reporting_flag import ReportingFlag

FLUENTD_CMD = "fluentd"  # Executable used to launch Fluentd.
FLUENTD_CONFIG_FLAG = "-c"  # CLI flag for Fluentd config file path.
VALUE_AGENT_TYPE_FLUENTD = "Fluentd"  # Agent type value reported in AgentDescription.
KEY_FLUENTD_PORT = "port"  # Fluentd monitor-agent config key for HTTP port.
KEY_FLUENTD_BIND = "bind"  # Fluentd monitor-agent config key for listen/bind host.
VALUE_MONITOR_AGENT_TYPE = "monitor_agent"  # Fluentd source @type used for monitor endpoint.
VALUE_BIND_ANY_IPV4 = "0.0.0.0"  # Fluentd bind value meaning all interfaces.
VALUE_LOOPBACK_IPV4 = "127.0.0.1"  # Loopback host used when bind is 0.0.0.0.
FLUENTD_CONFIG_API_PATH = "/api/config.json"  # monitor_agent runtime config endpoint.
FLUENTD_PLUGINS_API_PATH = "/api/plugins.json"  # monitor_agent endpoint exposing plugin health.
STARTUP_VERSION_DISCOVERY_DELAY_SECONDS = (
    5  # Delay before first version probe to let Fluentd startup settle.
)
KEY_AGENT_DESCRIPTION = "agent_description"  # Comment key for agent description metadata.
_FLUENTD_SOURCE_START = re.compile(r"^\s*<source>\s*$", re.IGNORECASE)
_FLUENTD_SOURCE_END = re.compile(r"^\s*</source>\s*$", re.IGNORECASE)
_FLUENTD_SOURCE_TYPE = re.compile(r"^\s*@type\s+(?P<value>\S+)\s*$", re.IGNORECASE)
_FLUENTD_SOURCE_KV = re.compile(
    r"^\s*(?P<key>port|bind)\s+(?P<value>\S.*)$",
    re.IGNORECASE,
)
_COMMENT_KV = re.compile(
    rf"^\s*#\s*(?P<key>{KEY_AGENT_DESCRIPTION}|{KEY_SERVICE_INSTANCE_ID_COMMENT})\s*"
    r"[:=]\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_YAML_KEY_VALUE = re.compile(r"^\s*(?P<key>@?type|bind|port)\s*:\s*(?P<value>.+?)\s*$")


def _apply_fluentd_comment(
    config: consumer_config.ConsumerConfig,
    logger: logging.Logger,
    match: re.Match[str],
) -> None:
    """Apply Fluentd comment metadata to consumer config fields.

    Why implementation-specific: `fluentd.conf` comment keys and parsing rules
    differ from the Fluent Bit bootstrap parser.
    """
    key = match.group("key").lower()
    value = match.group("value").strip()
    if key == KEY_SERVICE_INSTANCE_ID_COMMENT:
        value = resolve_service_instance_id_template(value)
    config[key] = value
    logger.info("located fluentd comment >%s< with value >%s<", key, value)


def _find_monitor_agent_source_bind_and_port(
    lines: list[str],
) -> tuple[str | None, int | None]:
    """Return monitor_agent source bind/port values parsed from Fluentd config text.

    Args:
        lines: Raw lines from a Fluentd configuration file.

    Returns:
        Tuple `(bind, port)` for the first `<source>` block with
        `@type monitor_agent`. If no matching block exists, returns `(None, None)`.

    Why implementation-specific: this reads `<source>` blocks and `@type
    monitor_agent`, which are Fluentd-specific config constructs.
    """
    logger = logging.getLogger(__name__)
    in_source = False
    monitor_agent_source = False
    bind: str | None = None
    port: int | None = None

    for raw_line in lines:
        if _FLUENTD_SOURCE_START.match(raw_line):
            in_source = True
            monitor_agent_source = False
            bind = None
            port = None
            continue

        if not in_source:
            continue

        if _FLUENTD_SOURCE_END.match(raw_line):
            if monitor_agent_source:
                return bind, port
            in_source = False
            continue

        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue

        source_type_match = _FLUENTD_SOURCE_TYPE.match(raw_line)
        if source_type_match is not None:
            monitor_agent_source = (
                source_type_match.group("value").strip().lower()
                == VALUE_MONITOR_AGENT_TYPE
            )
            continue

        if not monitor_agent_source:
            continue

        source_kv_match = _FLUENTD_SOURCE_KV.match(raw_line)
        if source_kv_match is None:
            continue

        key = source_kv_match.group("key").lower()
        value = source_kv_match.group("value").strip()
        if key == KEY_FLUENTD_BIND:
            bind = value
        elif key == KEY_FLUENTD_PORT:
            try:
                port = int(value)
            except ValueError:
                logger.warning(
                    "invalid monitor_agent port value in Fluentd config: %s",
                    value,
                )

    if in_source and monitor_agent_source:
        return bind, port
    return None, None


def _iter_nested_mappings(payload: Any) -> list[dict[str, Any]]:
    """Collect mapping nodes from nested YAML payload structures.

    Why implementation-specific: Fluentd YAML monitor_agent entries can be
    nested in lists/maps and need recursive mapping traversal.
    """
    mappings: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        mappings.append(payload)
        for child_value in payload.values():
            mappings.extend(_iter_nested_mappings(child_value))
    elif isinstance(payload, list):
        for child_value in payload:
            mappings.extend(_iter_nested_mappings(child_value))
    return mappings


def _extract_monitor_agent_values_from_mapping(
    mapping: dict[str, Any],
) -> tuple[str | None, int | None]:
    """Extract monitor_agent bind/port from one YAML mapping.

    Why implementation-specific: this matches Fluentd `@type/type:
    monitor_agent` mappings instead of Fluent Bit HTTP server keys.
    """
    source_type = mapping.get("@type")
    if source_type is None:
        source_type = mapping.get("type")
    if str(source_type or "").strip().lower() != VALUE_MONITOR_AGENT_TYPE:
        return None, None

    bind_value = mapping.get(KEY_FLUENTD_BIND)
    raw_port_value = mapping.get(KEY_FLUENTD_PORT)
    bind = str(bind_value).strip() if bind_value is not None else None

    if raw_port_value is None:
        return bind, None
    try:
        return bind, int(raw_port_value)
    except (TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "invalid monitor_agent port value in Fluentd YAML config: %s",
            raw_port_value,
        )
        return bind, None


def _find_monitor_agent_source_bind_and_port_yaml_fallback(
    lines: list[str],
) -> tuple[str | None, int | None]:
    """Parse monitor_agent bind/port from YAML lines without external deps.

    Why implementation-specific: this is a Fluentd monitor_agent fallback when
    PyYAML is unavailable.
    """
    logger = logging.getLogger(__name__)
    in_monitor_agent_mapping = False
    monitor_agent_indent = -1
    bind: str | None = None
    port: int | None = None

    for raw_line in lines:
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue

        line_indent = len(raw_line) - len(raw_line.lstrip(" "))
        key_value_match = _YAML_KEY_VALUE.match(raw_line)
        if key_value_match is None:
            if in_monitor_agent_mapping and line_indent <= monitor_agent_indent:
                if bind is not None or port is not None:
                    return bind, port
                in_monitor_agent_mapping = False
            continue

        key = key_value_match.group("key").strip().lower()
        value = key_value_match.group("value").strip().strip("'\"")

        if key in {"@type", "type"}:
            if in_monitor_agent_mapping and (bind is not None or port is not None):
                return bind, port
            in_monitor_agent_mapping = value.lower() == VALUE_MONITOR_AGENT_TYPE
            monitor_agent_indent = line_indent
            bind = None
            port = None
            continue

        if not in_monitor_agent_mapping:
            continue
        if line_indent <= monitor_agent_indent:
            in_monitor_agent_mapping = False
            continue

        if key == KEY_FLUENTD_BIND:
            bind = value
        elif key == KEY_FLUENTD_PORT:
            try:
                port = int(value)
            except ValueError:
                logger.warning(
                    "invalid monitor_agent port value in Fluentd YAML config: %s",
                    value,
                )
    if in_monitor_agent_mapping and (bind is not None or port is not None):
        return bind, port
    return None, None


def _find_monitor_agent_source_bind_and_port_yaml(
    lines: list[str],
) -> tuple[str | None, int | None]:
    """Parse monitor_agent bind/port from YAML-formatted Fluentd config.

    Why implementation-specific: monitor_agent source entries determine Fluentd
    status endpoint host/port.
    """
    logger = logging.getLogger(__name__)
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        logger.debug(
            "PyYAML not available; using fallback parser for Fluentd YAML config"
        )
        return _find_monitor_agent_source_bind_and_port_yaml_fallback(lines)

    try:
        parsed_payload = yaml.safe_load("".join(lines))
    except Exception as parse_error:  # pragma: no cover - parser exception variants
        logger.warning(
            "failed to parse Fluentd YAML config via PyYAML: %s",
            parse_error,
        )
        return _find_monitor_agent_source_bind_and_port_yaml_fallback(lines)

    for mapping in _iter_nested_mappings(parsed_payload):
        bind, port = _extract_monitor_agent_values_from_mapping(mapping)
        if bind is not None or port is not None:
            return bind, port

    return None, None


def _bind_host_for_server_url(bind: str | None) -> str | None:
    """Normalize Fluentd bind values for server URL host overrides.

    Why implementation-specific: Fluentd monitor_agent `0.0.0.0` must be
    rewritten to loopback for local status polling.
    """
    if bind is None:
        return None
    normalized = str(bind).strip()
    if not normalized:
        return None
    if normalized == VALUE_BIND_ANY_IPV4:
        return VALUE_LOOPBACK_IPV4
    return normalized


def _override_server_url_hostname_with_bind(
    server_url: str | None, bind: str | None
) -> str | None:
    """Return server_url with host overridden by Fluentd monitor_agent bind.

    Why implementation-specific: monitor_agent bind semantics determine the
    runtime status endpoint location for Fluentd.
    """
    if not server_url:
        return server_url
    resolved_bind_host = _bind_host_for_server_url(bind)
    if not resolved_bind_host:
        return server_url

    split_url = urlsplit(server_url)
    if not split_url.netloc:
        return server_url

    auth_prefix = ""
    if "@" in split_url.netloc:
        auth_prefix = f"{split_url.netloc.rsplit('@', 1)[0]}@"

    host_token = resolved_bind_host
    if ":" in host_token and not host_token.startswith("["):
        host_token = f"[{host_token}]"
    if split_url.port is not None:
        host_token = f"{host_token}:{split_url.port}"

    overridden_url = urlunsplit(
        (
            split_url.scheme,
            f"{auth_prefix}{host_token}",
            split_url.path,
            split_url.query,
            split_url.fragment,
        )
    )
    return overridden_url


def find_monitor_agent_source_bind_and_port(
    config_path: str | pathlib.Path,
) -> tuple[str | None, int | None]:
    """Inspect Fluentd config file and return monitor_agent bind/port settings.

    Args:
        config_path: Path to `fluentd.conf` (or equivalent) to parse.

    Returns:
        Tuple `(bind, port)` extracted from the first `<source>` block whose
        `@type` is `monitor_agent`. Returns `(None, None)` when no matching
        source block is found.

    Why implementation-specific: this inspects Fluentd monitor_agent
    declarations in `.conf` or YAML configuration files.
    """
    path = pathlib.Path(config_path)
    with open(path, encoding=consumer_config.UTF8_ENCODING) as handle:
        lines = handle.readlines()
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return _find_monitor_agent_source_bind_and_port_yaml(lines)
    return _find_monitor_agent_source_bind_and_port(lines)


def load_fluentd_config(config: consumer_config.ConsumerConfig) -> ConsumerConfig:
    """Load Fluentd monitor_agent-derived settings and metadata into config.

    Why implementation-specific: this translates monitor_agent bind/port into
    OpAMP host/port fields; Fluent Bit uses a different config model.
    """
    logger = logging.getLogger(__name__)
    path = config.agent_config_path
    if not path:
        raise ValueError(f"{CFG_AGENT_CONFIG_PATH} is not set")

    with open(path, encoding=consumer_config.UTF8_ENCODING) as handle:
        lines = handle.readlines()

    for raw_line in lines:
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue

        comment_match = _COMMENT_KV.match(raw_line)
        if comment_match is not None:
            _apply_fluentd_comment(config, logger, comment_match)

    bind, port = find_monitor_agent_source_bind_and_port(path)
    if bind is not None:
        config.agent_http_listen = bind
        config.server_url = _override_server_url_hostname_with_bind(
            config.server_url,
            bind,
        )
        logger.info(
            "located fluentd monitor_agent setting >%s< with value >%s<",
            KEY_FLUENTD_BIND,
            bind,
        )
    if port is not None:
        if (
            config.client_status_port is not None
            and int(config.client_status_port) != int(port)
        ):
            logger.info(
                "overriding configured client_status_port=%s with monitor_agent port=%s",
                config.client_status_port,
                port,
            )
        config.client_status_port = port
        config.agent_http_port = port
        config.agent_http_server = "on"
        logger.info(
            "located fluentd monitor_agent setting >%s< with value >%s<",
            KEY_FLUENTD_PORT,
            port,
        )

    return config


class FluentdOpAMPClient(AbstractOpAMPClient):
    """Concrete OpAMP client implementation for Fluentd-based agents.

    Why implementation-specific: Fluentd requires monitor_agent-specific
    version and health handling, so several runtime hooks are overridden.
    """

    _runtime_agent_command = FLUENTD_CMD
    _runtime_config_flag = FLUENTD_CONFIG_FLAG
    _heartbeat_paths = (FLUENTD_PLUGINS_API_PATH,)

    def __init__(self, base_url: str, config: ConsumerConfig | None = None) -> None:
        """Initialize Fluentd-specific runtime state and metadata defaults."""
        super().__init__(base_url, config)
        self.data.agent_type_name = VALUE_AGENT_TYPE_FLUENTD
        self._startup_version_delay_applied = False

    def get_custom_handler_folder(self) -> pathlib.Path:
        """Return the default handler folder used by the Fluentd client."""
        return pathlib.Path(__file__).resolve().parent / "custom_handlers"

    def _monitor_agent_host(self) -> str:
        """Return monitor_agent host used by Fluentd status/version requests.

        Why implementation-specific: Fluentd status/version calls use
        monitor_agent bind semantics, not Fluent Bit defaults.
        """
        configured_bind = _bind_host_for_server_url(self.config.agent_http_listen)
        return configured_bind or VALUE_LOOPBACK_IPV4

    def _monitor_agent_config_url(self, port: int) -> str:
        """Build Fluentd monitor_agent config endpoint URL for version discovery.

        Why implementation-specific: Fluentd version is discovered from
        monitor_agent `/api/config.json`.
        """
        host = self._monitor_agent_host()
        host_token = host
        if ":" in host and not host.startswith("["):
            host_token = f"[{host}]"
        return f"http://{host_token}:{int(port)}{FLUENTD_CONFIG_API_PATH}"

    def _monitor_agent_plugins_url(self, port: int) -> str:
        """Build Fluentd monitor_agent plugins endpoint URL for health polling.

        Why implementation-specific: Fluentd heartbeat health comes from
        monitor_agent `/api/plugins.json`.
        """
        host = self._monitor_agent_host()
        host_token = host
        if ":" in host and not host.startswith("["):
            host_token = f"[{host}]"
        return f"http://{host_token}:{int(port)}{FLUENTD_PLUGINS_API_PATH}"

    def add_agent_version(self, port: int) -> None:
        """Load version from Fluentd monitor_agent `/api/config.json`.

        Why implementation-specific: Fluentd exposes version via JSON at
        `api/config.json`, unlike Fluent Bit's root HTTP status payload.
        """
        logger = logging.getLogger(__name__)
        if not self._startup_version_delay_applied:
            time.sleep(STARTUP_VERSION_DISCOVERY_DELAY_SECONDS)
            self._startup_version_delay_applied = True
        config_url = self._monitor_agent_config_url(port)
        try:
            response = httpx.get(config_url, timeout=5.0)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                logger.warning("monitor_agent response not a JSON object: %s", payload)
                return
            version_value = payload.get("version")
            if version_value is None:
                logger.warning(
                    "monitor_agent response missing version attribute at %s",
                    config_url,
                )
                return
            version_text = str(version_value).strip()
            if not version_text:
                logger.warning(
                    "add_agent_version - no version_text"                )
                return
            self.data.agent_version = version_text
            self.data.agent_type_name = VALUE_AGENT_TYPE_FLUENTD
        except Exception as err:  # pragma: no cover - error path varies by env
            logger.warning("failed to read Fluentd version from monitor_agent: %s", err)

    def _health_from_metrics(
        self, msg: opamp_pb2.AgentToServer, text: str
    ) -> opamp_pb2.AgentToServer:
        """Parse Fluentd monitor_agent plugins JSON into OpAMP component health.

        Why implementation-specific: plugin health uses JSON fields such as
        `status` and `retry_count` instead of Fluent Bit metrics text.
        """
        logger = logging.getLogger(__name__)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as json_err:
            logger.warning("failed to parse monitor_agent plugins JSON payload - %s", json_err)
            return msg
        if not isinstance(payload, dict):
            return msg
        plugins = payload.get("plugins")
        if not isinstance(plugins, list):
            return msg

        for index, plugin in enumerate(plugins):
            if not isinstance(plugin, dict):
                continue
            component_name = str(
                plugin.get("plugin_id")
                or plugin.get("id")
                or plugin.get("type")
                or f"plugin_{index}"
            )
            raw_status = str(plugin.get("status") or "unknown")
            status = raw_status.strip().lower()
            retry_count_raw = plugin.get("retry_count", 0)
            try:
                retry_count = int(retry_count_raw)
            except (TypeError, ValueError):
                retry_count = 0

            status_healthy = status in {"running", "active", "ok"}
            retry_healthy = retry_count == 0
            component_healthy = status_healthy and retry_healthy
            component_status = f"status={raw_status}, retry_count={retry_count}"
            msg.health.component_health_map[component_name].CopyFrom(
                opamp_pb2.ComponentHealth(
                    healthy=component_healthy,
                    status=component_status,
                )
            )
        return msg

    def poll_local_status_with_codes(
        self, port: int
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Poll Fluentd monitor_agent plugins endpoint and return heartbeat maps.

        Why implementation-specific: Fluentd heartbeat health comes from
        `/api/plugins.json`, not multi-endpoint Fluent Bit status checks.
        """
        key = KEY_HEALTH
        url = self._monitor_agent_plugins_url(port)
        results: dict[str, str] = {}
        codes: dict[str, str] = {}
        try:
            response = httpx.get(url, timeout=self._http_timeout_seconds)
            results[key] = response.text
            codes[key] = str(response.status_code)
            response.raise_for_status()
            if (response.status_code < 200) or (response.status_code > 299):
                self.data.reporting_flags[ReportingFlag.REPORT_HEALTH] = True
                results[key] = f"{FLUENTD_PLUGINS_API_PATH}={response.status_code}"
                logging.getLogger(__name__).warning(
                    "Err checking status using %s got code %s",
                    FLUENTD_PLUGINS_API_PATH,
                    response.status_code,
                )
        except Exception as error:  # pragma: no cover - error path varies by env
            results[key] = f"{self._error_prefix}{error}"
            codes[key] = self._error_status
            self.data.reporting_flags[ReportingFlag.REPORT_HEALTH] = True
            logging.getLogger(__name__).warning(
                "Err checking status using %s got error %s",
                FLUENTD_PLUGINS_API_PATH,
                error,
            )
        return results, codes

    def get_agent_description(
        self, instance_uid: bytes | str | None = None
    ) -> opamp_pb2.AgentDescription:
        """Build description and force `service.type` to `Fluentd`.

        Why implementation-specific: this keeps identity consistent when
        config/comments omit or override `service.type`.
        """
        self.data.agent_type_name = VALUE_AGENT_TYPE_FLUENTD
        description = super().get_agent_description(instance_uid)
        for attribute in description.identifying_attributes:
            if attribute.key == KEY_SERVICE_TYPE:
                attribute.value.string_value = VALUE_AGENT_TYPE_FLUENTD
                break
        return description


def main() -> None:
    """Run Fluentd bootstrap with monitor_agent-aware config processing.

    Why implementation-specific: config parsing must derive monitor_agent
    bind/port before runtime validation and heartbeat polling.
    """
    try:
        tracemalloc.start()
        parser = build_common_cli_parser()
        args = parser.parse_args()
        config = load_config_from_cli_args(args)
        logger = configure_logging_for_config(config)

        if maybe_print_config_help(
            args=args,
            config=config,
            config_parameters_payload_builder=_config_parameters_payload,
        ):
            return

        config = load_fluentd_config(config)
        config = validate_runtime_server_config(
            config=config,
            localhost_base=LOCALHOST_BASE,
            missing_status_port_error="client_status_port not found in Fluentd config",
        )

        logger.debug("setting up OpAMP Fluentd client")
        client = FluentdOpAMPClient(config.server_url, config)
        client.launch_agent_process()
        client.add_agent_version(config.client_status_port)
        logger.info("introducing fluentd client to server")
        asyncio.run(run_client(client))
        asyncio.run(client._heartbeat_loop(config.client_status_port))
        client.terminate_agent_process()
    except KeyboardInterrupt as keyboard_interrupt:
        print("... bzzzz keyboard\n %s", keyboard_interrupt)
    except SystemExit as system_exit:
        print("... bzzzz brutal exit\n %s", system_exit)
    except Exception as err:
        print("... Fluentd bzzzzzzzzzzz \n %s \n %s", err, traceback.format_exc())

if __name__ == "__main__":
    main()
    print("... Bye")
    sys.exit(1)
