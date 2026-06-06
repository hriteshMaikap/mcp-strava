"""
Strava MCP Client — interactive chat using Google GenAI + SSE transport.

Prerequisites:
  1. Start the MCP server first:  uv run strava-mcp
  2. Set GEMINI_API_KEY in your .env file.
  3. Run this client:            uv run python client.py
"""

import os
import asyncio
import json
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession
from mcp.client.sse import sse_client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not set in .env")

MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:5001/sse")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_mcp_tools_as_gemini(mcp_tools) -> list:
    """Convert MCP tool descriptors → Gemini FunctionDeclaration objects."""
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=t.inputSchema,
                )
            ]
        )
        for t in mcp_tools.tools
    ]


async def _call_tool(session: ClientSession, name: str, args: dict) -> dict:
    """Execute one MCP tool call and log the raw payload to observability/."""
    result = await session.call_tool(name, arguments=args)

    if not result.content:
        print("    [No data returned]")
        return {"result": "Success (no data returned)"}

    raw_text = result.content[0].text

    # Persist full response for inspection
    os.makedirs("observability", exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"observability/{ts}_{name}.json"
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(json.loads(raw_text), f, indent=2)
    except json.JSONDecodeError:
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(raw_text)

    preview = raw_text[:300].replace("\n", " ") + ("..." if len(raw_text) > 300 else "")
    print(f"    [Data Preview] {preview}")
    print(f"    [Full response → {log_path}]")

    return {"result": raw_text}


async def _read_line(loop: asyncio.AbstractEventLoop, prompt: str) -> str:
    """Read a line from stdin without blocking the asyncio event loop.

    asyncio.to_thread / run_in_executor both run the callable in the default
    ThreadPoolExecutor, which is safe on all platforms including Windows.
    """
    return await loop.run_in_executor(None, lambda: input(prompt))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    loop = asyncio.get_event_loop()
    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"Connecting to MCP server at {MCP_SERVER_URL} …")

    async with sse_client(MCP_SERVER_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            gemini_tools = _load_mcp_tools_as_gemini(mcp_tools)

            print(f"Connected! Loaded {len(mcp_tools.tools)} tools.\n")
            print("=" * 63)
            print(" Interactive Strava Coach — type 'quit' to exit.")
            print("=" * 63 + "\n")

            # Persistent chat session keeps full conversation history
            chat = client.aio.chats.create(
                model="gemini-3.5-flash",
                config=types.GenerateContentConfig(
                    tools=gemini_tools,
                    temperature=0.2,
                ),
            )

            while True:
                # Use run_in_executor so stdin blocking never stalls anyio's
                # internal task group that keeps the SSE stream alive.
                try:
                    user_input = await _read_line(loop, "You: ")
                except (KeyboardInterrupt, EOFError):
                    print("\nGoodbye!")
                    break

                user_input = user_input.strip()
                if not user_input:
                    continue
                if user_input.lower() in ("quit", "exit", "q"):
                    print("Goodbye!")
                    break

                print("Gemini: [Thinking …]")
                response = await chat.send_message(user_input)

                # Gemini may chain multiple tool calls before replying
                while response.function_calls:
                    for func_call in response.function_calls:
                        print(f"  [Tool] → {func_call.name}  args={dict(func_call.args)}")
                        try:
                            tool_result = await _call_tool(
                                session, func_call.name, dict(func_call.args)
                            )
                        except Exception as exc:
                            print(f"  [Tool Error] {exc}")
                            tool_result = {"error": str(exc)}

                        print("  [Sending result back to Gemini …]")
                        response = await chat.send_message(
                            types.Part.from_function_response(
                                name=func_call.name,
                                response=tool_result,
                            )
                        )

                print(f"\nGemini: {response.text or '[no text reply]'}\n")


if __name__ == "__main__":
    asyncio.run(main())
