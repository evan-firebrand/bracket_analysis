#!/usr/bin/env python3
"""Run scenario analysis from the command line.

Simulates all possible tournament outcomes and reports:
- Win probabilities for each player
- Critical games (which upcoming matchups swing things the most)
- Finish position distributions
- Eliminated players
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.context import AnalysisContext
from core.narrative import describe_probability
from core.scenarios import run_scenarios
from core.scoring import ROUND_NAMES


def main():
    parser = argparse.ArgumentParser(description="Run NCAA bracket scenario analysis")
    parser.add_argument(
        "--data-dir", default="data", help="Path to data directory (default: data)"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results as JSON"
    )
    parser.add_argument(
        "--top-games", type=int, default=5, help="Number of critical games to show (default: 5)"
    )
    args = parser.parse_args()

    ctx = AnalysisContext(data_dir=args.data_dir)

    if not ctx.entries:
        print("No entries loaded.")
        return 1

    remaining = ctx.games_remaining()
    if remaining == 0:
        print("Tournament is complete! No scenarios to analyze.")
        return 0

    print(f"Running scenario analysis ({remaining} games remaining)...")
    sr = run_scenarios(ctx.entries, ctx.tournament, ctx.results)

    if args.json:
        _output_json(ctx, sr)
    else:
        _output_text(ctx, sr, args.top_games)

    return 0


def _output_json(ctx, sr):
    """Output results as JSON."""
    total = sr.total_scenarios
    output = {
        "engine": sr.engine,
        "total_scenarios": total,
        "games_remaining": ctx.games_remaining(),
        "win_probabilities": {},
        "eliminated": [],
        "critical_games": [],
        "finish_distributions": {},
    }

    for entry in ctx.entries:
        name = entry.player_name
        wins = sr.win_counts.get(name, 0)
        pct = wins / total if total > 0 else 0
        scored = ctx.get_scored(name)
        output["win_probabilities"][name] = {
            "win_pct": round(pct, 4),
            "scenarios_won": wins,
            "current_points": scored.total_points if scored else 0,
        }
        if sr.is_eliminated.get(name):
            output["eliminated"].append(name)

    for cg in sr.critical_games:
        game = {
            "slot_id": cg.slot_id,
            "team_a": cg.team_a,
            "team_b": cg.team_b,
            "max_swing": round(cg.max_swing, 4),
            "swings": {
                name: {"if_a_wins": round(a, 4), "if_b_wins": round(b, 4)}
                for name, (a, b) in cg.swings.items()
            },
        }
        output["critical_games"].append(game)

    for name, dist in sr.finish_distributions.items():
        output["finish_distributions"][name] = {
            str(pos): count for pos, count in sorted(dist.items())
        }

    print(json.dumps(output, indent=2))


def _output_text(ctx, sr, top_games):
    """Output results as formatted text."""
    total = sr.total_scenarios
    engine_label = "exact" if sr.engine == "brute_force" else "simulated"

    print(f"\n{'='*60}")
    print(f"  SCENARIO ANALYSIS RESULTS")
    print(f"  {total:,} {engine_label} scenarios | {ctx.games_remaining()} games remaining")
    print(f"  Engine: {sr.engine}")
    print(f"{'='*60}\n")

    # Win probabilities
    print("WIN PROBABILITIES")
    print("-" * 60)

    rows = []
    for entry in ctx.entries:
        name = entry.player_name
        wins = sr.win_counts.get(name, 0)
        pct = wins / total if total > 0 else 0
        scored = ctx.get_scored(name)
        rows.append((name, pct, wins, scored.total_points if scored else 0))

    rows.sort(key=lambda r: -r[1])

    print(f"{'Player':<20} {'Win %':>8} {'Scenarios':>12} {'Cur Pts':>8}")
    print(f"{'─'*20} {'─'*8} {'─'*12} {'─'*8}")

    for name, pct, wins, pts in rows:
        pct_str = "0%" if pct == 0 else f"{pct:.1%}"
        elim = " *" if sr.is_eliminated.get(name) else ""
        print(f"{name:<20} {pct_str:>8} {wins:>12,} {pts:>8}{elim}")

    # Narrative for leader
    if rows and rows[0][1] > 0:
        leader_name, leader_pct = rows[0][0], rows[0][1]
        print(f"\n  {leader_name} is the favorite — {describe_probability(leader_pct)}.")

    # Eliminated
    eliminated = [name for name, elim in sr.is_eliminated.items() if elim]
    if eliminated:
        print(f"\n  * Eliminated: {', '.join(eliminated)}")

    # Critical games
    if sr.critical_games:
        print(f"\n\nCRITICAL GAMES (top {top_games})")
        print("-" * 60)
        print("Games that swing win probabilities the most:\n")

        for cg in sr.critical_games[:top_games]:
            team_a_name = ctx.team_name(cg.team_a)
            team_b_name = ctx.team_name(cg.team_b)
            slot = ctx.tournament.slots.get(cg.slot_id)
            round_name = ROUND_NAMES.get(slot.round, "") if slot else ""

            print(f"  {team_a_name} vs {team_b_name} ({round_name}) — max swing: {cg.max_swing:.0%}")

            # Show top swings
            sorted_swings = sorted(
                cg.swings.items(), key=lambda x: -abs(x[1][0] - x[1][1])
            )
            for name, (pct_a, pct_b) in sorted_swings:
                swing = abs(pct_a - pct_b)
                if swing < 0.001:
                    continue
                print(
                    f"    {name:<18} "
                    f"if {team_a_name[:10]}: {pct_a:>6.1%}  "
                    f"if {team_b_name[:10]}: {pct_b:>6.1%}  "
                    f"swing: {swing:.1%}"
                )
            print()

    # Finish distributions summary
    print("\nFINISH POSITION SUMMARY")
    print("-" * 60)
    n_players = len(ctx.entries)
    print(f"{'Player':<20} {'1st':>6} {'Top 3':>6} {'Last':>6}")
    print(f"{'─'*20} {'─'*6} {'─'*6} {'─'*6}")

    for name, pct, wins, pts in rows:
        dist = sr.finish_distributions.get(name, {})
        top3 = sum(dist.get(p, 0) for p in [1, 2, 3]) / total if total > 0 else 0
        last = dist.get(n_players, 0) / total if total > 0 else 0
        win_str = "0%" if pct == 0 else f"{pct:.1%}"
        top3_str = "0%" if top3 == 0 else f"{top3:.1%}"
        last_str = "0%" if last == 0 else f"{last:.1%}"
        print(f"{name:<20} {win_str:>6} {top3_str:>6} {last_str:>6}")

    print()


if __name__ == "__main__":
    sys.exit(main() or 0)
