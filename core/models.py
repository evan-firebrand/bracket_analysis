"""Data models for NCAA bracket analysis."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Team:
    slug: str
    name: str
    seed: int
    region: str


@dataclass
class GameSlot:
    slot_id: str
    round: int
    region: str  # "East", "West", etc. or "Final Four" for late rounds
    position: int
    feeds_into: str | None  # slot_id of the next round game, None for championship
    top_team: str | None  # team slug (filled for R1, None for later rounds)
    bottom_team: str | None


@dataclass
class TournamentStructure:
    year: int
    teams: dict[str, Team]  # slug -> Team
    slots: dict[str, GameSlot]  # slot_id -> GameSlot
    slot_order: list[str]  # slot_ids in round/position order

    def get_feeder_slots(self, slot_id: str) -> list[str]:
        """Get the two slots that feed into this slot."""
        return [
            sid for sid, slot in self.slots.items()
            if slot.feeds_into == slot_id
        ]

    def get_round_slots(self, round_num: int) -> list[GameSlot]:
        """Get all slots for a given round."""
        return [s for s in self.slots.values() if s.round == round_num]

    def total_rounds(self) -> int:
        return max(s.round for s in self.slots.values())


@dataclass
class GameResult:
    winner: str  # team slug
    loser: str  # team slug
    score: str | None = None  # e.g. "85-62", optional display metadata


@dataclass
class Results:
    last_updated: str
    results: dict[str, GameResult]  # slot_id -> GameResult

    def is_complete(self, slot_id: str) -> bool:
        return slot_id in self.results

    def winner_of(self, slot_id: str) -> str | None:
        r = self.results.get(slot_id)
        return r.winner if r else None

    def completed_count(self) -> int:
        return len(self.results)


@dataclass
class PlayerEntry:
    player_name: str
    entry_name: str
    picks: dict[str, str]  # slot_id -> team slug


@dataclass
class ScoredEntry:
    player_name: str
    entry_name: str
    total_points: int
    points_by_round: dict[int, int]  # round -> points earned
    correct_picks: list[str]  # slot_ids picked correctly
    incorrect_picks: list[str]  # slot_ids picked incorrectly (game played, wrong pick)
    pending_picks: list[str]  # slot_ids not yet played
    max_possible: int  # current points + points from still-alive pending picks


@dataclass
class ScenarioResults:
    """Unified output from both brute-force and Monte Carlo engines."""
    engine: str  # "brute_force" or "monte_carlo"
    total_scenarios: int
    win_counts: dict[str, int]  # player_name -> number of scenarios where they win
    finish_distributions: dict[str, dict[int, int]]  # player_name -> {position: count}
    critical_games: list[CriticalGame] = field(default_factory=list)
    is_eliminated: dict[str, bool] = field(default_factory=dict)


@dataclass
class CriticalGame:
    slot_id: str
    team_a: str
    team_b: str
    swings: dict[str, tuple[float, float]]  # player_name -> (win% if A wins, win% if B wins)
