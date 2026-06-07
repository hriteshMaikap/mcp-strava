"""
Context Distillation — compress Strava API responses before LLM consumption.

Architecture:
    Strava API → Service Layer → **Distillation** → Tool Layer → MCP → LLM

Three compression techniques, applied in order:
    1. Structural stripping  — remove nulls, false booleans, UI/social metadata
    2. Semantic compression  — drop fields the LLM cannot interpret (polylines, avatar URLs)
    3. Statistical aggregation — replace per-second time series with per-km summaries
"""

from mcp_server.distillation.core import compact, strip_nulls, strip_fields
