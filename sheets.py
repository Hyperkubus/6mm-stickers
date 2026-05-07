#!/usr/bin/env python3
"""Render per-formation cut-out sticker sheets for printing.

For each formation in lists/israeli_full.csv we lay out every sticker
on A4 portrait pages with a slightly grey background (so the white
sticker edges show as the cut line), then concatenate the pages into
a single PDF per formation via rsvg-convert.

Output:
  sheets/<slug>-<page>.svg   one SVG per page (kept for inspection)
  sheets/<slug>.pdf          combined multi-page PDF for printing
"""

from __future__ import annotations

import csv
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from generator import (
    FONT_FAMILY,
    HQ_ROLES,
    build_sticker,
    get_icon_svg,
    map_role_to_description,
    role_base_form,
    row_name,
    sticker_width_mm,
)

ROOT = Path(__file__).parent
INPUT_CSV = ROOT / "lists" / "israeli_full.csv"
SHEETS_DIR = ROOT / "sheets"

# A4 portrait, all dimensions in mm.
PAGE_W = 210.0
PAGE_H = 297.0
PAGE_MARGIN = 10.0
TITLE_BAND = 12.0  # vertical space reserved at top for the formation title
GAP = 2.0  # gap between stickers, both axes
STICKER_H = 8.0
SLOT_GAP = 4.0  # extra vertical space between platoons / slots
SHEET_BG = "#E8E8E8"  # slightly grey so the white sticker edges read as cut lines

LAYOUT_X = PAGE_MARGIN
LAYOUT_Y = PAGE_MARGIN + TITLE_BAND
LAYOUT_W = PAGE_W - 2 * PAGE_MARGIN
LAYOUT_H = PAGE_H - LAYOUT_Y - PAGE_MARGIN


def slug(s: str) -> str:
    s = s.lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


_INNER_RE = re.compile(r"<\?xml[^>]*\?>\s*<svg[^>]*>(.*)</svg>\s*$", re.DOTALL)


def extract_inner(svg: str) -> str:
    m = _INNER_RE.match(svg)
    if not m:
        raise ValueError("could not strip outer <svg> wrapper")
    return m.group(1)


def pack_pages(rows: list[dict]) -> list[list[tuple[dict, float, float, int]]]:
    """First-fit pack stickers into pages.

    Each Hebrew formation letter starts on a fresh line with
    `SLOT_GAP` of extra vertical space above it, so each platoon /
    sub-company reads as its own block on the sheet. Returns a list
    of pages, each a list of (row, rel_x, rel_y, width_mm) tuples
    relative to the layout origin.
    """
    pages: list[list[tuple[dict, float, float, int]]] = [[]]
    cursor_x = 0.0
    cursor_y = 0.0
    prev_letter: str | None = None
    for row in rows:
        w = sticker_width_mm(row["base"])
        letter = row["designation"][3:]
        letter_changed = prev_letter is not None and letter != prev_letter

        if letter_changed:
            cursor_x = 0.0
            if pages[-1]:
                cursor_y += STICKER_H + GAP + SLOT_GAP
        elif cursor_x + w > LAYOUT_W + 1e-6:
            cursor_x = 0.0
            cursor_y += STICKER_H + GAP

        if cursor_y + STICKER_H > LAYOUT_H + 1e-6:
            pages.append([])
            cursor_x = 0.0
            cursor_y = 0.0

        pages[-1].append((row, cursor_x, cursor_y, w))
        cursor_x += w + GAP
        prev_letter = letter
    return [p for p in pages if p]


def make_page_svg(
    formation: str,
    page_num: int,
    total_pages: int,
    items: list[tuple[dict, float, float, int]],
    icon_cache: dict[tuple[str, bool], str],
) -> str:
    title = formation
    if total_pages > 1:
        title += f"  —  page {page_num} of {total_pages}"

    sticker_xml: list[str] = []
    for row, rel_x, rel_y, w in items:
        description = map_role_to_description(row["team_role"])
        is_hq = role_base_form(row["team_role"]) in HQ_ROLES
        key = (description, is_hq)
        if key not in icon_cache:
            icon_cache[key] = get_icon_svg(description, is_hq)
        sticker = build_sticker(row["designation"], row_name(row), icon_cache[key], w)
        inner = extract_inner(sticker)
        x = LAYOUT_X + rel_x
        y = LAYOUT_Y + rel_y
        sticker_xml.append(
            f'<svg x="{x:.3f}" y="{y:.3f}" width="{w}" height="{STICKER_H}" '
            f'viewBox="0 0 {w} {STICKER_H}">{inner}</svg>'
        )

    body = "\n  ".join(sticker_xml)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{PAGE_W}mm" height="{PAGE_H}mm"
     viewBox="0 0 {PAGE_W} {PAGE_H}">
  <rect width="{PAGE_W}" height="{PAGE_H}" fill="{SHEET_BG}" />
  <text x="{PAGE_W / 2}" y="{PAGE_MARGIN + 7:.2f}" font-family='{FONT_FAMILY}'
        font-size="5.5" text-anchor="middle" font-weight="bold"
        fill="#222">{title}</text>
  {body}
</svg>
"""


def main() -> int:
    SHEETS_DIR.mkdir(exist_ok=True)
    with INPUT_CSV.open(newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    formations: dict[str, list[dict]] = defaultdict(list)
    for row in all_rows:
        formations[row["formation_name"]].append(row)

    icon_cache: dict[tuple[str, bool], str] = {}
    for formation, rows in sorted(formations.items()):
        # Group by Hebrew formation letter — each letter is one
        # platoon/sub-company in the army (e.g. Mech Inf Co has three
        # platoons under letters ע, פ, צ). Within each letter block,
        # sort numerically by designation; for shared-designation
        # transports the variant name is the tiebreak so the
        # M113/Vayzata/Nagmasho't trio for one stand sits together.
        # Letters sort by Unicode codepoint, which (for every letter
        # in this army, sofit forms included) matches Hebrew
        # alphabetical order.
        def sort_key(r: dict) -> tuple:
            d = r["designation"]
            number = d[:3]  # stand number
            letter = d[3:]  # formation letter
            return (letter, number, r["name"])

        rows.sort(key=sort_key)
        pages = pack_pages(rows)
        slug_name = slug(formation)
        page_files: list[Path] = []
        for i, items in enumerate(pages, start=1):
            svg = make_page_svg(formation, i, len(pages), items, icon_cache)
            path = SHEETS_DIR / f"{slug_name}-{i}.svg"
            path.write_text(svg, encoding="utf-8")
            page_files.append(path)

        pdf_path = SHEETS_DIR / f"{slug_name}.pdf"
        subprocess.run(
            ["rsvg-convert", "-f", "pdf", "-o", str(pdf_path), *map(str, page_files)],
            check=True,
        )
        print(f"  {formation}: {len(rows)} stickers · {len(pages)} pages → {pdf_path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
