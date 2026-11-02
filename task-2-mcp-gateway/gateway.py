import json

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

app = FastAPI(title="MCP Security Gateway")

DOWNSTREAM_URL = "http://127.0.0.1:8001/mcp"

# Demo tokens for this assessment.
TOKEN_ROLES = {
    "admin-demo-token": "admin",
    "viewer-demo-token": "viewer",
}


def jsonrpc_error(request_id, code: int, message: str, status_code: int = 200):
    return JSONResponse(
        status_code=status_code,
        content={
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        },
    )


def get_role(authorization: str | None) -> str | None:
    if not authorization:
        return None

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None

    return TOKEN_ROLES.get(token.strip())


@app.post("/mcp")
async def proxy_mcp(request: Request):
    body = await request.body()

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonrpc_error(None, -32700, "Parse error")

    if (
        not isinstance(payload, dict)
        or payload.get("jsonrpc") != "2.0"
        or not isinstance(payload.get("method"), str)
        or "id" not in payload
    ):
        request_id = payload.get("id") if isinstance(payload, dict) else None
        return jsonrpc_error(request_id, -32600, "Invalid JSON-RPC request")

    request_id = payload["id"]
    role = get_role(request.headers.get("authorization"))

    if role is None:
        return jsonrpc_error(request_id, -32001, "Unauthorized")

    if payload["method"] == "tools/call":
        params = payload.get("params")

        if not isinstance(params, dict):
            return jsonrpc_error(request_id, -32602, "Invalid tool parameters")

        tool_name = params.get("name")

        if not isinstance(tool_name, str):
            return jsonrpc_error(request_id, -32602, "Missing or invalid tool name")

        if tool_name.startswith("admin_") and role != "admin":
            return jsonrpc_error(request_id, -32001, "Unauthorized Tool Call")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            upstream = await client.post(
                DOWNSTREAM_URL,
                content=body,
                headers={
                    "content-type": request.headers.get(
                        "content-type", "application/json"
                    )
                },
            )

        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers={
                "content-type": upstream.headers.get(
                    "content-type", "application/json"
                )
            },
        )

    except httpx.RequestError:
        return jsonrpc_error(
            request_id,
            -32000,
            "Downstream MCP server unavailable",
            status_code=502,
        )