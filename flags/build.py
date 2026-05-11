#!/usr/bin/env python3
"""Build the two historical flags that lipis/flag-icons doesn't carry.

The bundled flag set is vendored verbatim from lipis/flag-icons (MIT,
sourced from Wikimedia Commons) — see flags/LICENSE-lipis. lipis is
ISO 3166-1 only, so the Cold-War-era armies need:

    dd  East Germany (DDR)  — simplified, no emblem
    su  Soviet Union        — simplified, solid red

Run once:
    python flags/build.py

The script only writes files that don't already exist, so hand-edits
are preserved. Delete a file and re-run to regenerate it.
"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).parent


def _wrap(w: int, h: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">\n  '
        + body.strip()
        + "\n</svg>\n"
    )


def hstripes(w: int, h: int, colors: list[str]) -> str:
    n = len(colors)
    band = h / n
    bands = "\n  ".join(
        f'<rect x="0" y="{i*band:g}" width="{w}" height="{band:g}" fill="{c}" />'
        for i, c in enumerate(colors)
    )
    return _wrap(w, h, bands)


SPECS: dict[str, tuple[str, str]] = {
    "dd": ("East Germany (DDR, simplified, no emblem)",
           hstripes(500, 300, ["#000000", "#DD0000", "#FFCE00"])),
    "su": ("Soviet Union (simplified, no hammer/sickle)",
           hstripes(300, 200, ["#CC0000"])),
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
