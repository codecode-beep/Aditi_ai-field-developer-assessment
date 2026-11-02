# Task 2: MCP Security Gateway

A small HTTP/JSON-RPC proxy between an MCP client and a mock downstream MCP server. The gateway checks Bearer tokens, forwards allowed requests, and blocks viewers from calling tools whose names start with `admin_`.

## Files

- `gateway.py` — checks authorization and forwards allowed requests.
- `mock_server.py` — returns sample JSON-RPC tool-list and tool-call responses.
- `requirements.txt` — Python packages used by both servers.

## Setup

Run these commands from the repository root:

```bash
source .venv/bin/activate
python -m pip install -r task-2-mcp-gateway/requirements.txt
```

## Run the servers

Start each server in a separate Terminal window. In both windows, start from the repository root and activate the virtual environment.

**Terminal 1 — mock downstream server:**

```bash
cd task-2-mcp-gateway
uvicorn mock_server:app --host 127.0.0.1 --port 8001
```

**Terminal 2 — security gateway:**

```bash
cd task-2-mcp-gateway
uvicorn gateway:app --host 127.0.0.1 --port 8000
```

The client sends requests to the gateway at `http://127.0.0.1:8000/mcp`. The gateway forwards permitted requests to the mock server at `http://127.0.0.1:8001/mcp`.

## Demo tokens

| Token | Role |
|---|---|
| `viewer-demo-token` | viewer |
| `admin-demo-token` | admin |

Send a token in the HTTP header:

```text
Authorization: Bearer viewer-demo-token
```

## Try it

A viewer can request the tool list. The gateway forwards this request:

```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer viewer-demo-token" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

A viewer cannot call an admin tool. The gateway returns JSON-RPC error `-32001` without forwarding the call:

```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer viewer-demo-token" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"admin_reset_key","arguments":{}}}'
```

An admin can call the same tool. The gateway forwards it to the mock server:

```bash
curl -sS -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer admin-demo-token" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"admin_reset_key","arguments":{}}}'
```

Stop each server with **Ctrl+C** in its Terminal window.