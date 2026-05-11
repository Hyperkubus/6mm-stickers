#!/usr/bin/env python3
"""Render preview.html — one sample sticker per unique (symbol, label, width).

Each sample is rendered to PNG via rsvg-convert and embedded as a base64
data URI so the page is self-contained.
"""

from __future__ import annotations

import argparse
import base64
import csv
import html
import shutil
import subprocess
import sys
from pathlib import Path

from generator import (
    DEFAULT_OUT,
    add_common_args,
    parse_bool,
    resolve_background,
    row_width,
    sticker_filename,
)

ROOT = Path(__file__).parent
DEFAULT_PREVIEW = ROOT / "preview.html"
PREVIEW_DPI = 600


def render_png_data_uri(svg_path: Path) -> str:
    out = subprocess.run(
        ["rsvg-convert", "-d", str(PREVIEW_DPI), "-p", str(PREVIEW_DPI), str(svg_path)],
        check=True, capture_output=True,
    )
    return "data:image/png;base64," + base64.b64encode(out.stdout).decode("ascii")


def render_svg_data_uri(svg_path: Path) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg_path.read_bytes()).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render a preview HTML of every unique sticker.")
    add_common_args(p)
    p.add_argument("--out-stickers", type=Path, default=DEFAULT_OUT,
                   help="Directory where generator.py wrote the per-sticker SVGs.")
    p.add_argument("--out", type=Path, default=DEFAULT_PREVIEW,
                   help="Output HTML path.")
    args = p.parse_args(argv)

    bg = resolve_background(args)

    has_rsvg = shutil.which("rsvg-convert") is not None
    render = render_png_data_uri if has_rsvg else render_svg_data_uri

    if not args.csv.exists():
        print(f"Missing input: {args.csv}", file=sys.stderr)
        return 1

    with args.csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    seen: dict[tuple[str, bool, str, int], dict] = {}
    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        name = (row.get("name") or "").strip()
        designation = (row.get("designation") or "").strip()
        if not (symbol and name and designation):
            continue
        is_hq = parse_bool(row.get("hq"))
        width = row_width(row)
        key = (symbol, is_hq, name, width)
        if key not in seen:
            seen[key] = {
                "symbol": symbol, "is_hq": is_hq, "name": name, "width": width,
                "designation": designation,
                "formation": (row.get("formation") or "").strip(),
            }

    samples = sorted(seen.values(), key=lambda s: (s["width"], s["symbol"], s["name"]))

    cards = []
    for s in samples:
        svg_path = args.out_stickers / sticker_filename(s["designation"], s["name"])
        if not svg_path.exists():
            continue
        uri = render(svg_path)
        cards.append(f"""
        <figure class="sticker">
          <img src="{uri}" alt="{html.escape(s['designation'])}" />
          <figcaption>
            <div><b>{html.escape(s['designation'])}</b> &middot; {s['width']}×8 mm</div>
            <div>{html.escape(s['name'])} &middot; {html.escape(args.affiliation)} {html.escape(s['symbol'])}{' + HQ' if s['is_hq'] else ''}</div>
            <div class="muted">{html.escape(s['formation'])}</div>
          </figcaption>
        </figure>""")

    args.out.write_text(f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8" />
<title>6mm Sticker Preview</title>
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
<h1>{html.escape(args.csv.name)} — {len(cards)} unique stickers ({html.escape(args.affiliation)}, bg {bg})</h1>
<div class="grid">{''.join(cards)}</div>
</body></html>
""", encoding="utf-8")
    print(f"Wrote {args.out} with {len(cards)} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
