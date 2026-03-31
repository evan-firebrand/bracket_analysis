#!/usr/bin/env python3
"""Verify game scores by computing team point tallies.

Cross-checks data/results.json scores by:
1. Summing each team's total points across all tournament games
2. Listing per-game scores for manual spot-checking
3. Flagging statistical anomalies (unusual margins, point totals)

Usage:
    python scripts/verify_points.py
    python scripts/verify_points.py --team duke
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main():
    data_dir = Path(__file__).parent.parent / "data"
    results_path = data_dir / "results.json"

    if not results_path.exists():
        print("ERROR: data/results.json not found")
        sys.exit(1)

    results = json.loads(results_path.read_text())["results"]

    # Build per-team stats
    team_stats: dict[str, dict] = {}

    for slot_id, game in results.items():
        score = game.get("score")
        if not score:
            continue

        parts = score.split("-")
        if len(parts) != 2:
            continue

        w_pts, l_pts = int(parts[0]), int(parts[1])
        winner, loser = game["winner"], game["loser"]
        margin = w_pts - l_pts

        for team, pts, opp_pts, opp, won in [
            (winner, w_pts, l_pts, loser, True),
            (loser, l_pts, w_pts, winner, False),
        ]:
            if team not in team_stats:
                team_stats[team] = {
                    "games": [],
                    "total_pts": 0,
                    "total_opp_pts": 0,
                    "wins": 0,
                    "losses": 0,
                }
            team_stats[team]["games"].append(
                {
                    "slot_id": slot_id,
                    "pts": pts,
                    "opp_pts": opp_pts,
                    "opponent": opp,
                    "won": won,
                    "margin": margin if won else -margin,
                }
            )
            team_stats[team]["total_pts"] += pts
            team_stats[team]["total_opp_pts"] += opp_pts
            if won:
                team_stats[team]["wins"] += 1
            else:
                team_stats[team]["losses"] += 1

    # Filter to specific team if requested
    filter_team = None
    if len(sys.argv) > 2 and sys.argv[1] == "--team":
        filter_team = sys.argv[2]

    # Print report
    if filter_team:
        teams_to_show = [filter_team] if filter_team in team_stats else []
        if not teams_to_show:
            print(f"Team '{filter_team}' not found in results")
            sys.exit(1)
    else:
        # Sort by games played (desc), then total points
        teams_to_show = sorted(
            team_stats.keys(),
            key=lambda t: (-len(team_stats[t]["games"]), -team_stats[t]["total_pts"]),
        )

    print("=" * 70)
    print("TEAM POINT TALLIES — Cross-reference against ESPN/NCAA stats")
    print("=" * 70)

    for team in teams_to_show:
        stats = team_stats[team]
        num_games = len(stats["games"])
        avg = stats["total_pts"] / num_games if num_games > 0 else 0
        record = f"{stats['wins']}-{stats['losses']}"

        print(f"\n{team} ({record}) — {stats['total_pts']} total pts, {avg:.1f} avg")
        for g in stats["games"]:
            result = "W" if g["won"] else "L"
            print(
                f"  {g['slot_id']:25s}  {result} {g['pts']:3d}-{g['opp_pts']:3d}  "
                f"vs {g['opponent']:20s}  (margin: {g['margin']:+d})"
            )

    # Flag anomalies
    print("\n" + "=" * 70)
    print("ANOMALY CHECKS")
    print("=" * 70)

    anomalies = 0
    for slot_id, game in results.items():
        score = game.get("score")
        if not score:
            continue
        parts = score.split("-")
        w_pts, l_pts = int(parts[0]), int(parts[1])
        total = w_pts + l_pts
        margin = w_pts - l_pts

        # Flag unusual margins (>40 points)
        if margin > 40:
            print(f"  Large margin: {slot_id} — {game['winner']} beat {game['loser']} by {margin} ({score})")
            anomalies += 1

        # Flag very high totals (>190)
        if total > 190:
            print(f"  High total: {slot_id} — {total} combined points ({score})")
            anomalies += 1

        # Flag very low totals (<100)
        if total < 100:
            print(f"  Low total: {slot_id} — {total} combined points ({score})")
            anomalies += 1

    if anomalies == 0:
        print("  No anomalies detected")

    # Summary for web verification
    print("\n" + "=" * 70)
    print("FINAL FOUR TEAMS — Verify these totals against ESPN")
    print("=" * 70)

    ff_teams = ["uconn", "illinois", "michigan", "arizona"]
    for team in ff_teams:
        if team in team_stats:
            stats = team_stats[team]
            num_games = len(stats["games"])
            avg = stats["total_pts"] / num_games if num_games > 0 else 0
            print(f"  {team:15s}  {stats['total_pts']:4d} pts  {num_games} games  avg {avg:.1f}")


if __name__ == "__main__":
    main()
