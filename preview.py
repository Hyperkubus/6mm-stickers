#!/usr/bin/env python3
"""Render preview.html — one sample sticker per unique (icon, label) combination.

Each sample is rendered to PNG via rsvg-convert and embedded as a base64 data URI
so the page is self-contained.
"""

from __future__ import annotations

import base64
import csv
import html
import shutil
import subprocess
from pathlib import Path

from generator import (
    INPUT_CSV,
    OUT_DIR,
    map_role_to_description,
    role_base_form,
    row_name,
    sticker_width_mm,
    HQ_ROLES,
)

ROOT = Path(__file__).parent
PREVIEW_HTML = ROOT / "preview.html"
PREVIEW_DPI = 600


def render_png_data_uri(svg_path: Path) -> str:
    out = subprocess.run(
        ["rsvg-convert", "-d", str(PREVIEW_DPI), "-p", str(PREVIEW_DPI), str(svg_path)],
        check=True, capture_output=True,
    )
    return "data:image/png;base64," + base64.b64encode(out.stdout).decode("ascii")


def render_svg_data_uri(svg_path: Path) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg_path.read_bytes()).decode("ascii")


def main() -> int:
    has_rsvg = shutil.which("rsvg-convert") is not None
    render = render_png_data_uri if has_rsvg else render_svg_data_uri

    with INPUT_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    seen: dict[tuple[str, bool, str, int], dict] = {}
    for row in rows:
        team_role = row["team_role"]
        unit_name = row["unit_name"]
        description = map_role_to_description(team_role)
        is_hq = role_base_form(team_role) in HQ_ROLES
        name = row_name(row)
        width = sticker_width_mm(row["base"])
        key = (description, is_hq, name, width)
        if key not in seen:
            seen[key] = {
                "description": description,
                "is_hq": is_hq,
                "name": name,
                "width": width,
                "team_role": team_role,
                "unit_name": unit_name,
                "designation": row["designation"],
                "base": row["base"],
            }

    samples = sorted(seen.values(), key=lambda s: (s["width"], s["description"], s["name"]))

    cards = []
    for s in samples:
        svg_path = OUT_DIR / f"{s['designation']}.svg"
        if not svg_path.exists():
            continue
        uri = render(svg_path)
        cards.append(f"""
        <figure class="sticker">
          <img src="{uri}" alt="{html.escape(s['designation'])}" />
          <figcaption>
            <div><b>{html.escape(s['designation'])}</b> &middot; {s['width']}×8 mm</div>
            <div>{html.escape(s['name'])} &middot; {html.escape(s['description'])}{' + HQ' if s['is_hq'] else ''}</div>
            <div class="muted">{html.escape(s['team_role'])} / {html.escape(s['unit_name'])}</div>
          </figcaption>
        </figure>""")

    PREVIEW_HTML.write_text(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8" />
<title>6mm IDF Sticker Preview</title>
<style>
  body {{ font: 14px/1.4 -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f5; margin: 24px; }}
  h1 {{ font-size: 18px; margin: 0 0 16px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }}
  figure.sticker {{ background: white; padding: 12px; margin: 0; border: 1px solid #ddd; border-radius: 6px; }}
  figure.sticker img {{ display: block; height: 64px; width: auto; image-rendering: pixelated; }}
  figcaption {{ margin-top: 8px; font-size: 12px; }}
  .muted {{ color: #888; font-size: 11px; margin-top: 4px; }}
</style>
</head><body>
<h1>IDF Team Yankee Stickers — {len(cards)} unique (icon × label × width)</h1>
<div class="grid">{''.join(cards)}</div>
</body></html>
""")
    print(f"Wrote {PREVIEW_HTML} with {len(cards)} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
