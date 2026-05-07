#!/usr/bin/env python3
"""Generate printed unit-ID stickers for a 6mm IDF Team Yankee army.

One sticker per row in lists/israeli_full.csv. Output goes to out/.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

import military_symbol

ROOT = Path(__file__).parent
INPUT_CSV = ROOT / "lists" / "israeli_full.csv"
OUT_DIR = ROOT / "out"
FLAGS_DIR = ROOT / "flags"

BG_COLOR = "#FFFFFF"
FONT_FAMILY = '"RobotoMono Nerd Font", "RobotoMonoNerdFont", "DejaVu Sans Mono", monospace'
ISRAEL_BLUE = "#0038B8"


# ---------------------------------------------------------------------------
# team_role -> APP-6 description
# ---------------------------------------------------------------------------

ROLE_DESCRIPTIONS: dict[str, str] = {
    "Tank": "unknown armor",
    "HQ Tank": "unknown armor",
    "Galil rifle": "unknown infantry",
    "Galil HQ team": "unknown infantry",
    "FN MAG": "unknown machine gun",
    "RPG-7": "unknown anti-tank",
    "M47 Dragon": "unknown anti-tank",
    "52mm mortar": "unknown mortar",
    "81mm mortar carrier": "unknown self-propelled mortar",
    "120mm mortar carrier": "unknown self-propelled mortar",
    "155mm SP gun": "unknown self-propelled artillery",
    "ATGM carrier": "unknown anti-tank",
    "Pereh": "unknown anti-tank",
    "Jeep ATGM": "unknown wheeled anti-tank",
    "Rabbi ATGM": "unknown wheeled anti-tank",
    "BM-21": "unknown wheeled rocket artillery",
    "MLRS": "unknown rocket artillery",
    "Vulcan AA": "unknown self-propelled anti-aircraft",
    "Shilka AA": "unknown self-propelled anti-aircraft",
    "SAM": "unknown surface-to-air missile",
    "MANPADS": "unknown manpads",
    "Strike jet": "unknown fighter",
    "Attack heli": "unknown attack helicopter",
    "Transport": "unknown armored personnel carrier",
    "Transport heli": "unknown utility helicopter",
    "Transport heli swap": "unknown utility helicopter",
    "Transport variant": "unknown armored personnel carrier",
    "Recce": "unknown reconnaissance",
    "Artillery observer": "unknown observation post",
}

HQ_ROLES = {"HQ Tank", "Galil HQ team"}


def role_base_form(team_role: str) -> str:
    """Strip [Para]/[Reserve] tags, parenthetical option notes, em-dash annotations."""
    s = re.sub(r"\s*[—–-]\s*same model as above\s*$", "", team_role, flags=re.IGNORECASE)
    s = re.sub(r"\s*\[(Para|Reserve)\]", "", s)
    s = re.sub(r"\s*\([^)]*\)", "", s).strip()
    return s


def map_role_to_description(team_role: str) -> str:
    base = role_base_form(team_role)
    # `Transport (... UH-1)` is a utility helicopter, not an APC. The base
    # form is "Transport" so we'd otherwise route it to APC; check the
    # parenthetical first.
    if base == "Transport" and "UH-1" in team_role:
        return "unknown utility helicopter"
    if base in ROLE_DESCRIPTIONS:
        return ROLE_DESCRIPTIONS[base]
    raise ValueError(f"No description mapping for: {team_role!r} (base={base!r})")


# ---------------------------------------------------------------------------
# Unit name heuristics — populates the `name` column of the CSV.
#
# Rules (per project spec):
# - Tanks: model only ("Merkava 3", "Magach 6", "Sho't Blazer").
# - Infantry / weapons: weapon name ("Galil", "FN MAG", "RPG-7", …).
# - APCs: IDF nickname in caps ("ZELDA", "VAYZATA", "NAGMASH").
# - No size descriptors (Platoon / Company / Battery / Section).
#
# `derive_name` is the source of truth for the column. Once a row has a
# `name` value in the CSV it wins; the function is only consulted when the
# column is missing or empty (used by --update-csv to bootstrap).
# ---------------------------------------------------------------------------

TANK_NAMES = [
    ("Merkava 3", "Merkava 3"),
    ("Merkava 2", "Merkava 2"),
    ("Merkava 1", "Merkava 1"),
    ("Magach 6 (Blazer)", "Magach 6 Blazer"),
    ("Magach 6", "Magach 6"),
    ("Sho't", "Sho't Blazer"),
]

HELI_MODELS = ("AH-64", "AH-1", "CH-53", "UH-1")


def derive_name(team_role: str, unit_name: str) -> str:
    """Derive the (uppercase) display name for a row.

    The CSV's `name` column is the source of truth at runtime; this
    function only seeds it. All names are returned uppercase per project
    spec — hand-edits in the CSV are preserved verbatim, so a user wanting
    a mixed-case override can write one in.
    """
    base = role_base_form(team_role)

    if base in ("Tank", "HQ Tank"):
        for key, name in TANK_NAMES:
            if key in unit_name:
                return name.upper()
        return "TANK"

    if base == "Transport heli swap":
        return "CH-53"
    if base in ("Attack heli", "Transport heli"):
        for k in HELI_MODELS:
            if k in unit_name:
                return k
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
                return "ZELDA"
            if "Vayzata" in content:
                return "VAYZATA"
            if "Nagmasho" in content:
                return "NAGMASH"
            return content.upper()
        return "APC"

    if base == "Recce":
        if "Jeep" in unit_name:
            return "JEEP"
        if "M113" in unit_name:
            return "ZELDA"
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
        "BM-21": "BM-21",
        "MLRS": "MLRS",
        "Vulcan AA": "VULCAN",
        "Shilka AA": "SHILKA",
        "SAM": "CHAPARRAL",
        "MANPADS": "REDEYE",
        "Strike jet": "A-4 SKYHAWK",
        "Artillery observer": "M113 OP",
    }.get(base, base.upper())


# ---------------------------------------------------------------------------
# Icon SVG handling
# ---------------------------------------------------------------------------

def get_icon_svg(description: str, is_hq: bool) -> str:
    """Return a complete <svg>...</svg> string for the icon, with quirks applied."""
    # quirk: 'unknown rockets' doesn't resolve; use rocket artillery
    if description == "unknown rockets":
        description = "unknown rocket artillery"

    raw = military_symbol.get_symbol_svg_string_from_name(description)

    if description == "unknown fighter":
        # Close the open path (cumulus).
        def close_d(m: re.Match[str]) -> str:
            d = m.group(1).rstrip()
            if not d.lower().endswith("z"):
                d += " z"
            return f'd="{d}"'

        raw = re.sub(r'd="([^"]+)"', close_d, raw)
        # Override viewBox so wider wings aren't clipped.
        raw = re.sub(r'viewBox="[^"]+"', 'viewBox="0 0 200 160"', raw)
        raw = re.sub(r'\bwidth="[^"]+"', 'width="200"', raw, count=1)
        raw = re.sub(r'\bheight="[^"]+"', 'height="160"', raw, count=1)

    if is_hq:
        bar = (
            '<path d="M63,63 L137,63" stroke="rgb(0, 0, 0)" '
            'stroke-width="4" stroke-linecap="round" fill="none" />'
        )
        raw = raw.replace("</svg>", bar + "</svg>")

    return raw


def extract_inner_svg(svg_str: str) -> tuple[str, str]:
    """Strip the outer <svg ...> tag, return (inner content, viewBox)."""
    vb_m = re.search(r'viewBox="([^"]+)"', svg_str)
    vb = vb_m.group(1) if vb_m else "0 0 200 200"
    inner = re.sub(r"^<svg[^>]*>", "", svg_str.strip(), count=1)
    inner = re.sub(r"</svg>\s*$", "", inner)
    return inner.strip(), vb


# ---------------------------------------------------------------------------
# Israeli flag
# ---------------------------------------------------------------------------

def israel_flag_svg() -> str:
    """Clean Israeli flag, 11:8, white field, two blue stripes, hollow Star of David."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 160" width="220" height="160">
  <rect width="220" height="160" fill="#FFFFFF" />
  <rect x="0" y="25" width="220" height="20" fill="{ISRAEL_BLUE}" />
  <rect x="0" y="115" width="220" height="20" fill="{ISRAEL_BLUE}" />
  <g fill="none" stroke="{ISRAEL_BLUE}" stroke-width="4" stroke-linejoin="miter">
    <path d="M110,52 L138,100 L82,100 Z" />
    <path d="M110,108 L138,60 L82,60 Z" />
  </g>
</svg>
"""


def israel_flag_inner() -> str:
    return f"""<rect x="0" y="0" width="220" height="160" fill="#FFFFFF" />
<rect x="0" y="25" width="220" height="20" fill="{ISRAEL_BLUE}" />
<rect x="0" y="115" width="220" height="20" fill="{ISRAEL_BLUE}" />
<g fill="none" stroke="{ISRAEL_BLUE}" stroke-width="4" stroke-linejoin="miter">
<path d="M110,52 L138,100 L82,100 Z" />
<path d="M110,108 L138,60 L82,60 Z" />
</g>"""


# ---------------------------------------------------------------------------
# Sticker construction
# ---------------------------------------------------------------------------

def sticker_width_mm(base: str) -> int:
    return 40 if base == "40x20" else 20


def escape_xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_sticker(designation: str, name: str, icon_svg: str,
                  width_mm: int, bg: str = BG_COLOR) -> str:
    height_mm = 8
    is_wide = width_mm == 40

    icon_size = flag_size = 5.0
    margin = 0.3
    icon_x = margin
    flag_x = width_mm - margin - flag_size
    icon_y = flag_y = (height_mm - icon_size) / 2  # vertically centred (= 1.5)
    text_x = width_mm / 2

    if is_wide:
        label_size = 2.6
        desig_size = 4.5
    else:
        label_size = 1.9
        desig_size = 3.6

    icon_inner, icon_vb = extract_inner_svg(icon_svg)
    flag_inner = israel_flag_inner()

    desig_y = height_mm - 0.6

    # Available text width between icon and flag (with a small gutter).
    # rsvg-convert ignores SVG `textLength`/`lengthAdjust`, so we shrink the
    # font instead when the natural width would overflow. Monospace glyph
    # cell ≈ 0.6 × font-size.
    available_w = width_mm - (icon_x + icon_size) - (width_mm - flag_x) - 1.0
    natural_w = len(name) * label_size * 0.6
    if natural_w > available_w:
        label_size = max(available_w / (len(name) * 0.6), 1.3)
    label_y = 0.2 + label_size * 0.85

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{width_mm}mm" height="{height_mm}mm"
     viewBox="0 0 {width_mm} {height_mm}">
  <rect width="{width_mm}" height="{height_mm}" fill="{bg}" />
  <svg x="{icon_x}" y="{icon_y}" width="{icon_size}" height="{icon_size}"
       viewBox="{icon_vb}" preserveAspectRatio="xMidYMid meet">
    {icon_inner}
  </svg>
  <svg x="{flag_x}" y="{flag_y}" width="{flag_size}" height="{flag_size}"
       viewBox="0 0 220 160" preserveAspectRatio="xMidYMid meet">
    {flag_inner}
  </svg>
  <rect x="{flag_x}" y="{flag_y}" width="{flag_size}" height="{flag_size}"
        fill="none" stroke="#000" stroke-width="0.15" />
  <text x="{text_x}" y="{label_y:.2f}" font-family='{FONT_FAMILY}'
        font-size="{label_size:.2f}" text-anchor="middle"
        fill="#000">{escape_xml(name)}</text>
  <text x="{text_x}" y="{desig_y:.2f}" font-family='{FONT_FAMILY}'
        font-size="{desig_size}" text-anchor="middle" font-weight="bold"
        fill="#000" direction="ltr" unicode-bidi="bidi-override"
        >{escape_xml(designation)}</text>
</svg>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def row_name(row: dict) -> str:
    """Return the display name for a row, deriving + filling it in if missing."""
    existing = row.get("name", "").strip() if row.get("name") else ""
    if existing:
        return existing
    return derive_name(row["team_role"], row["unit_name"])


def update_csv(force: bool = False) -> int:
    """Add (or fill in) the `name` column. With `force`, overwrite existing values."""
    with INPUT_CSV.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "name" not in fieldnames:
        # Insert `name` right after `unit_name` for readability.
        idx = fieldnames.index("unit_name") + 1 if "unit_name" in fieldnames else len(fieldnames)
        fieldnames = fieldnames[:idx] + ["name"] + fieldnames[idx:]

    touched = 0
    for row in rows:
        if force or not row.get("name", "").strip():
            row["name"] = derive_name(row["team_role"], row["unit_name"])
            touched += 1

    with INPUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    verb = "overwrote" if force else "filled"
    print(f"Updated {INPUT_CSV}: {verb} `name` on {touched} rows ({len(rows)} total)")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--update-csv":
        return update_csv(force="--force" in argv[1:])
    return _generate()


def _generate() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    FLAGS_DIR.mkdir(exist_ok=True)
    (FLAGS_DIR / "il.svg").write_text(israel_flag_svg())

    if not INPUT_CSV.exists():
        print(f"Missing input: {INPUT_CSV}", file=sys.stderr)
        return 1

    with INPUT_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    icon_cache: dict[tuple[str, bool], str] = {}
    written = 0
    for row in rows:
        team_role = row["team_role"]
        designation = row["designation"]
        base = row["base"]

        description = map_role_to_description(team_role)
        is_hq = role_base_form(team_role) in HQ_ROLES
        cache_key = (description, is_hq)
        if cache_key not in icon_cache:
            icon_cache[cache_key] = get_icon_svg(description, is_hq)
        icon_svg = icon_cache[cache_key]

        name = row_name(row)
        width_mm = sticker_width_mm(base)
        sticker = build_sticker(designation, name, icon_svg, width_mm)

        out_path = OUT_DIR / f"{designation}.svg"
        out_path.write_text(sticker, encoding="utf-8")
        written += 1

    print(f"Wrote {written} stickers to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
