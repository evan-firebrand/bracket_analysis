# 006 — Claude integration uses tool-use over core/ functions

## Status
Active

## Problem
Phase 4 adds Claude (Anthropic LLM) to the app for two purposes: (1) generating personalized copy on every plugin page, and (2) answering arbitrary natural-language questions about the pool. The challenge is grounding Claude's responses in real data without hallucination. If Claude is given a plain text description of the pool state it may invent statistics; if it is given raw DataFrames or dataclass objects it cannot serialize them.

## Decision
Expose `core/` functions as **Anthropic tool-use schemas** via a new `core/ai/` package. Claude receives a list of tool schemas and calls them during inference. Each tool call is executed by a thin Python adapter that calls an existing `core/` function and returns compact JSON. Claude builds answers only from the data returned by tool calls.

`core/ai/tools.py` defines:
- `TOOLS` — list of Anthropic-compatible `{"name", "description", "input_schema"}` dicts
- `ADAPTERS` — dict mapping tool name → adapter function `(ctx: AnalysisContext, **kwargs) -> dict`
- `execute_tool(name, input_args, ctx)` — dispatcher; returns JSON string; catches exceptions

All adapter inputs are strings/ints (Claude cannot pass Python objects). All outputs are JSON-serializable primitives (no DataFrames, no dataclasses).

## Why not alternatives

**Give Claude a text summary of the pool**: Cheap but Claude can only answer questions covered by the summary. Arbitrary what-ifs and novel queries are impossible.

**Let Claude write/execute Python**: Too risky (arbitrary code execution) and too hard to audit. The tool-use API is structured and auditable by design.

**One mega-tool returning everything**: Wastes tokens on irrelevant data and defeats the purpose of letting Claude reason about which data it needs.

**Text-to-SQL/pandas query**: Requires a safe query sandbox and makes it hard to guarantee Claude only accesses permitted data. Tool schemas are the natural contract layer.

## Consequences
- `core/ai/` is a new sub-package of `core/`. It imports from `core/` but not from `analyses/` or `app.py`, maintaining the no-Streamlit constraint (ADR 001).
- Every factual claim Claude makes in a response traces to a named tool call, making the evidence packet auditable.
- Adding a new data source to the app requires adding a corresponding tool adapter — the tool list is the API surface Claude sees.
- Tool adapters must never raise unhandled exceptions; `execute_tool()` catches and wraps all errors in `{"error": ...}` JSON so Claude can degrade gracefully.
- 16 tools cover the initial surface: pool state, leaderboard, round results, per-player stats, bracket picks, scenarios/what-ifs, team info, pick popularity, odds. Additional tools added in later PRs as needed.

## Source
Phase 4 architecture plan (brainstorm session, April 2026). Implemented in PR #70.
