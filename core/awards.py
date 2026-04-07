"""Bracket superlatives — one award per player, based on their actual picks.

Each award is computed from real bracket data (picks, results, chalk scores,
agreement matrix). The winner is always the player who best fits that category,
and the blurb references their specific teams and games.

Usage::

    from core.awards import compute_awards
    awards = compute_awards(entries, tournament, results, scored_entries)
    for award in awards:
        print(f"{award.emoji} {award.name} — {award.winner}: {award.blurb}")
"""

from __future__ import annotations

from dataclasses import dataclass

from core.comparison import (
    agreement_matrix as compute_agreement_matrix,
)
from core.comparison import (
    chalk_score as compute_chalk_score,
)
from core.models import PlayerEntry, Results, ScoredEntry, TournamentStructure
from core.scoring import POINTS_PER_ROUND, ROUND_NAMES


@dataclass
class Award:
    name: str
    emoji: str
    winner: str  # player_name
    blurb: str   # flavor text referencing their actual picks


def _team(tournament: TournamentStructure, slug: str) -> str:
    """Return display name for a team slug."""
    t = tournament.teams.get(slug)
    return t.name if t else slug


def _avg_agreement(
    player_name: str,
    entries: list[PlayerEntry],
    matrix: dict[tuple[str, str], int],
) -> float:
    others = [e for e in entries if e.player_name != player_name]
    if not others:
        return 0.0
    return sum(matrix.get((player_name, o.player_name), 0) for o in others) / len(others)


def compute_awards(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
    scored: dict[str, ScoredEntry],
) -> list[Award]:
    """Compute bracket superlatives from actual player picks and results.

    Returns one Award per superlative. Awards that require completed games
    are skipped gracefully if no results exist yet.
    """
    if not entries:
        return []

    awards: list[Award] = []

    # Pre-compute shared data once
    chalk_scores = compute_chalk_score(entries, tournament)
    matrix = compute_agreement_matrix(entries, tournament)
    r1_slots = tournament.get_round_slots(1)
    r1_slot_ids = {s.slot_id for s in r1_slots}
    n_r1 = len(r1_slots)
    alive = set(tournament.teams.keys()) - {r.loser for r in results.results.values()}

    # ------------------------------------------------------------------ #
    # 1. The Oracle — most total correct picks                            #
    # ------------------------------------------------------------------ #
    oracle = max(entries, key=lambda e: len(scored[e.player_name].correct_picks))
    n_correct = len(scored[oracle.player_name].correct_picks)
    if n_correct > 0:
        best_slot = max(
            scored[oracle.player_name].correct_picks,
            key=lambda sid: tournament.slots[sid].round,
        )
        best_team = _team(tournament, oracle.picks[best_slot])
        best_rnd = ROUND_NAMES[tournament.slots[best_slot].round]
        blurb = (
            f"Got {n_correct} games right — including calling {best_team} "
            f"to win the {best_rnd}."
        )
    else:
        blurb = "No results yet, but stay tuned."
    awards.append(Award("The Oracle", "🔮", oracle.player_name, blurb))

    # ------------------------------------------------------------------ #
    # 2. Chalk It Up — highest chalk score (most favorites picked in R1)  #
    # ------------------------------------------------------------------ #
    chalk_winner = max(entries, key=lambda e: chalk_scores.get(e.player_name, 0.0))
    cs = chalk_scores.get(chalk_winner.player_name, 0.0)
    n_chalk = round(cs * n_r1)
    blurb = (
        f"Picked the favorite in {n_chalk}/{n_r1} first-round games. "
        f"Seeds exist for a reason."
    )
    awards.append(Award("Chalk It Up", "📋", chalk_winner.player_name, blurb))

    # ------------------------------------------------------------------ #
    # 3. The Contrarian — lowest chalk score (most upsets picked in R1)  #
    # ------------------------------------------------------------------ #
    contrarian = min(entries, key=lambda e: chalk_scores.get(e.player_name, 1.0))
    cs = chalk_scores.get(contrarian.player_name, 0.0)
    n_upset_picks = n_r1 - round(cs * n_r1)
    blurb = (
        f"Picked {n_upset_picks}/{n_r1} first-round upsets. "
        f"The chaos was the whole strategy."
    )
    awards.append(Award("The Contrarian", "🎲", contrarian.player_name, blurb))

    # ------------------------------------------------------------------ #
    # 4. Upset Whisperer — most R1 upsets correctly called               #
    # ------------------------------------------------------------------ #
    # Identify which R1 upsets actually happened (underdog won)
    actual_upsets: list[tuple[str, str, str]] = []  # (slot_id, underdog, favorite)
    for slot in r1_slots:
        if not results.is_complete(slot.slot_id):
            continue
        if not slot.top_team or not slot.bottom_team:
            continue
        top_seed = tournament.teams[slot.top_team].seed
        bot_seed = tournament.teams[slot.bottom_team].seed
        underdog = slot.bottom_team if top_seed < bot_seed else slot.top_team
        favorite = slot.top_team if top_seed < bot_seed else slot.bottom_team
        if results.winner_of(slot.slot_id) == underdog:
            actual_upsets.append((slot.slot_id, underdog, favorite))

    upset_hits: dict[str, list[tuple[str, str]]] = {e.player_name: [] for e in entries}
    for slot_id, underdog, favorite in actual_upsets:
        for entry in entries:
            if entry.picks.get(slot_id) == underdog:
                upset_hits[entry.player_name].append((underdog, favorite))

    whisper = max(entries, key=lambda e: len(upset_hits[e.player_name]))
    hits = upset_hits[whisper.player_name]
    if hits:
        example_u, example_f = hits[0]
        blurb = (
            f"Called {len(hits)} first-round upset(s), including "
            f"{_team(tournament, example_u)} over {_team(tournament, example_f)}."
        )
    else:
        blurb = "No upsets to call yet — check back after Round 1 wraps."
    awards.append(Award("Upset Whisperer", "🤫", whisper.player_name, blurb))

    # ------------------------------------------------------------------ #
    # 5. Safe Bet — highest average agreement with the group             #
    # ------------------------------------------------------------------ #
    safe = max(entries, key=lambda e: _avg_agreement(e.player_name, entries, matrix))
    avg = _avg_agreement(safe.player_name, entries, matrix)
    blurb = (
        f"Agreed with the group on {avg:.0f}/{len(tournament.slot_order)} "
        f"picks on average. Voted with the room."
    )
    awards.append(Award("Safe Bet", "🤝", safe.player_name, blurb))

    # ------------------------------------------------------------------ #
    # 6. Lone Wolf — lowest average agreement with the group             #
    # ------------------------------------------------------------------ #
    wolf = min(entries, key=lambda e: _avg_agreement(e.player_name, entries, matrix))
    avg = _avg_agreement(wolf.player_name, entries, matrix)
    blurb = (
        f"Only agreed with the group on {avg:.0f}/{len(tournament.slot_order)} "
        f"picks on average. Their own bracket, their own rules."
    )
    awards.append(Award("Lone Wolf", "🐺", wolf.player_name, blurb))

    # ------------------------------------------------------------------ #
    # 7. All-In — most alive pending points on their championship pick   #
    # ------------------------------------------------------------------ #
    all_in_pts: dict[str, int] = {}
    all_in_team: dict[str, str] = {}
    for entry in entries:
        champion = entry.picks.get("championship")
        if not champion or champion not in alive:
            all_in_pts[entry.player_name] = 0
            continue
        pending = sum(
            POINTS_PER_ROUND.get(tournament.slots[sid].round, 0)
            for sid in tournament.slot_order
            if not results.is_complete(sid) and entry.picks.get(sid) == champion
        )
        all_in_pts[entry.player_name] = pending
        all_in_team[entry.player_name] = champion

    allin = max(entries, key=lambda e: all_in_pts.get(e.player_name, 0))
    pts = all_in_pts.get(allin.player_name, 0)
    team_slug = all_in_team.get(allin.player_name, "")
    team_display = _team(tournament, team_slug) if team_slug else "their pick"
    blurb = (
        f"Has {pts} points riding on {team_display}. "
        f"Riding or dying with one team."
    )
    awards.append(Award("All-In", "🎰", allin.player_name, blurb))

    # ------------------------------------------------------------------ #
    # 8. The Optimist — highest max possible score remaining             #
    # ------------------------------------------------------------------ #
    optimist = max(entries, key=lambda e: scored[e.player_name].max_possible)
    mp = scored[optimist.player_name].max_possible
    current = scored[optimist.player_name].total_points
    blurb = (
        f"Sitting at {current} points but still has a max possible of {mp}. "
        f"The tournament isn't over."
    )
    awards.append(Award("The Optimist", "🌈", optimist.player_name, blurb))

    # ------------------------------------------------------------------ #
    # 9. Heartbreak Hotel — championship pick eliminated the earliest    #
    # ------------------------------------------------------------------ #
    champ_exit: dict[str, int] = {}
    for entry in entries:
        champion = entry.picks.get("championship")
        if not champion:
            continue
        for slot_id, result in results.results.items():
            if result.loser == champion:
                champ_exit[entry.player_name] = tournament.slots[slot_id].round
                break

    if champ_exit:
        heartbreak_name = min(champ_exit, key=champ_exit.get)
        exit_round = champ_exit[heartbreak_name]
        entry = next(e for e in entries if e.player_name == heartbreak_name)
        champ_display = _team(tournament, entry.picks.get("championship", ""))
        rnd_display = ROUND_NAMES.get(exit_round, f"Round {exit_round}")
        blurb = (
            f"Picked {champ_display} to win it all — "
            f"they went out in the {rnd_display}."
        )
        awards.append(Award("Heartbreak Hotel", "💔", heartbreak_name, blurb))

    # ------------------------------------------------------------------ #
    # 10. Crystal Ball — best Round 1 pick accuracy                      #
    # ------------------------------------------------------------------ #
    r1_completed = sum(1 for sid in r1_slot_ids if results.is_complete(sid))
    if r1_completed > 0:
        r1_correct: dict[str, int] = {
            e.player_name: sum(
                1 for sid in scored[e.player_name].correct_picks
                if sid in r1_slot_ids
            )
            for e in entries
        }
        crystal = max(r1_correct, key=r1_correct.get)
        n_right = r1_correct[crystal]
        blurb = (
            f"Got {n_right}/{r1_completed} completed Round of 64 games right. "
            f"Read the bracket perfectly."
        )
        awards.append(Award("Crystal Ball", "🔭", crystal, blurb))

    return awards
