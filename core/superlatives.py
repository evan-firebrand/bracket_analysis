"""Superlatives — end-of-tournament awards for each player.

Pure business logic. No Streamlit imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.comparison import chalk_score, contrarian_picks, pick_popularity
from core.models import PlayerEntry, Results, TournamentStructure
from core.recap import standings_diff
from core.scoring import POINTS_PER_ROUND, score_entry


@dataclass
class Superlative:
    title: str
    icon: str
    winner: str           # player_name (comma-separated if tied)
    value: str            # formatted stat, e.g. "990 points"
    description: str      # full sentence shown under the award
    runner_up: str | None = None
    runner_up_value: str | None = None
    is_tie: bool = False


def compute_superlatives(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> list[Superlative]:
    """Compute all superlatives. Returns one Superlative per award.

    Crystal Ball is omitted if the championship has not been played yet.
    """
    awards: list[Superlative] = []

    awards.append(_pool_champion(entries, tournament, results))
    awards.append(_most_accurate(entries, tournament, results))
    awards.append(_sharpest_round_one(entries, tournament, results))
    awards.append(_sweet_sixteen_savant(entries, tournament, results))
    awards.append(_final_four_prophet(entries, tournament, results))

    crystal = _crystal_ball(entries, tournament, results)
    if crystal is not None:
        awards.append(crystal)

    chalks = chalk_score(entries, tournament)
    awards.append(_mr_chalk(entries, chalks))
    awards.append(_chaos_agent(entries, chalks))
    awards.append(_contrarian_king(entries, tournament, results))
    awards.append(_biggest_bust(entries, tournament, results))
    awards.append(_most_heartbreaks(entries, tournament, results))
    awards.append(_hot_finisher(entries, tournament, results))

    return awards


# ---------------------------------------------------------------------------
# Individual award helpers
# ---------------------------------------------------------------------------


def _pick_winner(
    scores: dict[str, float | int],
) -> tuple[str, str | None, bool, float | int | None]:
    """Return (winner_str, runner_up | None, is_tie, runner_up_val | None).

    Higher score = better. Ties produce a comma-joined winner string.
    """
    if not scores:
        return ("(none)", None, False, None)
    sorted_players = sorted(scores.items(), key=lambda x: -x[1])
    best_val = sorted_players[0][1]
    winners = [n for n, v in sorted_players if v == best_val]
    runner_ups = [(n, v) for n, v in sorted_players if v != best_val]
    runner_up = runner_ups[0][0] if runner_ups else None
    runner_up_val: float | int | None = runner_ups[0][1] if runner_ups else None
    is_tie = len(winners) > 1
    winner_str = ", ".join(winners)
    return winner_str, runner_up, is_tie, runner_up_val


def _pool_champion(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative:
    scores = {e.player_name: score_entry(e, tournament, results).total_points for e in entries}
    winner, runner_up, is_tie, runner_up_val = _pick_winner(scores)
    best = scores[winner.split(", ")[0]]
    runner_up_value = f"{runner_up_val} pts" if runner_up_val is not None else None
    return Superlative(
        title="Pool Champion",
        icon="🏆",
        winner=winner,
        value=f"{best} points",
        description="Finished with the most points in the pool.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _most_accurate(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative:
    scores: dict[str, float] = {}
    details: dict[str, str] = {}
    for entry in entries:
        se = score_entry(entry, tournament, results)
        played = len(se.correct_picks) + len(se.incorrect_picks)
        pct = len(se.correct_picks) / played if played > 0 else 0.0
        scores[entry.player_name] = pct
        details[entry.player_name] = f"{len(se.correct_picks)}/{played}"

    winner, runner_up, is_tie, runner_up_val = _pick_winner(scores)
    winner_name = winner.split(", ")[0]
    best_pct = scores[winner_name]
    runner_up_value = (
        f"{runner_up_val:.1%} ({details[runner_up]})" if runner_up and runner_up_val is not None else None
    )
    return Superlative(
        title="Most Accurate",
        icon="🎯",
        winner=winner,
        value=f"{best_pct:.1%} ({details[winner_name]} games)",
        description="Picked the highest percentage of games correctly.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _sharpest_round_one(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative:
    scores: dict[str, int] = {}
    r1_correct: dict[str, int] = {}
    for entry in entries:
        se = score_entry(entry, tournament, results)
        pts = se.points_by_round.get(1, 0)
        scores[entry.player_name] = pts
        correct = sum(
            1 for sid in se.correct_picks
            if tournament.slots.get(sid) and tournament.slots[sid].round == 1
        )
        r1_correct[entry.player_name] = correct

    winner, runner_up, is_tie, runner_up_val = _pick_winner(scores)
    winner_name = winner.split(", ")[0]
    total_r1 = len(tournament.get_round_slots(1))
    correct = r1_correct[winner_name]
    runner_up_value = (
        f"{runner_up_val} pts ({r1_correct[runner_up]}/{total_r1})"
        if runner_up and runner_up_val is not None else None
    )
    return Superlative(
        title="Sharpest in Round 1",
        icon="🔍",
        winner=winner,
        value=f"{scores[winner_name]} pts ({correct}/{total_r1} correct)",
        description="Earned the most points in the Round of 64.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _sweet_sixteen_savant(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative:
    scores: dict[str, int] = {}
    s16_correct: dict[str, int] = {}
    for entry in entries:
        se = score_entry(entry, tournament, results)
        pts = se.points_by_round.get(3, 0)
        scores[entry.player_name] = pts
        correct = sum(
            1 for sid in se.correct_picks
            if tournament.slots.get(sid) and tournament.slots[sid].round == 3
        )
        s16_correct[entry.player_name] = correct

    winner, runner_up, is_tie, runner_up_val = _pick_winner(scores)
    winner_name = winner.split(", ")[0]
    total_s16 = len(tournament.get_round_slots(3))
    correct = s16_correct[winner_name]
    runner_up_value = (
        f"{runner_up_val} pts ({s16_correct[runner_up]}/{total_s16})"
        if runner_up and runner_up_val is not None else None
    )
    return Superlative(
        title="Sweet Sixteen Savant",
        icon="🔮",
        winner=winner,
        value=f"{scores[winner_name]} pts ({correct}/{total_s16} correct)",
        description="Earned the most points in the Sweet 16.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _final_four_prophet(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative:
    """Award to player(s) with the most correct Final Four game picks."""
    ff_slots = [sid for sid, s in tournament.slots.items() if s.round == 5]
    completed_ff = [sid for sid in ff_slots if results.is_complete(sid)]

    scores: dict[str, int] = {}
    for entry in entries:
        correct = sum(
            1 for sid in completed_ff
            if entry.picks.get(sid) == results.winner_of(sid)
        )
        scores[entry.player_name] = correct

    winner, runner_up, is_tie, runner_up_val = _pick_winner(scores)
    winner_name = winner.split(", ")[0]
    best = scores[winner_name]
    total = len(completed_ff)
    runner_up_value = (
        f"{runner_up_val}/{total} correct" if runner_up and runner_up_val is not None else None
    )
    return Superlative(
        title="Final Four Prophet",
        icon="🔭",
        winner=winner,
        value=f"{best}/{total} Final Four games correct",
        description="Predicted the most Final Four game outcomes correctly.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _crystal_ball(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative | None:
    """Award to player(s) who picked the national champion. None if not yet played."""
    champion = results.winner_of("championship")
    if champion is None:
        return None

    team = tournament.teams.get(champion)
    team_name = team.name if team else champion

    winners = [
        e.player_name for e in entries
        if e.picks.get("championship") == champion
    ]
    if not winners:
        return Superlative(
            title="Crystal Ball",
            icon="🔮",
            winner="Nobody",
            value="No one picked it",
            description=f"Nobody predicted {team_name} would win the championship.",
            is_tie=False,
        )

    is_tie = len(winners) > 1
    winner_str = ", ".join(winners)
    return Superlative(
        title="Crystal Ball",
        icon="🔮",
        winner=winner_str,
        value=f"Picked {team_name} to win it all",
        description=f"Correctly predicted {team_name} as the national champion.",
        is_tie=is_tie,
    )


def _mr_chalk(
    entries: list[PlayerEntry],
    chalks: dict[str, float],
) -> Superlative:
    winner, runner_up, is_tie, runner_up_val = _pick_winner(chalks)
    winner_name = winner.split(", ")[0]
    runner_up_value = f"{runner_up_val:.1%}" if runner_up and runner_up_val is not None else None
    return Superlative(
        title="Mr. Chalk",
        icon="📋",
        winner=winner,
        value=f"{chalks[winner_name]:.1%} chalk score",
        description="Played it the safest — picked the most heavily-seeded favorites in Round 1.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _chaos_agent(
    entries: list[PlayerEntry],
    chalks: dict[str, float],
) -> Superlative:
    # Lowest chalk score wins — invert for _pick_winner
    inverted = {name: -score for name, score in chalks.items()}
    winner, runner_up, is_tie, runner_up_val = _pick_winner(inverted)
    winner_name = winner.split(", ")[0]
    runner_up_value = (
        f"{chalks[runner_up]:.1%}" if runner_up and runner_up_val is not None else None
    )
    return Superlative(
        title="Chaos Agent",
        icon="🎲",
        winner=winner,
        value=f"{chalks[winner_name]:.1%} chalk score",
        description="Embraced the madness — picked the most upsets in Round 1.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _contrarian_king(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
    threshold: float = 0.20,
) -> Superlative:
    """Player with the most contrarian picks that turned out to be correct."""
    popularity = pick_popularity(entries, tournament)
    contrarian = contrarian_picks(entries, tournament, results, popularity, threshold)

    scores: dict[str, int] = {}
    for entry in entries:
        correct_count = sum(1 for cp in contrarian.get(entry.player_name, []) if cp.correct is True)
        scores[entry.player_name] = correct_count

    winner, runner_up, is_tie, runner_up_val = _pick_winner(scores)
    winner_name = winner.split(", ")[0]
    best = scores[winner_name]
    runner_up_value = (
        f"{runner_up_val} contrarian hits" if runner_up and runner_up_val is not None else None
    )
    return Superlative(
        title="Contrarian King",
        icon="👑",
        winner=winner,
        value=f"{best} low-consensus pick{'s' if best != 1 else ''} that hit",
        description=(
            f"Made the most correct picks that fewer than {threshold:.0%} of the pool shared."
        ),
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _biggest_bust(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative:
    """Player whose single most expensive incorrect pick cost the most points."""
    max_loss: dict[str, int] = {}
    worst_slot: dict[str, str] = {}
    worst_team: dict[str, str] = {}

    for entry in entries:
        se = score_entry(entry, tournament, results)
        top_loss = 0
        top_sid = ""
        top_team_slug = ""
        for sid in se.incorrect_picks:
            slot = tournament.slots.get(sid)
            if slot is None:
                continue
            pts = POINTS_PER_ROUND.get(slot.round, 0)
            if pts > top_loss:
                top_loss = pts
                top_sid = sid
                top_team_slug = entry.picks.get(sid, "")
        max_loss[entry.player_name] = top_loss
        worst_slot[entry.player_name] = top_sid
        worst_team[entry.player_name] = top_team_slug

    winner, runner_up, is_tie, runner_up_val = _pick_winner(max_loss)
    winner_name = winner.split(", ")[0]
    best_loss = max_loss[winner_name]
    slot = tournament.slots.get(worst_slot.get(winner_name, ""))
    round_name = _round_label(slot.round) if slot else "unknown round"
    picked_team = worst_team.get(winner_name, "")
    team = tournament.teams.get(picked_team)
    team_name = team.name if team else picked_team
    runner_up_value = (
        f"lost {runner_up_val} pts on one pick" if runner_up and runner_up_val is not None else None
    )
    return Superlative(
        title="Biggest Bust",
        icon="💥",
        winner=winner,
        value=f"Lost {best_loss} pts when {team_name} was eliminated ({round_name})",
        description="Had the most points wiped out by a single incorrect pick.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _most_heartbreaks(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative:
    """Player who trusted the most top-3 seeds that lost."""
    scores: dict[str, int] = {}
    for entry in entries:
        se = score_entry(entry, tournament, results)
        count = 0
        for sid in se.incorrect_picks:
            picked = entry.picks.get(sid)
            if not picked:
                continue
            team = tournament.teams.get(picked)
            if team and team.seed <= 3:
                count += 1
        scores[entry.player_name] = count

    winner, runner_up, is_tie, runner_up_val = _pick_winner(scores)
    winner_name = winner.split(", ")[0]
    best = scores[winner_name]
    runner_up_value = (
        f"{runner_up_val} heartbreak{'s' if runner_up_val != 1 else ''}"
        if runner_up and runner_up_val is not None else None
    )
    return Superlative(
        title="Most Heartbreaks",
        icon="💔",
        winner=winner,
        value=f"{best} top-3 seed{'s' if best != 1 else ''} that let them down",
        description="Trusted the most blue-chip favorites that got upset.",
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


def _hot_finisher(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> Superlative:
    """Player whose rank improved the most (worst rank → final rank)."""
    # Determine completed rounds
    completed_rounds: set[int] = set()
    for sid in results.results:
        slot = tournament.slots.get(sid)
        if slot:
            completed_rounds.add(slot.round)

    if not completed_rounds:
        # No games played — everyone ties at 1
        names = [e.player_name for e in entries]
        return Superlative(
            title="Hot Finisher",
            icon="🚀",
            winner=", ".join(names),
            value="No games played yet",
            description="Climbed the most positions from their worst rank to their final rank.",
            is_tie=True,
        )

    # Track rank_after per player per round (including initial rank = n_players for all)
    n = len(entries)
    rank_history: dict[str, list[int]] = {e.player_name: [n] for e in entries}

    for rnd in sorted(completed_rounds):
        diffs = standings_diff(tournament, results, entries, rnd)
        for diff in diffs:
            rank_history[diff.player_name].append(diff.rank_after)

    # final rank = rank_after the last completed round
    final_ranks = {e.player_name: rank_history[e.player_name][-1] for e in entries}
    worst_ranks = {e.player_name: max(rank_history[e.player_name]) for e in entries}
    improvements = {name: worst_ranks[name] - final_ranks[name] for name in worst_ranks}

    winner, runner_up, is_tie, runner_up_val = _pick_winner(improvements)
    winner_name = winner.split(", ")[0]
    best_improvement = improvements[winner_name]
    worst = worst_ranks[winner_name]
    final = final_ranks[winner_name]
    runner_up_value = (
        f"+{runner_up_val} places" if runner_up and runner_up_val is not None and runner_up_val > 0 else None
    )

    if best_improvement <= 0:
        desc = "Maintained their position — no significant rank changes all tournament."
        val = f"Held steady at {_ordinal(final)} place"
    else:
        val = f"Climbed from {_ordinal(worst)} to {_ordinal(final)} (+{best_improvement} places)"
        desc = "Made the biggest rank climb from their worst position to their final standing."

    return Superlative(
        title="Hot Finisher",
        icon="🚀",
        winner=winner,
        value=val,
        description=desc,
        runner_up=runner_up,
        runner_up_value=runner_up_value,
        is_tie=is_tie,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _round_label(round_num: int) -> str:
    labels = {
        1: "Round of 64",
        2: "Round of 32",
        3: "Sweet 16",
        4: "Elite 8",
        5: "Final Four",
        6: "Championship",
    }
    return labels.get(round_num, f"Round {round_num}")


def player_award_summary(
    entries: list[PlayerEntry],
    superlatives: list[Superlative],
) -> dict[str, list[str]]:
    """Return a dict of player_name -> list of award titles they won."""
    summary: dict[str, list[str]] = {e.player_name: [] for e in entries}
    for s in superlatives:
        for name in s.winner.split(", "):
            name = name.strip()
            if name in summary:
                summary[name].append(s.title)
    return summary
