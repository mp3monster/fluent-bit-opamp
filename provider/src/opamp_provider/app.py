"""Quart OpAMP server skeleton."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from google.protobuf import text_format
from quart import Quart, Response, jsonify, redirect, request, websocket

from opamp_provider import config as provider_config
from opamp_provider.config import CONFIG
from opamp_provider.proto import opamp_pb2
from opamp_provider.state import STORE, CommandRecord
from opamp_provider.transport import decode_message, encode_message
from shared.opamp_config import OPAMP_HTTP_PATH, OPAMP_TRANSPORT_HEADER_NONE, UTF8_ENCODING

app = Quart(__name__)
logger = logging.getLogger(__name__)

CONTENT_TYPE_PROTO = "application/x-protobuf"  # Content-Type for protobuf payloads.
LOG_HTTP_MSG = "opamp http AgentToServer:\n%s"  # Log format for HTTP messages.
LOG_WS_MSG = "opamp ws AgentToServer:\n%s"  # Log format for WebSocket messages.
ERR_UNSUPPORTED_HEADER = "unsupported transport header"  # Transport header error text.
LOG_REST_COMMAND = "queued command for client %s at %s"
LOG_SEND_COMMAND = "sent command to client %s at %s"
OPAMP_HEADER_NONE = OPAMP_TRANSPORT_HEADER_NONE  # Expected transport header value.

COMMAND_RESTART = "restart"


def _build_response(
    request_msg: opamp_pb2.AgentToServer,
    pending_command: CommandRecord | None,
) -> opamp_pb2.ServerToAgent:
    """Build a minimal ServerToAgent response for a request."""
    response = opamp_pb2.ServerToAgent()
    response.instance_uid = request_msg.instance_uid
    # Capabilities are read from config/opamp.json at startup.
    response.capabilities = CONFIG.server_capabilities
    # TODO(opamp): Implement operations that respond to AgentToServer fields:
    # - remote config offers (AgentRemoteConfig)
    # - connection settings offers (ConnectionSettingsOffers)
    # - packages available (PackagesAvailable)
    # - commands (ServerToAgentCommand)
    # - custom capabilities and custom messages
    # - instance UID reassignment (AgentIdentification)
    if pending_command is not None:
        if pending_command.command.lower() == COMMAND_RESTART:
            response.command.type = opamp_pb2.CommandType.CommandType_Restart
    return response


def _build_error(message: str) -> opamp_pb2.ServerToAgent:
    """Build a ServerToAgent error response."""
    response = opamp_pb2.ServerToAgent()
    response.error_response.type = (
        opamp_pb2.ServerErrorResponseType.ServerErrorResponseType_BadRequest
    )
    response.error_response.error_message = message
    return response


@app.post(OPAMP_HTTP_PATH)
async def opamp_http() -> Response:
    """Handle OpAMP HTTP POST requests."""
    data = await request.get_data()
    agent_msg = opamp_pb2.AgentToServer()
    if data:
        agent_msg.ParseFromString(data)

    logger.info(LOG_HTTP_MSG, text_format.MessageToString(agent_msg))
    client = STORE.upsert_from_agent_msg(agent_msg)
    pending_command = STORE.next_pending_command(client.client_id)

    # TODO(opamp): Implement per-operation processing for HTTP transport:
    # - status/health updates
    # - effective config reporting
    # - remote config status
    # - package statuses
    # - connection settings requests and status
    # - custom messages
    response_msg = _build_response(agent_msg, pending_command)
    payload = response_msg.SerializeToString()
    if pending_command is not None and response_msg.HasField("command"):
        STORE.mark_command_sent(client.client_id, pending_command)
        logger.info(LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc))
    return Response(payload, content_type=CONTENT_TYPE_PROTO)


@app.websocket(OPAMP_HTTP_PATH)
async def opamp_ws() -> None:
    """Handle OpAMP WebSocket connections."""
    while True:
        data = await websocket.receive()
        if isinstance(data, str):
            data = data.encode(UTF8_ENCODING)
        try:
            header, payload = decode_message(data)
            if header != OPAMP_HEADER_NONE:
                response_msg = _build_error(ERR_UNSUPPORTED_HEADER)
            else:
                agent_msg = opamp_pb2.AgentToServer()
                if payload:
                    agent_msg.ParseFromString(payload)
                logger.info(LOG_WS_MSG, text_format.MessageToString(agent_msg))
                client = STORE.upsert_from_agent_msg(agent_msg)
                pending_command = STORE.next_pending_command(client.client_id)
                # TODO(opamp): Implement per-operation processing for WebSocket transport:
                # - status/health updates
                # - effective config reporting
                # - remote config status
                # - package statuses
                # - connection settings requests and status
                # - custom messages
                response_msg = _build_response(agent_msg, pending_command)
        except ValueError as exc:
            response_msg = _build_error(str(exc))

        out_payload = response_msg.SerializeToString()
        await websocket.send(encode_message(out_payload))
        if response_msg.HasField("command"):
            STORE.mark_command_sent(client.client_id, pending_command)
            logger.info(LOG_SEND_COMMAND, client.client_id, datetime.now(timezone.utc))


@app.get("/api/clients")
async def list_clients() -> Response:
    """List all tracked clients."""
    clients = [client.model_dump(mode="json") for client in STORE.list()]
    return jsonify({"clients": clients, "total": len(clients)})


@app.get("/api/clients/<client_id>")
async def get_client(client_id: str) -> Response:
    """Get a single client record."""
    record = STORE.get(client_id)
    if record is None:
        return jsonify({"error": "client not found"}), 404
    return jsonify(record.model_dump(mode="json"))


@app.post("/api/clients/<client_id>/commands")
async def queue_command(client_id: str) -> Response:
    """Queue a command for a client."""
    payload = await request.get_json(silent=True)
    if not payload or "command" not in payload:
        return jsonify({"error": "command is required"}), 400
    command = str(payload["command"]).strip()
    if not command:
        return jsonify({"error": "command is required"}), 400
    cmd = STORE.queue_command(client_id, command)
    logger.info(LOG_REST_COMMAND, client_id, cmd.received_at)
    return jsonify(cmd.model_dump(mode="json")), 201


@app.get("/api/settings/comms")
async def get_comms_settings() -> Response:
    """Get communication threshold settings."""
    return jsonify(
        {
            "delayed_comms_seconds": CONFIG.delayed_comms_seconds,
            "significant_comms_seconds": CONFIG.significant_comms_seconds,
        }
    )


@app.put("/api/settings/comms")
async def update_comms_settings() -> Response:
    """Update communication threshold settings."""
    payload = await request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "payload is required"}), 400
    try:
        delayed = int(payload.get("delayed_comms_seconds", CONFIG.delayed_comms_seconds))
        significant = int(
            payload.get("significant_comms_seconds", CONFIG.significant_comms_seconds)
        )
    except (TypeError, ValueError):
        return jsonify({"error": "thresholds must be integers"}), 400
    if delayed <= 0 or significant <= 0:
        return jsonify({"error": "thresholds must be positive"}), 400
    if delayed >= significant:
        return jsonify({"error": "significant must be greater than delayed"}), 400
    config = provider_config.update_comms_thresholds(
        delayed=delayed,
        significant=significant,
    )
    return jsonify(
        {
            "delayed_comms_seconds": config.delayed_comms_seconds,
            "significant_comms_seconds": config.significant_comms_seconds,
        }
    )


@app.post("/api/clients/<client_id>/config")
async def set_requested_config(client_id: str) -> Response:
    """Set requested configuration for a client."""
    payload = await request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "payload is required"}), 400
    config_text = str(payload.get("config", "")).strip()
    if not config_text:
        return jsonify({"error": "config is required"}), 400
    version = payload.get("version")
    apply_at_raw = payload.get("apply_at")
    apply_at = None
    if apply_at_raw:
        try:
            apply_at = datetime.fromisoformat(str(apply_at_raw))
        except ValueError:
            return jsonify({"error": "apply_at must be ISO 8601"}), 400
    record = STORE.set_requested_config(
        client_id,
        config_text=config_text,
        version=str(version) if version else None,
        apply_at=apply_at,
    )
    return jsonify(record.model_dump(mode="json"))


@app.get("/")
async def root() -> Response:
    return redirect("/ui")


@app.get("/ui")
async def web_ui() -> Response:
    """Serve the provider web UI."""
    html = _WEB_UI_HTML
    return Response(html, content_type="text/html; charset=utf-8")


@app.get("/help")
async def help_page() -> Response:
    """Serve a simple help page."""
    return Response(_HELP_HTML, content_type="text/html; charset=utf-8")


_HELP_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OpAMP Provider Help</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #1b1f24;
      --muted: #4c5563;
      --panel: #ffffff;
      --accent: #425cc7;
      --bg: #f5f7fb;
    }
    body {
      margin: 0;
      font-family: \"Space Grotesk\", \"Trebuchet MS\", sans-serif;
      background: radial-gradient(circle at top left, #e8efff 0%, #f5f7fb 55%, #fff4d8 100%);
      color: var(--ink);
    }
    main {
      max-width: 880px;
      margin: 48px auto;
      padding: 32px;
      background: var(--panel);
      border: 2px solid #d7deee;
      border-radius: 18px;
      box-shadow: 0 20px 60px rgba(36, 58, 120, 0.12);
    }
    h1 { margin: 0 0 12px; font-size: 2rem; }
    p { color: var(--muted); line-height: 1.5; }
    ul { padding-left: 18px; }
    .tag { display: inline-block; padding: 4px 10px; border-radius: 999px; background: #e3e8ff; color: #2f3f8f; font-size: 0.85rem; }
  </style>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600&display=swap" rel="stylesheet">
</head>
<body>
  <main>
    <span class="tag">OpAMP Provider UI</span>
    <h1>Help</h1>
    <p>This console monitors connected agents, highlights late communications, and lets you queue commands or staged configurations.</p>
    <ul>
      <li>Amber rows are past the delayed comms threshold.</li>
      <li>Red rows are past the significant comms threshold.</li>
      <li>Rows with pending config or commands show a colored border.</li>
    </ul>
    <p>Use the main page to open an agent, paste config/commands, and save. Changes are queued until the next agent check-in.</p>
  </main>
  <footer class="footer">
    <div>Licensed under Apache 2.0 • Attribution: mp3monster.org</div>
  </footer>
</body>
</html>
"""


_WEB_UI_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>OpAMP Provider Console</title>
  <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
  <style>
    :root {
      color-scheme: light;
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #1b1f24;
      --muted: #4c5563;
      --accent: #425cc7;
      --accent-2: #f5a800;
      --border: #d7deee;
      --shadow: 0 24px 60px rgba(36, 58, 120, 0.15);
      --amber: #f5a800;
      --red: #e4574e;
      --ok: #2e7d64;
      --pending: #425cc7;
    }

    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Space Grotesk", "Trebuchet MS", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at top left, #e7eeff 0%, #f5f7fb 55%, #fff4d8 100%);
      min-height: 100vh;
    }

    header {
      padding: 28px 36px 16px;
    }

    .title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }

    h1 {
      margin: 0;
      font-size: 2.2rem;
      letter-spacing: -0.02em;
    }

    .meta-bar {
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }

    .pill {
      background: var(--panel);
      border: 1px solid var(--border);
      padding: 10px 14px;
      border-radius: 12px;
      box-shadow: 0 10px 20px rgba(44, 31, 21, 0.06);
      font-size: 0.95rem;
    }

    .pill strong { color: var(--accent); }

    main {
      padding: 0 36px 48px;
    }

    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      margin-bottom: 16px;
    }

    .controls label {
      font-size: 0.9rem;
      color: var(--muted);
    }

    input, select, textarea {
      font-family: "IBM Plex Mono", monospace;
      padding: 8px 10px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: #fff;
    }

    .table {
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border-radius: 18px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }

    th, td {
      text-align: left;
      padding: 14px 18px;
      border-bottom: 1px solid #eee3d8;
      font-size: 0.95rem;
    }

    th {
      background: #eef2ff;
      cursor: pointer;
      position: sticky;
      top: 0;
      z-index: 1;
    }

    tr:hover {
      background: #f2f5ff;
    }

    .status-dot {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-weight: 600;
    }

    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--ok);
    }

    .late-amber .dot { background: var(--amber); }
    .late-red .dot { background: var(--red); }

    .pending-border {
      border-left: 6px solid var(--pending);
    }

    .row-amber { background: rgba(243, 178, 75, 0.12); }
    .row-red { background: rgba(239, 107, 91, 0.18); }

    .pagination {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 16px;
      flex-wrap: wrap;
    }

    .pagination button {
      border: none;
      background: var(--accent);
      color: #fff;
      padding: 8px 14px;
      border-radius: 10px;
      cursor: pointer;
    }

    .pagination span {
      color: var(--muted);
    }

    .modal {
      position: fixed;
      inset: 0;
      background: rgba(23, 19, 17, 0.45);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      z-index: 50;
    }

    .modal.open { display: flex; }

    .modal-card {
      background: var(--panel);
      border: 3px solid var(--border);
      border-radius: 20px;
      padding: 24px;
      width: min(820px, 95vw);
      max-height: 90vh;
      overflow-y: auto;
      box-shadow: var(--shadow);
    }

    .modal-card.late-amber { border-color: var(--amber); }
    .modal-card.late-red { border-color: var(--red); }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .modal-header h2 { margin: 0; }

    .modal-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-top: 16px;
    }

    .field {
      background: #f7f9ff;
      border: 1px solid #e1e7f5;
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 0.9rem;
    }

    .field label {
      font-size: 0.75rem;
      color: var(--muted);
      display: block;
      margin-bottom: 6px;
    }

    textarea {
      width: 100%;
      min-height: 120px;
      resize: vertical;
    }

    .modal-actions {
      margin-top: 18px;
      display: flex;
      gap: 10px;
      justify-content: flex-end;
    }

    .modal-actions button {
      border: none;
      padding: 10px 16px;
      border-radius: 10px;
      cursor: pointer;
      font-weight: 600;
    }

    .save {
      background: var(--accent-2);
      color: #fff;
    }

    .cancel {
      background: #e8ded4;
      color: #4a3c30;
    }

    .fade-in {
      animation: fadeIn 0.5s ease both;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .footer {
      padding: 20px 36px 32px;
      color: var(--muted);
      font-size: 0.85rem;
      text-align: center;
    }
  </style>
</head>
<body>
  <header>
    <div class="title">
      <div>
        <h1>OpAMP Provider Console</h1>
        <div style="color: var(--muted); font-size: 0.95rem;">Client fleet, command queueing, and staged config control.</div>
      </div>
      <button id="helpBtn" class="pill" style="cursor: pointer;">Open Help</button>
    </div>
    <div class="meta-bar">
      <div class="pill">Last Updated: <strong id="lastUpdated">--</strong></div>
      <div class="pill">Agents: <strong id="agentCount">0</strong></div>
      <div class="pill">Late (Amber): <strong id="amberCount">0</strong></div>
      <div class="pill">Late (Red): <strong id="redCount">0</strong></div>
    </div>
  </header>
  <main>
    <div class="controls">
      <label>Refresh (s)
        <input id="refreshInput" type="number" min="5" value="30" />
      </label>
      <label>Page size
        <input id="pageSizeInput" type="number" min="5" value="20" />
      </label>
      <span style="color: var(--muted);">Click headers to sort.</span>
    </div>
    <table class="table fade-in">
      <thead>
        <tr>
          <th data-sort="client_id">Client ID</th>
          <th data-sort="status">Status</th>
          <th data-sort="last_communication">Last Seen</th>
          <th data-sort="current_config_version">Config Version</th>
          <th data-sort="client_version">Client Version</th>
          <th>Pending</th>
        </tr>
      </thead>
      <tbody id="clientBody"></tbody>
    </table>
    <div class="pagination">
      <button id="prevBtn">Prev</button>
      <button id="nextBtn">Next</button>
      <span>Page <span id="pageNum">1</span> of <span id="pageTotal">1</span></span>
      <label>Jump to
        <input id="pageJump" type="number" min="1" value="1" style="width: 70px;" />
      </label>
    </div>
  </main>
  <footer class="footer">
    <div>Licensed under Apache 2.0 • Attribution: mp3monster.org</div>
  </footer>

  <div id="modal" class="modal">
    <div id="modalCard" class="modal-card">
      <div class="modal-header">
        <h2 id="modalTitle">Client</h2>
        <button id="closeModal" class="cancel">Close</button>
      </div>
      <div class="modal-grid" id="modalFields"></div>
      <div style="margin-top: 16px;">
        <label style="font-size: 0.85rem; color: var(--muted);">Requested Configuration</label>
        <textarea id="configInput" placeholder="Paste new configuration here..."></textarea>
      </div>
      <div style="margin-top: 16px;">
        <label style="font-size: 0.85rem; color: var(--muted);">Command</label>
        <input id="commandInput" type="text" placeholder="restart" style="width: 100%;" />
      </div>
      <div class="modal-actions">
        <button id="saveBtn" class="save">Save</button>
        <button id="cancelBtn" class="cancel">Cancel</button>
      </div>
    </div>
  </div>

  <script>
    const state = {
      clients: [],
      sortKey: "client_id",
      sortDir: "asc",
      page: 1,
      pageSize: 20,
      refreshSeconds: 30,
      delayed: 60,
      significant: 300,
      timer: null,
    };

    const clientBody = document.getElementById("clientBody");
    const lastUpdated = document.getElementById("lastUpdated");
    const agentCount = document.getElementById("agentCount");
    const amberCount = document.getElementById("amberCount");
    const redCount = document.getElementById("redCount");
    const pageNum = document.getElementById("pageNum");
    const pageTotal = document.getElementById("pageTotal");
    const pageJump = document.getElementById("pageJump");
    const refreshInput = document.getElementById("refreshInput");
    const pageSizeInput = document.getElementById("pageSizeInput");
    const modal = document.getElementById("modal");
    const modalCard = document.getElementById("modalCard");
    const modalFields = document.getElementById("modalFields");
    const modalTitle = document.getElementById("modalTitle");
    const configInput = document.getElementById("configInput");
    const commandInput = document.getElementById("commandInput");

    let activeClient = null;

    document.querySelectorAll("th[data-sort]").forEach(th => {
      th.addEventListener("click", () => {
        const key = th.dataset.sort;
        if (state.sortKey === key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = key;
          state.sortDir = "asc";
        }
        renderTable();
      });
    });

    document.getElementById("prevBtn").addEventListener("click", () => {
      state.page = Math.max(1, state.page - 1);
      renderTable();
    });
    document.getElementById("nextBtn").addEventListener("click", () => {
      state.page = Math.min(totalPages(), state.page + 1);
      renderTable();
    });
    pageJump.addEventListener("change", () => {
      const val = parseInt(pageJump.value, 10);
      if (!Number.isNaN(val)) {
        state.page = Math.min(Math.max(1, val), totalPages());
        renderTable();
      }
    });

    refreshInput.addEventListener("change", () => {
      const val = parseInt(refreshInput.value, 10);
      if (!Number.isNaN(val) && val >= 5) {
        state.refreshSeconds = val;
        scheduleRefresh();
      }
    });

    pageSizeInput.addEventListener("change", () => {
      const val = parseInt(pageSizeInput.value, 10);
      if (!Number.isNaN(val) && val >= 5) {
        state.pageSize = val;
        state.page = 1;
        renderTable();
      }
    });

    document.getElementById("helpBtn").addEventListener("click", () => {
      window.open("/help", "_blank");
    });

    document.getElementById("closeModal").addEventListener("click", closeModal);
    document.getElementById("cancelBtn").addEventListener("click", closeModal);
    document.getElementById("saveBtn").addEventListener("click", saveChanges);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeModal();
      }
    });

    async function fetchSettings() {
      const resp = await fetch("/api/settings/comms");
      if (!resp.ok) return;
      const data = await resp.json();
      state.delayed = data.delayed_comms_seconds ?? 60;
      state.significant = data.significant_comms_seconds ?? 300;
    }

    async function fetchClients() {
      const resp = await fetch("/api/clients");
      if (!resp.ok) return;
      const data = await resp.json();
      state.clients = data.clients || [];
      lastUpdated.textContent = new Date().toLocaleTimeString();
      agentCount.textContent = state.clients.length;
      renderTable();
    }

    function totalPages() {
      return Math.max(1, Math.ceil(state.clients.length / state.pageSize));
    }

    function computeStatus(client) {
      if (!client.last_communication) {
        return { label: "unknown", cls: "" };
      }
      const last = new Date(client.last_communication);
      const delta = (Date.now() - last.getTime()) / 1000;
      if (delta > state.significant) {
        return { label: "late", cls: "late-red" };
      }
      if (delta > state.delayed) {
        return { label: "delayed", cls: "late-amber" };
      }
      return { label: "ok", cls: "" };
    }

    function hasPending(client) {
      const hasConfig = Boolean(client.requested_config);
      const hasCommand = Array.isArray(client.commands) && client.commands.some(cmd => !cmd.sent_at);
      return hasConfig || hasCommand;
    }

    function renderTable() {
      const sorted = [...state.clients].sort((a, b) => {
        const dir = state.sortDir === "asc" ? 1 : -1;
        const av = a[state.sortKey] ?? "";
        const bv = b[state.sortKey] ?? "";
        return av > bv ? dir : av < bv ? -dir : 0;
      });

      const total = totalPages();
      const pagination = document.querySelector(".pagination");
      if (pagination) {
        pagination.style.display = total > 1 ? "flex" : "none";
      }
      if (state.page > total) state.page = total;
      const start = (state.page - 1) * state.pageSize;
      const pageItems = sorted.slice(start, start + state.pageSize);

      let amber = 0;
      let red = 0;
      clientBody.innerHTML = "";
      pageItems.forEach(client => {
        const status = computeStatus(client);
        if (status.cls === "late-amber") amber += 1;
        if (status.cls === "late-red") red += 1;

        const tr = document.createElement("tr");
        if (status.cls === "late-amber") tr.classList.add("row-amber");
        if (status.cls === "late-red") tr.classList.add("row-red");
        if (hasPending(client)) tr.classList.add("pending-border");
        tr.addEventListener("click", () => openModal(client));

        tr.innerHTML = `
          <td>${client.client_id}</td>
          <td><span class="status-dot ${status.cls}"><span class="dot"></span>${status.label}</span></td>
          <td>${client.last_communication ? new Date(client.last_communication).toLocaleString() : "--"}</td>
          <td>${client.current_config_version ?? "--"}</td>
          <td>${client.client_version ?? "--"}</td>
          <td>${hasPending(client) ? "yes" : "no"}</td>
        `;
        clientBody.appendChild(tr);
      });

      amberCount.textContent = amber;
      redCount.textContent = red;
      pageNum.textContent = state.page;
      pageTotal.textContent = total;
      pageJump.value = state.page;
    }

    function openModal(client) {
      activeClient = client;
      modalTitle.textContent = `Client ${client.client_id}`;
      const status = computeStatus(client);
      modalCard.classList.remove("late-amber", "late-red");
      if (status.cls === "late-amber") modalCard.classList.add("late-amber");
      if (status.cls === "late-red") modalCard.classList.add("late-red");

      modalFields.innerHTML = "";
      const fields = [
        ["Capabilities", (client.capabilities || []).join(", ") || "--"],
        ["Node Age (s)", client.node_age_seconds?.toFixed?.(1) ?? "--"],
        ["Last Communication", client.last_communication ? new Date(client.last_communication).toLocaleString() : "--"],
        ["Current Config", client.current_config_version ?? "--"],
        ["Requested Config", client.requested_config_version ?? "--"],
        ["Client Version", client.client_version ?? "--"],
        ["Next Expected", client.next_expected_communication ? new Date(client.next_expected_communication).toLocaleString() : "--"],
      ];
      fields.forEach(([label, value]) => {
        const div = document.createElement("div");
        div.className = "field";
        div.innerHTML = `<label>${label}</label><div>${value}</div>`;
        modalFields.appendChild(div);
      });

      configInput.value = client.requested_config || "";
      commandInput.value = "";
      modal.classList.add("open");
    }

    function closeModal() {
      modal.classList.remove("open");
      activeClient = null;
      configInput.value = "";
      commandInput.value = "";
    }

    async function saveChanges() {
      if (!activeClient) return;
      const configValue = configInput.value.trim();
      const commandValue = commandInput.value.trim();
      if (!configValue && !commandValue) {
        closeModal();
        return;
      }
      if (configValue) {
        await fetch(`/api/clients/${activeClient.client_id}/config`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: configValue }),
        });
      }
      if (commandValue) {
        await fetch(`/api/clients/${activeClient.client_id}/commands`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command: commandValue }),
        });
      }
      closeModal();
      await fetchClients();
    }

    function scheduleRefresh() {
      if (state.timer) clearInterval(state.timer);
      state.timer = setInterval(fetchClients, state.refreshSeconds * 1000);
    }

    async function init() {
      await fetchSettings();
      await fetchClients();
      scheduleRefresh();
    }

    init();
  </script>
</body>
</html>
"""
