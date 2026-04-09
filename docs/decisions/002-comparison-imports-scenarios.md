# 002 — comparison imports from scenarios, not the reverse

## Status
Active

## Problem
`core/comparison.py` needs to run scenario simulations (e.g., to compute win probability deltas for counterfactual analysis). `core/scenarios.py` contains the simulation engine. If scenarios imported from comparison, there would be a circular dependency that Python cannot resolve.

## Decision
`core/comparison.py` may import from `core/scenarios.py`. `core/scenarios.py` must never import from `core/comparison.py`. The dependency flows one way: comparison → scenarios.

## Consequences
- New comparison utilities (counterfactual analysis, head-to-head diffs, swap finders) live in `core/comparison.py` and freely call `run_scenarios()` or `monte_carlo()`.
- New scenario engine features live in `core/scenarios.py` without any knowledge of comparison logic.
- If a new module needs both scenario output and comparison logic, it should import from both directly rather than routing through either.

## Source
Established in PR #24 (counterfactual entry builder). Cited explicitly in the PR Decisions section to prevent a circular import introduced during that implementation.
