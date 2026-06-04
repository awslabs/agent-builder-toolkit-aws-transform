#!/usr/bin/env python3
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Mock MCP Server: returns canned responses for MCP tool calls.

Standalone script (stdlib only) implementing the MCP stdio protocol.
Reads tool mock definitions from a JSON file specified via the
``MOCK_MCP_RESPONSES`` environment variable.

MCP Protocol (JSON-RPC 2.0 over stdio with newline-delimited JSON):
    Client → Server::

        {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}\\n

    Server → Client::

        {"jsonrpc":"2.0","id":1,"result":{...}}\\n

Note: agent-cli uses NDJSON (newline-delimited JSON) for stdio MCP
transport, not Content-Length framing.

Usage::

    MOCK_MCP_RESPONSES=/path/to/responses.json python3 mock_mcp_server.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def log(msg: str) -> None:
    """Log to stderr (stdout is reserved for the MCP protocol)."""
    print(f"[mock-mcp] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Tool schemas — loaded from mcp_tool_schemas.json (shared reference file).
# ---------------------------------------------------------------------------

_DEFAULT_SCHEMA: dict = {"type": "object", "properties": {}, "additionalProperties": True}


def _load_tool_catalog() -> tuple[dict[str, str], dict[str, dict]]:
    """Load tool descriptions and schemas from the companion JSON file.

    Returns ``(descriptions_dict, schemas_dict)``.  Falls back to empty
    dicts (every tool gets the permissive default schema) if the file is
    missing — this keeps the server functional even if the JSON is absent.
    """
    schema_file = Path(__file__).parent / "mcp_tool_schemas.json"
    if not schema_file.exists():
        log(f"WARNING: {schema_file} not found, using default schemas")
        return {}, {}
    try:
        catalog = json.loads(schema_file.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"WARNING: failed to load {schema_file}: {e}")
        return {}, {}

    tools = catalog.get("tools", {})
    descriptions: dict[str, str] = {}
    schemas: dict[str, dict] = {}
    for name, defn in tools.items():
        if "description" in defn:
            descriptions[name] = defn["description"]
        if "inputSchema" in defn:
            schemas[name] = defn["inputSchema"]
    log(f"Loaded {len(schemas)} tool schema(s) from {schema_file.name}")
    return descriptions, schemas


TOOL_DESCRIPTIONS, TOOL_SCHEMAS = _load_tool_catalog()


# ---------------------------------------------------------------------------
# Transport: Newline-delimited JSON-RPC over stdio (NDJSON)
# ---------------------------------------------------------------------------


def read_message() -> dict | None:
    """Read a newline-delimited JSON-RPC message from stdin.

    agent-cli uses NDJSON for stdio MCP transport: one JSON object per line.
    """
    while True:
        raw_line = sys.stdin.buffer.readline()
        if not raw_line:
            return None  # EOF
        line = raw_line.decode("utf-8").strip()
        if not line:
            continue  # skip blank lines
        return json.loads(line)


def write_message(msg: dict) -> None:
    """Write a newline-delimited JSON-RPC message to stdout."""
    body = json.dumps(msg) + "\n"
    sys.stdout.buffer.write(body.encode("utf-8"))
    sys.stdout.buffer.flush()


# ---------------------------------------------------------------------------
# Request handlers
# ---------------------------------------------------------------------------


def handle_initialize(request: dict) -> dict:
    """Respond to ``initialize`` with server capabilities."""
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": os.environ.get("MOCK_MCP_SERVER_NAME", "mock-mcp"),
                "version": "1.0.0",
            },
            "capabilities": {"tools": {}},
        },
    }


def handle_tools_list(request: dict, responses: list[dict]) -> dict:
    """Respond to ``tools/list`` with all tools from ``mcp_tool_schemas.json``.

    Advertises every tool from the schema catalog so the Agent sees
    the full toolset (matching production).  Scenario mock entries can
    override ``description`` or ``inputSchema`` for specific tools.  Tools
    called but not mocked will get a JSON-RPC error from ``handle_tools_call``.
    """
    # Build overrides from scenario mock definitions
    overrides: dict[str, dict] = {}
    for r in responses:
        name = r.get("tool", "")
        if name:
            overrides[name] = r

    tools = []
    seen: set[str] = set()

    # 1. Advertise ALL tools from the schema catalog
    for name in TOOL_DESCRIPTIONS:
        seen.add(name)
        ovr = overrides.get(name, {})
        tools.append(
            {
                "name": name,
                "description": ovr.get("description", TOOL_DESCRIPTIONS[name]),
                "inputSchema": ovr.get("inputSchema", TOOL_SCHEMAS.get(name, _DEFAULT_SCHEMA)),
            }
        )

    # 2. Add any scenario-only tools not in the catalog (e.g. planned tools)
    for r in responses:
        name = r.get("tool", "")
        if name and name not in seen:
            seen.add(name)
            tools.append(
                {
                    "name": name,
                    "description": r.get("description", f"Mock tool: {name}"),
                    "inputSchema": r.get("inputSchema", _DEFAULT_SCHEMA),
                }
            )

    return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"tools": tools}}


def handle_tools_call(request: dict, responses: list[dict]) -> dict:
    """Respond to ``tools/call`` with the canned response (or error)."""
    params = request.get("params", {})
    tool_name = params.get("name", "")
    log(f"tools/call: {tool_name}")

    for r in responses:
        if r.get("tool") == tool_name:
            response_data = r.get("response", {})
            log("  → returning canned response")
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"content": [{"type": "text", "text": json.dumps(response_data)}]},
            }

    log("  → no canned response, returning error")
    return {
        "jsonrpc": "2.0",
        "id": request.get("id"),
        "error": {
            "code": -32601,
            "message": f"Mock MCP: no canned response for tool '{tool_name}'",
        },
    }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def main() -> None:
    responses_file = os.environ.get("MOCK_MCP_RESPONSES")
    if not responses_file:
        log("ERROR: MOCK_MCP_RESPONSES environment variable not set")
        sys.exit(1)

    try:
        with open(responses_file) as f:
            responses: list[dict] = json.load(f)
    except Exception as e:
        log(f"ERROR: Failed to load {responses_file}: {e}")
        sys.exit(1)

    log(f"Loaded {len(responses)} mock response(s) from {responses_file}")

    while True:
        msg = read_message()
        if msg is None:
            break

        method = msg.get("method", "")

        # Notifications have no id and expect no response.
        if "id" not in msg:
            log(f"notification: {method}")
            continue

        log(f"request: {method}")

        if method == "initialize":
            response = handle_initialize(msg)
        elif method == "tools/list":
            response = handle_tools_list(msg, responses)
        elif method == "tools/call":
            response = handle_tools_call(msg, responses)
        else:
            response = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

        write_message(response)

    log("Server shutdown")


if __name__ == "__main__":
    main()
