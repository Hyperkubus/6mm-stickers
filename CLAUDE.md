# 6mm sticker generator — design notes

Hobby project: prints unit-ID stickers for 6mm Team Yankee armies.
The generator is faction-agnostic; the worked example is an Israeli
1979 army (`sources/israeli_full.csv`, 1979 stickers across 8 formations
+ the support pool, one per base).

## Pipeline

1. `<army>.csv` — inventory (one row per base). The generator only needs
   the minimal columns (designation, name, symbol, width, optional
   hq/formation/group); a richer source-of-truth CSV with extra columns
   is fine. `base` (`WxD` mm) is only needed by `bases.py`.
2. `generator.py` writes `out/{designation}-{slug}.svg`, one per row.
3. `preview.py` renders one sample sticker per unique (symbol, hq,
   name, width) tuple to `preview.html` (PNG via rsvg-convert, embedded
   as base64 data URIs).
4. `sheets.py` lays out every sticker per `formation` onto A4 portrait
   pages and concatenates into one PDF per formation under `sheets/`.
   `rsvg-convert -f pdf` does the multi-page PDF concatenation.
5. `bases.py` (optional, additive — the paper sticker flow above works
   without it) renders per-base ground-texture print files for the
   EufyMake E1 UV flatbed; see "Base print files" below.

`out/`, `sheets/` and `bases/` are gitignored — fully regenerable from
the CSV + the generator.

### CLI

```sh
python generator.py --csv <csv> --affiliation <a> [--background #HEX] \
                    [--country IL | --flag flags/foo.svg] [--out out/]
python sheets.py    --csv <csv> --affiliation <a> [--background ...]   \
                    [--country IL | --flag ...] [--out sheets/]
python preview.py   --csv <csv> --affiliation <a> ...
python generator.py --list-symbols
```

Affiliation defaults to `unknown`. Background defaults per affiliation:

| affiliation | icon frame      | default bg   | text          |
| ----------- | --------------- | ------------ | ------------- |
| friend      | blue rectangle  | `#002F5F`    | white + black outline |
| hostile     | red diamond     | `#DA291C`    | white + black outline |
| neutral     | green square    | `#808080`    | white + black outline |
| unknown     | yellow quatrefoil / cumulus | `#FFFFFF` | black |

Text color is decided by Rec. 601 luminance with a threshold of 160 —
the gray bg (luma 128) gets white text + outline.

## Sticker layout

8 mm tall, the lower 8 mm of the unit's base. Two physical widths
keyed off the CSV's `width` column:
- 40 mm sticker for wide bases.
- 20 mm sticker for everything else.

The top label runs at a single uniform 2.1 mm font-size on every
sticker so the army reads consistently across base sizes. The
designation grows on wide bases (4.5 mm vs 3.6 mm) because it has
more horizontal room between icon and flag there.

Left → right inside the sticker:
- 5×5 mm APP-6 unit icon (left, 0.3 mm horizontal margin, top edge
  at y=2.5 — pushed down so the label has its own band above).
- Top text — equipment / weapon name (e.g. `MERKAVA 3`, `FN MAG`,
  `AH-64`). 0.5 mm clearance from the sticker top edge.
- Bottom text — designation, prominent, centered (e.g. `א001` —
  letter-first per the IDF panel photo; `idf_migrate.letter_first()`
  does the reorder, the full CSV stays digits-first).
  0.5 mm clearance from the sticker bottom (descender to edge —
  matters for Hebrew final letters ן ך ץ ף).
- 5×3.64 mm flag (11:8 aspect, the renderer stretches non-11:8 flags
  with `preserveAspectRatio="none"`) with thin black border (right,
  0.3 mm horizontal margin, vertically centred against the icon).

Background fill from `AFFILIATION_BG[args.affiliation]` (or
`--background`). `build_sticker(...)` takes `bg` and the flag's inner
SVG so per-army parameters thread through cleanly.

## APP-6 icons (military_symbol)

We embed icon SVG content **inline** into each sticker — no `<image
href="…">` references, since several SVG renderers (including
rsvg-convert) won't follow them. `extract_inner_svg()` strips the
outer `<svg>` wrapper and returns the body + viewBox; the sticker SVG
nests it in a sized `<svg>` element.

### Affiliation prefix

`get_icon_svg(affiliation, symbol, is_hq)` forms
`f"{affiliation} {symbol}"` and passes it to
`military_symbol.get_symbol_svg_string_from_name`. So the `symbol`
column carries the bare phrase (`armor`, `infantry`,
`attack helicopter`, …) and affiliation is a per-army CLI flag.

### No echelon modifiers

Bare descriptions only — `"armor"`, never `"armor platoon"`. No
platoon dots, no company bars. The APP-6 echelon modifier visually
conflicts with the small print size and adds nothing useful at the
team-base scale.

### HQ marker

We **do not** use APP-6's flagstaff (it sticks out the side and
breaks the visual conformity of the sticker grid). Instead, when
`hq` is true on a row, we draw a horizontal black bar inside the
icon at the lobe / frame junction:

```
M63,63 L137,63   stroke=black, stroke-width=4, no halo
```

The icon coordinate space is 0–200 (viewBox `10.75 10.75 178.5 178.5`),
and y≈63 lands at the upper-lobe junction of the unknown quatrefoil
and inside the top portion of friend/hostile/neutral frames. No
white halo is needed because the bar stays within the fill.

### Library quirks

`military_symbol` v2.0.2 has two issues we work around:

- **`unknown fighter`** returns an SVG with an *open* path (looks
  like a cloud with gaps). Fix: add a trailing `z` to every path's
  `d` attribute, then override the viewBox to `0 0 200 160` because
  the library underestimates the wider aircraft curve and clips the
  wingtips at default bounds. Applied only for `unknown fighter` —
  friend/hostile/neutral fighters use rectangle/diamond/square
  frames that render fine without the fix.
- **`<aff> rockets`** doesn't resolve and silently defaults to a
  generic land unit. Fix: substitute `<aff> rocket artillery` for
  any symbol ending in `rockets` (MLRS / BM-21).

Both are handled in `get_icon_svg()` / `_normalize_symbol()`.

## Designation rendering

Designations can be any string. When the value mixes ASCII + non-ASCII
(Hebrew/Arabic/etc.), we add `direction="ltr"` +
`unicode-bidi="bidi-override"` so digits and the non-Latin letter
render in their CSV order — without the override, some renderers
reorder a mixed-script line. Pure-Latin designations skip the bidi
attributes so they don't get unnecessary attribute soup.

Font stack: `"Fira Code", "IBM Plex Sans Hebrew", "DejaVu Sans Mono",
monospace`. Fira Code carries the Latin glyphs (heavy weight, slashed
zeros). It has no Hebrew, so the renderer falls back glyph-by-glyph to
IBM Plex Sans Hebrew for Hebrew letters — both fonts are
fontconfig-installed via `apt install fonts-firacode fonts-ibm-plex`
(and DejaVu Sans Mono is the final safety net).

Label uses `font-weight="600"`; designation uses `font-weight="bold"`.
On dark backgrounds, both texts get a 0.06 mm black stroke with
`paint-order="stroke"` so the outline draws behind the fill — keeps
white-on-blue / red / gray readable.

Auto-shrink: monospace cell ≈ 0.6 × font-size, so a label that
exceeds `width - 2*0.3 mm` is shrunk uniformly (floor 1.3 mm).
rsvg-convert ignores SVG `textLength`, so we can't use the
declarative version.

## Flags

`flags/<iso>.svg` — every current ISO 3166-1 flag, vendored verbatim
from [lipis/flag-icons](https://github.com/lipis/flag-icons) (MIT,
sourced from Wikimedia Commons; see `flags/LICENSE-lipis`). lipis is
current-states-only, so the two Cold-War-era flags we need (`dd` East
Germany, `su` Soviet Union) are produced by `flags/build.py` as
simplified band-only versions. `cz` (modern Czech, identical to the
Czechoslovak flag) covers both eras.

The sticker renderer fits whatever's at the path into the 5×3.64 mm
slot with `preserveAspectRatio="none"`, so the upstream 4:3 ratio is
fine even though our slot is 11:8.

`--flag PATH` overrides `--country` and is the escape hatch for local
SVGs.

## IDF helpers (`idf_migrate.py`)

`sources/israeli_full.csv` is the rich source-of-truth: full army-list
structure (`kind`, `formation_name`, `letter`, `slot_*`, `unit_*`,
`team_role`, `team_position_*`, `base`) for composing and editing the
army. `idf_migrate.py` derives the minimal CSV
(`lists/israeli_minimal.csv`) the generator actually reads:

- `designation` and `name` copied across (hand-edits to `name` in the
  full CSV win; blanks are filled by `derive_name(team_role, unit_name)`).
- `symbol` from `team_role` (via `ROLE_SYMBOLS` and `role_base_form()`).
- `width` from `base`.
- `hq` from `team_role in {"HQ Tank", "Galil HQ team"}`.
- `formation` from `formation_name`.
- `group` from `letter` (first token, so `"א (Aleph)"` → `"א"`).

The full CSV is never modified. Re-run `python idf_migrate.py` to
refresh the minimal CSV after editing the source.

The Israeli army renders as APP-6 `unknown` (yellow) by deliberate
aesthetic choice, not a NATO-affiliation claim. Pass `--affiliation
friend` for blue rectangles.

### `name` column — IDF heuristics

`derive_name()` (in `idf_migrate.py`) drives the top label when the
CSV cell is blank; hand-edits win.

- **Tanks** — model only, no size descriptor: `Merkava 1/2/3`,
  `Magach 6`, `Magach 6 Blazer`, `Sho't Blazer`. HQ tanks share the
  same name (the HQ bar disambiguates).
- **Helicopters** — model + IDF Hebrew name: `AH-64 Peten`,
  `AH-1 Tzefa`, `CH-53 Yas'ur`. UH-1 is bare.
- **APCs** — chassis + IDF nickname in caps: `M113 Zelda`,
  `M113 Vayzata`, `Nagmashot`.
- **Infantry / weapons** — main weapon: `Galil`, `FN MAG`, `RPG-7`,
  `M47 Dragon`, `52mm`, `Redeye`.
- **Mortars / SP gun / TOW carrier / ATGM tank** — chassis:
  `M125` / `M106` / `M109` / `M150` / `Pereh` / `Jeep` / `Rabbi`.
- **AA / SAM / rockets** — chassis + system: `M163 VADS`,
  `ZSU-23-4 Shilka`, `M48 Chaparral`, `M270 MLRS`, `BM-21 Grad`.
- **Strike jet** — `A-4 Skyhawk`.
- **Artillery observer** — `M113 OP`.

Para / Reserve infantry intentionally share names with Mech (icons
are identical). A `P` / `R` suffix would be the natural future
refinement.

### Shared transport designations (IDF)

Mutually exclusive transport variants share a single designation per
slot, since you only field one variant per stand:
- Mech HQ transport: M113 / Vayzata / Nagmasho't share `002–004`.
- Mech platoon transport: M113 / Vayzata / Nagmasho't share `113–116`.
- Para HQ transport: M113 / UH-1 share `002–003`.
- Para platoon transport: M113[Para] / UH-1 / CH-53 share `113–116`.

Because the same designation maps to multiple distinct stickers
(different name, different icon shading), `out/` filenames include
the slugified name: `out/{designation}-{slug}.svg`.

## Base print files (`bases.py`)

Second output target: ground-textured bases printed on a **EufyMake E1
UV flatbed** (mini flatbed, 330×90 mm printable, white underlayer →
CMYK, no gloss — matte varnish afterwards). `bases.py` renders one
color + heightmap PNG pair per CSV row into `bases/`:

```sh
python bases.py --csv <csv> --country IL [--objectives N] \
                [--formation SUBSTR] [--seed 1979]
python bases_preview.py --country IL       # sample → bases_preview.html
```

Decisions (settled 2026-07, after a physical test print):

- **Print mode:** individual pre-cut bases positioned on a jig relative
  to the flatbed origin. Every crop carries a 1 mm bleed ring, and the
  sticker bleeds with it — its background color extends to the crop
  edges on left/right/bottom; the printed content and the sticker's top
  edge (interior boundary) stay on the nominal base outline (lower
  8 mm, same layout as the paper stickers).
- **Stickers are composited** onto the base texture — the paper sticker
  flow (`generator.py`/`sheets.py`/`preview.py`) stays fully functional
  without `bases.py`.
- **Relief printing is on** (heightmaps, **0.8 mm max relief** in Eufy
  Studio — settled 2026-07 via the 3D-viewer ×2 comparison and confirmed
  on a physical test print; the handoff's 0.3–0.5 mm is obsolete).
  Heightmap area under the sticker is flattened to 0. Polarity confirmed
  on the test print: white = raised.
- **Texture variants are per-platoon consistent, not identical**: all
  bases of one (formation, group) share a variant (reference / v1_rocky
  / v2_soil / v3_grass), each base gets its own random crop + 90°-step
  rotation. `v4_track` is reserved for objectives (`--objectives N`,
  **40×30 mm**, no sticker, crops centred on the vehicle track).
- All randomness is seeded (`--seed`, default 1979) with stable per-row
  keys — reruns are byte-identical.
- Substrate: **laser overhead-transparency film (plain PET)** — test
  print at 0.8 mm relief (worst case) is usable (2026-07; white
  underlayer provides opacity on the clear film). The cured ink stack
  curls the film slightly — a model's weight pushes it flat, so the
  glue-down to a rigid base must hold the curl permanently:
  full-surface bond (double-sided adhesive sheet / contact adhesive),
  not glue dots, or corners lift. The rigid base itself never sees UV
  heat. 1 mm PLA direct print had warped; PETG direct print untested
  and likely moot. Still open: long-term ink adhesion on the smooth
  PET (crosshatch-tape test) and the glue choice.
  **Next test (due ~2026-07-07): 1 mm laser-cut acrylic** — acrylic is
  the canonical UV-flatbed substrate; if direct print on pre-cut
  acrylic blanks works, that revives the original jig plan and the
  film route becomes the fallback.

Scale is locked to the validated texture scale: 1536 px / 130 mm ≈
11.815 px/mm ≈ 300 DPI, embedded in the PNGs — **place at 100% in Eufy
Studio, never "fit to bed"**. 20×40 mm base + bleed → 260×496 px.

`textures/` holds the five 1536×1024 textures + matching heightmaps
(AI-generated Golan basalt/grass/soil terrain, color-matched set;
`generate_heightmaps.py` in there is the reproducible heightmap
derivation, needs opencv/scipy which are *not* in requirements.txt).
Preprocessing for the E1's midtone compression happens in code at load
(`Textures`): mean-only color-match of v1–v4 to reference (matching
std too imports the reference's contrast and ruins the low-contrast
v3), contrast & saturation +18 %, shadow lift, extra unsharp on v3.
The vendored PNGs stay pristine.

The `base` CSV column (`WxD` mm, sticker spans W along the lower 8 mm
of D) drives crop sizes. Army base sizes: 20×20 (small weapon teams),
20×30 (most vehicles), 20×40 (tanks, helis, jets, Nagmasho't, M109,
BM-21, Pereh — big-model calls made 2026-07), 40×20 (wide infantry).

### Jig plates (`jig.py`)

The plate compositor + jig generator, built around **one reusable jig
per pocket geometry** (not per print job). Wide 40×20 infantry bases
are rotated upright (`--no-rotate` to disable) — flatbed orientation
is irrelevant — collapsing the classes to 20×40 / 20×30 / 20×20
+ 40×30 objectives. Outputs under gitignored `jig/`:

- `jig-<class>.svg` + `jig-a4-N.svg` — 4 reusable jig strips, nested
  two-per-A4 inset 5 mm from the sheet edges (no cut lands on a sheet
  edge). All four jigs share ONE uniform outer footprint (290×90, the max
  pocket extent across classes — smaller-pocket jigs just carry extra
  border) so a single printed clamp fits every jig. Outline a few mm
  shorter than the sheet, all four corners 3 mm rounded; the engraved
  origin datum (not the corner) is the flatbed reference, refined by
  the calibration print. Kerf-compensated holes, engraved slot numbers,
  red=cut / blue=engrave.
- `blanks-<class>-N.svg` — dense A4 blank-cutting sheets (0.8 mm
  spacing, 2 mm edge margin via `--blank-gap/--blank-margin`); each
  jig's own dropouts count toward the blank total.
- `plate-<class>-NN-color.png/-height.png` — print plates on the fixed
  grid, 300.101 DPI, place at 100%. Empty grid slots on the last plate
  of a class just print nothing.
- `manifest.csv` — class/plate/slot → designation/position.

Filters `--formation/--group/--objectives`; geometry
`--margin/--gap/--clearance/--kerf/--radius`, `--plate WxH`. Calibrated
values (2026-07, 1 mm acrylic): `--kerf 0.15`, `--clearance 0.0` (slip
fit — the coupon's c=0.0 pocket seated perfectly; empirical fit is
kerf-independent as long as production reuses the coupon's kerf).
`--calibrate` writes four test artifacts in dependency order:
`calibration-material.svg` first (power/speed: 16 squares in 16 stroke
colors to map to a settings ladder in the laser software — or use the
software's native material test), then `calibration-kerf.svg` at the
chosen settings (30 mm square; kerf = (hole − dropout)/2), then re-run
with the measured `--kerf` so `calibration-fit.svg`'s clearance-ladder
labels are honest (snug pocket's label = `--clearance`; its two blanks
sit at the production 0.8 mm sheet spacing as a nesting stress test),
and `calibration-print.png` any time (window-origin check; border
offset = `--origin-x/--origin-y`, which shift all print plates). Full
army
= 1983 bases → 4 jigs (2 A4) + 25 blank sheets (27 A4 total) + 81
print plates. Workflow: cut jigs once, tape to flatbed against origin
(**verify the window-starts-at-origin assumption with a calibration
print**), drop blanks in — only size matters, the print makes each
base self-identifying — print color+height at 100 %, unload, refill.
Sticker bleed overprints ~1 mm onto the jig, so the jig gets inky;
that's by design.

## Rotor discs (`rotors.py`)

PropBlur-style spinning-rotor discs for the helicopters, printed on
clear laser-transparency film with the **white ink layer disabled**
(the PNGs carry real alpha; white underlayer would kill the
transparency). One disc per type at true 1:285 rotor diameter —
AH-64/UH-1 51.3 mm, AH-1 47.1 mm, CH-53 77.3 mm — plus packed
330×90 mm plates (`--counts ah64=8,...`) and `rotors/preview.png`.
Same 300.101 DPI place-at-100% rule as the bases. Each plate copy gets
a seeded random blade rotation so multiples don't look photocopied.
Look tuning knobs at the top of the file: `SWEEP_*`, `SOLID_*`,
`FEATHER_POW`.

Plates are 297×90 A4-transparency strips. Each `plate-N.png` carries
two magenta registration crosshairs; the matching `plate-N-cut.svg`
has the same crosshairs plus per-disc perimeter circle (true rotor
radius) and a 0.6 mm center hole (`HOLE_MM`). Laser side: LightBurn →
Laser Tools → **Print and Cut**, align to the two crosshairs (handles
offset + rotation), cut. Requires a CO₂ laser — clear PET is
transparent to blue diodes.

Assembly (validated on a test disc 2026-07): mount **ink-side down**
(PET protects the print; residual film curl reads as rotor coning).
Manual fallback: cut on the printed ring, punch the center hole on a
hard flat backing — freehand drilling bends the disc.

## Stack

- Python 3.12 (military-symbol 2.x uses 3.12 f-string syntax). Pinned
  in `flake.nix`.
- `military-symbol==2.0.2`, `pyyaml` (its runtime dep), `svgwrite`
  (kept in requirements for now even though we currently build SVG
  strings directly).
- `pillow` + `numpy` — texture preprocessing / compositing in
  `bases.py`. On NixOS the pip wheels need `libstdc++` on
  `LD_LIBRARY_PATH`; the flake's dev shell sets this.
- `librsvg` (provides `rsvg-convert`) — used by `preview.py`,
  `sheets.py` and `bases.py` (sticker rasterization). Also pulled in
  by the flake's dev shell.
