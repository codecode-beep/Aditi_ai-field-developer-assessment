# Task 4: Rate Limiting and Model Fallback

It is a small LLM gateway demo. It tracks token reservations for each tenant in an on-disk SQLite database. If the primary mock provider returns HTTP 429 or takes longer than 3 seconds, the gateway sends the request to a backup provider.

## Requirements

From the repository root, activate your virtual environment and install the dependencies:

```bash
source .venv/bin/activate
pip install -r task_4_rate_limit_fallback/requirements.txt
```

## Run the demo

Open two Terminal tabs. In both, go to the repository root and activate the virtual environment.

**Terminal 1 — start the mock providers:**

```bash
cd task_4_rate_limit_fallback
uvicorn mock_provider:app --host 127.0.0.1 --port 8001
```

**Terminal 2 — start the gateway:**

```bash
cd task_4_rate_limit_fallback
uvicorn router:app --host 127.0.0.1 --port 8000
```

The SQLite database is created automatically when the gateway starts.

## Test the fallback

Send a request to the gateway:

```bash
curl -i -sS -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Authorization: Bearer tenant-a-demo-key" \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-model","messages":[{"role":"user","content":"Hello"}],"max_tokens":100}'
```

By default, the primary mock provider returns HTTP 429. The gateway should return a successful response from the backup provider, with the header:

```text
x-model-provider: backup
```

## Test timeout fallback

Stop the mock provider and restart it with this setting:

```bash
PRIMARY_BEHAVIOR=timeout uvicorn mock_provider:app --host 127.0.0.1 --port 8001
```

Send the request again. The primary provider should time out after 3 seconds, and the gateway should return a response from the backup. Restart the mock provider without `PRIMARY_BEHAVIOR=timeout` to restore its default behavior.

## Test the token limit and tenant isolation

First, send a request using `tenant-a-demo-key` with `"max_tokens":49000`. Then send another request using the same key with `"max_tokens":1000`. The second request should receive HTTP 429 with a sanitized gateway error and a `Retry-After` header.

Send the small request with `tenant-b-demo-key`. It should succeed because the gateway tracks each tenant separately.

Token use is reserved based on the request content and requested `max_tokens`. Reservations expire after 60 seconds.

## Notes

This task uses mock providers and demo API keys. It does not call a real LLM provider. The SQLite database file is created locally when the gateway starts.