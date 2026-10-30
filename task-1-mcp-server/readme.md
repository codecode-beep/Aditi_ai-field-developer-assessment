# MCP Customer Server

A small Python MCP server that exposes customer lookup and refund request tools over stdio.

## Tools

### `get_customer_record`

- Input: `customer_id`
- Format: `CUST-` followed by exactly five uppercase letters or digits
- Example: `CUST-A123B`
- Returns a sample customer record.

### `trigger_refund`

- Inputs:
  - `customer_id`: same format as above
  - `amount`: finite number greater than zero
  - `reason`: at least 10 characters
- Returns a mock refund request result. It does not issue a real refund.

## Setup

Create and activate a virtual environment, then install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

## Run

```bash
python server.py

## Inspect the tools

With the virtual environment active, start the MCP Inspector:

```bash
npx @modelcontextprotocol/inspector python server.py
```

If you run into an npm cache error, use a temporary cache:

```bash
npx --cache /tmp/mcp-inspector-cache @modelcontextprotocol/inspector python server.py
```