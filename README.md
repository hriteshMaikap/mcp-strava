# Strava MCP

An MCP server for giving an AI assistant the Strava context it needs to build a realistic, personalized running plan.

This project is intentionally narrow in scope. It is not trying to expose every Strava capability for every possible workflow. The current toolset is designed for coaching-style use cases such as:

- understanding recent running history
- reviewing individual runs in detail
- checking rolled-up athlete stats
- extracting enough context to build a personalized training plan

If your goal is route discovery, segment browsing, club analysis, or broad Strava exploration, this server is probably too focused in its current form.

## What It Does Well

This server is best used when you want an AI model to:

- inspect your running consistency and weekly mileage
- review recent activities and long-run patterns
- identify relevant benchmark efforts from your activity history
- understand recovery, pace trends, and training load
- propose a grounded half-marathon or similar running plan

That is the primary distribution story for this repository: personalized plan generation from your own Strava data.

## Available Tools

- `login`
  Completes the Strava OAuth flow and stores tokens locally in `.strava_token.json`.
- `list_athlete_activities`
  Lists activity summaries so the model can explore your training history.
- `get_activity_by_id`
  Fetches one activity in detail, including splits and optional segment efforts.
- `get_athlete_stats`
  Fetches rolled-up athlete statistics from Strava.

## Safety And Privacy

Before pushing this repository publicly:

- keep `.env` out of Git
- keep `.strava_token.json` out of Git
- rotate credentials immediately if either file was ever committed anywhere
- review client config files before sharing screenshots or snippets, because they can reveal absolute local paths

This repo already ignores `.env` and `.strava_token.json`.

Important: the server now avoids returning raw `access_token` and `refresh_token` values from the `login` tool response. Tokens are still stored locally for API access, but they are not echoed back to the MCP client.

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv)
- a Strava API application with:
  - Authorization Callback Domain: `localhost`
  - Redirect URI: `http://localhost:8000`

Create a local `.env` file:

```env
STRAVA_CLIENT_ID=your_strava_client_id
STRAVA_CLIENT_SECRET=your_strava_client_secret
```

## Local Setup With `uv`

Install dependencies:

```bash
uv sync
```

Run the server directly:

```bash
uv run strava-mcp
```

Or:

```bash
uv run python server.py
```

## Claude Desktop

Example `claude_desktop_config.json` entry:

```json
{
  "mcpServers": {
    "strava-mcp": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\YOUR_USER\\path\\to\\strava-mcp",
        "run",
        "strava-mcp"
      ]
    }
  }
}
```

Why this form:

- it avoids hard-coding the venv Python path
- it uses the packaged entrypoint from `pyproject.toml`
- it keeps the server startup consistent across machines

## GitHub Copilot And Other MCP Clients

Any MCP client that supports a stdio server can use the same command pattern:

```json
{
  "command": "uv",
  "args": [
    "--directory",
    "/absolute/path/to/strava-mcp",
    "run",
    "strava-mcp"
  ]
}
```

If the client supports environment injection, provide `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET` there instead of relying on a local `.env` file.

## Coaching Prompt Structure

This server works best when the AI coach follows a structured intake process instead of jumping straight into a plan.

Rather than hard-coding one personal prompt, use a framework like this:

1. Define the coaching role
   Tell the model to act like a realistic running coach that prioritizes achievable progress over motivational fluff.

2. State the goal clearly
   Include the race distance, target outcome, and whether the target is completion-focused or time-focused.

3. Provide athlete background
   Include training age, current consistency, body context if relevant, and any cross-training or strength work.

4. List running constraints
   Mention preferred run frequency, available training days, terrain, treadmill access, weather constraints, and scheduling limits.

5. Mention injury and recovery context
   Include current pain points, recurring issues, deload preferences, and anything the coach should avoid overloading.

6. Tell the coach to inspect Strava before planning
   Ask it to review activity history, recent consistency, long runs, pace trends, and current weekly mileage before writing the plan.

7. Tell the coach to identify benchmark efforts
   Ask it to find useful reference performances such as recent best efforts at 5K, 10K, or longer sustained runs.

8. Define the preferred training structure
   Specify whether you want easy runs, workouts, long runs, recovery emphasis, or a fixed number of sessions per week.

9. Define the plan output
   Ask for a week-by-week structure, pace guidance in your preferred units, progression logic, deload weeks, and coaching notes for each run.

10. Require grounded reasoning
    Tell the model to explain why the volume and workout progression fit the athlete's current level rather than giving a generic template.

## Example Questions For The Coach

If you want a simpler template, these are the kinds of questions or inputs you would give your AI coach:

- What race or distance am I training for?
- What is my actual current running level based on my Strava history?
- What are my recent weekly mileage and consistency patterns?
- Which activities best represent my current fitness?
- How well do I handle easy runs, faster efforts, and long runs?
- What recovery or injury risks show up from my training pattern?
- Given my gym schedule and recovery limits, how many runs per week are realistic?
- What training paces are appropriate for me right now?
- How many weeks should my plan be?
- Where should deload weeks go?
- What should each run of the week be trying to achieve?
- What is the most realistic way to progress toward my goal without overreaching?

## Suggested Usage Flow

For the coaching use case, the model should generally:

1. call `login`
2. call `list_athlete_activities`
3. inspect relevant runs with `get_activity_by_id`
4. call `get_athlete_stats`
5. synthesize current fitness, volume, and patterns
6. produce a realistic plan with deloads and progression

## Publishing Checklist

- confirm `.env` is not tracked
- confirm `.strava_token.json` is not tracked
- confirm no committed files contain copied token values
- confirm the README does not promise unsupported Strava features
- confirm the MCP client examples do not expose your personal filesystem paths
