import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any

import aiosqlite
import tiktoken


DATABASE_PATH = Path(__file__).with_name("rate_limit.db")
TOKEN_LIMIT = 50_000
WINDOW_SECONDS = 60
DEFAULT_MAX_OUTPUT_TOKENS = 1_000

# This tokenizer is for OpenAI-style models.
ENCODING = tiktoken.get_encoding("cl100k_base")


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__("Tenant token limit exceeded")


class RequestExceedsWindowLimit(Exception):
    pass


def estimate_request_tokens(payload: dict[str, Any]) -> int:
    """Estimate prompt tokens and reserve the requested output token budget."""
    max_output_tokens = payload.get("max_completion_tokens")

    if max_output_tokens is None:
        max_output_tokens = payload.get(
            "max_tokens",
            DEFAULT_MAX_OUTPUT_TOKENS,
        )

    if (
        isinstance(max_output_tokens, bool)
        or not isinstance(max_output_tokens, int)
        or max_output_tokens < 0
    ):
        raise ValueError("max_tokens must be a non-negative integer")

    prompt_text = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    prompt_tokens = len(ENCODING.encode(prompt_text, disallowed_special=()))

    # Reserve the maximum possible output tokens up front. This prevents
    # simultaneous requests from exceeding the limit before they finish.
    return max(1, prompt_tokens + max_output_tokens)


class TokenRateLimiter:
    def __init__(
        self,
        database_path: Path = DATABASE_PATH,
        token_limit: int = TOKEN_LIMIT,
        window_seconds: int = WINDOW_SECONDS,
    ):
        self.database_path = database_path
        self.token_limit = token_limit
        self.window_seconds = window_seconds

    async def initialize(self) -> None:
        """Create the database file and table if they don't exist."""
        async with aiosqlite.connect(
            str(self.database_path),
            timeout=5,
        ) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_hash TEXT NOT NULL,
                    tokens INTEGER NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_usage_tenant_created
                ON usage_events (tenant_hash, created_at)
                """
            )
            await db.commit()

    async def reserve_tokens(
        self,
        tenant_api_key: str,
        tokens: int,
    ) -> int:
        """Atomically check the rolling limit and record this request's budget."""
        if tokens > self.token_limit:
            raise RequestExceedsWindowLimit

        tenant_hash = hashlib.sha256(
            tenant_api_key.encode("utf-8")
        ).hexdigest()

        now = time.time()
        window_start = now - self.window_seconds

        async with aiosqlite.connect(
            str(self.database_path),
            timeout=5,
        ) as db:
            await db.execute("PRAGMA busy_timeout=5000")

            # Lock the write transaction before checking usage. This keeps two
            # simultaneous requests from both passing based on the same total.
            await db.execute("BEGIN IMMEDIATE")

            await db.execute(
                "DELETE FROM usage_events WHERE created_at <= ?",
                (window_start,),
            )

            cursor = await db.execute(
                """
                SELECT created_at, tokens
                FROM usage_events
                WHERE tenant_hash = ? AND created_at > ?
                ORDER BY created_at ASC
                """,
                (tenant_hash, window_start),
            )
            events = await cursor.fetchall()
            await cursor.close()

            used_tokens = sum(event_tokens for _, event_tokens in events)

            if used_tokens + tokens > self.token_limit:
                remaining_tokens = used_tokens
                retry_after = self.window_seconds

                # Find when enough of the oldest usage will expire for this
                # request to fit within the limit.
                for created_at, event_tokens in events:
                    remaining_tokens -= event_tokens
                    if remaining_tokens + tokens <= self.token_limit:
                        retry_after = max(
                            1,
                            math.ceil(
                                created_at + self.window_seconds - now
                            ),
                        )
                        break

                await db.rollback()
                raise RateLimitExceeded(retry_after)

            cursor = await db.execute(
                """
                INSERT INTO usage_events (tenant_hash, tokens, created_at)
                VALUES (?, ?, ?)
                """,
                (tenant_hash, tokens, now),
            )
            reservation_id = cursor.lastrowid
            await cursor.close()
            await db.commit()

            return int(reservation_id)
        