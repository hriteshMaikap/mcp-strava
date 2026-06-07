"""
agent.py - Agent harness for the terminal client.

Owns task execution policy: context assembly, model/tool loop, step budgets,
tool validation, retry accounting, and stop reasons.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Literal

from google.genai import types
from mcp import ClientSession as McpSession

from cli_client.chat_session import ChatSession
from cli_client.orchestrator import execute_tool


OnToolCall = Callable[[str, dict], None]
OnToolResult = Callable[[str, str], None]
OnToolError = Callable[[str, str], None]

StopReason = Literal[
    "final",
    "max_steps",
    "tool_error_budget",
    "repeated_tool_budget",
    "empty_model_response",
]


@dataclass(frozen=True)
class AgentConfig:
    """Runtime guardrails for one agent task."""

    max_steps: int = 12
    max_tool_errors: int = 3
    max_same_tool_repeats: int = 4
    recent_turns: int = 8


@dataclass
class AgentStep:
    """Trace record for one model or tool action."""

    index: int
    kind: str
    tool_name: str | None = None
    args: dict | None = None
    preview: str | None = None
    log_path: str | None = None
    error: str | None = None


@dataclass
class AgentRunResult:
    """Complete result returned to the CLI after one user task."""

    final_text: str
    tools_used: list[str]
    steps: list[AgentStep] = field(default_factory=list)
    stop_reason: StopReason = "final"


class AgentRunner:
    """
    Small, explicit agent loop around Gemini function calling and MCP tools.

    The model decides which tool to call. The harness decides whether that tool
    is valid, executes it through MCP, feeds the result back, and keeps looping
    until the task is answered or a guardrail is hit.
    """

    def __init__(
        self,
        *,
        chat,
        mcp: McpSession,
        tool_names: Iterable[str],
        config: AgentConfig | None = None,
    ) -> None:
        self._chat = chat
        self._mcp = mcp
        self._tool_names = set(tool_names)
        self._config = config or AgentConfig()

    async def run(
        self,
        *,
        session: ChatSession,
        user_message: str,
        on_tool_call: OnToolCall,
        on_tool_result: OnToolResult,
        on_tool_error: OnToolError,
    ) -> AgentRunResult:
        """Run one user task to completion under the configured guardrails."""
        session.compact_if_needed()
        response = await self._chat.send_message(
            self._build_task_message(session, user_message)
        )

        steps: list[AgentStep] = []
        tools_used: list[str] = []
        tool_errors = 0
        tool_counts: dict[str, int] = {}

        for step_index in range(1, self._config.max_steps + 1):
            function_calls = response.function_calls or []

            if not function_calls:
                text = response.text
                if text:
                    steps.append(AgentStep(index=step_index, kind="final"))
                    return AgentRunResult(
                        final_text=text,
                        tools_used=tools_used,
                        steps=steps,
                        stop_reason="final",
                    )
                return AgentRunResult(
                    final_text="[no reply]",
                    tools_used=tools_used,
                    steps=steps,
                    stop_reason="empty_model_response",
                )

            for func_call in function_calls:
                name = func_call.name
                args = dict(func_call.args or {})
                tools_used.append(name)
                tool_counts[name] = tool_counts.get(name, 0) + 1

                if tool_counts[name] > self._config.max_same_tool_repeats:
                    text = (
                        "I stopped because the same tool was requested too many "
                        f"times: {name}."
                    )
                    steps.append(
                        AgentStep(
                            index=step_index,
                            kind="error",
                            tool_name=name,
                            args=args,
                            error=text,
                        )
                    )
                    return AgentRunResult(
                        final_text=text,
                        tools_used=tools_used,
                        steps=steps,
                        stop_reason="repeated_tool_budget",
                    )

                on_tool_call(name, args)

                if name not in self._tool_names:
                    tool_errors += 1
                    error = f"Unknown MCP tool: {name}"
                    on_tool_error(name, error)
                    tool_payload = self._tool_error_payload(name, error)
                    steps.append(
                        AgentStep(
                            index=step_index,
                            kind="tool_error",
                            tool_name=name,
                            args=args,
                            error=error,
                        )
                    )
                else:
                    tool_payload = await execute_tool(
                        self._mcp,
                        name,
                        args,
                        on_result=on_tool_result,
                        on_error=on_tool_error,
                    )
                    if not tool_payload.get("ok", False):
                        tool_errors += 1
                    steps.append(
                        AgentStep(
                            index=step_index,
                            kind="tool_call",
                            tool_name=name,
                            args=args,
                            preview=tool_payload.get("preview"),
                            log_path=tool_payload.get("log_path"),
                            error=tool_payload.get("error"),
                        )
                    )

                if tool_errors >= self._config.max_tool_errors:
                    return AgentRunResult(
                        final_text=(
                            "I hit repeated tool errors before I could complete "
                            "the task. Check the last tool error and try again."
                        ),
                        tools_used=tools_used,
                        steps=steps,
                        stop_reason="tool_error_budget",
                    )

                response = await self._chat.send_message(
                    types.Part.from_function_response(
                        name=name,
                        response=tool_payload,
                    )
                )

        return AgentRunResult(
            final_text=(
                "I stopped after reaching the agent step limit before producing "
                "a final answer."
            ),
            tools_used=tools_used,
            steps=steps,
            stop_reason="max_steps",
        )

    def _build_task_message(self, session: ChatSession, user_message: str) -> str:
        context = session.build_agent_context(self._config.recent_turns)
        return (
            "CLIENT-MANAGED CONTEXT\n"
            f"{context}\n\n"
            "CURRENT USER TASK\n"
            f"{user_message}\n\n"
            "Run the task as an agent. Use MCP tools when Strava data is needed, "
            "then stop with the final answer once the task is satisfied."
        )

    @staticmethod
    def _tool_error_payload(name: str, error: str) -> dict:
        return {
            "ok": False,
            "tool_name": name,
            "error": error,
            "result": None,
            "preview": error,
            "log_path": None,
        }
