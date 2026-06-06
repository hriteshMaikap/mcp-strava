# Strava MCP

An MCP server and CLI client for giving an AI assistant the Strava context it needs to build a realistic, personalized running plan, analyse your performance, and act as a data-driven sports coach.

## Two Ways to Use

This project caters to two specific use cases:

### 1. The MCP Server (For Claude Desktop & GitHub Copilot)

For people who want to plug the Strava context directly into their existing AI environments via the Model Context Protocol (MCP).

#### Claude Desktop
You can set up the server for Claude Desktop by using stdio mode. Add this to your `claude_desktop_config.json`:

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

#### GitHub Copilot
Any MCP client that supports a stdio server or streamable-http can use the same command pattern:

```json
{
	"servers": {
		"strava-mcp": {
			"url": "http://127.0.0.1:5001/mcp",
			"type": "http"
		}
	},
	"inputs": []
}
```

*Note: Make sure you provide `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET` via your `.env` file or environment variables.*

---

### 2. The Terminal Client (The CLI Route)

For those who are broke like me and want to interact via the terminal. This uses a built-in CLI client powered by Google's Gemini API (coz free!), functioning as a direct chat interface with your Strava data.

**Prerequisites:**
- Get a free API Key from [Google AI Studio](https://aistudio.google.com/).
- This project leverages **Gemma 4 31B** (`gemma-4-31b-it`) by default (as configured in `llm.py`), giving you a powerful, data-driven local coach.

**Setup:**
Create a local `.env` file with your credentials:

```env
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
GEMINI_API_KEY=your_gemini_api_key
```

**Run the CLI Client:**

```bash
uv run python src/cli_client/main.py
```

---

## Capabilities & Available Tools

This assistant is a terse, numbers-first sports performance coach. It has access to a wide array of tools to fetch activities, analyze streams, review segments, and more.

### Tool Categories
- **Authentication**: `login`
- **Athlete Data**: `get_athlete_profile`, `get_athlete_stats`, `get_athlete_zones`, `get_athlete_clubs`, `get_gear_detail`
- **Activities**: `list_activities`, `get_activity_detail`, `get_activity_details_batch`, `get_activity_laps`, `get_activity_zones`
- **Telemetry Streams**: `get_pace_profile`, `get_hr_profile`, `get_power_profile`, `get_gps_track`, `get_raw_streams`, `analyse_distance_segment`
- **Segments**: `get_starred_segments`, `get_segment`, `get_segment_efforts`, `explore_segments`, `star_segment`, `get_segment_effort_streams`

### Known Limitations (Work In Progress)

- **Telemetry Streams**: If you don't want to burn your tokens, **avoid using telemetry streams based tools**. It is too unrestricted and currently a work in progress. We are actively trying to understand return formats and create better context to get the best data possible with the minimum amount of tokens, maximizing outputs so the CLI feels like an actual coach. It will work much better later.

### Example Prompts

You can ask the coach complex, analytical questions about your training data:

- **"Show me my pace details for the longest run I have made."**
- **"Explain run splits for longest run, where could I have improved."**
- "What is my actual current running level based on my Strava history?"
- "Which activities best represent my current fitness?"
- "What are my recent weekly mileage and consistency patterns?"
- "Given my gym schedule and recovery limits, how many runs per week are realistic?"

---

## Prerequisites & Installation

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv)
- A Strava API application with:
  - Authorization Callback Domain: `localhost`
  - Redirect URI: `http://localhost:8000`

Install dependencies:

```bash
uv sync
```

## Safety And Privacy

- Keep `.env` and `.strava_token.json` out of Git.
- Rotate credentials immediately if leaked.
- The server avoids returning raw `access_token` and `refresh_token` values to the AI model. Tokens are stored locally for API access only.
