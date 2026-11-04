import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from rate_limiter import (
    RateLimitExceeded,
    RequestExceedsWindowLimit,
    TokenRateLimiter,
    estimate_request_tokens,
)


PRIMARY_URL = "http://127.0.0.1:8001/primary"
BACKUP_URL = "http://127.0.0.1:8001/backup"
PROVIDER_TIMEOUT_SECONDS = 3.0

rate_limiter = TokenRateLimiter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await rate_limiter.initialize()
    yield


app = FastAPI(
    title="LLM Rate Limit and Fallback Gateway",
    lifespan=lifespan,
)


def gateway_error(
    code: str,
    message: str,
    status_code: int,
    retry_after: int | None = None,
) -> JSONResponse:
    headers = {}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)

    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "type": "gateway_error",
                "code": code,
                "message": message,
            }
        },
    )


def get_tenant_api_key(authorization: str | None) -> str | None:
    if not authorization:
        return None

    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None

    token = token.strip()
    return token or None


async def post_with_timeout(
    client: httpx.AsyncClient,
    url: str,
    payload: dict[str, Any],
) -> httpx.Response:
    # asyncio.wait_for works with Python 3.10.
    return await asyncio.wait_for(
        client.post(url, json=payload),
        timeout=PROVIDER_TIMEOUT_SECONDS,
    )


async def call_backup(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
) -> httpx.Response:
    response = await post_with_timeout(client, BACKUP_URL, payload)
    response.raise_for_status()
    return response


@app.post("/v1/chat/completions")
async def route_completion(request: Request):
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        return gateway_error(
            "invalid_request",
            "Request body must be valid JSON.",
            400,
        )

    if not isinstance(payload, dict):
        return gateway_error(
            "invalid_request",
            "Request body must be a JSON object.",
            400,
        )

    tenant_api_key = get_tenant_api_key(
        request.headers.get("authorization")
    )
    if tenant_api_key is None:
        return gateway_error(
            "missing_api_key",
            "A Bearer tenant API key is required.",
            401,
        )

    try:
        token_budget = estimate_request_tokens(payload)
    except ValueError:
        return gateway_error(
            "invalid_token_budget",
            "max_tokens must be a non-negative integer.",
            400,
        )

    try:
        await rate_limiter.reserve_tokens(tenant_api_key, token_budget)
    except RequestExceedsWindowLimit:
        return gateway_error(
            "request_exceeds_token_limit",
            "This request's token budget exceeds the per-minute limit.",
            413,
        )
    except RateLimitExceeded as exc:
        return gateway_error(
            "tenant_token_limit",
            "Tenant token limit exceeded. Try again later.",
            429,
            retry_after=exc.retry_after,
        )

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            try:
                primary_response = await post_with_timeout(
                    client,
                    PRIMARY_URL,
                    payload,
                )
            except asyncio.TimeoutError:
                # The primary exceeded the 3-second deadline.
                provider_response = await call_backup(client, payload)
                provider_used = "backup"
            else:
                if primary_response.status_code == 429:
                    # The primary is rate-limiting us; try the backup.
                    provider_response = await call_backup(client, payload)
                    provider_used = "backup"
                else:
                    primary_response.raise_for_status()
                    provider_response = primary_response
                    provider_used = "primary"

            result = provider_response.json()

    except asyncio.TimeoutError:
        return gateway_error(
            "provider_timeout",
            "The model providers did not respond in time.",
            504,
        )
    except httpx.HTTPStatusError:
        return gateway_error(
            "provider_failure",
            "The model provider request failed.",
            502,
        )
    except httpx.RequestError:
        return gateway_error(
            "provider_unavailable",
            "The model provider is unavailable.",
            502,
        )
    except ValueError:
        return gateway_error(
            "invalid_provider_response",
            "The model provider returned an invalid response.",
            502,
        )

    if not isinstance(result, dict):
        return gateway_error(
            "invalid_provider_response",
            "The model provider returned an invalid response.",
            502,
        )

    return JSONResponse(
        content=result,
        headers={"X-Model-Provider": provider_used},
    )