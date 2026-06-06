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

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def last_n_turns(self, n: int = 10) -> list[Turn]:
        return self.history[-n:]

    def tool_usage_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for turn in self.history:
            for t in turn["tools_used"]:
                counts[t] = counts.get(t, 0) + 1
        return counts

    def __len__(self) -> int:
        return len(self.history)