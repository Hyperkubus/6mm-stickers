#!/usr/bin/env python3
"""Render a visual sample of base print files to bases_preview.html.

Picks a handful of bases per texture variant (plus objectives), renders
them with the exact same seeded pipeline as bases.py, and embeds the
color + heightmap pairs side by side as base64 PNGs, upscaled for
on-screen inspection. Nothing here affects the print files.
"""

from __future__ import annotations

import argparse
import base64
import csv
import sys
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from PIL import Image

from generator import (
    add_common_args,
    build_sticker,
    get_icon_svg,
    load_flag,
    parse_bool,
    resolve_background,
)
from bases import (
    DEFAULT_TEXTURES,
    OBJECTIVE_BASE,
    OBJECTIVE_VARIANT,
    Textures,
    parse_base,
    render_base,
    row_rng,
    variant_for_platoon,
)

ROOT = Path(__file__).parent
DEFAULT_HTML = ROOT / "bases_preview.html"

ZOOM = 4  # on-screen upscale factor
PER_VARIANT = 3


def to_data_uri(img: Image.Image) -> str:
    img = img.resize((img.width * ZOOM, img.height * ZOOM), Image.NEAREST)
    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render bases_preview.html.")
    add_common_args(p)
    p.add_argument("--textures", type=Path, default=DEFAULT_TEXTURES)
    p.add_argument("--seed", type=int, default=1979)
    p.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = p.parse_args(argv)

    if not args.csv.exists():
        print(f"Missing input: {args.csv}", file=sys.stderr)
        return 1

    bg = resolve_background(args)
    flag_inner, flag_vb = load_flag(args.country, args.flag)
    textures = Textures(args.textures)

    with args.csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # Sample: for each variant, a few rows with distinct base sizes.
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not ((row.get("base") or "").strip()):
            continue
        v = variant_for_platoon(
            args.seed, row.get("formation") or "", row.get("group") or "")
        seen_bases = {r["base"] for r in by_variant[v]}
        if len(by_variant[v]) < PER_VARIANT and row["base"] not in seen_bases:
            by_variant[v].append(row)

    icon_cache: dict[tuple[str, bool], str] = {}
    cards: list[str] = []

    def card(title: str, sub: str, color: Image.Image, height: Image.Image) -> str:
        return (
            f'<div class="card"><div class="t">{title}</div>'
            f'<div class="s">{sub}</div>'
            f'<img src="{to_data_uri(color)}"><img src="{to_data_uri(height)}">'
            f"</div>"
        )

    for variant in sorted(by_variant):
        for row in by_variant[variant]:
            base_w, base_d = parse_base(row["base"])
            symbol = (row.get("symbol") or "").strip()
            is_hq = parse_bool(row.get("hq"))
            key = (symbol, is_hq)
            if key not in icon_cache:
                icon_cache[key] = get_icon_svg(args.affiliation, symbol, is_hq)
            sticker_svg = build_sticker(
                row["designation"], row["name"], icon_cache[key], base_w,
                bg, flag_inner, flag_vb,
            )
            rng = row_rng(args.seed, row["designation"], row["name"])
            color, height = render_base(
                textures, variant, base_w, base_d, rng, sticker_svg,
                sticker_bg=bg)
            cards.append(card(
                f"{row['designation']} · {row['name']}",
                f"{variant} · {row['base']} mm · {row['formation']}",
                color, height,
            ))

    for i in (1, 2):
        ow, od = parse_base(OBJECTIVE_BASE)
        rng = row_rng(args.seed, f"OBJ{i:02d}", "objective")
        color, height = render_base(
            textures, OBJECTIVE_VARIANT, ow, od, rng, None, objective=True)
        cards.append(card(f"OBJ{i:02d}", f"{OBJECTIVE_VARIANT} · {OBJECTIVE_BASE} mm",
                          color, height))

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Base print preview</title>
<style>
  body {{ background:#2b2b2b; color:#ddd; font-family:sans-serif; margin:20px; }}
  .grid {{ display:flex; flex-wrap:wrap; gap:16px; }}
  .card {{ background:#3a3a3a; padding:10px; border-radius:6px; }}
  .card img {{ display:inline-block; margin-right:8px; vertical-align:bottom;
               image-rendering:pixelated; }}
  .t {{ font-weight:bold; }}
  .s {{ font-size:12px; color:#999; margin-bottom:8px; }}
</style></head><body>
<h2>Base print files — sample ({ZOOM}× zoom, color + heightmap)</h2>
<div class="grid">{''.join(cards)}</div>
</body></html>
"""
    args.html.write_text(html, encoding="utf-8")
    print(f"Wrote {args.html} with {len(cards)} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
