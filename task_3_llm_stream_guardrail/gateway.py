import copy
import json

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from redactor import StreamingPIIRedactor

app = FastAPI(title="LLM Streaming Guardrail")

PROVIDER_URL = "http://127.0.0.1:8002/v1/chat/completions"


def encode_event(event: dict) -> str:
    """Format an event as Server-Sent Events (SSE)."""
    return f"data: {json.dumps(event, separators=(',', ':'))}\n\n"


def make_content_event(template: dict, safe_text: str) -> str:
    """Put filtered text into an OpenAI-style streaming event."""
    event = copy.deepcopy(template)
    event["choices"][0]["delta"]["content"] = safe_text
    event["choices"][0]["finish_reason"] = None
    return encode_event(event)


@app.post("/v1/chat/completions")
async def stream_completion(request: Request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "Request body must be valid JSON"}},
        )

    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"error": {"message": "Request body must be a JSON object"}},
        )

    # This gateway always requests a streamed response from the provider.
    payload["stream"] = True

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(connect=5.0, read=None, write=5.0, pool=5.0)
    )

    try:
        provider_request = client.build_request(
            "POST",
            PROVIDER_URL,
            json=payload,
            headers={"accept": "text/event-stream"},
        )
        provider_response = await client.send(provider_request, stream=True)
    except httpx.RequestError:
        await client.aclose()
        return JSONResponse(
            status_code=502,
            content={"error": {"message": "LLM provider is unavailable"}},
        )

    if provider_response.status_code >= 400:
        await provider_response.aclose()
        await client.aclose()
        return JSONResponse(
            status_code=502,
            content={"error": {"message": "LLM provider request failed"}},
        )

    async def filtered_stream():
        redactor = StreamingPIIRedactor()
        last_content_event = None
        data_lines = []
        saw_done = False

        def process_event(data: str) -> list[str]:
            nonlocal last_content_event, saw_done

            if data == "[DONE]":
                output = []
                final_text = redactor.finish()

                if final_text and last_content_event:
                    output.append(
                        make_content_event(last_content_event, final_text)
                    )

                output.append("data: [DONE]\n\n")
                saw_done = True
                return output

            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                # Don't forward an event we can't safely inspect.
                return []

            if not isinstance(event, dict):
                return []

            choices = event.get("choices")
            if not isinstance(choices, list) or not choices:
                return [encode_event(event)]

            choice = choices[0]
            delta = choice.get("delta", {})

            if isinstance(delta, dict) and isinstance(delta.get("content"), str):
                last_content_event = event
                safe_text = redactor.feed(delta["content"])

                if safe_text:
                    return [make_content_event(event, safe_text)]

                # The text is being held briefly so PII split across chunks
                # can be detected before anything is sent to the client.
                return []

            output = []

            # Send the final buffered text before the provider's finish event.
            if choice.get("finish_reason") is not None:
                final_text = redactor.finish()
                if final_text and last_content_event:
                    output.append(
                        make_content_event(last_content_event, final_text)
                    )

            output.append(encode_event(event))
            return output

        try:
            async for line in provider_response.aiter_lines():
                if line == "":
                    if data_lines:
                        data = "\n".join(data_lines)
                        data_lines = []

                        for output_line in process_event(data):
                            yield output_line

                        if saw_done:
                            break

                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())

            # Process a final SSE event if the stream ended without a blank line.
            if data_lines and not saw_done:
                for output_line in process_event("\n".join(data_lines)):
                    yield output_line

            # Flush buffered text if the provider ended without sending [DONE].
            if not saw_done:
                final_text = redactor.finish()
                if final_text and last_content_event:
                    yield make_content_event(last_content_event, final_text)
                yield "data: [DONE]\n\n"

        except httpx.RequestError:
            # Avoid exposing internal provider details to the client.
            error_event = {
                "error": {"message": "LLM provider stream was interrupted"}
            }
            yield encode_event(error_event)
            yield "data: [DONE]\n\n"

        finally:
            await provider_response.aclose()
            await client.aclose()

    return StreamingResponse(
        filtered_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )