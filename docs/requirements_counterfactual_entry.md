# Requirements: Counterfactual Entry Builder

## Problem

We frequently need to answer "what if Player X had picked differently?" questions. Today this requires writing throwaway code each time — manually constructing a `PlayerEntry`, swapping picks, rebuilding the entries list, and running scenarios. This is error-prone (easy to forget downstream pick dependencies) and creates duplicated logic across analyses.

Examples of questions this would answer:
- "If Rebecca had picked Arizona instead of Michigan, what's her win probability?" (Q6/Q9 analysis)
- "What if Evan had picked UConn over Duke in the Elite 8 — does he survive?"
- "Show me the single pick change that would most improve scrapr's position"

## User Stories

**US-1: Single pick swap**
As an analyst, I want to change one pick in a player's bracket and see the impact on their win probability, so I can quantify "one pick changes everything" narratives.

Acceptance criteria:
- Specify a player, a slot, and a new team
- Get back a modified entry that can be scored and run through scenarios
- The original entry is not mutated

**US-2: Downstream pick propagation**
As an analyst, I want the system to handle downstream dependencies when I swap a pick, so I don't get invalid brackets.

Acceptance criteria:
- If I swap a Semi 2 pick from Michigan to Arizona, and the player originally picked Michigan as champion, the championship pick should also update to Arizona (since Michigan can no longer reach the final in this hypothetical)
- If I swap a Sweet 16 pick, all downstream slots where the original team was picked should cascade to the new team
- If the player didn't pick the original team downstream, those picks are left unchanged

**US-3: Scenario comparison**
As an analyst, I want to compare win probabilities before and after a pick swap, so I can present a clean "X% → Y%" delta.

Acceptance criteria:
- Run `brute_force_scenarios` (or `monte_carlo_scenarios`) with original entries and with modified entries
- Return both results for comparison
- Handle the edge case where the swap makes the bracket identical to another player's

**US-4: Bulk exploration (stretch)**
As an analyst, I want to test every possible single-pick swap for a player and find the one that maximizes their win probability, so I can identify "the pick that would have changed everything."

Acceptance criteria:
- For each remaining/pending slot, try each possible team, run scenarios, rank by win probability improvement
- Return the top N most impactful swaps
- Must be performant: with 3 remaining games and 2 options each, this is 6 swaps × 8 scenarios = trivial. With 15 remaining games it could be expensive — should respect the brute_force_threshold.

## Proposed Interface

```python
# core/scenarios.py or core/comparison.py

def counterfactual_entry(
    entry: PlayerEntry,
    pick_overrides: dict[str, str],
    propagate: bool = True,
) -> PlayerEntry:
    """Create a modified copy of a player's bracket with pick swaps.
    
    Args:
        entry: The original player entry (not mutated).
        pick_overrides: Map of slot_id -> new team slug.
        propagate: If True, cascade changes to downstream slots
                   where the player originally picked the replaced team.
    
    Returns:
        A new PlayerEntry with modified picks.
    """
```

## Constraints

- Must not mutate the original `PlayerEntry`
- Must work with existing `score_entry()` and `brute_force_scenarios()` without modification
- Propagation logic needs access to `TournamentStructure` to know which slots feed into which (use `get_feeder_slots()`)
- No new dependencies

## Out of Scope

- Modifying game results (already handled by `what_if()` in `core/scenarios.py`)
- Multi-player swaps (changing picks for two players simultaneously)
- UI/plugin integration (this is a core utility — plugins can use it later)

## Priority

Nice-to-have. We've done two analyses (Q6, Q9) using inline throwaway code. A third instance would justify the abstraction. If bracket autopsy or "one pick changes everything" becomes a recurring plugin section, this moves to should-have.

## Testing

- Swap a single pick with no downstream dependency → only that slot changes
- Swap a pick with downstream dependency (e.g., Semi 2 team that was also picked as champion) → champion pick cascades
- Swap a pick where the player didn't pick that team downstream → no cascade
- Verify original entry is unchanged after swap
- Score the counterfactual entry and verify points differ as expected
- Run scenarios with counterfactual entry and verify win probabilities shift
