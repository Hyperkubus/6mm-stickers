#!/usr/bin/env python3
"""Render per-formation cut-out sticker sheets for printing.

Groups rows by the optional `formation` column and lays each formation
out on A4 portrait pages with a slightly grey background (so the white
sticker edges show as the cut line). Pages are concatenated into one
PDF per formation via `rsvg-convert -f pdf`.

Output:
  sheets/<slug>-<page>.svg   one SVG per page (kept for inspection)
  sheets/<slug>.pdf          combined multi-page PDF for printing

Within a formation, rows are kept in CSV order. Whenever the `group`
column changes, a fresh line starts (with extra vertical space) so each
platoon / sub-block reads as its own band.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

from generator import (
    FONT_FAMILY,
    add_common_args,
    build_sticker,
    get_icon_svg,
    load_flag,
    parse_bool,
    resolve_background,
    row_width,
)

ROOT = Path(__file__).parent
DEFAULT_SHEETS_DIR = ROOT / "sheets"

# A4 portrait, all dimensions in mm.
PAGE_W = 210.0
PAGE_H = 297.0
PAGE_MARGIN = 10.0
TITLE_BAND = 12.0
GAP = 2.0
STICKER_H = 8.0
SLOT_GAP = 4.0
SHEET_BG = "#E8E8E8"

LAYOUT_X = PAGE_MARGIN
LAYOUT_Y = PAGE_MARGIN + TITLE_BAND
LAYOUT_W = PAGE_W - 2 * PAGE_MARGIN
LAYOUT_H = PAGE_H - LAYOUT_Y - PAGE_MARGIN


def slug(s: str) -> str:
    s = s.lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "sheet"


_INNER_RE = re.compile(r"<\?xml[^>]*\?>\s*<svg[^>]*>(.*)</svg>\s*$", re.DOTALL)


def extract_inner(svg: str) -> str:
    m = _INNER_RE.match(svg)
    if not m:
        raise ValueError("could not strip outer <svg> wrapper")
    return m.group(1)


def pack_pages(rows: list[dict]) -> list[list[tuple[dict, float, float, int]]]:
    """First-fit pack stickers into pages, breaking lines on `group` changes."""
    pages: list[list[tuple[dict, float, float, int]]] = [[]]
    cursor_x = 0.0
    cursor_y = 0.0
    prev_group: str | None = None
    for row in rows:
        w = row_width(row)
        group = (row.get("group") or "").strip()
        group_changed = prev_group is not None and group != prev_group

        if group_changed:
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
        prev_group = group
    return [p for p in pages if p]


def make_page_svg(
    formation: str,
    page_num: int,
    total_pages: int,
    items: list[tuple[dict, float, float, int]],
    affiliation: str,
    bg: str,
    flag_inner: str,
    flag_vb: str,
    icon_cache: dict[tuple[str, bool], str],
) -> str:
    title = formation
    if total_pages > 1:
        title += f"  —  page {page_num} of {total_pages}"

    sticker_xml: list[str] = []
    for row, rel_x, rel_y, w in items:
        symbol = (row.get("symbol") or "").strip()
        is_hq = parse_bool(row.get("hq"))
        key = (symbol, is_hq)
        if key not in icon_cache:
            icon_cache[key] = get_icon_svg(affiliation, symbol, is_hq)
        sticker = build_sticker(
            row["designation"], row["name"], icon_cache[key], w,
            bg, flag_inner, flag_vb,
        )
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


def group_by_formation(rows: list[dict]) -> "OrderedDict[str, list[dict]]":
    out: OrderedDict[str, list[dict]] = OrderedDict()
    for r in rows:
        f = (r.get("formation") or "").strip() or "stickers"
        out.setdefault(f, []).append(r)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render per-formation A4 sticker sheets.")
    add_common_args(p)
    p.add_argument("--out", type=Path, default=DEFAULT_SHEETS_DIR,
                   help="Output directory for the per-formation SVGs/PDFs.")
    args = p.parse_args(argv)

    if not args.csv.exists():
        print(f"Missing input: {args.csv}", file=sys.stderr)
        return 1

    bg = resolve_background(args)
    flag_inner, flag_vb = load_flag(args.country, args.flag)

    args.out.mkdir(exist_ok=True, parents=True)
    with args.csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    formations = group_by_formation(rows)
    icon_cache: dict[tuple[str, bool], str] = {}
    for formation, formation_rows in formations.items():
        pages = pack_pages(formation_rows)
        slug_name = slug(formation)
        page_files: list[Path] = []
        for i, items in enumerate(pages, start=1):
            svg = make_page_svg(
                formation, i, len(pages), items,
                args.affiliation, bg, flag_inner, flag_vb, icon_cache,
            )
            path = args.out / f"{slug_name}-{i}.svg"
            path.write_text(svg, encoding="utf-8")
            page_files.append(path)

        pdf_path = args.out / f"{slug_name}.pdf"
        subprocess.run(
            ["rsvg-convert", "-f", "pdf", "-o", str(pdf_path), *map(str, page_files)],
            check=True,
        )
        print(f"  {formation}: {len(formation_rows)} stickers · {len(pages)} pages → {pdf_path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
