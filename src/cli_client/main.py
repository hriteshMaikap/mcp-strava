"""
client.py — CLI Entry Point

The thinnest possible shell. Wires all four layers together:

  ui.py            ← terminal presentation & loaders
  chat_session.py  ← session identity & history
  llm.py           ← Gemini client & tool schema translation
  orchestrator.py  ← Gemini ↔ MCP tool-call loop

All business logic lives in those modules. This file only:
  · starts the MCP connection
  · reads user input
  · dispatches commands
  · calls orchestrate → records history → renders output
"""

from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from mcp import ClientSession as McpSession
from mcp.client.sse import sse_client

from cli_client import ui
from cli_client import llm
from cli_client.agent import AgentRunner
from cli_client.chat_session import ChatSession

load_dotenv()

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:5001/sse")


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

def _handle_history(session: ChatSession) -> None:
    if not session.history:
        ui.print_info("no history yet this session")
        return

    print()
    for i, turn in enumerate(session.history, 1):
        role_label = (
            f"{ui.C.AMBER}YOU{ui.C.RESET}"
            if turn["role"] == "user"
            else f"{ui.C.CHALK}AGENT{ui.C.RESET}"
        )
        tools = ""
        if turn["tools_used"]:
            tools = (
                f"  {ui.C.DIM}[{', '.join(turn['tools_used'])}]{ui.C.RESET}"
            )
        ts = f"{ui.C.SLATE}{turn['ts']}{ui.C.RESET}"
        print(f"  {ts}  {role_label}{tools}")
        for line in turn["text"].splitlines():
            print(f"    {ui.C.DIM}{line}{ui.C.RESET}")
        print()


def _handle_sport(parts: list[str], session: ChatSession) -> None:
    if len(parts) < 2:
        ui.print_info(f"current sport: {session.sport}  ·  options: run ride swim")
        return
    sport = parts[1].lower()
    valid_map = {
        "run": "run", "running": "run",
        "ride": "ride", "cycling": "ride", "bike": "ride",
        "swim": "swim", "swimming": "swim",
    }
    mapped = valid_map.get(sport)
    if not mapped:
        ui.print_error(f"unknown sport '{sport}' — choose from: run ride swim")
        return
    session.set_sport(mapped)
    ui.print_sport_switch(mapped)


# ---------------------------------------------------------------------------
# Main async loop
# ---------------------------------------------------------------------------

async def async_main() -> None:
    loop = asyncio.get_event_loop()

    ui.print_banner()
    ui.print_info(f"connecting to MCP server at {MCP_SERVER_URL}")

    async with sse_client(MCP_SERVER_URL) as (read, write):
        async with McpSession(read, write) as mcp_session:
            await mcp_session.initialize()
            mcp_tools_raw = await mcp_session.list_tools()

            # ── LLM layer ──────────────────────────────────────────────
            gemini_client = llm.build_client()
            gemini_tools  = llm.mcp_tools_to_gemini(mcp_tools_raw)
            chat           = llm.create_chat(gemini_client, gemini_tools)
            agent          = AgentRunner(
                chat=chat,
                mcp=mcp_session,
                tool_names=[tool.name for tool in mcp_tools_raw.tools],
            )

            tool_count = len(mcp_tools_raw.tools)
            ui.print_info(f"ready · {tool_count} tools loaded")
            print()

            # ── Session layer ──────────────────────────────────────────
            session = ChatSession()
            ui.print_session_header(session.chat_id, session.sport)
            print()
            ui.print_info("type 'help' for commands\n")

            # ── REPL ───────────────────────────────────────────────────
            while True:
                raw = await loop.run_in_executor(
                    None, lambda: ui.prompt_user(session.sport)
                )

                if raw == "__EXIT__":
                    print(f"\n  {ui.C.DIM}session ended · {len(session)} turns logged{ui.C.RESET}\n")
                    break

                text = raw.strip()
                if not text:
                    continue

                # ── built-in commands ──────────────────────────────────
                lower = text.lower()

                if lower in ("quit", "exit", "q"):
                    print(f"\n  {ui.C.DIM}session ended · {len(session)} turns logged{ui.C.RESET}\n")
                    break

                if lower == "help":
                    ui.print_help()
                    continue

                if lower == "history":
                    _handle_history(session)
                    continue

                if lower == "clear":
                    session.clear()
                    ui.print_info("history cleared")
                    continue

                if lower.startswith("sport"):
                    _handle_sport(lower.split(), session)
                    continue

                # ── agent turn ─────────────────────────────────────────
                session.add_user(text)

                loader = ui.Loader(sport=session.sport).start()

                try:
                    result = await agent.run(
                        session=session,
                        user_message=text,
                        on_tool_call=lambda name, args: (
                            loader.set_verb(ui.tool_verb(name)),
                        ),
                        on_tool_result=lambda preview, path: (
                            loader.clear_verb(),
                        ),
                        on_tool_error=lambda name, err: (
                            loader.stop(clear=True),
                            ui.print_tool_error(name, err),
                            loader.start(),
                        ),
                    )
                except Exception as exc:
                    loader.stop()
                    ui.print_error(str(exc))
                    continue
                finally:
                    loader.stop()

                session.add_agent(result.final_text, result.tools_used)
                ui.print_agent_response(result.final_text)


def main() -> None:
    """Synchronous entry point for the console script."""
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
