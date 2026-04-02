"""Extract bracket picks from ESPN DOM text dump.

Parses the text output from fetch_espn_bracket.py's debug dump and maps
ESPN's display names to our team slugs and slot IDs from tournament.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


def build_name_to_slug(tournament: dict) -> dict[str, str]:
    """Build a mapping from various ESPN display name forms to our team slugs."""
    mapping = {}
    for slug, info in tournament["teams"].items():
        name = info["name"]
        mapping[name.lower()] = slug
        clean = re.sub(r"[.'()]", "", name).strip().lower()
        mapping[clean] = slug
        mapping[slug.replace("_", " ")] = slug

    # ESPN-specific display name overrides (from observed DOM text)
    espn_overrides = {
        "ohio state": "ohio_st",
        "st john's": "st_johns",
        "st johns": "st_johns",
        "ca baptist": "cal_baptist",
        "michigan st": "michigan_st",
        "n dakota st": "north_dakota_st",
        "miami": "miami_fl",
        "miami oh": "miami_ohio",
        "miami ohio": "miami_ohio",
        "hawai'i": "hawaii",
        "prairie view": "prairie_view_am",
        "kennesaw st": "kennesaw_st",
        "queens": "queens_nc",
        "utah state": "utah_st",
        "iowa state": "iowa_st",
        "saint louis": "saint_louis",
        "saint mary's": "saint_marys",
        "saint marys": "saint_marys",
        "texas a&m": "texas_am",
        "wright st": "wright_st",
        "tennessee st": "tennessee_st",
        "high point": "high_point",
        "northern iowa": "northern_iowa",
        "north carolina": "north_carolina",
        "south florida": "south_florida",
        "santa clara": "santa_clara",
        "long island": "long_island",
        "texas tech": "texas_tech",
    }
    mapping.update(espn_overrides)
    return mapping


ESPN_ABBR_TO_SLUG = {
    "DUKE": "duke",
    "OSU": "ohio_st",
    "SJU": "st_johns",
    "KU": "kansas",
    "LOU": "louisville",
    "MSU": "michigan_st",
    "UCLA": "ucla",
    "CONN": "uconn",
    "FLA": "florida",
    "CLEM": "clemson",
    "VAN": "vanderbilt",
    "NEB": "nebraska",
    "UNC": "north_carolina",
    "ILL": "illinois",
    "SMC": "saint_marys",
    "HOU": "houston",
    "ARIZ": "arizona",
    "USU": "utah_st",
    "WIS": "wisconsin",
    "ARK": "arkansas",
    "TEX": "texas",
    "GONZ": "gonzaga",
    "MIA": "miami_fl",
    "PUR": "purdue",
    "MICH": "michigan",
    "SLU": "saint_louis",
    "TTU": "texas_tech",
    "ALA": "alabama",
    "TENN": "tennessee",
    "UVA": "virginia",
    "SCU": "santa_clara",
    "ISU": "iowa_st",
    "BYU": "byu",
    "VILL": "villanova",
    "UGA": "georgia",
    "UK": "kentucky",
    "TCU": "tcu",
    "IOWA": "iowa",
    "TA&M": "texas_am",
    "TAMU": "texas_am",
    "MIZ": "missouri",
    "UNI": "northern_iowa",
    "MCN": "mcneese",
    "M-OH": "miami_ohio",
    "USF": "south_florida",
    "TROY": "troy",
    "HP": "high_point",
    "AKRON": "akron",
    "HOF": "hofstra",
    "PENN": "penn",
    "VCU": "vcu",
    "FURM": "furman",
    "NDSU": "north_dakota_st",
    "CAL": "cal_baptist",
    "LIU": "long_island",
    "QU": "queens_nc",
    "PVAM": "prairie_view_am",
    "HOW": "howard",
    "TENN ST": "tennessee_st",
    "TSU": "tennessee_st",
    "KENN": "kennesaw_st",
    "KSU": "kennesaw_st",
    "IDAHO": "idaho",
    "SIE": "siena",
}


def resolve_team(name: str, name_map: dict[str, str]) -> str | None:
    key = name.strip().lower()
    if key in name_map:
        return name_map[key]
    clean = re.sub(r"[.'()]", "", key).strip()
    if clean in name_map:
        return name_map[clean]
    return None


def build_matchup_index(tournament: dict) -> dict[tuple[str, str], str]:
    """Build {frozenset(top_team, bottom_team): slot_id} for R1 slots."""
    index = {}
    for slot in tournament["slots"]:
        if slot["round"] == 1 and slot["top_team"] and slot["bottom_team"]:
            key = (min(slot["top_team"], slot["bottom_team"]),
                   max(slot["top_team"], slot["bottom_team"]))
            index[key] = slot["slot_id"]
    return index


def build_slot_structures(tournament: dict) -> dict:
    """Build slot lookup structures."""
    slots_by_round_region = {}
    slot_by_id = {}
    feeders = {}  # slot_id -> [feeder_slot_ids]

    for slot in tournament["slots"]:
        slot_by_id[slot["slot_id"]] = slot
        key = (slot["round"], slot["region"].lower())
        slots_by_round_region.setdefault(key, []).append(slot)
        if slot["feeds_into"]:
            feeders.setdefault(slot["feeds_into"], []).append(slot["slot_id"])

    for key in slots_by_round_region:
        slots_by_round_region[key].sort(key=lambda s: s["position"])

    return {
        "by_round_region": slots_by_round_region,
        "by_id": slot_by_id,
        "feeders": feeders,
    }


def parse_picks_from_text(text: str, tournament: dict) -> dict[str, str]:
    """Parse bracket picks from ESPN page text dump.

    Strategy:
    - Extract Pick: blocks and CHAMPIONSHIP PICK
    - For R1: use the abbreviation to identify the picked team, use the two
      team names in the block to identify which matchup slot
    - For R2+: use point values (+20=R2, +40=R3, +80=R4, +160=R5) to categorize,
      use the abbreviation for the pick, track positional ordering per round
    - Map ordered picks within each round to slots by region order
    """
    name_map = build_name_to_slug(tournament)
    matchup_index = build_matchup_index(tournament)
    slot_structs = build_slot_structures(tournament)
    slots_by_rr = slot_structs["by_round_region"]

    lines = text.split("\n")

    # Extract Pick: blocks and championship
    pick_blocks = []
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "Pick:":
            block = [stripped]
            j = i + 1
            while j < len(lines):
                line = lines[j].strip()
                if line == "Pick:" or line == "CHAMPIONSHIP PICK":
                    break
                block.append(line)
                j += 1
            pick_blocks.append(block)
            i = j
        elif stripped == "CHAMPIONSHIP PICK":
            if i + 1 < len(lines):
                pick_blocks.append(["CHAMPIONSHIP PICK", lines[i + 1].strip()])
            i += 2
        else:
            i += 1

    # Classify each block
    r1_picks = []   # list of (slot_id, picked_slug)
    later_picks = []  # all R2+ picks in bracket order
    championship_pick = None

    for block in pick_blocks:
        if block[0] == "CHAMPIONSHIP PICK":
            team_name = block[1] if len(block) > 1 else None
            if team_name:
                championship_pick = resolve_team(team_name, name_map)
            continue

        # The abbreviation is always block[1]
        abbr = block[1] if len(block) > 1 else ""

        # Resolve abbreviation to slug
        picked_slug = ESPN_ABBR_TO_SLUG.get(abbr)
        if not picked_slug:
            # Try resolving as a name
            picked_slug = resolve_team(abbr, name_map)
        if not picked_slug:
            continue

        # Check if R2+ (has "over" on the third line)
        is_later_round = len(block) > 2 and block[2].startswith("over ")

        if not is_later_round:
            # Round 1 — extract both team names to identify the matchup slot
            teams_found = []
            for line in block[1:]:
                slug = resolve_team(line, name_map)
                if slug and slug not in teams_found:
                    teams_found.append(slug)

            # Find which R1 slot contains these two teams
            slot_id = None
            if len(teams_found) >= 2:
                # Try all pairs
                for a in range(len(teams_found)):
                    for b in range(a + 1, len(teams_found)):
                        key = (min(teams_found[a], teams_found[b]),
                               max(teams_found[a], teams_found[b]))
                        if key in matchup_index:
                            slot_id = matchup_index[key]
                            break
                    if slot_id:
                        break

            if slot_id:
                r1_picks.append((slot_id, picked_slug))
            else:
                # Fallback: still record the pick positionally
                r1_picks.append((None, picked_slug))
        else:
            # Later round — collect in order, assign round by position
            # ESPN always shows picks in strict bracket order:
            # R2 (16), R3 (8), R4 (4), R5 (2)
            later_picks.append(picked_slug)

    # Split later_picks by position: first 16 = R2, next 8 = R3, next 4 = R4, rest = R5
    r2_picks = later_picks[0:16]
    r3_picks = later_picks[16:24]
    r4_picks = later_picks[24:28]
    r5_picks = later_picks[28:30]

    # Build final picks dict
    picks = {}

    # Round 1: use slot_id from matchup identification
    for slot_id, slug in r1_picks:
        if slot_id:
            picks[slot_id] = slug

    # Rounds 2-5: map by position within region order
    region_order = ["east", "south", "west", "midwest"]

    def assign_positional(round_num: int, round_picks: list[str]):
        if round_num == 5:
            # Final Four
            ff_slots = slots_by_rr.get((5, "final four"), [])
            for i, slot in enumerate(ff_slots):
                if i < len(round_picks):
                    picks[slot["slot_id"]] = round_picks[i]
            return

        idx = 0
        for region in region_order:
            region_slots = slots_by_rr.get((round_num, region), [])
            for slot in region_slots:
                if idx < len(round_picks):
                    picks[slot["slot_id"]] = round_picks[idx]
                    idx += 1

    assign_positional(2, r2_picks)
    assign_positional(3, r3_picks)
    assign_positional(4, r4_picks)
    assign_positional(5, r5_picks)

    # Championship
    if championship_pick:
        picks["championship"] = championship_pick

    return picks


def validate_bracket_tree(picks: dict[str, str], tournament: dict) -> list[str]:
    """Validate that picks form a valid bracket tree.

    Returns list of error messages (empty = valid).
    """
    errors = []
    slot_structs = build_slot_structures(tournament)
    feeders = slot_structs["feeders"]

    for slot_id, picked_team in picks.items():
        if slot_id in feeders:
            feeder_ids = feeders[slot_id]
            feeder_picks = [picks.get(fid) for fid in feeder_ids]
            if picked_team not in feeder_picks:
                errors.append(
                    f"{slot_id}: picked {picked_team} but feeders "
                    f"{feeder_ids} have picks {feeder_picks}"
                )

    return errors


def extract_and_save(
    text_path: str = "data/debug/bracket_text.txt",
    tournament_path: str = "data/tournament.json",
    output_path: str = "data/entries/rebecca_extracted.json",
    player_name: str = "Rebecca",
) -> dict:
    """Extract picks from debug text and save to JSON."""
    text = Path(text_path).read_text(encoding="utf-8")
    tournament = json.loads(Path(tournament_path).read_text(encoding="utf-8"))

    picks = parse_picks_from_text(text, tournament)

    # Validate
    errors = validate_bracket_tree(picks, tournament)
    if errors:
        print(f"WARNING: {len(errors)} bracket tree violations:")
        for e in errors:
            print(f"  {e}")

    result = {
        "player_name": player_name,
        "entry_name": f"{player_name}'s Picks 2",
        "picks": picks,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    return result


if __name__ == "__main__":
    result = extract_and_save()
    picks = result.get("picks", {})
    print(f"Extracted {len(picks)} picks for {result['player_name']}")
    if len(picks) != 63:
        print(f"WARNING: Expected 63 picks, got {len(picks)}")
    for slot_id, team in sorted(picks.items()):
        print(f"  {slot_id}: {team}")
