# MCP Client Setup Scripts

This folder contains MCP setup scripts for Claude Desktop, ChatGPT/Codex CLI, and VS Code.

For the full repository script catalog (all non-MCP scripts included), see
[`../docs/scripts.md`](../docs/scripts.md).

## Script roles

- `configure-claude-desktop-fastmcp.sh` / `configure-claude-desktop-fastmcp.ps1`
  Wrapper focused on Claude Desktop defaults.
- `configure-codex-fastmcp.sh` / `configure-codex-fastmcp.ps1`
  Wrapper focused on ChatGPT/Codex defaults.
- `configure-mcp-clients-fastmcp.sh` / `configure-mcp-clients-fastmcp.ps1`
  Canonical script that supports all targets and options.

Wrappers forward arguments to the canonical script and only change defaults and naming compatibility.

## How the scripts work

The canonical script configures one or more targets from `claude`, `chatgpt`, and `vscode`.

- Claude Desktop:
  writes `mcpServers` entry in Claude config using remote transport:
  `mcp-remote <http://host:port/sse>` or fallback `npx -y mcp-remote <http://host:port/sse>`.
- ChatGPT/Codex:
  creates a stdio MCP entry via `codex mcp add ... uv run ... fastmcp run ...`.
- VS Code:
  generates/merges `.vscode/mcp.json` `servers` entry using FastMCP JSON output.
- Legacy cleanup:
  known old names (`OpAMP Server`, `opamp-server`, `opampServer`) are removed except for the active configured name.
- Validation:
  options requiring values fail fast when missing (for example `--opamp-server-ip` without a value).

## FastMCP role

FastMCP is used for local stdio-style MCP process wiring:

- Required for ChatGPT/Codex registration path (`fastmcp run ...`).
- Required for VS Code JSON generation path (`fastmcp install mcp-json ...`).
- Not required for Claude Desktop remote setup, because Claude uses `mcp-remote` to connect to the provider SSE endpoint.

In short:

- Claude path: remote transport (`mcp-remote`).
- ChatGPT/Codex and VS Code paths: local stdio tooling (`fastmcp` + `uv`).

## Required server parameters

Always pass server host (and usually port) so scripts do not prompt:

- Bash: `--opamp-server-ip <host-or-ip>` and optional `--opamp-server-port <port>`
- PowerShell: `-OpAMPServerIp <host-or-ip>` and optional `-OpAMPServerPort <port>`

These values set:

- `OPAMP_SERVER_IP`
- `OPAMP_SERVER_URL` (`http://<host-or-ip>:<port>`, default `8080`)
- `OPAMP_MCP_SSE_URL` (`http://<host-or-ip>:<port>/sse`, default `8080`)

## Parameters

`configure-claude-desktop-fastmcp` wrapper:

- `--name` / `-Name`: Claude display/server name (default `OpAMP Server`)
- `--clients` / `-Clients`: optional override target list (default `claude`)
- `--opamp-server-ip` / `-OpAMPServerIp`: OpAMP server host/IP
- `--opamp-server-port` / `-OpAMPServerPort`: OpAMP server port (default `8080`)
- `--server-spec` / `-ServerSpec`: forwarded for compatibility (not used by Claude remote transport setup)
- `--project` / `-Project`: forwarded for compatibility
- `--no-editable` / `-NoEditable`: forwarded for compatibility
- `--help` / `-Help`: show usage

`configure-codex-fastmcp` wrapper:

- `--name` / `--server-name` / `-ServerName`: ChatGPT/Codex server name (default `opamp-server`)
- `--clients` / `-Clients`: optional override target list (default `chatgpt`)
- `--opamp-server-ip` / `-OpAMPServerIp`: OpAMP server host/IP
- `--opamp-server-port` / `-OpAMPServerPort`: OpAMP server port (default `8080`)
- `--server-spec` / `-ServerSpec`: Python server spec passed to `fastmcp run`
- `--project` / `-Project`: project path used by `uv run --project`
- `--no-editable` / `-NoEditable`: skip `--with-editable`
- `--help` / `-Help`: show usage

`configure-mcp-clients-fastmcp` canonical script:

- `--clients` / `-Clients`: comma-separated targets (`claude`, `chatgpt`, `vscode`)
- `--claude-name` / `-ClaudeName`: Claude entry name (default `OpAMP Server`)
- `--chatgpt-name` / `--server-name` / `-ChatGPTName`: Codex entry name (default `opamp-server`)
- `--vscode-name` / `-VSCodeName`: VS Code server key (default `opampServer`)
- `--vscode-config` / `-VSCodeConfigPath`: VS Code MCP config path (default `.vscode/mcp.json`)
- `--claude-config` (bash only): Claude config path override
- `--server-spec` / `-ServerSpec`: Python server spec passed to `fastmcp run`
- `--project` / `-Project`: project path used by `uv run --project`
- `--opamp-server-ip` / `-OpAMPServerIp`: OpAMP server host/IP
- `--opamp-server-port` / `-OpAMPServerPort`: OpAMP server port (default `8080`)
- `--no-editable` / `-NoEditable`: skip `--with-editable`
- `-h` / `--help` / `-Help`: show usage

## Usage examples

PowerShell:

```powershell
& ".\mcp\configure-claude-desktop-fastmcp.ps1" -OpAMPServerIp localhost -OpAMPServerPort 8080
& ".\mcp\configure-codex-fastmcp.ps1" -OpAMPServerIp localhost -OpAMPServerPort 8080
& ".\mcp\configure-mcp-clients-fastmcp.ps1" -Clients "claude,chatgpt" -OpAMPServerIp localhost -OpAMPServerPort 8080
```

Bash:

```bash
./mcp/configure-claude-desktop-fastmcp.sh --opamp-server-ip localhost --opamp-server-port 8080
./mcp/configure-codex-fastmcp.sh --opamp-server-ip localhost --opamp-server-port 8080
./mcp/configure-mcp-clients-fastmcp.sh --clients claude,chatgpt --opamp-server-ip localhost --opamp-server-port 8080
```

## Verify client config after running scripts

Claude Desktop (Windows):

```powershell
Get-Content "$env:APPDATA\Claude\claude_desktop_config.json"
```

Claude Desktop (Linux/macOS):

```bash
cat "${XDG_CONFIG_HOME:-$HOME/.config}/Claude/claude_desktop_config.json"
```

Confirm `mcpServers` contains your configured server (default wrapper name: `OpAMP Server`) and that the command is `mcp-remote` (or `npx` with `mcp-remote` args).

ChatGPT/Codex CLI:

```bash
codex mcp list
codex mcp get opamp-server
```

VS Code (only when using the canonical multi-client script with `vscode` target):

```bash
cat .vscode/mcp.json
```

## Related docs

- Script catalog: [`../docs/scripts.md`](../docs/scripts.md)
- Auth and MCP bearer-token behavior: [`../docs/authentication.md`](../docs/authentication.md)
- Endpoint definitions (`/sse`, `/messages`, `/mcp`): [`../docs/endpoints.md`](../docs/endpoints.md)
