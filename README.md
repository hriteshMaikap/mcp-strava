# Strava MCP

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![MCP Protocol](https://img.shields.io/badge/Protocol-MCP-orange.svg)](https://modelcontextprotocol.io/)

Strava MCP is a Model Context Protocol (MCP) server and interactive command-line interface (CLI) client designed to give AI assistants direct, structured access to your Strava training data. By acting as a data-driven sports performance coach, it enables LLMs to construct personalized training plans, analyze workouts, and track progress using raw telemetry and athlete metrics.

The project features a custom **Context Distillation Engine** that solves LLM context window issues by condensing raw, high-resolution Strava API payloads (often >50K tokens) by up to **98.6%** without sacrificing key analytical details.

---

## Key Features

- **Double-Agent Utility**: 
  - **MCP Server**: Seamless stdio/HTTP integration with Claude Desktop, GitHub Copilot, Cursor, or any other MCP-compliant client.
  - **Terminal Client**: A lightweight, standalone CLI agent powered by Google's **Gemma 4 31B** for a data-driven coaching experience directly in your terminal.
- **Client-Side Agent Harness**:
  - Owns the model/tool loop instead of relying on a single LLM call.
  - Manages MCP tool validation, execution budgets, repeated-tool protection, tool-error recovery, and stop reasons.
  - Maintains compact session memory plus recent turns so long chats keep the useful context without flooding the model.
- **Context Distillation Engine**:
  - **Structural Stripping**: Recursive removal of empty fields, redundant UI metadata, null values, and noise booleans.
  - **Semantic Compression**: Automated stripping of polylines, image assets, and zero-activity sports blocks.
  - **Statistical Telemetry Aggregation**: Translates raw time-series arrays (thousands of per-second data points) into concise per-kilometer summaries, complete with pace variability, heart rate drift, and normalized power calculations.
- **Full-Spectrum Strava Context**: Complete tool support for athlete statistics, fitness zones, gear, activity details, laps, segment efforts, and telemetry streams.

---

## Context Distillation & Token Efficiency

Raw Strava API payloads are built for rich UI rendering and contain per-second GPS/heart-rate streams. Feeding this raw data directly to an LLM easily overflows context windows:
- A raw `get_pace_profile` stream for a 12km run occupies **~56,822 tokens**.
- Our **Context Distillation Engine** aggregates and filters this down to **~789 tokens (a 70x compression ratio)**.
- Cumulative tokens for complex multi-tool queries drop from **440,663** down to **6,293 tokens**, making telemetry analysis highly efficient and affordable.

---

## Installation & Initial Setup

Before choosing how you want to interact with the project, configure your Strava API credentials and local environment.

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (fast Python package installer and resolver)

### 1. Clone & Install
```bash
git clone https://github.com/your-username/strava-mcp.git
cd strava-mcp
uv sync
```

### 2. Register Your Strava Application
1. Log into your account and navigate to [Strava API Settings](https://www.strava.com/settings/api).
2. Create a new application.
3. Set **Authorization Callback Domain** to `localhost`.
4. Note your Client ID and Client Secret.

### 3. Environment Configuration
Create a `.env` file in the root of the project:
```env
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
# GEMINI_API_KEY=your_gemini_api_key (Only required for the CLI client)
```

---

## Usage Guide

### 1. Integrating as an MCP Server

#### For Claude Desktop
Add the following configuration to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "strava-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/strava-mcp",
        "run",
        "strava-mcp"
      ]
    }
  }
}
```

#### For GitHub Copilot / Cursor
Connect via stdio or host the server locally and connect using the streamable-http configuration:
```json
{
  "servers": {
    "strava-mcp": {
      "url": "http://127.0.0.1:5001/mcp",
      "type": "http"
    }
  }
}
```

---

### 2. Standalone Terminal CLI Client

For local terminal-based interaction. This client runs a small agent harness around a Gemini chat session and the local MCP server.

**Prerequisites:**
- Obtain a free API key from [Google AI Studio](https://aistudio.google.com/).
- Set the key in your `.env` file as `GEMINI_API_KEY`.
- By default, the client leverages **Gemma 4 31B** (`gemma-4-31b-it`).
  - **Maximum Context Length**: 262,144 tokens (includes input and output combined).
  - **Maximum Output Limit**: Varies by provider (typically 8,192 to 33,000 tokens).

**Run the CLI Client:**
```bash
uv run python src/cli_client/main.py
```

### CLI Agent Architecture

The terminal client is split into focused layers:

| Layer | Role |
|---|---|
| `main.py` | Starts the MCP connection, builds the agent, and runs the REPL. |
| `agent.py` | Runs the agent loop: context assembly, function-call handling, budgets, retries, and stop reasons. |
| `orchestrator.py` | Executes MCP tools, normalizes tool responses, and writes observability logs. |
| `chat_session.py` | Tracks turns, active sport context, compact session memory, and recent context. |
| `llm.py` | Creates the Gemini client/chat and converts MCP tool schemas into Gemini function declarations. |

Each agent turn continues until the model produces a final answer or a guardrail is reached, such as `max_steps`, repeated tool calls, or repeated tool errors. Raw tool payloads are still written under `observability/`, while the model receives a structured function response containing success state, result text, preview, and log path.

---

## Tool Capabilities

The assistant is equipped with the following toolsets:

| Category | Tools | Description |
|---|---|---|
| **Authentication** | `login` | OAuth flow and local token negotiation. |
| **Athlete Data** | `get_athlete_profile`, `get_athlete_stats`, `get_athlete_zones`, `get_athlete_clubs`, `get_gear_detail` | Retrieves personal records, HR/Power zones, and gear list. |
| **Activities** | `list_activities`, `get_activity_detail`, `get_activity_details_batch`, `get_activity_laps`, `get_activity_zones` | Fetches historical lists, details, and zone distributions. |
| **Telemetry Streams** | `get_pace_profile`, `get_hr_profile`, `get_power_profile`, `get_gps_track`, `get_raw_streams`, `analyse_distance_segment` | Returns distilled per-km telemetry for pacing, HR, and power. |
| **Segments** | `get_starred_segments`, `get_segment`, `get_segment_efforts`, `explore_segments`, `star_segment` | Explores, stars, and analyzes efforts on specific segments. |

---

## Example Prompts & Coaching Interrogation

You can ask the coach complex analytical questions about your training data:
- **"Show me my pace details for the longest run I have made."**
- **"Explain run splits for the longest run, where could I have improved?"**
- **"What are my recent weekly mileage and consistency patterns?"**
- **"Calculate my heart rate drift on my last threshold run and explain the aerobic efficiency impact."**
- **"Based on my historical workout logs, what is my estimated running profile?"**

---

## Safety and Privacy

- **Git Discipline**: The `.env` file and `.strava_token.json` contain sensitive API keys and access tokens. They are listed in `.gitignore` and should never be committed.
- **Credential Safety**: The MCP server never exposes raw OAuth tokens (`access_token`, `refresh_token`) to the LLM. All tokens are kept strictly server-side.
- **Local Isolation**: All calculations and distillation steps are processed locally inside your environment.

---

## Future Roadmap

The future expansion of Strava MCP focuses on enhancing client-side execution boundaries, caching efficiency, and telemetry analytics:

1. **Smart Cache Layer**: Implement a local SQLite caching system for token-heavy telemetry profiles to avoid making redundant Strava API requests for unchanged activities.
2. **Client-Side Token Budgeting**: Introduce dynamic thresholds in the Orchestrator layer that automatically switch distillation modes (e.g. summarizing further or truncating details) when hitting context bounds.
3. **Advanced Biometric Calculations**:
   - Compute normalized power curves and heart rate drift indexes dynamically inside the distillation engine.
   - Detect training overload signals by calculating acute-to-chronic workload ratios (ACWR) using rolling weekly summaries.
4. **Platform Agnostic Support**: Structure the ingestion pipeline to allow import of raw FIT or GPX files directly from other fitness portals (e.g., Garmin Connect, Wahoo) alongside Strava.

---

## Contributing

Contributions are welcome! Please follow these guidelines:
1. Fork the repository and create your branch: `git checkout -b feature/amazing-feature`.
2. Ensure your changes compile and pass code formatting linting rules.
3. Submit a pull request detailing the changes and performance impacts.

---

## License

Distributed under the MIT License. See `LICENSE` for more information.
