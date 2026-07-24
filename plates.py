#!/usr/bin/env python3
"""Custom fixed-layout print plates for a hand-made (3D-printed) jig.

Unlike jig.py — which *generates* a laser-cut jig and lays plates on the
grid it produced — this targets a jig whose pocket layout is already
fixed in the real world (here: a 3D-printed 20x40 jig). You describe the
physical layout (datum corner, first-pocket offset, actual-base spacing,
rows x cols) and it emits:

  align-<class>.png      alignment print: nominal base OUTLINES (no
                         texture) + slot numbers + datum marks, magenta
                         on transparent. Place at 100% at the flatbed
                         origin, print onto a taped scrap, and check the
                         outlines drop onto the real pockets before
                         committing textured plates.
  plate-<class>-NN-color.png / -height.png
                         the real textured plates on the same layout.
  manifest-<class>.csv   plate/slot -> designation/name/position.

Spacing is between ACTUAL base edges. The per-base PNGs carry a 1 mm
bleed ring, so at 5 mm spacing the visible ink gap is 5 - 2*bleed = 3 mm
— the bleed overlaps into the gap on purpose (hides placement error).

The datum corner is the image corner the jig is registered to. Default
'br' (lower-right): base #1's right+bottom edges sit `first` mm from the
image's right+bottom edges; columns march left, rows march up, so slot 1
is the bottom-right pocket.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from argparse import Namespace
from math import ceil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bases import BLEED_MM, DPI, parse_base
from jig import collect_items, mmpx

ROOT = Path(__file__).parent
ORANGE = (255, 102, 0, 255)  # bright orange, alignment marks

# per-class jig geometry (cols, rows) — matches the physical 3D-printed jigs.
# 20x40 9x2 is the calibrated reference; 20x20 9x3 and 40x30 6x2 confirmed;
# 20x30 9x2 with cols still to be confirmed against its jig.
CLASS_GRID = {
    "20x40": (9, 2),
    "20x30": (9, 2),
    "20x20": (9, 3),
    "40x30": (6, 2),
}


def _font(px: int) -> ImageFont.FreeTypeFont:
    """Best-effort legible font; fall back to PIL's bitmap default."""
    for q in ("DejaVu Sans:style=Bold", "monospace"):
        try:
            path = subprocess.run(["fc-match", "-f", "%{file}", q],
                                  capture_output=True, text=True,
                                  check=True).stdout.strip()
            if path:
                return ImageFont.truetype(path, px)
        except Exception:
            pass
    return ImageFont.load_default()


def _arrow_id(dr, font, cx: float, cy: float, num: int, up: bool) -> None:
    """Draw `num` with a small triangle pointing up/down, centered at cx,cy."""
    txt = str(num)
    tw = dr.textlength(txt, font=font)
    aw = ah = mmpx(1.3)
    gap = mmpx(0.4)
    x = cx - (aw + gap + tw) / 2
    ytop, ybot = cy - ah / 2, cy + ah / 2
    axc = x + aw / 2
    tri = ([(axc, ytop), (x, ybot), (x + aw, ybot)] if up
           else [(x, ytop), (x + aw, ytop), (axc, ybot)])
    dr.polygon(tri, fill=ORANGE)
    dr.text((x + aw + gap, cy), txt, fill=ORANGE, font=font, anchor="lm")


def custom_grid(w: float, d: float, plate_w: float, plate_h: float,
                first_x: float, first_y: float, spacing: float,
                cols: int, rows: int,
                origin: str) -> list[tuple[float, float]]:
    """Nominal base top-left (x, y) in PIL image mm, in slot order.

    Slot order fills the datum row first, then inward: r=0 is the row on
    the datum edge, c=0 the column on the datum edge. So for 'br' slot 1
    is bottom-right, slot 2 is one pocket to its left, etc. first_x/first_y
    are the datum-corner offsets to base #1 (they can differ, e.g. the jig
    has 5 mm across, 2 mm along the datum edge).
    """
    pitch_x = w + spacing
    pitch_y = d + spacing
    right = "r" in origin  # datum on the right edge -> columns march left
    bottom = "b" in origin  # datum on the bottom edge -> rows march up
    positions = []
    for r in range(rows):
        for c in range(cols):
            x = (plate_w - first_x - w - c * pitch_x) if right else (first_x + c * pitch_x)
            y = (plate_h - first_y - d - r * pitch_y) if bottom else (first_y + r * pitch_y)
            positions.append((x, y))
    return positions


def render_plate(pockets: list[dict], bases_dir: Path, out: Path, name: str,
                 render_w: float, plate_h: float, content_left: float,
                 ox: float, oy: float, dx_px: int = 0, dy_px: int = 0) -> None:
    """Composite the base PNGs onto a plate cropped to `content_left`.

    Color is RGBA (transparent between/around bases already). Height is
    written LA — grayscale + alpha — so everything outside a base pocket
    is truly transparent, not opaque black (the flatbed lays no relief
    or ink there)."""
    wpx, hpx = mmpx(render_w), mmpx(plate_h)
    color = Image.new("RGBA", (wpx, hpx), (0, 0, 0, 0))
    hgray = Image.new("L", (wpx, hpx), 0)
    halpha = Image.new("L", (wpx, hpx), 0)  # 0 = transparent
    for p in pockets:
        px = mmpx(p["x"] - content_left - ox - BLEED_MM) + dx_px
        py = mmpx(p["y"] - oy - BLEED_MM) + dy_px
        c = Image.open(bases_dir / f"{p['stem']}.png").convert("RGBA")
        h = Image.open(bases_dir / f"{p['stem']}-height.png").convert("L")
        if p["rot"]:
            c = c.transpose(Image.ROTATE_90)
            h = h.transpose(Image.ROTATE_90)
        color.alpha_composite(c, (px, py))
        hgray.paste(h, (px, py))
        halpha.paste(Image.new("L", h.size, 255), (px, py))  # opaque on-base
    color.save(out / f"plate-{name}-color.png", dpi=(DPI, DPI))
    Image.merge("LA", (hgray, halpha)).save(
        out / f"plate-{name}-height.png", dpi=(DPI, DPI))


def write_alignment(out: Path, cls: str, w: float, d: float,
                    positions: list[tuple[float, float]],
                    render_w: float, plate_h: float, content_left: float,
                    origin: str, cols: int, rows: int,
                    dx_px: int = 0, dy_px: int = 0) -> None:
    wpx, hpx = mmpx(render_w), mmpx(plate_h)
    img = Image.new("RGBA", (wpx, hpx), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    lw = max(1, mmpx(0.2))
    ring = 1.0  # rectangle sits 1 mm outside each base = the print bleed edge
    gap_font = _font(mmpx(2.0))

    # datum corner marker (registration reference: br -> lower-right of the
    # cropped image, still base #1's datum corner)
    corners = {"tl": (0, 0), "tr": (wpx - 1, 0),
               "bl": (0, hpx - 1), "br": (wpx - 1, hpx - 1)}
    dx, dy = corners.get(origin, corners["br"])
    sx = -1 if dx else 1  # inward directions
    sy = -1 if dy else 1
    arm = mmpx(8)
    dr.line((dx, dy, dx + sx * arm, dy), fill=ORANGE, width=lw)
    dr.line((dx, dy, dx, dy + sy * arm), fill=ORANGE, width=lw)

    boxes = []
    for x, y in positions:
        x0 = mmpx(x - content_left - ring) + dx_px
        y0 = mmpx(y - ring) + dy_px
        x1 = mmpx(x - content_left + w + ring) + dx_px
        y1 = mmpx(y + d + ring) + dy_px
        dr.rectangle((x0, y0, x1, y1), outline=ORANGE, width=lw)
        boxes.append((x0, y0, x1, y1))

    # slot ids go on the solid bridge between stacked rows (the pockets are
    # hollow, so an id centered in a frame would float over the void), with a
    # triangle pointing to the slot it names: up -> top row, down -> bottom.
    if rows == 2:
        off = mmpx(4.2)
        for c in range(cols):
            bx0, by0, bx1, _ = boxes[c]            # bottom-row slot c+1
            _, _, _, ty1 = boxes[cols + c]         # top-row slot cols+c+1
            cxp = (bx0 + bx1) / 2
            gy = (ty1 + by0) / 2                    # middle of the bridge
            _arrow_id(dr, gap_font, cxp - off, gy, cols + c + 1, up=True)
            _arrow_id(dr, gap_font, cxp + off, gy, c + 1, up=False)
    else:  # 1 or 3+ rows: put each id in the gap on the far side of the
           # pocket from the datum (a solid bridge/margin, never over the
           # hollow cutout), arrow pointing back into its pocket
        bottom = "b" in origin  # rows march up from a bottom datum
        for slot, (x0, y0, x1, y1) in enumerate(boxes, 1):
            cx = (x0 + x1) / 2
            if bottom:
                _arrow_id(dr, gap_font, cx, y0 - mmpx(1.5), slot, up=False)
            else:
                _arrow_id(dr, gap_font, cx, y1 + mmpx(1.5), slot, up=True)

    img.save(out / f"align-{cls}.png", dpi=(DPI, DPI))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", type=Path, default=ROOT / "lists/israeli_minimal.csv")
    p.add_argument("--bases", type=Path, default=ROOT / "bases")
    p.add_argument("--out", type=Path, default=ROOT / "plates")
    p.add_argument("--class", dest="cls", default="20x40",
                   help="pocket class WxD (native + rotated feed it)")
    p.add_argument("--formation", help="substring filter on the formation column")
    p.add_argument("--group", help="exact group letter filter")
    p.add_argument("--plate", default="330x90", help="plate WxH mm (E1 window)")
    p.add_argument("--first-x", type=float, default=5.0,
                   help="datum-corner offset to base #1 across the edge, mm")
    p.add_argument("--first-y", type=float, default=2.0,
                   help="datum-corner offset to base #1 along the edge, mm")
    p.add_argument("--spacing", type=float, default=5.0,
                   help="gap between ACTUAL base edges, mm")
    p.add_argument("--cols", type=int, default=None,
                   help="columns (default: per-class jig geometry, see CLASS_GRID)")
    p.add_argument("--rows", type=int, default=None,
                   help="rows (default: per-class jig geometry, see CLASS_GRID)")
    p.add_argument("--origin", default="br", choices=["tl", "tr", "bl", "br"],
                   help="image corner the jig is registered to (default br)")
    p.add_argument("--no-rotate", dest="rotate", action="store_false",
                   help="keep wide bases landscape instead of rotating upright")
    p.add_argument("--origin-x", type=float, default=0.0,
                   help="printable-window origin offset, mm")
    p.add_argument("--origin-y", type=float, default=0.0)
    p.add_argument("--shift-x", type=float, default=0.0,
                   help="nudge all content toward the datum corner, mm "
                        "(margin correction; positive = toward the origin)")
    p.add_argument("--shift-y", type=float, default=0.0)
    p.add_argument("--align-only", action="store_true",
                   help="write only the alignment print, skip textured plates")
    args = p.parse_args(argv)

    # per-class jig geometry (cols x rows). Physical calibration, not derivable:
    #   20x40 9x2 (calibrated), 20x20 9x3, 40x30 objectives 6x2 (all confirmed);
    #   20x30 9x2 assumed (cols unconfirmed). --cols/--rows override.
    dcols, drows = CLASS_GRID.get(args.cls, (9, 2))
    if args.cols is None:
        args.cols = dcols
    if args.rows is None:
        args.rows = drows

    plate_w, plate_h = parse_base(args.plate)
    cw, cd = parse_base(args.cls)

    gather = Namespace(csv=args.csv, formation=args.formation, group=args.group,
                       objectives=0, rotate=args.rotate)
    members = [it for it in collect_items(gather)
               if it["w"] == cw and it["d"] == cd]
    if not members:
        print(f"No bases in class {args.cls}.")
        return 1

    # fill order: by designation letter then number (e.g. א001 < א002 <
    # ב001). Hebrew letters sort in aleph-bet order by codepoint, so each
    # company stays contiguous across plates.
    def desig_key(it: dict) -> tuple[str, int]:
        m = re.match(r"(\D*?)(\d*)$", it["designation"].strip())
        return (m.group(1), int(m.group(2)) if m.group(2) else 0)

    members.sort(key=desig_key)

    positions = custom_grid(cw, cd, plate_w, plate_h, args.first_x, args.first_y,
                            args.spacing, args.cols, args.rows, args.origin)
    per_plate = len(positions)
    # crop the empty side off: left edge = leftmost pocket's bleed edge
    content_left = min(x for x, _ in positions) - BLEED_MM
    render_w = plate_w - content_left

    # geometry sanity: warn if any pocket (with bleed) escapes the plate
    for x, y in positions:
        if x < 0 or y < 0 or x + cw > plate_w or y + cd > plate_h:
            print(f"WARNING: pocket at ({x:.1f},{y:.1f}) exceeds the "
                  f"{plate_w:.0f}x{plate_h:.0f} plate", flush=True)
            break

    # margin nudge toward the datum corner (br -> down-right), in px
    toward_x = 1 if "r" in args.origin else -1
    toward_y = 1 if "b" in args.origin else -1
    dx_px = toward_x * mmpx(args.shift_x)
    dy_px = toward_y * mmpx(args.shift_y)

    # one subfolder per base size so the classes don't intermingle
    out_dir = args.out / args.cls
    out_dir.mkdir(parents=True, exist_ok=True)
    write_alignment(out_dir, args.cls, cw, cd, positions,
                    render_w, plate_h, content_left, args.origin,
                    args.cols, args.rows, dx_px, dy_px)
    print(f"Wrote {out_dir}/align-{args.cls}.png "
          f"({per_plate} slots, {args.cols}x{args.rows}, datum {args.origin})")

    if args.align_only:
        return 0

    n_plates = ceil(len(members) / per_plate)
    with (out_dir / f"manifest-{args.cls}.csv").open(
            "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["class", "plate", "slot", "x_mm", "y_mm",
                     "designation", "name"])
        for n in range(1, n_plates + 1):
            batch = members[(n - 1) * per_plate:n * per_plate]
            loaded = [dict(it, x=positions[i][0], y=positions[i][1])
                      for i, it in enumerate(batch)]
            render_plate(loaded, args.bases, out_dir,
                         f"{args.cls}-{n:02d}", render_w, plate_h,
                         content_left, args.origin_x, args.origin_y,
                         dx_px, dy_px)
            for slot, pk in enumerate(loaded, 1):
                wr.writerow([args.cls, n, slot, f"{pk['x']:.2f}",
                             f"{pk['y']:.2f}", pk["designation"], pk["name"]])

    print(f"Wrote {n_plates} plates ({len(members)} bases, {per_plate}/plate) "
          f"to {out_dir}, plus manifest-{args.cls}.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
