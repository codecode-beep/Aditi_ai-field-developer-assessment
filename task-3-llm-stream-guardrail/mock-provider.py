import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

app = FastAPI(title="Mock LLM Provider")


@app.post("/v1/chat/completions")
async def chat_completions():
    async def generate_stream():
        # Sensitive values are deliberately split across stream chunks.
        chunks = [
            "Contact: alexa@exa",
            "mple.com. SSN: 123-",
            "45-6789. Card: 4111 1111 ",
            "1111 1111. This is the end.",
        ]

        for text in chunks:
            event = {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": text},
                        "finish_reason": None,
                    }
                ]
            }

            yield f"data: {json.dumps(event)}\n\n"
            await asyncio.sleep(0.2)

        finish_event = {
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ]
        }
        yield f"data: {json.dumps(finish_event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )