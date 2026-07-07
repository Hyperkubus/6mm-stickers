#!/usr/bin/env python3
"""Jig + print-plate generator for the EufyMake E1 flatbed.

One REUSABLE jig per pocket geometry, uniform print plates that all
share it, and dense blank-cutting sheets — instead of a bespoke jig
per print job. Wide (40x20) bases are rotated upright so they share
the tank jig; the class list collapses to 20x40 / 20x30 / 20x20
(+ 40x30 objectives).

Outputs under jig/:

  jig-<class>.svg        one reusable jig strip per pocket class
                         (kerf-compensated holes, engraved slot
                         numbers, flatbed-origin datum)
  jig-a4-N.svg           the jig strips nested two-per-A4 for cutting
  blanks-<class>-N.svg   dense A4 sheets of blank cutouts (the jig's
                         own dropouts count toward the total)
  plate-<class>-NN-color.png / -height.png
                         print plates on the fixed grid, 300.101 DPI,
                         place at 100%
  manifest.csv           class/plate/slot -> designation/name/position

Workflow: laser the jig sheets once, laser blanks as needed, tape the
right jig to the flatbed against origin, drop blanks in (only size
matters; the print makes each base self-identifying), load
plate-<class>-NN color+height in Eufy Studio at 100%, print, unload,
refill, next plate. Same jig all day.

Assumptions, marked: printable window starts at the flatbed origin
(verify with a calibration print); gap 4 mm keeps jig bridges sturdy;
clearance 0.2 mm + kerf 0.15 mm suit 1 mm acrylic — all overridable.
"""

from __future__ import annotations

import argparse
import csv
import sys
from math import ceil
from pathlib import Path

from PIL import Image

from bases import BLEED_MM, DPI, OBJECTIVE_BASE, PX_PER_MM, base_stem, parse_base

ROOT = Path(__file__).parent

CUT = "#ff0000"  # laser convention: red = cut
ENGRAVE = "#0000ff"  # blue = engrave
A4 = (297.0, 210.0)  # landscape


def mmpx(mm: float) -> int:
    return int(round(mm * PX_PER_MM))


def collect_items(args) -> list[dict]:
    items = []
    with args.csv.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if args.formation and args.formation not in (row.get("formation") or ""):
                continue
            if args.group and (row.get("group") or "").strip() != args.group:
                continue
            base = (row.get("base") or "").strip()
            if not base:
                continue
            w, d = parse_base(base)
            rot = args.rotate and w > d  # pack wide bases upright
            items.append({
                "w": d if rot else w, "d": w if rot else d, "rot": rot,
                "group": (row.get("group") or "").strip(),
                "designation": row["designation"], "name": row["name"],
                "stem": base_stem(row["designation"], row["name"]),
            })
    for i in range(1, args.objectives + 1):
        w, d = parse_base(OBJECTIVE_BASE)
        rot = args.rotate and w > d  # same portrait packing as the bases
        items.append({
            "w": d if rot else w, "d": w if rot else d, "rot": rot,
            "group": "", "designation": f"OBJ{i:02d}", "name": "objective",
            "stem": base_stem(f"OBJ{i:02d}", "objective"),
        })
    # company letter first: each print plate comes out company-contiguous,
    # matching the painting/storage batching
    items.sort(key=lambda i: (-i["d"], -i["w"], i["group"],
                              i["designation"], i["name"]))
    return items


def grid(w: float, d: float, plate_w: float, plate_h: float,
         margin: float, gap: float) -> list[tuple[float, float]]:
    cols = int((plate_w - 2 * margin + gap) // (w + gap))
    rows = int((plate_h - 2 * margin + gap) // (d + gap))
    return [(margin + c * (w + gap), margin + r * (d + gap))
            for r in range(rows) for c in range(cols)]


def svg_group(pockets: list[dict], ow: float, oh: float,
              clearance: float, kerf: float, radius: float,
              label: str = "") -> str:
    # target hole = base + clearance; the beam eats kerf/2 per edge on a
    # hole, so draw the rect kerf smaller and keep it centered.
    # ow/oh are the UNIFORM outer dimensions shared by all four jigs, so a
    # single clamp fits every one — a few mm shorter than the sheet so the
    # cut never lands on a sheet edge. All four corners rounded; the
    # engraved origin datum (not the corner itself) is the flatbed
    # reference, refined by the calibration print.
    r = radius
    tx, ty = ow - 2.5, 3.0
    parts = [
        f'<path d="M{r},0 L{ow - r:.3f},0 A{r},{r} 0 0 1 {ow:.3f},{r} '
        f'L{ow:.3f},{oh - r:.3f} A{r},{r} 0 0 1 {ow - r:.3f},{oh:.3f} '
        f'L{r},{oh:.3f} A{r},{r} 0 0 1 0,{oh - r:.3f} '
        f'L0,{r} A{r},{r} 0 0 1 {r},0 Z" '
        f'fill="none" stroke="{CUT}" stroke-width="0.05"/>',
        # engraved origin datum at the (0,0) coordinate origin; the rounded
        # corner trims its tip, leaving two edge ticks that point at origin
        f'<path d="M0,6 L0,0 L6,0" fill="none" stroke="{ENGRAVE}" stroke-width="0.3"/>',
        f'<text x="{tx}" y="{ty}" font-size="2.2" fill="{ENGRAVE}" '
        f'font-family="monospace" transform="rotate(90 {tx} {ty})">'
        f'0,0 &#8592;{(" " + label) if label else ""}</text>',
    ]
    for slot, p in enumerate(pockets, 1):
        hw = p["w"] + clearance - kerf
        hd = p["d"] + clearance - kerf
        hx = p["x"] + (p["w"] - hw) / 2
        hy = p["y"] + (p["d"] - hd) / 2
        parts.append(f'<rect x="{hx:.3f}" y="{hy:.3f}" width="{hw:.3f}" '
                     f'height="{hd:.3f}" rx="{radius}" ry="{radius}" '
                     f'fill="none" stroke="{CUT}" stroke-width="0.05"/>')
        parts.append(f'<text x="{p["x"]:.2f}" y="{p["y"] - 0.8:.2f}" '
                     f'font-size="2" fill="{ENGRAVE}" '
                     f'font-family="monospace">{slot}</text>')
    return "\n".join(parts)


def write_svg(path: Path, group: str, w: float, h: float) -> None:
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}mm" height="{h}mm" '
        f'viewBox="0 0 {w} {h}">\n{group}\n</svg>', encoding="utf-8")


def write_blank_sheets(out: Path, cls: str, w: float, d: float, count: int,
                       kerf: float, radius: float, gap: float,
                       margin: float) -> int:
    """Dense A4 blank sheets; draw = base + kerf so the kept piece cuts
    to nominal size. Full sheets are identical, so only ONE svg is
    written per layout — the filename says how often to cut it
    (blanks-<cls>-12x.svg), plus a single partial sheet for the
    remainder. Returns total sheets to cut."""
    bw, bd = w + kerf, d + kerf
    cols = int((A4[0] - 2 * margin + gap) // (bw + gap))
    rows = int((A4[1] - 2 * margin + gap) // (bd + gap))
    per_sheet = cols * rows

    def sheet_svg(n_blanks: int) -> str:
        parts = []
        for i in range(n_blanks):
            r, c = divmod(i, cols)
            x = margin + c * (bw + gap)
            y = margin + r * (bd + gap)
            parts.append(f'<rect x="{x:.3f}" y="{y:.3f}" width="{bw:.3f}" '
                         f'height="{bd:.3f}" rx="{radius}" ry="{radius}" '
                         f'fill="none" stroke="{CUT}" stroke-width="0.05"/>')
        return "\n".join(parts)

    full, rem = divmod(count, per_sheet)
    if full:
        write_svg(out / f"blanks-{cls}-{full}x.svg", sheet_svg(per_sheet), *A4)
    if rem:
        write_svg(out / f"blanks-{cls}-rest-1x.svg", sheet_svg(rem), *A4)
    return full + (1 if rem else 0)


def write_plates(pockets: list[dict], bases_dir: Path, out: Path, name: str,
                 plate_w: float, plate_h: float,
                 ox: float = 0.0, oy: float = 0.0) -> None:
    wpx, hpx = mmpx(plate_w), mmpx(plate_h)
    color = Image.new("RGBA", (wpx, hpx), (0, 0, 0, 0))
    height = Image.new("L", (wpx, hpx), 0)
    for p in pockets:
        # the per-base PNGs include the 1 mm bleed ring beyond the pocket;
        # ox/oy compensate a printable window that doesn't start at the
        # flatbed origin (measured with the calibration print)
        px = mmpx(p["x"] - ox - BLEED_MM)
        py = mmpx(p["y"] - oy - BLEED_MM)
        c = Image.open(bases_dir / f"{p['stem']}.png").convert("RGBA")
        h = Image.open(bases_dir / f"{p['stem']}-height.png").convert("L")
        if p["rot"]:
            c = c.transpose(Image.ROTATE_90)
            h = h.transpose(Image.ROTATE_90)
        color.alpha_composite(c, (px, py))
        height.paste(h, (px, py))
    color.save(out / f"plate-{name}-color.png", dpi=(DPI, DPI))
    height.save(out / f"plate-{name}-height.png", dpi=(DPI, DPI))


def write_calibration(out: Path, plate_w: float, plate_h: float,
                      kerf: float, radius: float) -> None:
    """Test artifacts, in dependency order:

    calibration-material.svg
                           STAGE 0 — power/speed grid. An SVG cannot set
                           laser power, so the 16 squares use 16 distinct
                           stroke colors: map each color to one rung of
                           your power/speed ladder in the laser software
                           (rows P1..P4 ascending power, cols S1..S4
                           ascending speed). If your software has a
                           native material test (LightBurn does), use
                           that instead. Pick the cleanest through-cut.
    calibration-kerf.svg   STAGE 1 — a single square drawn at exactly
                           30.00 mm. Cut on production settings on the
                           production acrylic, then caliper the dropout
                           (D) and the hole (H): kerf = (H - D) / 2
                           (sanity check: 30.00 - D should match).
                           Re-run --calibrate with --kerf <measured>.
    calibration-fit.svg    STAGE 2 — five 20x20 pockets labeled with the
                           --clearance value each hole corresponds to AT
                           THE GIVEN --kerf (labels are only honest after
                           stage 1), plus two production-drawn blanks.
                           The snug pocket's label is your --clearance.
    calibration-print.png  E1 origin check, independent of the laser —
                           window border, center cross, mm rulers. Print
                           at 100 % onto a taped scrap at the flatbed
                           origin; the border's offset from the sheet
                           corner is --origin-x/--origin-y.
    """
    mat = []
    for r in range(4):
        for c in range(4):
            hue = (r * 4 + c) * 22  # 16 distinct, software maps color->layer
            x, y = 8 + c * 12, 8 + r * 12
            mat.append(f'<rect x="{x}" y="{y}" width="8" height="8" '
                       f'fill="none" stroke="hsl({hue},100%,45%)" '
                       f'stroke-width="0.05"/>')
    for c in range(4):
        mat.append(f'<text x="{8 + c * 12}" y="6.5" font-size="2.2" '
                   f'fill="{ENGRAVE}" font-family="monospace">S{c + 1}</text>')
    for r in range(4):
        mat.append(f'<text x="2" y="{14 + r * 12}" font-size="2.2" '
                   f'fill="{ENGRAVE}" font-family="monospace">P{r + 1}</text>')
    write_svg(out / "calibration-material.svg", "\n".join(mat), 60, 60)

    write_svg(out / "calibration-kerf.svg",
              f'<rect x="5" y="5" width="30" height="30" fill="none" '
              f'stroke="{CUT}" stroke-width="0.05"/>\n'
              f'<text x="5" y="3.5" font-size="2.2" fill="{ENGRAVE}" '
              f'font-family="monospace">drawn 30.00: kerf=(H-D)/2</text>',
              40, 40)

    parts = []
    x = 6.0
    for i, c in enumerate((0.0, 0.1, 0.2, 0.3, 0.4)):
        hw = 20 + c - kerf
        parts.append(f'<rect x="{x:.3f}" y="6" width="{hw:.3f}" '
                     f'height="{hw:.3f}" rx="{radius}" ry="{radius}" '
                     f'fill="none" stroke="{CUT}" stroke-width="0.05"/>')
        parts.append(f'<text x="{x:.2f}" y="4.5" font-size="2.2" '
                     f'fill="{ENGRAVE}" font-family="monospace">c={c:.1f}</text>')
        x += hw + 5
    # production-drawn blanks at the production 0.8 mm sheet spacing —
    # also proves the settings survive the dense blank-sheet nesting
    for _ in range(2):
        parts.append(f'<rect x="{x:.3f}" y="6" width="{20 + kerf:.3f}" '
                     f'height="{20 + kerf:.3f}" rx="{radius}" ry="{radius}" '
                     f'fill="none" stroke="{CUT}" stroke-width="0.05"/>')
        x += 20 + kerf + 0.8
    x += 4.2
    parts.append(f'<text x="{x - 50:.2f}" y="31" font-size="2.2" '
                 f'fill="{ENGRAVE}" font-family="monospace">blanks</text>')
    write_svg(out / "calibration-fit.svg", "\n".join(parts), x + 6, 34)

    from PIL import ImageDraw
    wpx, hpx = mmpx(plate_w), mmpx(plate_h)
    img = Image.new("RGBA", (wpx, hpx), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    mag = (255, 0, 255, 255)
    lw = max(1, mmpx(0.25))
    d.rectangle((0, 0, wpx - 1, hpx - 1), outline=mag, width=lw)
    cx, cy = wpx // 2, hpx // 2
    d.line((cx - mmpx(5), cy, cx + mmpx(5), cy), fill=mag, width=lw)
    d.line((cx, cy - mmpx(5), cx, cy + mmpx(5)), fill=mag, width=lw)
    for mm in range(0, int(plate_w) + 1, 5):
        t = mmpx(3 if mm % 10 == 0 else 1.5)
        d.line((mmpx(mm), 0, mmpx(mm), t), fill=mag, width=lw)
        if mm % 50 == 0:
            d.text((mmpx(mm) + 4, t + 4), str(mm), fill=mag)
    for mm in range(0, int(plate_h) + 1, 5):
        t = mmpx(3 if mm % 10 == 0 else 1.5)
        d.line((0, mmpx(mm), t, mmpx(mm)), fill=mag, width=lw)
        if mm % 50 == 0:
            d.text((t + 4, mmpx(mm) + 4), str(mm), fill=mag)
    img.save(out / "calibration-print.png", dpi=(DPI, DPI))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Reusable jigs + uniform print plates + blank sheets.")
    p.add_argument("--csv", type=Path, default=ROOT / "lists/israeli_minimal.csv")
    p.add_argument("--bases", type=Path, default=ROOT / "bases")
    p.add_argument("--out", type=Path, default=ROOT / "jig")
    p.add_argument("--formation", help="substring filter on the formation column")
    p.add_argument("--group", help="exact group letter filter")
    p.add_argument("--objectives", type=int, default=0)
    p.add_argument("--plate", default="297x90",
                   help="jig strip WxH mm — default is an A4 strip that fits "
                        "inside the E1's 330x90 printable window")
    p.add_argument("--margin", type=float, default=3.0,
                   help="strip edge to first pocket, mm")
    p.add_argument("--gap", type=float, default=4.0,
                   help="bridge width between pockets, mm")
    p.add_argument("--blank-gap", type=float, default=0.8,
                   help="spacing between blanks on the dense cutting sheets, mm")
    p.add_argument("--blank-margin", type=float, default=2.0,
                   help="sheet edge margin on the blank cutting sheets, mm")
    p.add_argument("--clearance", type=float, default=0.0,
                   help="pocket oversize vs blank, mm (0.0 = slip fit, "
                        "measured on the fit coupon 2026-07 at kerf 0.15)")
    p.add_argument("--kerf", type=float, default=0.15,
                   help="laser kerf compensation, mm")
    p.add_argument("--radius", type=float, default=3.0,
                   help="base corner radius, mm")
    p.add_argument("--no-rotate", dest="rotate", action="store_false",
                   help="keep wide (40x20) bases landscape instead of "
                        "rotating them onto the tank jig")
    p.add_argument("--origin-x", type=float, default=0.0,
                   help="printable-window origin offset from the flatbed "
                        "origin, mm (measure with calibration-print.png)")
    p.add_argument("--origin-y", type=float, default=0.0)
    p.add_argument("--calibrate", action="store_true",
                   help="write calibration-fit.svg (laser clearance coupon) "
                        "and calibration-print.png (E1 origin check), then exit")
    args = p.parse_args(argv)

    plate_w, plate_h = parse_base(args.plate)
    if args.calibrate:
        args.out.mkdir(parents=True, exist_ok=True)
        write_calibration(args.out, plate_w, plate_h, args.kerf, args.radius)
        print(f"Wrote {args.out}/calibration-material.svg — STAGE 0: map the "
              f"16 colors to a power/speed ladder in your laser software "
              f"(or use its native material test); pick the cleanest cut")
        print(f"Wrote {args.out}/calibration-kerf.svg — STAGE 1: cut at the "
              f"chosen settings, kerf = (hole - dropout) / 2, then re-run "
              f"--calibrate --kerf <measured>")
        print(f"Wrote {args.out}/calibration-fit.svg — STAGE 2 (labels assume "
              f"kerf={args.kerf}): snug pocket's label is your --clearance")
        print(f"Wrote {args.out}/calibration-print.png — E1 origin check, "
              f"any time: border offset = --origin-x/--origin-y")
        return 0
    items = collect_items(args)
    if not items:
        print("No matching rows.", file=sys.stderr)
        return 1
    missing = [i["stem"] for i in items
               if not (args.bases / f"{i['stem']}.png").exists()
               or not (args.bases / f"{i['stem']}-height.png").exists()]
    if missing:
        print(f"{len(missing)} base file(s) missing under {args.bases} "
              f"(run bases.py first), e.g. {missing[0]}", file=sys.stderr)
        return 1

    # group into pocket classes, biggest first
    classes: dict[str, list[dict]] = {}
    for it in items:
        classes.setdefault(f"{it['w']}x{it['d']}", []).append(it)

    # pre-pass: pocket grid per class + the uniform outer size (max extent
    # across all classes) so every jig shares one footprint / clamp
    class_grid: dict[str, tuple[float, float, list]] = {}
    uw = uh = 0.0
    for cls in classes:
        w, d = parse_base(cls)
        positions = grid(w, d, plate_w, plate_h, args.margin, args.gap)
        class_grid[cls] = (w, d, positions)
        uw = max(uw, max(x + w for x, y in positions) + args.margin)
        uh = max(uh, max(y + d for x, y in positions) + args.margin)

    args.out.mkdir(parents=True, exist_ok=True)
    jig_groups = []
    total_plates = 0
    blank_sheets = 0
    summary = []

    with (args.out / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["class", "plate", "slot", "x_mm", "y_mm",
                     "designation", "name"])
        for cls, members in classes.items():
            w, d, positions = class_grid[cls]
            pockets = [dict(w=w, d=d, x=x, y=y) for x, y in positions]
            g = svg_group(pockets, uw, uh, args.clearance,
                          args.kerf, args.radius, label=f"JIG {cls}")
            jig_groups.append(g)
            write_svg(args.out / f"jig-{cls}.svg", g, uw, uh)

            n_plates = ceil(len(members) / len(positions))
            for n in range(1, n_plates + 1):
                batch = members[(n - 1) * len(positions):n * len(positions)]
                loaded = [dict(it, x=positions[i][0], y=positions[i][1])
                          for i, it in enumerate(batch)]
                write_plates(loaded, args.bases, args.out,
                             f"{cls}-{n:02d}", plate_w, plate_h,
                             args.origin_x, args.origin_y)
                for slot, pk in enumerate(loaded, 1):
                    wr.writerow([cls, n, slot, f"{pk['x']:.2f}",
                                 f"{pk['y']:.2f}", pk["designation"],
                                 pk["name"]])
            total_plates += n_plates

            # jig dropouts are blanks too
            need = max(0, len(members) - len(positions))
            sheets = write_blank_sheets(args.out, cls, w, d, need, args.kerf,
                                        args.radius, args.blank_gap,
                                        args.blank_margin)
            blank_sheets += sheets
            summary.append(f"{cls}: {len(members)} bases, "
                           f"{len(positions)}/jig, {n_plates} plates, "
                           f"{sheets} blank sheets")

    # nest the uniform jig strips two-per-A4: centered horizontally and
    # stacked with margins so no cut line lands on a sheet edge
    xoff = max(3.0, (A4[0] - uw) / 2)
    vgap = 10.0
    yoff = max(5.0, (A4[1] - 2 * uh - vgap) / 2)
    for s, i in enumerate(range(0, len(jig_groups), 2), 1):
        pair = [f'<g transform="translate({xoff:.2f},{yoff:.2f})">'
                f'{jig_groups[i]}</g>']
        if i + 1 < len(jig_groups):
            pair.append(f'<g transform="translate({xoff:.2f},'
                        f'{yoff + uh + vgap:.2f})">{jig_groups[i + 1]}</g>')
        write_svg(args.out / f"jig-a4-{s}.svg", "\n".join(pair), *A4)

    for line in summary:
        print(line)
    jig_sheets = (len(jig_groups) + 1) // 2
    print(f"Total: {len(items)} bases, {len(classes)} reusable jigs "
          f"({jig_sheets} A4), {total_plates} print plates, "
          f"{blank_sheets} blank A4 sheets "
          f"→ {jig_sheets + blank_sheets} sheets of acrylic")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
