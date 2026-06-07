"""
chat_session.py — Chat Management Layer

Owns the session identity and conversation history.
No LLM calls. No terminal I/O. Pure data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypedDict


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class Turn(TypedDict):
    role: str           # "user" | "agent"
    text: str
    ts: str             # ISO timestamp
    tools_used: list[str]


# ---------------------------------------------------------------------------
# ChatSession
# ---------------------------------------------------------------------------

@dataclass
class ChatSession:
    """
    Lightweight session container.

    chat_id  — hex representation of a UUID4, e.g. 'a3f9c1d2...'
    sport    — active sport context, governs loader verbs & prompt colour
    history  — ordered list of Turn dicts (question → response pairs)
    """

    sport: str = "generic"
    chat_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    history: list[Turn] = field(default_factory=list)
    memory_summary: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds")
    )

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_user(self, text: str) -> None:
        self.history.append(Turn(
            role="user",
            text=text,
            ts=datetime.utcnow().isoformat(timespec="seconds"),
            tools_used=[],
        ))

    def add_agent(self, text: str, tools_used: list[str] | None = None) -> None:
        self.history.append(Turn(
            role="agent",
            text=text,
            ts=datetime.utcnow().isoformat(timespec="seconds"),
            tools_used=tools_used or [],
        ))

    def set_sport(self, sport: str) -> None:
        """Update active sport context (run | ride | swim | generic)."""
        valid = {"run", "ride", "swim", "generic"}
        self.sport = sport if sport in valid else "generic"

    def clear(self) -> None:
        self.history.clear()
        self.memory_summary = ""

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def last_n_turns(self, n: int = 10) -> list[Turn]:
        return self.history[-n:]

    def build_agent_context(self, recent_turns: int = 8) -> str:
        """
        Build compact, explicit context for the agent runner.

        Gemini's chat object still owns provider-side state, but this gives the
        client harness deterministic control over what matters for each turn.
        """
        parts = [
            f"Active sport context: {self.sport}",
            f"Session id: {self.chat_id}",
        ]
        if self.memory_summary:
            parts.append(f"Session memory:\n{self.memory_summary}")

        recent = self.last_n_turns(recent_turns)
        if recent:
            lines = []
            for turn in recent:
                tools = ""
                if turn["tools_used"]:
                    tools = f" tools={','.join(turn['tools_used'])}"
                lines.append(f"{turn['role']}: {turn['text']}{tools}")
            parts.append("Recent turns:\n" + "\n".join(lines))

        return "\n\n".join(parts)

    def compact_if_needed(self, keep_turns: int = 12) -> None:
        """
        Keep old chat history available as a compact client-side memory.

        This is deterministic rather than LLM-generated: it preserves task
        phrasing and tool names without spending another model call.
        """
        if len(self.history) <= keep_turns:
            return

        old_turns = self.history[:-keep_turns]
        summary_lines = []
        if self.memory_summary:
            summary_lines.append(self.memory_summary)

        for turn in old_turns:
            text = " ".join(turn["text"].split())
            if len(text) > 220:
                text = text[:217] + "..."
            tools = ""
            if turn["tools_used"]:
                tools = f" [{', '.join(turn['tools_used'])}]"
            summary_lines.append(f"{turn['role']}: {text}{tools}")

        self.memory_summary = "\n".join(summary_lines[-40:])
        self.history = self.history[-keep_turns:]

    def tool_usage_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for turn in self.history:
            for t in turn["tools_used"]:
                counts[t] = counts.get(t, 0) + 1
        return counts

    def __len__(self) -> int:
        return len(self.history)
