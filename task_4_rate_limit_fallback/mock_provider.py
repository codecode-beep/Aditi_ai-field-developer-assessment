import asyncio
import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Mock Model Providers")

# Supported values: "429", "timeout", or "success"
PRIMARY_BEHAVIOR = os.getenv("PRIMARY_BEHAVIOR", "429").lower()


def completion_response(provider: str, payload: dict[str, Any]) -> dict:
    return {
        "id": f"mock-{provider}-completion",
        "model": f"mock-{provider}-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": f"Response from the {provider} model.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
        },
    }


@app.post("/primary")
async def primary_model(payload: dict[str, Any]):
    if PRIMARY_BEHAVIOR == "429":
        return JSONResponse(
            status_code=429,
            content={"error": "Mock primary provider rate limit reached"},
        )

    if PRIMARY_BEHAVIOR == "timeout":
        # The router's timeout is 3 seconds, so this request should time out.
        await asyncio.sleep(4)

    return completion_response("primary", payload)


@app.post("/backup")
async def backup_model(payload: dict[str, Any]):
    return completion_response("backup", payload)
