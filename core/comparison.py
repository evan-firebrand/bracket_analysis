"""Comparison logic for bracket analysis.

Pure business logic — no Streamlit imports. Used by H2H and group picks plugins.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from core.models import PlayerEntry, Results, TournamentStructure
from core.scoring import POINTS_PER_ROUND, get_alive_teams


# --- Head to Head ---


@dataclass
class H2HResult:
    player_a: str
    player_b: str
    agree: list[str]  # slot_ids where they picked the same team
    disagree_a_right: list[str]  # slot_ids where A was right, B was wrong
    disagree_b_right: list[str]  # slot_ids where B was right, A was wrong
    disagree_both_wrong: list[str]  # slot_ids where both were wrong
    disagree_pending: list[str]  # slot_ids where they differ and game not played
    pending_points: int  # total points at stake in pending disagreements

    @property
    def total_disagree(self) -> int:
        return (
            len(self.disagree_a_right)
            + len(self.disagree_b_right)
            + len(self.disagree_both_wrong)
            + len(self.disagree_pending)
        )


def head_to_head(
    entry_a: PlayerEntry,
    entry_b: PlayerEntry,
    tournament: TournamentStructure,
    results: Results,
) -> H2HResult:
    """Compare two brackets and categorize every game slot."""
    agree = []
    disagree_a_right = []
    disagree_b_right = []
    disagree_both_wrong = []
    disagree_pending = []

    for slot_id in tournament.slot_order:
        pick_a = entry_a.picks.get(slot_id)
        pick_b = entry_b.picks.get(slot_id)

        if pick_a == pick_b:
            agree.append(slot_id)
        elif results.is_complete(slot_id):
            winner = results.winner_of(slot_id)
            if pick_a == winner:
                disagree_a_right.append(slot_id)
            elif pick_b == winner:
                disagree_b_right.append(slot_id)
            else:
                disagree_both_wrong.append(slot_id)
        else:
            disagree_pending.append(slot_id)

    pending_points = sum(
        POINTS_PER_ROUND.get(tournament.slots[s].round, 0)
        for s in disagree_pending
    )

    return H2HResult(
        player_a=entry_a.player_name,
        player_b=entry_b.player_name,
        agree=agree,
        disagree_a_right=disagree_a_right,
        disagree_b_right=disagree_b_right,
        disagree_both_wrong=disagree_both_wrong,
        disagree_pending=disagree_pending,
        pending_points=pending_points,
    )


# --- Agreement Matrix ---


def agreement_matrix(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
) -> dict[tuple[str, str], int]:
    """Pairwise count of matching picks between all players.

    Returns dict mapping (player_a, player_b) -> agreement count.
    """
    matrix = {}
    for i, a in enumerate(entries):
        for j, b in enumerate(entries):
            if i >= j:
                continue
            count = sum(
                1
                for slot_id in tournament.slot_order
                if a.picks.get(slot_id) == b.picks.get(slot_id)
            )
            matrix[(a.player_name, b.player_name)] = count
            matrix[(b.player_name, a.player_name)] = count
    return matrix


# --- Pick Popularity ---


def pick_popularity(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
) -> dict[str, Counter]:
    """For each slot, count how many players picked each team.

    Returns dict mapping slot_id -> Counter(team_slug -> count).
    """
    popularity: dict[str, Counter] = {}
    for slot_id in tournament.slot_order:
        counter: Counter = Counter()
        for entry in entries:
            pick = entry.picks.get(slot_id)
            if pick:
                counter[pick] += 1
        popularity[slot_id] = counter
    return popularity


# --- Team Exposure ---


def team_exposure(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> dict[str, int]:
    """For each alive team, total points at risk across all players in remaining games.

    "Exposure" = if this team gets eliminated, how many total points
    across all brackets become impossible.
    """
    alive = get_alive_teams(tournament, results)
    completed_slots = set(results.results.keys())
    exposure: dict[str, int] = {}

    for entry in entries:
        for slot_id in tournament.slot_order:
            if slot_id in completed_slots:
                continue
            team = entry.picks.get(slot_id)
            if team and team in alive:
                pts = POINTS_PER_ROUND.get(tournament.slots[slot_id].round, 0)
                exposure[team] = exposure.get(team, 0) + pts

    return exposure


# --- Contrarian Picks ---


@dataclass
class ContrarianPick:
    slot_id: str
    round: int
    team: str
    count: int  # how many players picked this
    total_players: int
    pct: float  # count / total_players
    correct: bool | None  # True/False if resolved, None if pending


def contrarian_picks(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
    popularity: dict[str, Counter],
    threshold: float = 0.20,
) -> dict[str, list[ContrarianPick]]:
    """For each player, find picks that fewer than threshold% of the group shares."""
    n_players = len(entries)
    if n_players == 0:
        return {}

    contrarian: dict[str, list[ContrarianPick]] = {}

    for entry in entries:
        picks_list = []
        for slot_id in tournament.slot_order:
            pick = entry.picks.get(slot_id)
            if not pick:
                continue
            count = popularity[slot_id].get(pick, 0)
            pct = count / n_players
            if pct < threshold:
                slot = tournament.slots[slot_id]
                if results.is_complete(slot_id):
                    correct = results.winner_of(slot_id) == pick
                else:
                    correct = None
                picks_list.append(ContrarianPick(
                    slot_id=slot_id,
                    round=slot.round,
                    team=pick,
                    count=count,
                    total_players=n_players,
                    pct=pct,
                    correct=correct,
                ))
        contrarian[entry.player_name] = picks_list

    return contrarian


# --- Chalk Score ---


def chalk_score(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
) -> dict[str, float]:
    """For each player, calculate how "chalky" their bracket is.

    Chalk score = percentage of Round 1 picks where they chose the higher seed.
    100% = pure chalk (always picked the favorite).
    0% = pure upset (always picked the underdog).

    Returns dict mapping player_name -> chalk percentage (0.0 to 1.0).
    """
    r1_slots = [s for s in tournament.slots.values() if s.round == 1]
    if not r1_slots:
        return {}

    scores: dict[str, float] = {}

    for entry in entries:
        chalk_picks = 0
        total_picks = 0

        for slot in r1_slots:
            pick = entry.picks.get(slot.slot_id)
            if not pick or not slot.top_team or not slot.bottom_team:
                continue

            total_picks += 1
            top_seed = tournament.teams.get(slot.top_team)
            bottom_seed = tournament.teams.get(slot.bottom_team)

            if top_seed and bottom_seed:
                # top_team is higher seed (lower number = better)
                higher_seed_team = (
                    slot.top_team
                    if top_seed.seed <= bottom_seed.seed
                    else slot.bottom_team
                )
                if pick == higher_seed_team:
                    chalk_picks += 1

        scores[entry.player_name] = (
            chalk_picks / total_picks if total_picks > 0 else 0.0
        )

    return scores


def group_chalk_score(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
) -> float:
    """Overall group chalk score — average across all players."""
    individual = chalk_score(entries, tournament)
    if not individual:
        return 0.0
    return sum(individual.values()) / len(individual)
