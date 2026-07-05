#!/usr/bin/env python3
"""Generate per-base print files for the EufyMake E1 flatbed.

For every CSV row (one row per base) this renders a pair of PNGs under
bases/:

  {designation}-{slug}.png         color: ground-texture crop with the
                                   unit sticker composited into the lower
                                   8 mm of the base
  {designation}-{slug}-height.png  aligned greyscale heightmap for relief
                                   printing (white = raised, sticker area
                                   flattened to 0)

Physical scale is locked to the validated texture scale: the source
textures are 130 mm wide at 1536 px, i.e. ~11.815 px/mm (~300 DPI).
Never let Eufy Studio rescale ("fit to bed") — place at 100%.

Each crop gets a 1 mm bleed ring on every side (print mode: pre-cut
bases positioned on a jig, so overspray hides placement error). The
sticker bleeds with it: its background color extends to the crop edges
on left/right/bottom, while the printed content (and the sticker's top
edge, an interior boundary) stays on the nominal base outline.

Texture variants: unit bases draw from reference/v1_rocky/v2_soil/
v3_grass, assigned per platoon — every base of one (formation, group)
uses the same variant but its own random crop and 90-degree rotation.
v4_track is reserved for objectives (--objectives N, 40x30 mm, no
sticker), cropped along the vehicle track.

All randomness is seeded from --seed plus stable row keys, so reruns
reproduce identical files until the seed changes.

Preprocessing (validated against a physical test print — the E1
compresses midtones) is applied to the vendored textures in code:
color-match v1-v4 to the reference, contrast and saturation +18%,
shadow lift so basalt doesn't sink to black, extra sharpening for the
soft v3.
"""

from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
from pathlib import Path

import csv

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from generator import (
    add_common_args,
    build_sticker,
    get_icon_svg,
    load_flag,
    parse_bool,
    resolve_background,
)

ROOT = Path(__file__).parent
DEFAULT_OUT = ROOT / "bases"
DEFAULT_TEXTURES = ROOT / "textures"

# 130 mm wide at 1536 px — the validated physical scale. Do not change.
PX_PER_MM = 1536 / 130.0
DPI = PX_PER_MM * 25.4

BLEED_MM = 1.0
STICKER_H_MM = 8.0

UNIT_VARIANTS = ["reference", "v1_rocky", "v2_soil", "v3_grass"]
OBJECTIVE_VARIANT = "v4_track"
OBJECTIVE_BASE = "40x30"

# v4 vehicle track, endpoints in source-texture px (eyeballed from the
# image; the track runs top-center to bottom-right). Objective crops are
# centred on this line, which also keeps them away from the repetitive
# scree areas near the top-left and right edges.
TRACK_P0 = (540.0, 0.0)
TRACK_P1 = (1450.0, 1024.0)


def mm_to_px(mm: float) -> int:
    return round(mm * PX_PER_MM)


def parse_base(value: str) -> tuple[int, int]:
    """`"20x40"` → (width 20, depth 40), sticker always spans the width."""
    m = re.fullmatch(r"(\d+)x(\d+)", value.strip())
    if not m:
        raise ValueError(f"Bad base size: {value!r} (expected e.g. 20x40)")
    return int(m.group(1)), int(m.group(2))


# ---------------------------------------------------------------------------
# Texture loading + preprocessing
# ---------------------------------------------------------------------------

def _match_color(img: np.ndarray, ref: np.ndarray) -> np.ndarray:
    """Per-channel mean shift so all variants sit in one palette.

    Means only, deliberately: matching std too would import the
    reference's contrast and turn the low-contrast v3 into coffee
    grounds. Each variant keeps its own contrast character.
    """
    out = img.copy()
    for c in range(3):
        out[..., c] = img[..., c] - img[..., c].mean() + ref[..., c].mean()
    return out


def _shadow_lift(img: np.ndarray, lift: float = 10.0) -> np.ndarray:
    """Raise the darkest tones without touching mids/highs."""
    return img + lift * (1.0 - img / 255.0) ** 2


class Textures:
    """Preprocessed color + heightmap arrays for every variant."""

    def __init__(self, tex_dir: Path):
        ref_raw = np.asarray(
            Image.open(tex_dir / "tex_reference.png").convert("RGB"), dtype=np.float32
        )
        self.color: dict[str, Image.Image] = {}
        self.height: dict[str, Image.Image] = {}
        self.gray: dict[str, np.ndarray] = {}  # downscaled luminance, crop scoring
        for variant in UNIT_VARIANTS + [OBJECTIVE_VARIANT]:
            arr = np.asarray(
                Image.open(tex_dir / f"tex_{variant}.png").convert("RGB"),
                dtype=np.float32,
            )
            if variant != "reference":
                arr = _match_color(arr, ref_raw)
            img = Image.fromarray(
                np.clip(arr, 0, 255).astype(np.uint8), "RGB"
            )
            img = ImageEnhance.Contrast(img).enhance(1.18)
            img = ImageEnhance.Color(img).enhance(1.18)
            arr = _shadow_lift(np.asarray(img, dtype=np.float32))
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
            if variant == "v3_grass":
                img = img.filter(
                    ImageFilter.UnsharpMask(radius=2, percent=100, threshold=2)
                )
            self.color[variant] = img
            self.height[variant] = Image.open(
                tex_dir / f"heightmap_{variant}.png"
            ).convert("L")
            g = np.asarray(img.convert("L"), dtype=np.float32)
            self.gray[variant] = g[::4, ::4]


# ---------------------------------------------------------------------------
# Crop selection
# ---------------------------------------------------------------------------

def _random_box(rng: random.Random, tex_w: int, tex_h: int, w: int, h: int) -> tuple[int, int]:
    return rng.randrange(tex_w - w + 1), rng.randrange(tex_h - h + 1)


def _feature_score(gray4: np.ndarray, x: int, y: int, w: int, h: int, thresh: float) -> float:
    """Fraction of dark (rock/scrub) pixels inside the crop, on the /4 grid."""
    tile = gray4[y // 4:(y + h) // 4, x // 4:(x + w) // 4]
    return float((tile < thresh).mean())


def pick_crop(
    textures: Textures,
    variant: str,
    rng: random.Random,
    w_px: int,
    h_px: int,
    objective: bool = False,
) -> tuple[int, int, int]:
    """Return (x, y, rot90_steps) for a crop of w_px × h_px (pre-rotation)."""
    tex = textures.color[variant]
    rot = rng.randrange(4)
    cw, ch = (h_px, w_px) if rot % 2 else (w_px, h_px)

    if objective:
        # Centre the crop on the vehicle track, jittered along + across it.
        t = rng.uniform(0.12, 0.88)
        cx = TRACK_P0[0] + t * (TRACK_P1[0] - TRACK_P0[0]) + rng.uniform(-40, 40)
        cy = TRACK_P0[1] + t * (TRACK_P1[1] - TRACK_P0[1]) + rng.uniform(-40, 40)
        x = round(min(max(cx - cw / 2, 0), tex.width - cw))
        y = round(min(max(cy - ch / 2, 0), tex.height - ch))
        return x, y, rot

    if variant == "v3_grass":
        # v3 is nearly featureless; take the first candidate crop with at
        # least a little rock/scrub in it (fall back to the best of the
        # batch). First-acceptable rather than rockiest-of-N keeps variety.
        gray4 = textures.gray[variant]
        thresh = float(np.percentile(gray4, 8))
        best, best_score = None, -1.0
        for _ in range(8):
            x, y = _random_box(rng, tex.width, tex.height, cw, ch)
            score = _feature_score(gray4, x, y, cw, ch, thresh)
            if score >= 0.02:
                return x, y, rot
            if score > best_score:
                best, best_score = (x, y), score
        return best[0], best[1], rot

    x, y = _random_box(rng, tex.width, tex.height, cw, ch)
    return x, y, rot


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def rasterize_sticker(svg: str, w_px: int, h_px: int) -> Image.Image:
    from io import BytesIO
    out = subprocess.run(
        ["rsvg-convert", "-w", str(w_px), "-h", str(h_px), "-f", "png"],
        input=svg.encode("utf-8"), capture_output=True, check=True,
    )
    return Image.open(BytesIO(out.stdout)).convert("RGB")


def render_base(
    textures: Textures,
    variant: str,
    base_w_mm: int,
    base_d_mm: int,
    rng: random.Random,
    sticker_svg: str | None,
    sticker_bg: str = "#FFFFFF",
    objective: bool = False,
) -> tuple[Image.Image, Image.Image]:
    """Render one base → (color PNG image, heightmap PNG image)."""
    w_px = mm_to_px(base_w_mm + 2 * BLEED_MM)
    h_px = mm_to_px(base_d_mm + 2 * BLEED_MM)
    x, y, rot = pick_crop(textures, variant, rng, w_px, h_px, objective=objective)
    cw, ch = (h_px, w_px) if rot % 2 else (w_px, h_px)

    def crop_rot(img: Image.Image) -> Image.Image:
        tile = img.crop((x, y, x + cw, y + ch))
        if rot:
            tile = tile.rotate(90 * rot, expand=True)
        return tile

    color = crop_rot(textures.color[variant])
    height = crop_rot(textures.height[variant])

    bleed_px = mm_to_px(BLEED_MM)
    if sticker_svg is not None:
        sw = mm_to_px(base_w_mm)
        sh = mm_to_px(STICKER_H_MM)
        sticker = rasterize_sticker(sticker_svg, sw, sh)
        sx = bleed_px
        sy = h_px - bleed_px - sh  # anchored to the nominal base bottom edge
        # The sticker bleeds too: fill background color out to the crop
        # edges on left/right/bottom so a placement error shows sticker
        # color, not a texture sliver. The top edge is an interior
        # boundary on the base and stays nominal.
        ImageDraw.Draw(color).rectangle((0, sy, w_px, h_px), fill=sticker_bg)
        color.paste(sticker, (sx, sy))
        # Flatten the sticker area (incl. bleed) so ink lands level.
        height.paste(0, (0, sy, w_px, h_px))

    return color, height


def save_pair(color: Image.Image, height: Image.Image, out: Path, stem: str) -> None:
    color.save(out / f"{stem}.png", dpi=(DPI, DPI))
    height.save(out / f"{stem}-height.png", dpi=(DPI, DPI))


def base_stem(designation: str, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "base"
    return f"{designation}-{slug}"


def variant_for_platoon(seed: int, formation: str, group: str) -> str:
    rng = random.Random(f"{seed}:variant:{formation}:{group}")
    return rng.choice(UNIT_VARIANTS)


def row_rng(seed: int, designation: str, name: str) -> random.Random:
    return random.Random(f"{seed}:crop:{designation}:{name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Render per-base texture+sticker print files for the E1 flatbed.")
    add_common_args(p)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory.")
    p.add_argument("--textures", type=Path, default=DEFAULT_TEXTURES,
                   help="Directory with tex_*.png / heightmap_*.png.")
    p.add_argument("--seed", type=int, default=1979,
                   help="Master seed for crop/variant assignment (default: 1979).")
    p.add_argument("--objectives", type=int, default=0,
                   help="Also render N 40x30 objective bases from the v4 track texture.")
    p.add_argument("--formation", default=None,
                   help="Only render rows whose formation contains this substring.")
    args = p.parse_args(argv)

    if not args.csv.exists():
        print(f"Missing input: {args.csv}", file=sys.stderr)
        return 1

    bg = resolve_background(args)
    flag_inner, flag_vb = load_flag(args.country, args.flag)
    textures = Textures(args.textures)
    args.out.mkdir(exist_ok=True, parents=True)

    with args.csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if args.formation:
        rows = [r for r in rows
                if args.formation.lower() in (r.get("formation") or "").lower()]

    icon_cache: dict[tuple[str, bool], str] = {}
    written = 0
    for row in rows:
        designation = (row.get("designation") or "").strip()
        name = (row.get("name") or "").strip()
        symbol = (row.get("symbol") or "").strip()
        base = (row.get("base") or "").strip()
        if not (designation and name and symbol and base):
            print(f"Skipping incomplete row (designation={designation!r}, "
                  f"base={base!r})", file=sys.stderr)
            continue

        base_w, base_d = parse_base(base)
        is_hq = parse_bool(row.get("hq"))
        key = (symbol, is_hq)
        if key not in icon_cache:
            icon_cache[key] = get_icon_svg(args.affiliation, symbol, is_hq)
        sticker_svg = build_sticker(
            designation, name, icon_cache[key], base_w, bg, flag_inner, flag_vb,
        )

        variant = variant_for_platoon(
            args.seed, row.get("formation") or "", row.get("group") or "")
        rng = row_rng(args.seed, designation, name)
        color, height = render_base(
            textures, variant, base_w, base_d, rng, sticker_svg, sticker_bg=bg)
        save_pair(color, height, args.out, base_stem(designation, name))
        written += 1

    for i in range(1, args.objectives + 1):
        ow, od = parse_base(OBJECTIVE_BASE)
        rng = row_rng(args.seed, f"OBJ{i:02d}", "objective")
        color, height = render_base(
            textures, OBJECTIVE_VARIANT, ow, od, rng, None, objective=True)
        save_pair(color, height, args.out, f"OBJ{i:02d}-objective")
        written += 1

    print(f"Wrote {written} base pairs (color + height) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
