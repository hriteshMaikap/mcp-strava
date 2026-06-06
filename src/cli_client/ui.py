"""
ui.py — Presentation & Terminal UX Layer

Everything the athlete sees. ANSI art, loaders, banners, formatted output.
No business logic. No I/O outside of display.
"""

from __future__ import annotations

import itertools
import sys
import threading
import time
from enum import Enum


# ---------------------------------------------------------------------------
# ANSI colour palette  (256-colour + reset)
# ---------------------------------------------------------------------------

class C:
    """Colour constants. All terminal paint lives here."""
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"

    # Amber / performance orange — primary accent
    AMBER   = "\033[38;5;214m"
    ORANGE  = "\033[38;5;208m"
    GOLD    = "\033[38;5;220m"

    # Slate / asphalt — structural chrome
    SLATE   = "\033[38;5;240m"
    CHALK   = "\033[38;5;252m"
    WHITE   = "\033[38;5;255m"

    # Sport-specific signal colours
    RUN     = "\033[38;5;196m"   # red  — heart-rate red
    CYCLE   = "\033[38;5;33m"    # blue — road blue
    SWIM    = "\033[38;5;45m"    # cyan — lane water

    # Status
    OK      = "\033[38;5;82m"
    WARN    = "\033[38;5;226m"
    ERR     = "\033[38;5;196m"


# ---------------------------------------------------------------------------
# Tool-name → human-friendly verb mapping
# ---------------------------------------------------------------------------

TOOL_VERBS: dict[str, str] = {
    # auth
    "login":                      "authenticating",
    "check_auth":                 "checking credentials",
    # activities
    "list_activities":            "fetching your activities",
    "get_activity_detail":        "loading activity details",
    "get_activity_details_batch": "loading activity details",
    "get_activity_laps":          "pulling lap splits",
    "get_activity_zones":         "reading heart-rate zones",
    # athlete
    "get_athlete_profile":        "loading your profile",
    "get_athlete_stats":          "pulling lifetime stats",
    "get_athlete_zones":          "reading training zones",
    "get_athlete_clubs":          "checking your clubs",
    "get_gear":                   "loading gear info",
    # segments
    "get_starred_segments":       "loading starred segments",
    "get_segment":                "pulling segment data",
    "get_segment_efforts":        "scanning segment efforts",
    "explore_segments":           "exploring nearby segments",
    "star_segment":               "starring the segment",
    # streams
    "get_activity_streams":       "streaming sensor data",
    "get_segment_effort_streams": "streaming effort data",
    "get_activity_hr_stream":     "reading heart-rate stream",
    "get_activity_power_stream":  "reading power stream",
    "get_activity_pace_stream":   "reading pace stream",
    "get_activity_elevation_stream": "reading elevation data",
    "get_activity_cadence_stream":   "reading cadence stream",
}

_FALLBACK_VERB = "processing"


# ---------------------------------------------------------------------------
# Sport-specific loader verbs  (idle / thinking phrases)
# ---------------------------------------------------------------------------

class SportVerbs(Enum):
    """Rotating status phrases shown while the agent thinks."""
    RUNNING = [
        "pacing the effort",
        "reading the splits",
        "checking cadence",
        "scanning the segment",
        "calculating VO₂",
        "parsing stride data",
        "syncing GPS trace",
        "pulling elevation",
    ]
    CYCLING = [
        "spinning up power",
        "reading the watts",
        "checking gear ratio",
        "analysing power curve",
        "scanning the peloton",
        "pulling FTP data",
        "parsing cadence stream",
        "loading climb profile",
    ]
    SWIMMING = [
        "counting the laps",
        "reading stroke rate",
        "parsing split times",
        "checking SWOLF score",
        "syncing pool data",
        "analysing turn efficiency",
        "loading CSS pace",
        "pulling distance per stroke",
    ]
    GENERIC = [
        "querying the data",
        "interrogating Strava",
        "pulling your stats",
        "crunching numbers",
        "fetching the feed",
        "running the query",
        "loading athlete data",
        "syncing with server",
    ]


# ---------------------------------------------------------------------------
# Spinner / Loader
# ---------------------------------------------------------------------------

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Loader:
    """Non-blocking terminal spinner with sport-aware rotating verbs."""

    def __init__(self, sport: str = "generic") -> None:
        sport_map = {
            "run": SportVerbs.RUNNING,
            "running": SportVerbs.RUNNING,
            "ride": SportVerbs.CYCLING,
            "cycling": SportVerbs.CYCLING,
            "swim": SportVerbs.SWIMMING,
            "swimming": SportVerbs.SWIMMING,
        }
        verbs_enum = sport_map.get(sport.lower(), SportVerbs.GENERIC)
        self._verbs = itertools.cycle(verbs_enum.value)
        self._frames = itertools.cycle(SPINNER_FRAMES)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._override_verb: str | None = None

    def set_verb(self, verb: str) -> None:
        """Push a specific verb onto the spinner (e.g. from a tool call)."""
        with self._lock:
            self._override_verb = verb

    def clear_verb(self) -> None:
        """Return to auto-rotating sport verbs."""
        with self._lock:
            self._override_verb = None

    def start(self) -> "Loader":
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def stop(self, clear: bool = True) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
        if clear:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def _spin(self) -> None:
        verb = next(self._verbs)
        tick = 0
        while not self._stop.is_set():
            frame = next(self._frames)
            with self._lock:
                display = self._override_verb or verb
            sys.stdout.write(
                f"\r  {C.AMBER}{frame}{C.RESET}  "
                f"{C.DIM}{display}{C.RESET}  "
            )
            sys.stdout.flush()
            time.sleep(0.09)
            tick += 1
            if tick % 22 == 0:          # rotate verb every ~2 s
                verb = next(self._verbs)

    def __enter__(self) -> "Loader":
        return self.start()

    def __exit__(self, *_) -> None:
        self.stop()


# ---------------------------------------------------------------------------
# Banner & chrome
# ---------------------------------------------------------------------------

BANNER = f"""{C.AMBER}{C.BOLD}
  ██████ ████████ ██████   █████  ██    ██  █████
  ██        ██    ██   ██ ██   ██ ██    ██ ██   ██
  ███████   ██    ██████  ███████ ██    ██ ███████
       ██   ██    ██   ██ ██   ██  ██  ██  ██   ██
  ██████    ██    ██   ██ ██   ██   ████   ██   ██{C.RESET}
{C.SLATE}  ─────────────────────────────────────────────────
  S P O R T S   D A T A   C O M M A N D   C E N T R E{C.RESET}
"""

DIVIDER      = f"{C.SLATE}  {'─' * 57}{C.RESET}"
THIN_DIVIDER = f"{C.SLATE}  {'·' * 57}{C.RESET}"


def print_banner() -> None:
    print(BANNER)
    print(DIVIDER)
    sport_line = (
        f"  {C.RUN}● RUN{C.RESET}  "
        f"{C.CYCLE}● CYCLE{C.RESET}  "
        f"{C.SWIM}● SWIM{C.RESET}  "
        f"{C.DIM}· type 'help' · 'quit' to exit{C.RESET}"
    )
    print(f"  {sport_line}")
    print(DIVIDER + "\n")


def print_help() -> None:
    print(DIVIDER)
    rows = [
        ("help",          "show this panel"),
        ("sport <type>",  "set active sport context  [run|ride|swim]"),
        ("history",       "print this session's Q&A log"),
        ("clear",         "wipe session history"),
        ("quit / q",      "exit the command centre"),
    ]
    print(f"\n  {C.GOLD}{C.BOLD}COMMANDS{C.RESET}")
    for cmd, desc in rows:
        print(f"    {C.AMBER}{cmd:<18}{C.RESET}{C.DIM}{desc}{C.RESET}")
    print(f"\n  {C.GOLD}{C.BOLD}EXAMPLE QUERIES{C.RESET}")
    examples = [
        "What's my average pace over the last 10 runs?",
        "Show my best 5 km segment efforts this month.",
        "Compare my FTP trend across the last 8 rides.",
        "What's my SWOLF score in today's swim?",
        "Am I overtraining based on my TSS this week?",
    ]
    for ex in examples:
        print(f"    {C.DIM}› {ex}{C.RESET}")
    print()
    print(DIVIDER + "\n")


def tool_verb(name: str) -> str:
    """Map a tool name to a human-friendly action phrase."""
    return TOOL_VERBS.get(name, _FALLBACK_VERB)


def print_tool_call(name: str, args: dict) -> None:
    """Silent — tool calls are shown via the spinner verb, not printed."""
    pass


def print_tool_result(preview: str, log_path: str) -> None:
    """Silent — results go to observability only."""
    pass


def print_tool_error(name: str, err: str) -> None:
    print(f"\r\033[K  {C.ERR}✗{C.RESET}  {C.DIM}{err}{C.RESET}")


def print_agent_response(text: str) -> None:
    print(f"\n{THIN_DIVIDER}")
    # Indent response, preserve newlines
    for line in text.splitlines():
        print(f"  {C.CHALK}{line}{C.RESET}")
    print(f"{THIN_DIVIDER}\n")


def print_session_header(chat_id: str, sport: str) -> None:
    sport_colour = {
        "run": C.RUN, "ride": C.CYCLE, "swim": C.SWIM
    }.get(sport, C.AMBER)
    print(
        f"  {C.DIM}session {C.RESET}{C.SLATE}{chat_id[:8]}…{C.RESET}  "
        f"{sport_colour}■ {sport.upper()}{C.RESET}"
    )


def prompt_user(sport: str) -> str:
    sport_colour = {
        "run": C.RUN, "ride": C.CYCLE, "swim": C.SWIM
    }.get(sport, C.AMBER)
    tag = f"{sport_colour}{sport.upper()}{C.RESET}"
    try:
        return input(f"\n  {tag} {C.AMBER}›{C.RESET} ")
    except (KeyboardInterrupt, EOFError):
        return "__EXIT__"


def print_error(msg: str) -> None:
    print(f"\n  {C.ERR}ERROR{C.RESET}  {C.DIM}{msg}{C.RESET}\n")


def print_info(msg: str) -> None:
    print(f"  {C.SLATE}·{C.RESET}  {C.DIM}{msg}{C.RESET}")


def print_sport_switch(sport: str) -> None:
    colour = {"run": C.RUN, "ride": C.CYCLE, "swim": C.SWIM}.get(sport, C.AMBER)
    print(f"\n  {colour}■ Sport context → {sport.upper()}{C.RESET}\n")