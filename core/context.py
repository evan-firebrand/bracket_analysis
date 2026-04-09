"""AnalysisContext — shared data object passed to all plugins."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

import pandas as pd

from core.loader import load_entries, load_results, load_tournament
from core.models import (
    PlayerEntry,
    Results,
    ScenarioResults,
    ScoredEntry,
    TournamentStructure,
)
from core.scenarios import run_scenarios
from core.scoring import (
    ROUND_NAMES,
    build_leaderboard,
    get_alive_teams,
    score_entry,
)

# AI layer is optional — if anthropic isn't installed, AI methods degrade to None.
try:
    from core.ai import agent as _ai_agent
    from core.ai.cache import ContentCache, compute_data_hash
    from core.ai.evidence import EvidencePacket, log_audit
    _AI_IMPORT_OK = True
except Exception:  # pragma: no cover - exercised when anthropic missing
    _ai_agent = None
    ContentCache = None  # type: ignore[misc,assignment]
    compute_data_hash = None  # type: ignore[assignment]
    EvidencePacket = None  # type: ignore[misc,assignment]
    log_audit = None  # type: ignore[assignment]
    _AI_IMPORT_OK = False


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

        # Scenario results (eagerly computed so home screen can use them)
        try:
            self.scenario_results: ScenarioResults | None = run_scenarios(
                self.entries, self.tournament, self.results
            )
        except Exception:
            self.scenario_results = None

        # AI content (loaded if available)
        self.ai_content: dict | None = self._load_ai_content(data_dir)

        # Live AI layer state — populated by configure_ai()
        self._ai_config: dict = {}
        self._ai_enabled: bool = False
        self._data_dir: Path = data_dir
        self._data_hash_cached: str | None = None
        self._content_cache: "ContentCache | None" = None
        self._audit_dir: Path = data_dir / "ai_audit"

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

    # --- Live AI layer (Phase 4) ---

    def configure_ai(self, ai_config: dict | None) -> None:
        """Wire up the live AI layer.

        Called from app.py after loading config.yaml's ``ai:`` block. ``ai_config``
        is a plain dict so core/ stays Streamlit-free (ADR-001).

        Keys (all optional):
          - enabled: bool — master switch (default True if anthropic is installed)
          - cache_enabled: bool — whether to cache page copy (default True)
          - cache_dir: str — where to write cache files (default ``data/content/cache``)
          - audit_dir: str — where to write audit logs (default ``data/ai_audit``)
        """
        cfg = dict(ai_config or {})
        self._ai_config = cfg
        self._ai_enabled = bool(cfg.get("enabled", True)) and _AI_IMPORT_OK

        cache_dir = Path(cfg.get("cache_dir", self._data_dir / "content" / "cache"))
        self._audit_dir = Path(cfg.get("audit_dir", self._data_dir / "ai_audit"))

        cache_enabled = bool(cfg.get("cache_enabled", True))
        if cache_enabled and _AI_IMPORT_OK and ContentCache is not None:
            self._content_cache = ContentCache(cache_dir=cache_dir)
        else:
            self._content_cache = None

    @property
    def data_hash(self) -> str:
        """Short sha256 of the current data files. Cached per context instance."""
        if self._data_hash_cached is None:
            if compute_data_hash is None:
                self._data_hash_cached = "no-ai"
            else:
                self._data_hash_cached = compute_data_hash(self._data_dir)
        return self._data_hash_cached

    def generate_copy(
        self,
        lens: str,
        page: str,
        viewer: str | None = None,
    ) -> str | None:
        """Generate AI page copy for a given lens + page.

        Returns the generated text on success, or ``None`` on any failure
        (AI disabled, missing API key, agent error). Callers must handle
        ``None`` by falling back to template copy.

        Cache is keyed on ``(lens, viewer, data_hash)`` so the first visitor
        after a data change triggers generation and subsequent visitors hit
        cache. Audit logs are written to ``self._audit_dir`` per call.
        """
        if not self._ai_enabled or _ai_agent is None:
            return None

        viewer_key = viewer or "__anon__"

        # Cache hit?
        if self._content_cache is not None:
            cached = self._content_cache.get(lens, viewer_key, self.data_hash)
            if cached is not None and cached.get("content"):
                return cached["content"]

        context_dict = {
            "page": page,
            "viewer": viewer,
            "data_hash": self.data_hash,
            "current_round": self.current_round(),
            "games_remaining": self.games_remaining(),
        }

        try:
            text, evidence = _ai_agent.generate(lens, context_dict, self)
        except _ai_agent.AIUnavailableError as exc:
            print(f"[ai] generate_copy unavailable for lens={lens}: {exc}")
            return None
        except Exception as exc:  # noqa: BLE001 — never let AI break a page
            print(f"[ai] generate_copy failed for lens={lens}: {exc}")
            return None

        if self._content_cache is not None:
            try:
                self._content_cache.put(
                    lens,
                    viewer_key,
                    self.data_hash,
                    text,
                    evidence.to_dict(),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[ai] cache write failed for lens={lens}: {exc}")

        try:
            log_audit(evidence, self._audit_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"[ai] audit log failed for lens={lens}: {exc}")

        return text

    def answer_question(
        self,
        question: str,
        viewer: str | None = None,
        history: list[dict] | None = None,
    ) -> Generator[str, None, None]:
        """Stream a chat answer to a user question.

        Yields tokens as they arrive. Chat is **never cached** — each call
        runs a fresh agent loop. On AI failure, yields a single fallback
        line and returns cleanly so the Streamlit stream doesn't hang.
        """
        if not self._ai_enabled or _ai_agent is None or EvidencePacket is None:
            yield (
                "Sorry — the AI assistant isn't available right now. "
                "Try again later or check the static analysis tabs."
            )
            return

        messages: list[dict] = list(history or [])
        messages.append({"role": "user", "content": question})

        packet = EvidencePacket(lens="chat", viewer=viewer)

        try:
            for token in _ai_agent.stream("chat", messages, self, evidence=packet):
                yield token
        except _ai_agent.AIUnavailableError as exc:
            print(f"[ai] answer_question unavailable: {exc}")
            yield (
                "Sorry — the AI assistant isn't available right now. "
                "Try again later or check the static analysis tabs."
            )
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[ai] answer_question failed: {exc}")
            yield f"\n\n_Error generating answer: {exc}_"
            return

        try:
            if log_audit is not None:
                log_audit(packet, self._audit_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"[ai] chat audit log failed: {exc}")

    def generate_recap_with_redteam(
        self,
        page: str = "round_recap",
        viewer: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Generate a round recap and (optionally) a red-team review of it.

        Returns ``(recap_text, redteam_text)``. ``redteam_text`` is ``None``
        when ``ai.redteam_recap`` is disabled in config or when the red-team
        pass fails. ``recap_text`` is ``None`` when AI is disabled or the
        recap call fails.

        The recap call goes through the live agent loop directly (not
        ``generate_copy``) so we can capture the EvidencePacket and pass it
        verbatim to the red-team pass. The recap result is still cached on
        success and audited like any other ``generate_copy`` call.
        """
        if not self._ai_enabled or _ai_agent is None or EvidencePacket is None:
            return None, None

        viewer_key = viewer or "__anon__"
        cached_evidence: dict | None = None
        recap_text: str | None = None
        evidence = None

        # Cache hit?
        if self._content_cache is not None:
            cached = self._content_cache.get("recap", viewer_key, self.data_hash)
            if cached is not None and cached.get("content"):
                recap_text = cached["content"]
                cached_evidence = cached.get("evidence")

        if recap_text is None:
            context_dict = {
                "page": page,
                "viewer": viewer,
                "data_hash": self.data_hash,
                "current_round": self.current_round(),
                "games_remaining": self.games_remaining(),
            }
            try:
                recap_text, evidence = _ai_agent.generate("recap", context_dict, self)
            except _ai_agent.AIUnavailableError as exc:
                print(f"[ai] recap unavailable: {exc}")
                return None, None
            except Exception as exc:  # noqa: BLE001
                print(f"[ai] recap failed: {exc}")
                return None, None

            if self._content_cache is not None:
                try:
                    self._content_cache.put(
                        "recap",
                        viewer_key,
                        self.data_hash,
                        recap_text,
                        evidence.to_dict(),
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[ai] recap cache write failed: {exc}")

            try:
                log_audit(evidence, self._audit_dir)
            except Exception as exc:  # noqa: BLE001
                print(f"[ai] recap audit log failed: {exc}")

        # Red-team disabled?
        if not self._ai_config.get("redteam_recap", False):
            return recap_text, None

        # Build the evidence packet payload for the red-team prompt
        if evidence is not None:
            evidence_payload = evidence.to_dict()
        elif cached_evidence is not None:
            evidence_payload = cached_evidence
        else:
            evidence_payload = {"tool_calls": [], "scope_block": "(no evidence captured)"}

        redteam_context = {
            "page": page,
            "viewer": viewer,
            "draft_recap": recap_text,
            "evidence_packet": evidence_payload,
        }
        try:
            redteam_text, _redteam_packet = _ai_agent.generate(
                "recap_redteam", redteam_context, self
            )
        except Exception as exc:  # noqa: BLE001 — red-team failure must not break recap
            print(f"[ai] redteam pass failed: {exc}")
            return recap_text, None

        return recap_text, redteam_text
