from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock MCP Server")


@app.post("/mcp")
async def handle_mcp(payload: dict[str, Any]):
    request_id = payload.get("id")
    method = payload.get("method")

    if payload.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32600,
                    "message": "Invalid JSON-RPC request",
                },
            },
        )

    if method == "tools/list":
        result = {
            "tools": [
                {
                    "name": "get_status",
                    "description": "Get a sample service status.",
                    "inputSchema": {"type": "object", "properties": {}},
                },
                {
                    "name": "admin_reset_key",
                    "description": "Sample admin-only tool.",
                    "inputSchema": {"type": "object", "properties": {}},
                },
            ]
        }

    elif method == "tools/call":
        params = payload.get("params") or {}
        tool_name = params.get("name")

        if not isinstance(tool_name, str):
            return JSONResponse(
                status_code=200,
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Missing or invalid tool name",
                    },
                },
            )

        result = {
            "content": [
                {
                    "type": "text",
                    "text": f"Mock server executed tool: {tool_name}",
                }
            ],
            "isError": False,
        }

    else:
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": "Method not found",
                },
            },
        )

    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }