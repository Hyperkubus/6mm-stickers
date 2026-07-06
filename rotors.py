#!/usr/bin/env python3
"""Spinning-rotor discs for the helicopter bases, printed on clear film.

Generates one translucent motion-blur disc per helicopter type at true
1:285 rotor diameter, plus packed 330x90 mm plates for the EufyMake E1
(place at 100% in Eufy Studio, same rule as bases.py). The PNGs carry a
real alpha channel: print them on transparent film with the white ink
layer DISABLED so the disc stays see-through.

The look follows the PropBlur style (propblur.com): the film stays
fully clear except for N swept blade smears - each blade nearly solid
at the root (roots barely blur), sweeping back into a long feathered
arc toward the fast-moving tip - plus a solid hub. A thin ring at the
exact rotor radius is the cut guide.

    python rotors.py                         # singles + plates + preview
    python rotors.py --counts ah64=8,ch53=4  # override plate counts
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from bases import DPI, PX_PER_MM

ROOT = Path(__file__).parent
DEFAULT_OUT = ROOT / "rotors"
DEFAULT_TEXTURES = ROOT / "textures"

SCALE = 285.0
SS = 3  # supersampling factor

# diameter / chord in metres (real airframe), blades, plate-count default.
# Counts are physical models, not CSV rows - the CSV's UH-1/CH-53 rows are
# mostly mutually-exclusive transport variants of the same stands.
ROTORS = {
    "ah64": dict(label="AH-64 Peten", diameter=14.63, blades=4, chord=0.53, count=8),
    "ah1": dict(label="AH-1 Tzefa", diameter=13.41, blades=2, chord=0.69, count=8),
    "uh1": dict(label="UH-1", diameter=14.63, blades=2, chord=0.53, count=12),
    "ch53": dict(label="CH-53 Yas'ur", diameter=22.02, blades=6, chord=0.66, count=6),
}

PLATE_MM = (297.0, 90.0)  # A4-transparency strip inside the E1's window
MARGIN_MM = 0.6  # canvas margin around the cut line
GAP_MM = 2.0  # spacing between discs on a plate
CROSSHAIRS = ((5.0, 5.0), (292.0, 85.0))  # LightBurn Print-and-Cut marks
HOLE_MM = 0.6  # center hole diameter for the rotor shaft
CUT = "#ff0000"
ENGRAVE = "#0000ff"

INK = (35, 35, 35)
SWEEP_ROOT_DEG = 10.0  # angular smear at the blade root...
SWEEP_TIP_DEG = 65.0  # ...growing toward the fast-moving tip
SOLID_ROOT = 0.92  # blade-core opacity at the root...
SOLID_TIP = 0.18  # ...feathering out at the tip
FEATHER_POW = 1.7  # trailing-edge falloff sharpness
HUB_MM = 1.3  # solid hub radius at scale
CUT_RING_MM = 0.12
CUT_RING_ALPHA = 0.45


def render_disc(spec: dict) -> Image.Image:
    r_mm = spec["diameter"] * 1000 / SCALE / 2
    chord_mm = spec["chord"] * 1000 / SCALE
    n = spec["blades"]

    size_mm = 2 * (r_mm + MARGIN_MM)
    size = int(round(size_mm * PX_PER_MM)) * SS
    mm_per_px = size_mm / size

    c = (size - 1) / 2
    yy, xx = np.mgrid[0:size, 0:size]
    x = (xx - c) * mm_per_px
    y = (yy - c) * mm_per_px
    r = np.hypot(x, y)
    theta = np.arctan2(y, x)

    rr = np.maximum(r, 0.3)  # keep 1/r finite at the hub

    # PropBlur-style blades: a nearly solid core at the root sweeping
    # back into a feathered arc whose angular length grows with radius
    t = np.clip(r / r_mm, 0, 1)
    sweep = np.radians(SWEEP_ROOT_DEG + (SWEEP_TIP_DEG - SWEEP_ROOT_DEG) * t**1.4)
    solid = SOLID_ROOT + (SOLID_TIP - SOLID_ROOT) * t**1.2
    beta = np.arctan2(chord_mm / 2, rr)  # blade angular half-width at radius r
    alpha = np.zeros_like(r)
    for k in range(n):
        lead = k * 2 * np.pi / n
        d = np.mod(lead - theta, 2 * np.pi)  # trailing distance behind the blade
        d2 = np.minimum(d, 2 * np.pi - d)  # unsigned distance to the blade axis
        half = beta * (1 + 2.5 * t)  # motion blur widens the core toward the tip
        core = solid * np.clip((half - d2) / (0.5 * half), 0, 1)
        smear = 0.9 * solid * np.clip(1 - d / sweep, 0, 1) ** FEATHER_POW
        alpha = np.maximum(alpha, np.maximum(core, smear))

    alpha *= np.clip((r_mm - r) / 0.12, 0, 1)  # anti-aliased rim

    # solid hub, fading into the disc
    alpha = np.maximum(alpha, np.clip((HUB_MM * 1.7 - r) / (HUB_MM * 0.7), 0, 1))

    # cut guide ring at the exact rotor radius
    ring = np.abs(r - r_mm) < CUT_RING_MM / 2
    alpha = np.where(ring, np.maximum(alpha, CUT_RING_ALPHA), alpha)

    rgba = np.zeros((size, size, 4), dtype=np.float64)
    rgba[..., :3] = INK
    rgba[..., 3] = alpha * 255

    # centre drill marker: lighter dot punched into the hub
    rgba[..., :3] = np.where((r < 0.25)[..., None], 120, rgba[..., :3])

    img = Image.fromarray(rgba.round().astype(np.uint8), "RGBA")
    out = img.resize((size // SS, size // SS), Image.LANCZOS)
    return out


def pack_plates(discs: list[tuple[str, Image.Image]]) -> list[list[dict]]:
    """Shelf-pack (type, disc) squares into plates; positions in mm."""
    pw, ph = PLATE_MM
    plates: list[list[dict]] = []
    plate: list[dict] = []
    x = y = shelf_h = 0.0
    for key, disc in sorted(discs, key=lambda d: -d[1].width):
        w = disc.width / PX_PER_MM
        if plate and x + w > pw and y + shelf_h + w > ph:
            plates.append(plate)
            plate, x, y, shelf_h = [], 0.0, 0.0, 0.0
        if x + w > pw:
            y += shelf_h + GAP_MM
            x = shelf_h = 0.0
        plate.append({"key": key, "img": disc, "x": x, "y": y, "w": w})
        x += w + GAP_MM
        shelf_h = max(shelf_h, w)
    if plate:
        plates.append(plate)
    return plates


def write_plate(placed: list[dict], out: Path, n: int, dpi) -> None:
    """Print PNG (discs + magenta Print-and-Cut crosshairs) and the
    matching cut SVG (same crosshairs + disc perimeter + center hole).
    Laser side: LightBurn -> Laser Tools -> Print and Cut, align to the
    two crosshairs, then cut."""
    from PIL import ImageDraw
    pw, ph = PLATE_MM
    img = Image.new("RGBA", (int(round(pw * PX_PER_MM)),
                             int(round(ph * PX_PER_MM))), (0, 0, 0, 0))
    for p in placed:
        img.paste(p["img"], (int(round(p["x"] * PX_PER_MM)),
                             int(round(p["y"] * PX_PER_MM))), p["img"])
    d = ImageDraw.Draw(img)
    lw = max(1, int(round(0.25 * PX_PER_MM)))
    arm = 3 * PX_PER_MM
    for cx, cy in CROSSHAIRS:
        px, py = cx * PX_PER_MM, cy * PX_PER_MM
        d.line((px - arm, py, px + arm, py), fill=(255, 0, 255, 255), width=lw)
        d.line((px, py - arm, px, py + arm), fill=(255, 0, 255, 255), width=lw)
    img.save(out / f"plate-{n}.png", dpi=dpi)

    parts = []
    for cx, cy in CROSSHAIRS:
        parts.append(f'<path d="M{cx - 3},{cy} L{cx + 3},{cy} M{cx},{cy - 3} '
                     f'L{cx},{cy + 3}" fill="none" stroke="{ENGRAVE}" '
                     f'stroke-width="0.1"/>')
    for p in placed:
        r = ROTORS[p["key"]]["diameter"] * 1000 / SCALE / 2
        cx, cy = p["x"] + p["w"] / 2, p["y"] + p["w"] / 2
        parts.append(f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}" '
                     f'fill="none" stroke="{CUT}" stroke-width="0.05"/>')
        parts.append(f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{HOLE_MM / 2}" '
                     f'fill="none" stroke="{CUT}" stroke-width="0.05"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{pw}mm" '
           f'height="{ph}mm" viewBox="0 0 {pw} {ph}">\n'
           + "\n".join(parts) + "\n</svg>")
    (out / f"plate-{n}-cut.svg").write_text(svg, encoding="utf-8")


def render_preview(discs: dict[str, Image.Image], textures: Path) -> Image.Image | None:
    """Composite the four discs over the reference ground texture."""
    ref = textures / "tex_reference.png"
    if not ref.exists():
        return None
    gap = int(round(4 * PX_PER_MM))
    w = sum(d.width for d in discs.values()) + gap * (len(discs) + 1)
    h = max(d.height for d in discs.values()) + 2 * gap
    bg = Image.open(ref).convert("RGBA").resize((w, h))
    x = gap
    for disc in discs.values():
        bg.paste(disc, (x, (h - disc.height) // 2), disc)
        x += disc.width + gap
    return bg


def parse_counts(arg: str | None) -> dict[str, int]:
    counts = {k: v["count"] for k, v in ROTORS.items()}
    for part in (arg or "").split(","):
        if not part.strip():
            continue
        key, _, val = part.partition("=")
        if key.strip() not in counts:
            raise SystemExit(f"Unknown rotor type {key!r} (have {', '.join(counts)})")
        counts[key.strip()] = int(val)
    return counts


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render spinning-rotor discs.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--textures", type=Path, default=DEFAULT_TEXTURES)
    p.add_argument("--counts", help="plate counts, e.g. ah64=8,ah1=8,uh1=12,ch53=6")
    p.add_argument("--seed", type=int, default=1979)
    args = p.parse_args(argv)

    counts = parse_counts(args.counts)
    args.out.mkdir(parents=True, exist_ok=True)
    dpi = (DPI, DPI)

    discs: dict[str, Image.Image] = {}
    for key, spec in ROTORS.items():
        disc = render_disc(spec)
        discs[key] = disc
        disc.save(args.out / f"{key}.png", dpi=dpi)
        d_mm = spec["diameter"] * 1000 / SCALE
        print(f"{key}: {spec['label']}, {d_mm:.1f} mm disc, "
              f"{spec['blades']} blades, x{counts[key]}")

    # each plate copy gets its own blade angle so a flight of four
    # doesn't look photocopied on the table (disc is inscribed in a
    # square canvas, so rotation never clips)
    plate_discs = [
        (k, discs[k].rotate(
            random.Random(f"{args.seed}:rotor:{k}:{i}").uniform(0, 360),
            resample=Image.BICUBIC))
        for k, n in counts.items() for i in range(n)
    ]
    plates = pack_plates(plate_discs)
    for i, placed in enumerate(plates, 1):
        write_plate(placed, args.out, i, dpi)
    print(f"{len(plate_discs)} discs on {len(plates)} plate(s) "
          f"(plate-N.png print + plate-N-cut.svg for LightBurn Print and Cut)")

    preview = render_preview(discs, args.textures)
    if preview is not None:
        preview.save(args.out / "preview.png", dpi=dpi)
        print(f"Wrote {args.out}/preview.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
