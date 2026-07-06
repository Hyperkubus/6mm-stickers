# 6mm base & sticker factory

A production system for 6mm Team Yankee armies: unit-ID **stickers**
(print on paper, cut, done), ground-textured **bases** with relief for
a EufyMake E1 UV flatbed printer + laser-cut acrylic blanks and
reusable print jigs, transparent **spinning-rotor discs** for the
helicopters, and a **markings & painting reference**. Ships with a
worked example for an Israeli army (`sources/israeli_full.csv`, 1979
bases across 8 formations + a support pool), but the generators are
faction-agnostic.

Everything is driven by one CSV (one row per base) and fully
regenerable — edit the army list, rerun, reprint.

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
your_army.csv            one row per base, minimal columns
        │
        ▼
  generator.py          →  out/<designation>-<slug>.svg    (one sticker per base)
        │
        ├── preview.py     →  preview.html      (sample of each unique sticker)
        ├── sheets.py      →  sheets/<formation>.pdf  (per-formation A4 cut-out sheets)
        │
        └── bases.py       →  bases/<designation>-<slug>.png (+ -height.png)
                │              ground-texture base prints, sticker composited
                ├── bases_preview.py  →  bases_preview.html   (2D sample sheet)
                ├── bases_3d.py       →  bases_3d.html        (orbitable 3D relief preview)
                └── jig.py            →  jig/                 (laser jigs + blank sheets
                                                               + E1 print plates + manifest)
  rotors.py             →  rotors/    (transparent rotor-blur discs + print plates)
  markings/index.html      markings & painting reference (hand-authored)
```

The sticker flow (`generator.py`/`preview.py`/`sheets.py`) works
standalone — the base-printing flow is additive. All generated
directories (`out/`, `sheets/`, `bases/`, `jig/`, `rotors/`, the
preview HTMLs) are gitignored and fully regenerable.

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
`sources/israeli_full.csv`, which keeps the full army-list structure)
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

`sources/israeli_full.csv` is the rich source-of-truth for the worked
example: full army-list structure (`kind`, `formation_name`,
`team_role`, `base`, etc.) for composing and editing the army.
`idf_migrate.py` derives the minimal CSV the generator actually reads:

```sh
python idf_migrate.py            # writes lists/israeli_minimal.csv
```

Re-run whenever you edit the full CSV. For any other army, skip this
step and just write the minimal columns directly in your own CSV.

## Textured bases (EufyMake E1 UV flatbed)

`bases.py` turns each CSV row into a print-ready pair: a **color PNG**
(seeded random crop of an AI-generated Golan terrain texture, the
unit's sticker composited onto the lower 8 mm, 1 mm bleed all round)
and an aligned **heightmap PNG** for the E1's relief printing (white =
raised; the sticker area is flattened). Texture variants are assigned
per company — all bases of one (formation, group) share a variant,
each base gets its own crop — so platoons look related, not cloned.
Everything is seeded (`--seed`, default 1979): reruns are
byte-identical.

```sh
python bases.py --csv lists/israeli_minimal.csv --country IL --objectives 4
python bases_preview.py --country IL    # 2D sample sheet
python bases_3d.py --country IL         # interactive 3D relief preview (three.js)
```

**Validated print settings** (physical tests, 2026-07): 0.8 mm max
relief in Eufy Studio, heightmap polarity white = raised, textures at
the locked scale of 300.101 DPI — **always place files at 100 % in
Eufy Studio, never "fit to bed"**.

### Production: jigs, blanks, plates (`jig.py`)

`jig.py` generates the whole physical production kit around **one
reusable laser-cut jig per base geometry** (20×40 / 20×30 / 20×20
+ 40×30 objectives — wide infantry bases are auto-rotated upright so
they share the tank jig):

```sh
python jig.py --objectives 4
```

- `jig-a4-N.svg` — the 4 reusable jig strips, nested two per A4 sheet
  of 1 mm acrylic (red = cut, blue = engrave, kerf-compensated pockets,
  3 mm rounded corners, engraved slot numbers, flatbed-origin datum).
- `blanks-<class>-N.svg` — dense A4 sheets of base blanks.
- `plate-<class>-NN-color.png / -height.png` — E1 print plates on the
  jig's fixed grid, plus `manifest.csv` mapping every slot to its unit.

Workflow: laser the jigs once, tape one to the flatbed against the
origin, drop blanks into the pockets (only the size matters — the
print makes every base self-identifying), print the plate pair at
100 %, unload, refill. The worked example army: 1983 bases → 27 A4
sheets of acrylic, 81 print plates. Calibrate `--kerf`/`--clearance`
to your laser, and verify the printable-window origin with a test
print before the first real run.

## Rotor discs (`rotors.py`)

PropBlur-style motion-blur discs for helicopters, printed on clear
laser-transparency (PET) film with the **white ink layer disabled** —
the PNGs carry real alpha, so the disc stays see-through. True 1:285
rotor diameters (AH-64/UH-1 51.3 mm, AH-1 47.1 mm, CH-53 77.3 mm),
packed print plates with per-copy random blade rotation:

```sh
python rotors.py --counts ah64=8,ah1=8,uh1=12,ch53=6
```

Cut on the printed ring, mount ink-side down, make the center hole
with a punch on a flat backing (or laser-cut hole + perimeter).

## Markings & painting reference (`markings/`)

`markings/index.html` — self-contained, browsable offline: the IDF
white-chevron company marking system with a per-company assignment
table for this army, צ plates, orange air-recognition panels, a paint
table (Vallejo, Sinai Grey 82 base), per-unit cards with placement
diagrams and real reference photos, bench tips, and honest confidence
notes about which claims are verified vs. worth a photo check.

## Stack

- Python 3.12, `military-symbol` 2.x for APP-6 icons, `pyyaml`
  (its dep), `svgwrite`. Pinned in `flake.nix`.
- `pillow` + `numpy` for texture preprocessing / compositing
  (`bases.py`, `jig.py`, `rotors.py`). On NixOS the pip wheels need
  `libstdc++` on `LD_LIBRARY_PATH` — the flake's dev shell sets it.
- `librsvg` (`rsvg-convert`) for SVG → PNG / PDF.
- Fonts: Fira Code (Latin, slashed zero, heavy weight) +
  IBM Plex Sans Hebrew (Hebrew letter fallback) +
  DejaVu Sans Mono (final fallback). Apt:
  `fonts-firacode fonts-ibm-plex fonts-dejavu`.

See `CLAUDE.md` for the design notes — sticker layout maths, APP-6
quirks, font fallbacks, HQ-bar handling, etc.
