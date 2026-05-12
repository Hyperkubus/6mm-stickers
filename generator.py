#!/usr/bin/env python3
"""Generate printed unit-ID stickers for 6mm Team Yankee armies.

Reads a minimal CSV (designation, name, symbol, width, plus optional
hq/formation/group) and writes per-sticker SVGs under out/.

Usage:
    python generator.py --csv lists/israeli_minimal.csv \
                        --affiliation unknown --country IL
    python generator.py --list-symbols

The Israeli army in lists/israeli_minimal.csv is rendered with
`--affiliation unknown` (yellow APP-6 quatrefoils on a white background)
by deliberate aesthetic choice — not a statement about Israel's relation
to NATO. Override with --affiliation friend to get blue rectangles
instead.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

import military_symbol

ROOT = Path(__file__).parent
DEFAULT_CSV = ROOT / "lists" / "israeli_minimal.csv"
DEFAULT_OUT = ROOT / "out"
FLAGS_DIR = ROOT / "flags"

FONT_FAMILY = '"Fira Code", "IBM Plex Sans Hebrew", "DejaVu Sans Mono", monospace'

AFFILIATIONS = ("friend", "hostile", "neutral", "unknown")

# Strong colors with white text + thin black outline on the dark three;
# white background with black text on `unknown` (preserves the IDF look).
AFFILIATION_BG = {
    "friend":  "#002F5F",  # NATO field-manual navy
    "hostile": "#DA291C",  # Soviet 1980 flag red
    "neutral": "#808080",  # medium gray
    "unknown": "#FFFFFF",
}


def text_style(bg_hex: str) -> tuple[str, str]:
    """Return (fill, stroke) for text on `bg_hex`. Stroke is empty for light bgs."""
    bg = bg_hex.lstrip("#")
    r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
    # Rec. 601 luminance; threshold tuned so #808080 (luma=128) gets white text.
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    if luminance < 160:
        return ("#FFFFFF", "#000000")
    return ("#000000", "")


# ---------------------------------------------------------------------------
# APP-6 icon handling
# ---------------------------------------------------------------------------

def _normalize_symbol(symbol: str) -> str:
    """Apply known military_symbol library quirks at the phrase level."""
    # 'rockets' (any affiliation) silently resolves to a generic land unit; the
    # working phrase is 'rocket artillery'.
    if symbol.endswith(" rockets") or symbol == "rockets":
        return symbol.removesuffix("rockets") + "rocket artillery"
    return symbol


def _shrink_white_halo(svg: str, width: str = "2") -> str:
    """Reduce the thick white halo stroke the library draws behind each frame."""
    return re.sub(
        r'stroke="#ffffff" stroke-width="[^"]+"',
        f'stroke="#ffffff" stroke-width="{width}"',
        svg,
    )


def get_icon_svg(affiliation: str, symbol: str, is_hq: bool) -> str:
    """Return a complete <svg>...</svg> string for the icon."""
    symbol = _normalize_symbol(symbol)
    description = f"{affiliation} {symbol}"
    raw = military_symbol.get_symbol_svg_string_from_name(description)
    raw = _shrink_white_halo(raw)

    # `unknown fighter` returns an SVG with open paths (cumulus frame missing
    # its `z` closures) and an under-sized viewBox that clips the wingtips.
    # The library bug is unknown-specific because only the cumulus shape is
    # affected; friend/hostile/neutral fighters use rectangle/diamond/square
    # frames that render fine.
    if affiliation == "unknown" and symbol == "fighter":
        def close_d(m: re.Match[str]) -> str:
            d = m.group(1).rstrip()
            if not d.lower().endswith("z"):
                d += " z"
            return f'd="{d}"'

        raw = re.sub(r'd="([^"]+)"', close_d, raw)
        raw = re.sub(r'viewBox="[^"]+"', 'viewBox="0 0 200 160"', raw)
        raw = re.sub(r'\bwidth="[^"]+"', 'width="200"', raw, count=1)
        raw = re.sub(r'\bheight="[^"]+"', 'height="160"', raw, count=1)

    if is_hq:
        # Horizontal bar inside the icon at y=63 (upper-lobe junction of the
        # unknown quatrefoil, also lands inside the friend rectangle / hostile
        # diamond / neutral square). Avoids APP-6's flagstaff, which would
        # break the sticker grid by sticking out the side.
        bar = (
            '<path d="M63,63 L137,63" stroke="rgb(0, 0, 0)" '
            'stroke-width="4" stroke-linecap="round" fill="none" />'
        )
        raw = raw.replace("</svg>", bar + "</svg>")

    return raw


def extract_inner_svg(svg_str: str) -> tuple[str, str]:
    """Strip the outer <svg ...> tag, return (inner content, viewBox)."""
    vb_m = re.search(r'viewBox="([^"]+)"', svg_str)
    vb = vb_m.group(1) if vb_m else "0 0 200 200"
    inner = re.sub(r"^<svg[^>]*>", "", svg_str.strip(), count=1)
    inner = re.sub(r"</svg>\s*$", "", inner)
    return inner.strip(), vb


# ---------------------------------------------------------------------------
# Flag handling
# ---------------------------------------------------------------------------

def load_flag(country: str | None, flag_path: Path | None) -> tuple[str, str]:
    """Return (inner SVG content, viewBox) for the flag, or ('', '') if none."""
    if flag_path:
        path = flag_path
    elif country:
        path = FLAGS_DIR / f"{country.lower()}.svg"
        if not path.exists():
            raise SystemExit(
                f"No bundled flag for country {country!r} (looked at {path}).\n"
                f"Download an SVG from Wikimedia Commons and drop it there, "
                f"or pass --flag PATH explicitly."
            )
    else:
        return "", ""
    return extract_inner_svg(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Sticker construction
# ---------------------------------------------------------------------------

def sticker_filename(designation: str, name: str) -> str:
    """Filename for a sticker SVG.

    The name is included because mutually exclusive variants (e.g.
    M113/Vayzata/Nagmasho't transports for the same infantry team) may
    deliberately share a designation, so the designation alone is not
    unique. The slug only uses ASCII + digits, so non-Latin scripts in
    the name fall through to whatever's safe.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        slug = "sticker"
    return f"{designation}-{slug}.svg"


def escape_xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _mixes_scripts(s: str) -> bool:
    """True if the string mixes ASCII and non-ASCII characters."""
    has_ascii = any(ord(c) < 128 and c.isalnum() for c in s)
    has_unicode = any(ord(c) >= 128 for c in s)
    return has_ascii and has_unicode


def build_sticker(
    designation: str,
    name: str,
    icon_svg: str,
    width_mm: int,
    bg: str,
    flag_inner: str,
    flag_vb: str,
) -> str:
    height_mm = 8
    is_wide = width_mm == 40
    fill, stroke = text_style(bg)

    icon_size = 5.0
    flag_w = 5.0
    flag_h = flag_w * 8 / 11  # 11:8 (Israeli flag aspect; close enough for most others)
    x_margin = 0.3
    text_margin = 0.5

    icon_x = x_margin
    icon_y = 2.5  # pushed down so the label has its own band above the icon/flag
    flag_x = width_mm - x_margin - flag_w
    flag_y = icon_y + (icon_size - flag_h) / 2
    text_x = width_mm / 2

    label_size = 2.1
    desig_size = 4.5 if is_wide else 3.6

    icon_inner, icon_vb = extract_inner_svg(icon_svg)

    desig_y = (height_mm - text_margin) - desig_size * 0.2

    # rsvg-convert ignores SVG `textLength`/`lengthAdjust`, so we shrink the
    # font when the natural width would overflow. Monospace cell ≈ 0.6 × size.
    available_w = width_mm - 2 * x_margin
    if name:
        natural_w = len(name) * label_size * 0.6
        if natural_w > available_w:
            label_size = max(available_w / (len(name) * 0.6), 1.3)
    label_y = text_margin + label_size * 0.85

    text_outline = (
        f' stroke="{stroke}" stroke-width="0.06" paint-order="stroke"'
        if stroke else ""
    )

    # Only flip on bidi-override when the designation mixes scripts (mixed
    # digits + Hebrew/Arabic/etc). Pure-Latin designations don't need it.
    bidi_attrs = (
        ' direction="ltr" unicode-bidi="bidi-override"'
        if _mixes_scripts(designation) else ""
    )

    flag_block = ""
    if flag_inner:
        flag_block = (
            f'<svg x="{flag_x}" y="{flag_y}" width="{flag_w}" height="{flag_h:.3f}" '
            f'viewBox="{flag_vb}" preserveAspectRatio="none">{flag_inner}</svg>\n  '
            f'<rect x="{flag_x}" y="{flag_y}" width="{flag_w}" height="{flag_h:.3f}" '
            f'fill="none" stroke="#000" stroke-width="0.15" />'
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     width="{width_mm}mm" height="{height_mm}mm"
     viewBox="0 0 {width_mm} {height_mm}">
  <rect width="{width_mm}" height="{height_mm}" fill="{bg}" />
  <svg x="{icon_x}" y="{icon_y}" width="{icon_size}" height="{icon_size}"
       viewBox="{icon_vb}" preserveAspectRatio="xMidYMid meet">
    {icon_inner}
  </svg>
  {flag_block}
  <text x="{text_x}" y="{label_y:.2f}" font-family='{FONT_FAMILY}'
        font-size="{label_size:.2f}" text-anchor="middle"
        font-weight="600" fill="{fill}"{text_outline}>{escape_xml(name)}</text>
  <text x="{text_x}" y="{desig_y:.2f}" font-family='{FONT_FAMILY}'
        font-size="{desig_size}" text-anchor="middle" font-weight="bold"
        fill="{fill}"{text_outline}{bidi_attrs}>{escape_xml(designation)}</text>
</svg>
"""


# ---------------------------------------------------------------------------
# CSV row helpers
# ---------------------------------------------------------------------------

def parse_bool(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in ("1", "true", "yes", "y", "hq")


def row_width(row: dict) -> int:
    w = (row.get("width") or "").strip()
    if not w:
        return 20
    return int(w)


# ---------------------------------------------------------------------------
# Common APP-6 symbol phrases
# ---------------------------------------------------------------------------

COMMON_SYMBOLS: list[tuple[str, str]] = [
    ("armor", "tank / armored fighting vehicle"),
    ("infantry", "rifle squad / team"),
    ("anti-tank", "AT weapons (RPG, ATGM teams, dedicated AT)"),
    ("wheeled anti-tank", "wheeled AT (Jeep TOW, BRDM-AT)"),
    ("machine gun", "MG team"),
    ("mortar", "light mortar team"),
    ("self-propelled mortar", "vehicle-mounted mortar (M125, M106, 2S9)"),
    ("self-propelled artillery", "SPG (M109, 2S1, 2S3)"),
    ("artillery", "towed gun"),
    ("rocket artillery", "MLRS, BM-21 (`rockets` is auto-fixed to this)"),
    ("self-propelled anti-aircraft", "ZSU-23-4, M163 VADS, Gepard, Tunguska"),
    ("anti-aircraft", "towed AA gun"),
    ("surface-to-air missile", "SAM (Chaparral, SA-8, Hawk)"),
    ("manpads", "shoulder-fired SAM (Stinger, Strela)"),
    ("attack helicopter", "AH-64, Mi-24, AH-1"),
    ("utility helicopter", "UH-1, Mi-8, CH-53"),
    ("fighter", "fixed-wing strike (A-4, Su-25)"),
    ("armored personnel carrier", "tracked APC (M113, BTR-50)"),
    ("wheeled armored personnel carrier", "wheeled APC (BTR-70/80, Fuchs)"),
    ("reconnaissance", "scout / recce element"),
    ("wheeled reconnaissance", "BRDM, jeep recce, Luchs"),
    ("observation post", "FO / artillery OP"),
    ("engineer", "combat engineers"),
    ("signal", "comms / signals"),
    ("supply", "logistics"),
]


def print_symbol_list() -> int:
    width = max(len(s) for s, _ in COMMON_SYMBOLS)
    print("Common APP-6 symbol phrases (write these in the `symbol` column):\n")
    for sym, desc in COMMON_SYMBOLS:
        print(f"  {sym:<{width}}  — {desc}")
    print()
    print("Affiliation prefix (friend/hostile/neutral/unknown) is set per-army")
    print("via --affiliation, not in the CSV. Anything `military_symbol` accepts")
    print("as a symbol phrase will work; the list above is the convenient subset.")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def add_common_args(p: argparse.ArgumentParser) -> None:
    """Shared CLI args between generator / sheets / preview."""
    p.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to the army CSV.")
    p.add_argument("--affiliation", choices=AFFILIATIONS, default="unknown",
                   help="APP-6 affiliation (default: unknown).")
    p.add_argument("--background",
                   help="Sticker background hex (default depends on --affiliation).")
    p.add_argument("--country",
                   help="ISO 3166-1 alpha-2 code for the bundled flag (e.g. IL, DE).")
    p.add_argument("--flag", type=Path,
                   help="Custom flag SVG path. Wins over --country.")


def resolve_background(args: argparse.Namespace) -> str:
    return args.background or AFFILIATION_BG[args.affiliation]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate per-sticker SVGs from an army CSV.")
    add_common_args(p)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output directory.")
    p.add_argument("--list-symbols", action="store_true",
                   help="Print common APP-6 symbol phrases and exit.")
    args = p.parse_args(argv)

    if args.list_symbols:
        return print_symbol_list()

    if not args.csv.exists():
        print(f"Missing input: {args.csv}", file=sys.stderr)
        return 1

    bg = resolve_background(args)
    flag_inner, flag_vb = load_flag(args.country, args.flag)

    args.out.mkdir(exist_ok=True, parents=True)
    with args.csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    icon_cache: dict[tuple[str, bool], str] = {}
    written = 0
    for row in rows:
        symbol = (row.get("symbol") or "").strip()
        designation = (row.get("designation") or "").strip()
        name = (row.get("name") or "").strip()
        if not (symbol and designation and name):
            print(
                f"Skipping incomplete row (designation={designation!r}, "
                f"name={name!r}, symbol={symbol!r})",
                file=sys.stderr,
            )
            continue

        is_hq = parse_bool(row.get("hq"))
        cache_key = (symbol, is_hq)
        if cache_key not in icon_cache:
            icon_cache[cache_key] = get_icon_svg(args.affiliation, symbol, is_hq)

        sticker = build_sticker(
            designation, name, icon_cache[cache_key], row_width(row),
            bg, flag_inner, flag_vb,
        )
        (args.out / sticker_filename(designation, name)).write_text(sticker, encoding="utf-8")
        written += 1

    print(f"Wrote {written} stickers to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
