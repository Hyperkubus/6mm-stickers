# 6mm IDF sticker generator

Prints unit-ID stickers for a 6mm Team Yankee Israeli army — 1979
stickers across 8 formations and the support pool, one per base.

Each sticker is 8 mm tall and goes on the lower edge of the base:

- **Top label** — equipment / weapon (e.g. `MERKAVA 3`, `M163 VADS`,
  `AH-64 PETEN`).
- **Designation** — the four-character team ID (`001א`, `611ך` …),
  digits + Hebrew letter (Aleph through Tav, including final forms).
- **APP-6 unit icon** on the left, **Israeli flag** on the right.

A 20 mm base gets a 20 × 8 mm sticker, a 40 × 20 mm base gets a
40 × 8 mm sticker.

## Pipeline

```
lists/israeli_full.csv          one row per base
        │
        ▼
  generator.py        →  out/<designation>.svg   (one per base)
        │
        ├── preview.py    →  preview.html        (sample of each unique sticker)
        │
        └── sheets.py     →  sheets/<formation>.pdf
                              (per-formation cut-out sheets, A4)
```

`out/`, `sheets/`, and `preview.html` are gitignored — fully
regenerable from the CSV plus the generator.

## Usage

```sh
# install deps (Nix flake provided; or use a venv)
nix develop                # or: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt

# generate every individual sticker SVG
python generator.py

# preview a sample of each unique sticker (PNG embedded in HTML)
python preview.py && open preview.html

# render per-formation A4 cut-out sheets, one PDF per formation
python sheets.py && open sheets/merkava-3-tank-company.pdf
```

`python generator.py --update-csv` fills in any blank `name` cells
in the CSV from `derive_name(team_role, unit_name)`. Add `--force`
to overwrite existing values (used after changing the naming
rules).

## Naming rules

The `name` column drives the top label. Rules are documented in
`CLAUDE.md` and implemented in `derive_name()`. Short summary:

| Category                        | Example label      |
| ------------------------------- | ------------------ |
| Tanks                           | `MERKAVA 3`, `MAGACH 6 BLAZER`, `SHO'T BLAZER` |
| Helicopters (model + IDF name)  | `AH-64 PETEN`, `AH-1 TZEFA`, `CH-53 YAS'UR`, `UH-1` |
| APCs (chassis + IDF nickname)   | `M113 ZELDA`, `TIRAN VAYZATA`, `NAGMASHOT` |
| Infantry (main weapon)          | `GALIL`, `FN MAG`, `RPG-7`, `M47 DRAGON`, `52MM`, `REDEYE` |
| Mortars / SP / TOW (chassis)    | `M125`, `M106`, `M109`, `M150`, `PEREH` |
| AA / SAM / rockets (chassis + system) | `M163 VADS`, `ZSU-23-4 SHILKA`, `M48 CHAPARRAL`, `M270 MLRS`, `BM-21 GRAD` |
| Strike jet                      | `A-4 SKYHAWK` |
| Artillery observer              | `M113 OP` |

## Stack

- Python 3.12, `military-symbol` 2.x for APP-6 icons, `pyyaml`
  (its dep), `svgwrite`. Pinned in `flake.nix`.
- `librsvg` (`rsvg-convert`) for SVG → PNG / PDF.
- Fonts: Fira Code (Latin, slashed zero, heavy weight) +
  IBM Plex Sans Hebrew (Hebrew letter fallback) +
  DejaVu Sans Mono (final fallback). Apt:
  `fonts-firacode fonts-ibm-plex fonts-dejavu`.

See `CLAUDE.md` for the design notes — sticker layout maths,
APP-6 quirks, font fallbacks, HQ-bar handling, etc.
