#!/usr/bin/env python3
"""Bootstrap the bundled simple-flag SVGs.

The sticker renderer uses `preserveAspectRatio="none"` to fit each flag
into the 5×3.64 mm slot, so internal proportions don't have to match
the official ratio exactly — but we try anyway for honesty's sake.

Run once:
    python flags/build.py

Resulting SVGs are committed (they are the source-of-truth for the
shipped flag set). Edit individual SVGs by hand for refinements;
re-running this script will *not* overwrite hand-edited files unless
you delete them first.

Complex flags (Union Jack, US stars/stripes, KR taegukgi, CN/VN stars,
PK/TR crescent, IN chakra, SA script, DDR/SU emblems) are not produced
here — drop the official SVG from Wikimedia Commons at
flags/<iso>.svg to use them.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).parent


def hstripes(w: int, h: int, colors: list[str]) -> str:
    n = len(colors)
    band = h / n
    bands = "\n  ".join(
        f'<rect x="0" y="{i*band:g}" width="{w}" height="{band:g}" fill="{c}" />'
        for i, c in enumerate(colors)
    )
    return _wrap(w, h, bands)


def vstripes(w: int, h: int, colors: list[str]) -> str:
    n = len(colors)
    band = w / n
    bands = "\n  ".join(
        f'<rect x="{i*band:g}" y="0" width="{band:g}" height="{h}" fill="{c}" />'
        for i, c in enumerate(colors)
    )
    return _wrap(w, h, bands)


def nordic_cross(w: int, h: int, field: str, cross: str, frame: str | None = None) -> str:
    # Cross arms: 1/7 of the height (~standard ratio). Centred vertically;
    # offset to the hoist (left third) horizontally.
    arm = h / 7
    cy = (h - arm) / 2
    # The vertical arm sits 1/3 of the way from the hoist.
    cx = h / 3 - arm / 2  # so the cross is in the canton-ish area
    if frame:
        # Outer frame stripe behind the cross (e.g. Iceland/Norway).
        outer = arm * 1.7
        ocy = (h - outer) / 2
        ocx = h / 3 - outer / 2
        frame_xml = (
            f'<rect x="0" y="{ocy:g}" width="{w}" height="{outer:g}" fill="{frame}" />\n  '
            f'<rect x="{ocx:g}" y="0" width="{outer:g}" height="{h}" fill="{frame}" />'
        )
    else:
        frame_xml = ""
    body = f"""<rect width="{w}" height="{h}" fill="{field}" />
  {frame_xml}
  <rect x="0" y="{cy:g}" width="{w}" height="{arm:g}" fill="{cross}" />
  <rect x="{cx:g}" y="0" width="{arm:g}" height="{h}" fill="{cross}" />""".strip()
    return _wrap(w, h, body)


def japan(w: int, h: int) -> str:
    r = h * 3 / 10  # disc diameter = 3/5 of the height
    body = f"""<rect width="{w}" height="{h}" fill="#FFFFFF" />
  <circle cx="{w/2:g}" cy="{h/2:g}" r="{r:g}" fill="#BC002D" />"""
    return _wrap(w, h, body)


def jordan(w: int, h: int) -> str:
    # Black/white/green horizontal stripes + red hoist triangle.
    body = f"""<rect x="0" y="0" width="{w}" height="{h/3:g}" fill="#000000" />
  <rect x="0" y="{h/3:g}" width="{w}" height="{h/3:g}" fill="#FFFFFF" />
  <rect x="0" y="{2*h/3:g}" width="{w}" height="{h/3:g}" fill="#007A3D" />
  <polygon points="0,0 0,{h:g} {h/2:g},{h/2:g}" fill="#CE1126" />"""
    return _wrap(w, h, body)


def czech(w: int, h: int) -> str:
    # White over red, blue triangle from the hoist reaching halfway.
    body = f"""<rect x="0" y="0" width="{w}" height="{h/2:g}" fill="#FFFFFF" />
  <rect x="0" y="{h/2:g}" width="{w}" height="{h/2:g}" fill="#D7141A" />
  <polygon points="0,0 0,{h:g} {w/2:g},{h/2:g}" fill="#11457E" />"""
    return _wrap(w, h, body)


def greece(w: int, h: int) -> str:
    # 9 horizontal stripes (blue/white) + blue canton with white cross,
    # canton covers top 5 stripes.
    stripe = h / 9
    canton = stripe * 5
    rects = []
    for i in range(9):
        color = "#0D5EAF" if i % 2 == 0 else "#FFFFFF"
        rects.append(f'<rect x="0" y="{i*stripe:g}" width="{w}" height="{stripe:g}" fill="{color}" />')
    arm = canton / 5
    body = "\n  ".join(rects) + f"""
  <rect x="0" y="0" width="{canton:g}" height="{canton:g}" fill="#0D5EAF" />
  <rect x="0" y="{(canton-arm)/2:g}" width="{canton:g}" height="{arm:g}" fill="#FFFFFF" />
  <rect x="{(canton-arm)/2:g}" y="0" width="{arm:g}" height="{canton:g}" fill="#FFFFFF" />"""
    return _wrap(w, h, body)


def _wrap(w: int, h: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n  '
        + body.strip()
        + "\n</svg>\n"
    )


# Color constants from the official flag specs (Wikipedia).
SPECS: dict[str, tuple[str, str]] = {
    # ---------------------------------------------------------------- NATO
    "de": ("Germany",       hstripes(500, 300, ["#000000", "#DD0000", "#FFCE00"])),
    "fr": ("France",        vstripes(300, 200, ["#002395", "#FFFFFF", "#ED2939"])),
    "it": ("Italy",         vstripes(300, 200, ["#009246", "#FFFFFF", "#CE2B37"])),
    "nl": ("Netherlands",   hstripes(300, 200, ["#AE1C28", "#FFFFFF", "#21468B"])),
    "be": ("Belgium",       vstripes(150, 130, ["#000000", "#FAE042", "#ED2939"])),
    "lu": ("Luxembourg",    hstripes(500, 300, ["#ED2939", "#FFFFFF", "#00A1DE"])),
    "pt": ("Portugal (simplified, no shield)", vstripes(600, 400, ["#006600", "#FF0000"])),
    "es": ("Spain (simplified, no arms)",      hstripes(500, 300, ["#AA151B", "#F1BF00", "#AA151B"])),
    "gr": ("Greece",        greece(540, 360)),
    "no": ("Norway",        nordic_cross(220, 160, "#EF2B2D", "#FFFFFF", frame="#FFFFFF") if False
                            else nordic_cross(220, 160, "#EF2B2D", "#002868", frame="#FFFFFF")),
    "dk": ("Denmark",       nordic_cross(370, 280, "#C8102E", "#FFFFFF")),
    "is": ("Iceland",       nordic_cross(250, 180, "#02529C", "#DC1E35", frame="#FFFFFF")),
    "tr": ("Türkiye (simplified, no crescent/star)", hstripes(600, 400, ["#E30A17"])),
    # ---------------------------------------------------------- Warsaw Pact
    "pl": ("Poland",        hstripes(800, 500, ["#FFFFFF", "#DC143C"])),
    "hu": ("Hungary",       hstripes(600, 300, ["#CE2939", "#FFFFFF", "#477050"])),
    "bg": ("Bulgaria",      hstripes(500, 300, ["#FFFFFF", "#00966E", "#D62612"])),
    "ro": ("Romania",       vstripes(300, 200, ["#002B7F", "#FCD116", "#CE1126"])),
    "cz": ("Czechoslovakia / Czechia", czech(300, 200)),
    "ru": ("Russia / USSR (simplified, no hammer/sickle)", hstripes(300, 200, ["#FFFFFF", "#0039A6", "#D52B1E"])),
    "su": ("Soviet Union (simplified)", hstripes(300, 200, ["#CC0000"])),
    "dd": ("East Germany (DDR, simplified, no emblem)", hstripes(500, 300, ["#000000", "#DD0000", "#FFCE00"])),
    # ----------------------------------------------------------- Middle East
    "eg": ("Egypt (simplified, no eagle)", hstripes(900, 600, ["#CE1126", "#FFFFFF", "#000000"])),
    "sy": ("Syria (simplified, no stars)", hstripes(900, 600, ["#CE1126", "#FFFFFF", "#000000"])),
    "lb": ("Lebanon (simplified, no cedar)", hstripes(300, 200, ["#ED1C24", "#FFFFFF", "#ED1C24"])),
    "ir": ("Iran (simplified, no emblem/script)", hstripes(700, 400, ["#239F40", "#FFFFFF", "#DA0000"])),
    "iq": ("Iraq (simplified, no script)", hstripes(300, 200, ["#CE1126", "#FFFFFF", "#000000"])),
    "jo": ("Jordan",        jordan(300, 150)),
    # ---------------------------------------------------------- Asia-Pacific
    "jp": ("Japan",         japan(300, 200)),
    "vn": ("Vietnam (simplified, no star)", hstripes(300, 200, ["#DA251D"])),
    "cn": ("China (simplified, no stars)",  hstripes(300, 200, ["#EE1C25"])),
    "in": ("India (simplified, no chakra)", hstripes(900, 600, ["#FF9933", "#FFFFFF", "#138808"])),
    "ie": ("Ireland",       vstripes(200, 100, ["#169B62", "#FFFFFF", "#FF883E"])),
}


def main() -> int:
    written = 0
    for iso, (label, svg) in SPECS.items():
        path = OUT / f"{iso}.svg"
        if path.exists():
            continue
        path.write_text(svg, encoding="utf-8")
        print(f"  wrote {path.name}  — {label}")
        written += 1
    print(f"Bundled {written} flag SVGs (existing files were left alone).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
