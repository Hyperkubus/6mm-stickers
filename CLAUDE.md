# 6mm sticker generator — design notes

Hobby project: prints unit-ID stickers for 6mm Team Yankee armies.
The generator is faction-agnostic; the worked example is an Israeli
1979 army (`sources/israeli_full.csv`, 1979 stickers across 8 formations
+ the support pool, one per base).

## Pipeline

1. `<army>.csv` — inventory (one row per base). The generator only needs
   the minimal columns (designation, name, symbol, width, optional
   hq/formation/group); a richer source-of-truth CSV with extra columns
   is fine.
2. `generator.py` writes `out/{designation}-{slug}.svg`, one per row.
3. `preview.py` renders one sample sticker per unique (symbol, hq,
   name, width) tuple to `preview.html` (PNG via rsvg-convert, embedded
   as base64 data URIs).
4. `sheets.py` lays out every sticker per `formation` onto A4 portrait
   pages and concatenates into one PDF per formation under `sheets/`.
   `rsvg-convert -f pdf` does the multi-page PDF concatenation.

`out/` and `sheets/` are gitignored — fully regenerable from the CSV
+ the generator.

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
- Bottom text — designation, prominent, centered (e.g. `001א`).
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

## Stack

- Python 3.12 (military-symbol 2.x uses 3.12 f-string syntax). Pinned
  in `flake.nix`.
- `military-symbol==2.0.2`, `pyyaml` (its runtime dep), `svgwrite`
  (kept in requirements for now even though we currently build SVG
  strings directly).
- `librsvg` (provides `rsvg-convert`) — used by `preview.py` and
  `sheets.py`. Also pulled in by the flake's dev shell.
