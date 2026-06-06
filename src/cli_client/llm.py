"""
llm.py — LLM Initialisation Layer

Owns Gemini client creation, tool schema translation, and chat session
construction. Returns ready-to-use objects; does NOT send any messages.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from mcp import ClientSession as McpSession

load_dotenv()

_MODEL = "gemma-4-31b-it"

_SYSTEM_PROMPT = """\
You are STRAVA, a terse, data-driven sports performance coach embedded in a
command-line terminal. You specialise in running, cycling, and swimming.

Personality:
  • Low-key and direct — no fluff, no motivational clichés.
  • Numbers-first: lead with the metric, follow with brief interpretation.
  • Use athlete jargon naturally (TSS, FTP, SWOLF, VO₂max, CTL, ATL, IF).
  • One-line observations are fine. Long prose is not.

Format rules:
  • Use plain text only — no markdown headers, no bullet symbols (use ·).
  • Separate logical sections with a blank line.
  • Timestamps in hh:mm:ss. Distances in km or m. Pace in min/km or /100 m.
  • If data is missing, say so concisely — never fabricate numbers.

Your job: analyse the athlete's Strava data, answer performance questions,
and surface insights they haven't asked for if the data warrants it.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_client() -> genai.Client:
    """Initialise and return a Gemini API client."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set in .env")
    return genai.Client(api_key=api_key)


def mcp_tools_to_gemini(mcp_session_tools) -> list[types.Tool]:
    """
    Convert MCP tool descriptors → Gemini FunctionDeclaration wrappers.

    Each MCP tool becomes its own types.Tool so Gemini can resolve them
    individually during parallel function calls.
    """
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
        for t in mcp_session_tools.tools
    ]


def create_chat(
    client: genai.Client,
    gemini_tools: list[types.Tool],
) -> genai.types.AsyncChat:
    """
    Spin up a stateful Gemini chat with system prompt + tools pre-loaded.
    Returns an async chat object ready for .send_message() calls.
    """
    return client.aio.chats.create(
        model=_MODEL,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            tools=gemini_tools,
            temperature=0.15,      # tight for data work
            top_p=0.9,
        ),
    )