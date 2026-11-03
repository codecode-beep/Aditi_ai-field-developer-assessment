# Task 3: LLM Streaming PII Guardrail

An LLM gateway that streams a provider’s response to a client while redacting email addresses, SSNs, and credit card numbers.

The mock provider deliberately splits sensitive values across response chunks. The gateway buffers a small amount of text, redacts detected PII, and streams the filtered SSE events to the client.

## Files

- `mock_provider.py` — sends a sample response as Server-Sent Events (SSE).
- `gateway.py` — forwards requests to the mock provider and filters response deltas.
- `redactor.py` — detects and replaces supported PII with `[REDACTED]`.
- `requirements.txt` — Python dependencies.

## Setup

Run these commands from the repository root:

```bash
source .venv/bin/activate
python -m pip install -r task-3-llm-stream-guardrail/requirements.txt
```

## Run the servers

Start each server in a separate Terminal window. In both windows, start from the repository root and activate the virtual environment.

**Terminal 1 — mock LLM provider:**

```bash
cd task-3-llm-stream-guardrail
uvicorn mock_provider:app --host 127.0.0.1 --port 8002
```

**Terminal 2 — streaming gateway:**

```bash
cd task-3-llm-stream-guardrail
uvicorn gateway:app --host 127.0.0.1 --port 8000
```

The client sends requests to `http://127.0.0.1:8000/v1/chat/completions`. The gateway connects to the mock provider at `http://127.0.0.1:8002/v1/chat/completions`.

## Try it

In a third Terminal window, send a request through the gateway:

```bash
curl -N -sS -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-model","messages":[{"role":"user","content":"Generate a response."}]}'
```

The streamed output should show `[REDACTED]` in place of the sample email, SSN, and card number. `-N` tells `curl` not to buffer the stream.
 