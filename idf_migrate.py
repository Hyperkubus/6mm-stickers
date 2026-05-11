#!/usr/bin/env python3
"""IDF-specific helpers for `lists/israeli_full.csv`.

The generic generator only needs a minimal column set
(designation, name, symbol, width, hq, formation, group). This script
derives those columns from the rich IDF-specific columns we keep in the
CSV for army-list editing — `kind`, `formation_name`, `letter`,
`slot_*`, `unit_*`, `team_role`, `team_position_*`, `base`.

Run after any edit to the CSV:

    python idf_migrate.py            # fill in blanks
    python idf_migrate.py --force    # overwrite derived columns

Original IDF columns are preserved; only the minimal derived columns
are written (or rewritten with --force).

The Israeli army renders as APP-6 `unknown` (yellow quatrefoils) by
default — an aesthetic choice rather than a NATO-affiliation claim.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DEFAULT_CSV = ROOT / "lists" / "israeli_full.csv"

# Minimal derived columns appended (in this order) to the CSV.
DERIVED_COLS = ["symbol", "width", "hq", "formation", "group", "name"]


# ---------------------------------------------------------------------------
# team_role -> APP-6 symbol (without affiliation prefix)
# ---------------------------------------------------------------------------

ROLE_SYMBOLS: dict[str, str] = {
    "Tank": "armor",
    "HQ Tank": "armor",
    "Galil rifle": "infantry",
    "Galil HQ team": "infantry",
    "FN MAG": "machine gun",
    "RPG-7": "anti-tank",
    "M47 Dragon": "anti-tank",
    "52mm mortar": "mortar",
    "81mm mortar carrier": "self-propelled mortar",
    "120mm mortar carrier": "self-propelled mortar",
    "155mm SP gun": "self-propelled artillery",
    "ATGM carrier": "anti-tank",
    "Pereh": "anti-tank",
    "Jeep ATGM": "wheeled anti-tank",
    "Rabbi ATGM": "wheeled anti-tank",
    "BM-21": "wheeled rocket artillery",
    "MLRS": "rocket artillery",
    "Vulcan AA": "self-propelled anti-aircraft",
    "Shilka AA": "self-propelled anti-aircraft",
    "SAM": "surface-to-air missile",
    "MANPADS": "manpads",
    "Strike jet": "fighter",
    "Attack heli": "attack helicopter",
    "Transport": "armored personnel carrier",
    "Transport heli": "utility helicopter",
    "Transport heli swap": "utility helicopter",
    "Transport variant": "armored personnel carrier",
    "Recce": "reconnaissance",
    "Artillery observer": "observation post",
}

HQ_ROLES = {"HQ Tank", "Galil HQ team"}


def role_base_form(team_role: str) -> str:
    """Strip [Para]/[Reserve] tags, parenthetical option notes, em-dash annotations."""
    s = re.sub(r"\s*[—–-]\s*same model as above\s*$", "", team_role, flags=re.IGNORECASE)
    s = re.sub(r"\s*\[(Para|Reserve)\]", "", s)
    s = re.sub(r"\s*\([^)]*\)", "", s).strip()
    return s


def map_role_to_symbol(team_role: str) -> str:
    base = role_base_form(team_role)
    # `Transport (... UH-1)` is a utility helicopter, not an APC.
    if base == "Transport" and "UH-1" in team_role:
        return "utility helicopter"
    if base in ROLE_SYMBOLS:
        return ROLE_SYMBOLS[base]
    raise ValueError(f"No symbol mapping for: {team_role!r} (base={base!r})")


# ---------------------------------------------------------------------------
# Unit name heuristics (label on the sticker)
# ---------------------------------------------------------------------------

TANK_NAMES = [
    ("Merkava 3", "Merkava 3"),
    ("Merkava 2", "Merkava 2"),
    ("Merkava 1", "Merkava 1"),
    ("Magach 6 (Blazer)", "Magach 6 Blazer"),
    ("Magach 6", "Magach 6"),
    ("Sho't", "Sho't Blazer"),
]

HELI_MODELS: list[tuple[str, str]] = [
    ("AH-64", "AH-64 PETEN"),
    ("AH-1", "AH-1 TZEFA"),
    ("CH-53", "CH-53 YAS'UR"),
    ("UH-1", "UH-1"),
]


def derive_name(team_role: str, unit_name: str) -> str:
    """Derive the uppercase top-label name. CSV hand-edits win at runtime."""
    base = role_base_form(team_role)

    if base in ("Tank", "HQ Tank"):
        for key, name in TANK_NAMES:
            if key in unit_name:
                return name.upper()
        return "TANK"

    if base == "Transport heli swap":
        return "CH-53 YAS'UR"
    if base in ("Attack heli", "Transport heli"):
        for key, name in HELI_MODELS:
            if key in unit_name:
                return name
        return "UH-1" if base == "Transport heli" else "HELI"

    if base in ("Transport", "Transport variant"):
        if "UH-1" in team_role:
            return "UH-1"
        m = re.search(r"\(([^)]+)\)", team_role)
        if m:
            content = m.group(1)
            content = re.sub(r"^HQ\s+", "", content)
            content = re.sub(r"^Reserve\s+", "", content)
            content = re.sub(r"\s+variant$", "", content)
            if "M113" in content:
                return "M113 ZELDA"
            if "Vayzata" in content:
                return "M113 VAYZATA"
            if "Nagmasho" in content:
                return "NAGMASHOT"
            return content.upper()
        return "APC"

    if base == "Recce":
        if "Jeep" in unit_name:
            return "JEEP"
        if "M113" in unit_name:
            return "M113 ZELDA"
        if "Rabbi" in unit_name:
            return "RABBI"
        return "RECCE"

    return {
        "Galil HQ team": "GALIL",
        "Galil rifle": "GALIL",
        "FN MAG": "FN MAG",
        "RPG-7": "RPG-7",
        "M47 Dragon": "M47 DRAGON",
        "52mm mortar": "52MM",
        "81mm mortar carrier": "M125",
        "120mm mortar carrier": "M106",
        "155mm SP gun": "M109",
        "ATGM carrier": "M150",
        "Pereh": "PEREH",
        "Jeep ATGM": "JEEP",
        "Rabbi ATGM": "RABBI",
        "BM-21": "BM-21 GRAD",
        "MLRS": "M270 MLRS",
        "Vulcan AA": "M163 VADS",
        "Shilka AA": "ZSU-23-4 SHILKA",
        "SAM": "M48 CHAPARRAL",
        "MANPADS": "REDEYE",
        "Strike jet": "A-4 SKYHAWK",
        "Artillery observer": "M113 OP",
    }.get(base, base.upper())


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def width_for_base(base: str) -> int:
    return 40 if base == "40x20" else 20


def group_for_letter(letter: str) -> str:
    """Hebrew letter column is e.g. `"א (Aleph)"`. Keep just the letter for sort/break key."""
    return letter.strip().split()[0] if letter else ""


def migrate(csv_path: Path, force: bool) -> int:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    for col in DERIVED_COLS:
        if col not in fieldnames:
            fieldnames.append(col)

    touched = 0
    for row in rows:
        team_role = row["team_role"]
        unit_name = row.get("unit_name", "")

        updates = {
            "symbol":    map_role_to_symbol(team_role),
            "width":     str(width_for_base(row["base"])),
            "hq":        "true" if role_base_form(team_role) in HQ_ROLES else "",
            "formation": row.get("formation_name", ""),
            "group":     group_for_letter(row.get("letter", "")),
            "name":      row.get("name", "") or derive_name(team_role, unit_name),
        }

        changed = False
        for col, value in updates.items():
            current = row.get(col, "")
            if force or not current:
                if current != value:
                    row[col] = value
                    changed = True
        if changed:
            touched += 1

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    verb = "rewrote" if force else "filled"
    print(f"Updated {csv_path}: {verb} derived columns on {touched} rows ({len(rows)} total)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Populate IDF CSV's derived (minimal) columns.")
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing values in derived columns.")
    args = p.parse_args(argv)
    if not args.csv.exists():
        print(f"Missing input: {args.csv}", file=sys.stderr)
        return 1
    return migrate(args.csv, args.force)


if __name__ == "__main__":
    raise SystemExit(main())
