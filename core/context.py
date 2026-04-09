"""AnalysisContext — shared data object passed to all plugins."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from core.loader import load_entries, load_results, load_tournament
from core.models import (
    PlayerEntry,
    Results,
    ScenarioResults,
    ScoredEntry,
    TournamentStructure,
)
from core.scoring import (
    ROUND_NAMES,
    build_leaderboard,
    get_alive_teams,
    score_entry,
)


class AnalysisContext:
    """Central data object that all analysis plugins receive.

    Loads all data files, pre-computes leaderboard, and provides helper methods
    so plugins don't need to re-derive common information.
    """

    def __init__(self, data_dir: str | Path = "data", view_as_of_round: int | None = None):
        data_dir = Path(data_dir)

        # Load raw data
        self.tournament: TournamentStructure = load_tournament(
            data_dir / "tournament.json"
        )
        raw_results = load_results(data_dir / "results.json")

        # Optionally filter results to a historical round snapshot
        if view_as_of_round is not None:
            filtered = {
                slot_id: result
                for slot_id, result in raw_results.results.items()
                if (slot := self.tournament.slots.get(slot_id)) and slot.round <= view_as_of_round
            }
            self.results = Results(last_updated=raw_results.last_updated, results=filtered)
        else:
            self.results = raw_results

        self.view_round: int | None = view_as_of_round  # None = live/current
        self.entries: list[PlayerEntry] = load_entries(
            data_dir / "entries" / "player_brackets.json"
        )

        # Pre-compute
        self.leaderboard: pd.DataFrame = build_leaderboard(
            self.entries, self.tournament, self.results
        )
        self.scored_entries: dict[str, ScoredEntry] = {
            entry.player_name: score_entry(entry, self.tournament, self.results)
            for entry in self.entries
        }
        self.alive_teams: set[str] = get_alive_teams(
            self.tournament, self.results
        )

        # Scenario results (populated later by scenario engine)
        self.scenarios: ScenarioResults | None = None

        # AI content (loaded if available)
        self.ai_content: dict | None = self._load_ai_content(data_dir)

    def _load_ai_content(self, data_dir: Path) -> dict | None:
        """Load approved AI-generated content if available."""
        path = data_dir / "content" / "approved.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None

    # --- Helper methods for plugins ---

    def team_name(self, slug: str) -> str:
        """Get display name for a team slug."""
        team = self.tournament.teams.get(slug)
        return team.name if team else slug

    def team_seed(self, slug: str) -> int | None:
        """Get seed number for a team slug."""
        team = self.tournament.teams.get(slug)
        return team.seed if team else None

    def round_name(self, round_num: int) -> str:
        """Get display name for a round number."""
        return ROUND_NAMES.get(round_num, f"Round {round_num}")

    def is_alive(self, team_slug: str) -> bool:
        """Check if a team is still in the tournament."""
        return team_slug in self.alive_teams

    def current_round(self) -> int:
        """Determine the current round based on completed games."""
        if not self.results.results:
            return 0
        completed_rounds = set()
        for slot_id in self.results.results:
            slot = self.tournament.slots.get(slot_id)
            if slot:
                completed_rounds.add(slot.round)
        return max(completed_rounds) if completed_rounds else 0

    def games_remaining(self) -> int:
        """Count games not yet played."""
        return len(self.tournament.slots) - self.results.completed_count()

    def player_names(self) -> list[str]:
        """Get list of all player names."""
        return [e.player_name for e in self.entries]

    def get_entry(self, player_name: str) -> PlayerEntry | None:
        """Get a player's entry by name."""
        for entry in self.entries:
            if entry.player_name == player_name:
                return entry
        return None

    def get_scored(self, player_name: str) -> ScoredEntry | None:
        """Get a player's scored entry by name."""
        return self.scored_entries.get(player_name)

    def get_ai_headline(self) -> str | None:
        """Get AI-generated headline if available."""
        if self.ai_content:
            return self.ai_content.get("headline")
        return None

    def get_ai_player_summary(self, player_name: str) -> str | None:
        """Get AI-generated summary for a specific player."""
        if self.ai_content:
            summaries = self.ai_content.get("player_summaries", {})
            return summaries.get(player_name.lower())
        return None

    def get_ai_stories(self) -> list[dict]:
        """Get AI-generated story cards."""
        if self.ai_content:
            return self.ai_content.get("stories", [])
        return []

    def get_ai_recap(self) -> str | None:
        """Get AI-generated round recap."""
        if self.ai_content:
            return self.ai_content.get("recap")
        return None
