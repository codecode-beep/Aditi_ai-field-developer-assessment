import asyncio
import json
import logging
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import McpError
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ErrorData,
    ServerResult,
    TextContent,
    Tool,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError


# Keep application logs off stdout; stdout carries MCP protocol messages.
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

CUSTOMER_ID_PATTERN = r"^CUST-[A-Z0-9]{5}$"


class CustomerRecordArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)


class RefundArgs(CustomerRecordArgs):
    amount: float = Field(gt=0, allow_inf_nan=False, strict=True)
    reason: str = Field(min_length=10)


server = Server("customer-tools")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_customer_record",
            description="Look up a customer record by customer ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "pattern": CUSTOMER_ID_PATTERN,
                        "description": "CUST- followed by exactly five uppercase letters or digits.",
                    }
                },
                "required": ["customer_id"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="trigger_refund",
            description="Record a mock refund request. No real refund is issued.",
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "pattern": CUSTOMER_ID_PATTERN,
                        "description": "CUST- followed by exactly five uppercase letters or digits.",
                    },
                    "amount": {
                        "type": "number",
                        "exclusiveMinimum": 0,
                        "description": "A finite number greater than zero.",
                    },
                    "reason": {
                        "type": "string",
                        "minLength": 10,
                        "description": "At least 10 characters.",
                    },
                },
                "required": ["customer_id", "amount", "reason"],
                "additionalProperties": False,
            },
        ),
    ]


async def handle_call_tool(request: CallToolRequest) -> ServerResult:
    name = request.params.name
    arguments: dict[str, Any] = request.params.arguments or {}

    try:
        if name == "get_customer_record":
            args = CustomerRecordArgs.model_validate(arguments)
            result = {
                "customer_id": args.customer_id,
                "name": "Sample Customer",
                "status": "active",
            }

        elif name == "trigger_refund":
            args = RefundArgs.model_validate(arguments)
            result = {
                "status": "refund_requested",
                "customer_id": args.customer_id,
                "amount": args.amount,
                "reason": args.reason,
            }

        else:
            raise McpError(
                ErrorData(code=-32602, message=f"Unknown tool: {name}")
            )

    except ValidationError as exc:
        # This handler is registered at the request layer, so this becomes
        # a JSON-RPC error response with code -32602.
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise McpError(
            ErrorData(
                code=-32602,
                message=f"Invalid parameters for tool '{name}': {details}",
            )
        ) from exc

    return ServerResult(
        CallToolResult(
            content=[TextContent(type="text", text=json.dumps(result))],
            isError=False,
        )
    )


# Replace the SDK's normal tool-call wrapper with this request-level handler.
server.request_handlers[CallToolRequest] = handle_call_tool


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())