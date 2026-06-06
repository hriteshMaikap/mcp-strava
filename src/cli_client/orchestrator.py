"""
orchestrator.py — Request Orchestration Layer

Drives the Gemini ↔ MCP tool-call loop. Receives a user message, runs
tool calls until the model produces a final text reply, and returns it.

No terminal I/O here. UI callbacks are injected so this layer stays
testable and display-agnostic.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Callable

from google.genai import types
from mcp import ClientSession as McpSession


# ---------------------------------------------------------------------------
# Callbacks type aliases (keeps the signature readable)
# ---------------------------------------------------------------------------

OnToolCall    = Callable[[str, dict], None]          # (tool_name, args)
OnToolResult  = Callable[[str, str], None]           # (preview, log_path)
OnToolError   = Callable[[str, str], None]           # (tool_name, err_msg)


# ---------------------------------------------------------------------------
# MCP bridge
# ---------------------------------------------------------------------------

async def _execute_tool(
    mcp: McpSession,
    name: str,
    args: dict,
    on_result: OnToolResult,
    on_error: OnToolError,
) -> dict:
    """
    Call one MCP tool, persist the raw payload to observability/, and
    return a clean result dict for Gemini's function-response turn.
    """
    try:
        result = await mcp.call_tool(name, arguments=args)
    except Exception as exc:
        on_error(name, str(exc))
        return {"error": str(exc)}

    if not result.content:
        on_result("[no data returned]", "—")
        return {"result": "Success (no data returned)"}

    # FastMCP serialises Python lists as multiple TextContent blocks.
    # Join them all into a single JSON array so nothing is lost.
    text_parts = [block.text for block in result.content if hasattr(block, "text")]

    if len(text_parts) <= 1:
        raw_text = text_parts[0] if text_parts else ""
    else:
        # Wrap individual JSON fragments into a proper JSON array.
        raw_text = "[" + ", ".join(text_parts) + "]"

    # Persist to observability/
    os.makedirs("observability", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"observability/{ts}_{name}.json"
    try:
        parsed = json.loads(raw_text)
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(parsed, f, indent=2)
    except json.JSONDecodeError:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

    preview = raw_text[:280].replace("\n", " ")
    if len(raw_text) > 280:
        preview += "…"

    on_result(preview, log_path)
    return {"result": raw_text}


# ---------------------------------------------------------------------------
# Main orchestration entry point
# ---------------------------------------------------------------------------

async def run_turn(
    *,
    chat,                          # genai async chat object
    mcp: McpSession,
    user_message: str,
    on_tool_call: OnToolCall,
    on_tool_result: OnToolResult,
    on_tool_error: OnToolError,
) -> tuple[str, list[str]]:
    """
    Send *user_message* to Gemini, resolve all tool-call rounds, and return:
      (final_text_reply, list_of_tool_names_used)

    The caller never touches the Gemini or MCP APIs directly.
    """
    response = await chat.send_message(user_message)
    tools_used: list[str] = []

    # Gemini may chain several rounds of tool calls before producing text.
    while response.function_calls:
        for func_call in response.function_calls:
            name = func_call.name
            args = dict(func_call.args)
            tools_used.append(name)

            on_tool_call(name, args)

            tool_result = await _execute_tool(
                mcp, name, args,
                on_result=on_tool_result,
                on_error=on_tool_error,
            )

            response = await chat.send_message(
                types.Part.from_function_response(
                    name=name,
                    response=tool_result,
                )
            )

    final_text = response.text or "[no reply]"
    return final_text, tools_used