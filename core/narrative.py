"""Template-based natural language helpers.

These provide instant, deterministic, free descriptions for structural content.
For richer, AI-generated narratives, see the AI content pipeline.
"""

from __future__ import annotations


def describe_probability(win_pct: float) -> str:
    """Describe a win probability in natural language."""
    if win_pct <= 0:
        return "mathematically eliminated \u2014 no path to first place"
    if win_pct < 0.01:
        return "a miracle run \u2014 less than 1 in 100 outcomes"
    if win_pct < 0.05:
        return "a long shot, but stranger things have happened in March"
    if win_pct < 0.15:
        return "still in the hunt, but needs some things to break right"
    if win_pct < 0.30:
        return "a real contender with a solid path"
    if win_pct < 0.50:
        return "one of the favorites \u2014 things are looking good"
    if win_pct < 0.70:
        return "sitting pretty \u2014 more likely than not to win it all"
    if win_pct < 0.90:
        return "in the driver's seat \u2014 would take a lot to knock them off"
    return "all but locked up \u2014 it would take a miracle for anyone else"


def describe_trend(rank_change: int) -> str:
    """Describe a rank change in natural language."""
    if rank_change == 0:
        return "holding steady"
    if rank_change >= 5:
        return "rocketing up the standings"
    if rank_change >= 3:
        return "surging up the standings"
    if rank_change >= 1:
        return "climbing"
    if rank_change <= -5:
        return "in freefall"
    if rank_change <= -3:
        return "took a big hit"
    return "slipped a bit"


def describe_pick_popularity(pct: float) -> str:
    """Describe how popular a pick was among the group."""
    if pct >= 0.90:
        return "the chalk pick \u2014 almost everyone had this one"
    if pct >= 0.70:
        return "a very popular pick"
    if pct >= 0.50:
        return "picked by the majority"
    if pct >= 0.30:
        return "a split decision in the group"
    if pct >= 0.15:
        return "a contrarian call \u2014 going against the crowd"
    if pct >= 0.05:
        return "a bold call that almost nobody else made"
    return "a lone wolf pick \u2014 nobody else had this"


def describe_elimination(is_eliminated: bool, max_possible: int, leader_score: int) -> str:
    """Describe a player's elimination status."""
    if is_eliminated:
        return "Eliminated \u2014 can't catch the leader even with a perfect remaining bracket"
    gap = max_possible - leader_score
    if gap <= 0:
        return "On the bubble \u2014 needs everything to go right"
    if gap < 50:
        return "Alive but on thin ice \u2014 very little margin for error"
    if gap < 150:
        return "Still alive with room to maneuver"
    return "Alive with plenty of upside remaining"


def describe_max_possible(current: int, max_possible: int) -> str:
    """Describe the gap between current score and max possible."""
    remaining = max_possible - current
    if remaining == 0:
        return "All picks resolved \u2014 no more points available"
    if remaining < 50:
        return f"Only {remaining} more points possible"
    if remaining < 200:
        return f"{remaining} points still in play"
    return f"{remaining} points of upside remaining \u2014 a lot can still change"


def ordinal(n: int) -> str:
    """Convert number to ordinal string (1st, 2nd, 3rd, etc.)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
