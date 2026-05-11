# 6mm sticker generator

Prints unit-ID stickers for 6mm Team Yankee armies — one per base.
Ships with a worked example for an Israeli 1979 army (`lists/israeli_full.csv`,
1979 stickers across 8 formations + the support pool), but the generator
itself is faction-agnostic.

Each sticker is 8 mm tall and goes on the lower edge of the base:

- **Top label** — equipment / weapon (e.g. `MERKAVA 3`, `M163 VADS`,
  `AH-64 PETEN`, `LEOPARD 2`).
- **Designation** — the team ID (`001א`, `1.PLT.A`, …).
- **APP-6 unit icon** on the left, **national flag** on the right.

A 20 mm-wide base gets a 20 × 8 mm sticker; a 40 mm-wide base gets
40 × 8 mm. (The Israeli CSV uses bases described as `20x40` — meaning
20 mm wide, 40 mm deep for a tank — so most tank stickers are 20 mm
wide.)

## Pipeline

```
your_army.csv          one row per base, minimal columns
        │
        ▼
  generator.py        →  out/<designation>-<slug>.svg   (one per base)
        │
        ├── preview.py    →  preview.html        (sample of each unique sticker)
        │
        └── sheets.py     →  sheets/<formation>.pdf   (per-formation A4 sheets)
```

`out/`, `sheets/`, and `preview.html` are gitignored — fully
regenerable from the CSV plus the generator.

## CSV schema

Required columns:

| column        | description                                            |
| ------------- | ------------------------------------------------------ |
| `designation` | team ID; goes in the bottom row of the sticker         |
| `name`        | top-row label (model/weapon, e.g. `MERKAVA 3`)         |
| `symbol`      | APP-6 symbol phrase (no affiliation prefix), e.g. `armor`, `infantry`. Run `python generator.py --list-symbols` for the common ones. |
| `width`       | sticker width in mm — `20` or `40`                     |

Optional columns:

| column        | description                                            |
| ------------- | ------------------------------------------------------ |
| `hq`          | `true` to draw the HQ bar inside the icon              |
| `formation`   | groups rows into one PDF per formation in `sheets.py`  |
| `group`       | within a formation, breaks each `group` change onto a fresh line (with extra vertical space) — use to separate platoons / sub-blocks |

Extra columns are ignored, so a richer source-of-truth CSV (like
`lists/israeli_full.csv`, which keeps the full army-list structure)
can coexist with the minimal generator columns.

## Usage

```sh
# install deps (Nix flake provided; or use a venv)
nix develop                # or: python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt

# generate every individual sticker SVG
python generator.py --country IL          # --csv defaults to lists/israeli_minimal.csv

# preview a sample of each unique sticker (PNG embedded in HTML)
python preview.py --country IL && open preview.html

# render per-formation A4 cut-out sheets, one PDF per formation
python sheets.py --country IL && open sheets/merkava-3-tank-company.pdf
```

### Affiliation, background, flag

`--affiliation` picks the APP-6 affiliation, which sets the icon
frame/color and a default background:

| affiliation | icon frame      | default bg   | text          |
| ----------- | --------------- | ------------ | ------------- |
| `friend`    | blue rectangle  | `#002F5F`    | white + black outline |
| `hostile`   | red diamond     | `#DA291C`    | white + black outline |
| `neutral`   | green square    | `#808080`    | white + black outline |
| `unknown`   | yellow quatrefoil (cumulus for fixed-wing) | `#FFFFFF` | black |

Override the background with `--background #RRGGBB`. The text color
switches automatically based on background luminance.

`--country IL` (lower- or upper-case ISO 3166-1 alpha-2) picks a flag
from `flags/<iso>.svg`; `--flag PATH` overrides with a custom SVG.
See `flags/README.md` for the bundled set and how to add more.

### Why unknown for the Israeli example?

Aesthetic preference, not a NATO-affiliation claim. The yellow
quatrefoil reads well at 5 × 5 mm and avoids the question of which
faction Israel "belongs to" on the Cold War map. Pass `--affiliation
friend` to swap to NATO-blue rectangles if you'd rather.

## Web UI (Docker)

A small Flask wrapper around the same CLIs is provided for people who'd
rather click than type:

```sh
docker compose up --build       # then open http://localhost:8000
```

Pick a bundled CSV (or upload your own), choose affiliation / flag /
background, and download a preview HTML, a zip of per-sticker SVGs, or
a zip of per-formation A4 PDFs. Source lives under `webapp/`.

## IDF list maintenance

`lists/israeli_full.csv` is the rich source-of-truth for the worked
example: full army-list structure (`kind`, `formation_name`,
`team_role`, `base`, etc.) for composing and editing the army.
`idf_migrate.py` derives the minimal CSV the generator actually reads:

```sh
python idf_migrate.py            # writes lists/israeli_minimal.csv
```

Re-run whenever you edit the full CSV. For any other army, skip this
step and just write the minimal columns directly in your own CSV.

## Stack

- Python 3.12, `military-symbol` 2.x for APP-6 icons, `pyyaml`
  (its dep), `svgwrite`. Pinned in `flake.nix`.
- `librsvg` (`rsvg-convert`) for SVG → PNG / PDF.
- Fonts: Fira Code (Latin, slashed zero, heavy weight) +
  IBM Plex Sans Hebrew (Hebrew letter fallback) +
  DejaVu Sans Mono (final fallback). Apt:
  `fonts-firacode fonts-ibm-plex fonts-dejavu`.

See `CLAUDE.md` for the design notes — sticker layout maths, APP-6
quirks, font fallbacks, HQ-bar handling, etc.
