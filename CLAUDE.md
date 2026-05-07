# 6mm IDF Sticker Generator — design notes

Hobby project: prints unit-ID stickers for a 6mm Team Yankee Israeli army.
One sticker per base (1979 across 8 formations + support pool).

## Pipeline

1. `lists/israeli_full.csv` — inventory (one row per base).
2. `generator.py` reads it and writes `out/{designation}.svg`, one per row.
3. `preview.py` renders one sample sticker per unique (icon, label, width)
   tuple to `preview.html` (PNG via rsvg-convert, embedded as base64 data
   URIs, so the file is fully self-contained).
4. `sheets.py` lays out every sticker per formation onto A4 portrait
   pages with a slightly grey background and combines the pages into
   one PDF per formation under `sheets/`. `rsvg-convert -f pdf` does
   the multi-page PDF concatenation.

`out/` and `sheets/` are gitignored — fully regenerable from the CSV +
generator.

## Sticker layout

8 mm tall, the lower 8 mm of the unit's base. Two physical widths:
- `40x20` base → 40 × 8 mm sticker.
- everything else (`20x20`, `20x30`, `20x40`) → 20 × 8 mm sticker.

The top label runs at a single uniform 2.1 mm font-size on every
sticker so the army reads consistently across base sizes. The
designation does grow on wide bases (4.5 mm vs 3.6 mm) because it has
more horizontal room between icon and flag there.

Left → right inside the sticker:
- 5×5 mm APP-6 unit icon (left, 0.3 mm horizontal margin, top edge
  at y=2.5 — pushed down so the label has its own band above).
- Top text — equipment / weapon name (e.g. `MERKAVA 3`, `FN MAG`,
  `AH-64`). 0.5 mm clearance from the sticker top edge.
- Bottom text — designation, prominent, centered (e.g. `001א`).
  0.5 mm clearance from the sticker bottom (descender to edge —
  matters for Hebrew final letters ן ך ץ ף).
- 5×3.64 mm Israeli flag (proper 11:8 aspect) with thin black
  border (right, 0.3 mm horizontal margin, vertically centred
  against the icon).

Background fill `#FFFFFF`. The constant lives at the top of `generator.py`
and is parameterised in `build_sticker(...)` so it can become per-faction
later.

## APP-6 icons (military_symbol)

We embed icon SVG content **inline** into each sticker — no `<image
href="…">` references, since several SVG renderers (including
rsvg-convert) won't follow them. `extract_inner_svg()` strips the outer
`<svg>` wrapper and returns the body + viewBox; the sticker SVG nests it
in a sized `<svg>` element.

### Affiliation

Always **unknown** (yellow quatrefoil for ground / rotary, yellow cumulus
for fixed-wing). Configurable later via the description prefix.

### No echelon modifiers

Bare descriptions only — `"unknown armor"`, never `"unknown armor
platoon"`. No platoon dots, no company bars from the library. The
APP-6 echelon modifier visually conflicts with the small print size and
adds nothing useful at the team-base scale.

### HQ marker

We **do not** use APP-6's flagstaff (it sticks out the side and breaks
the visual conformity of the sticker grid). Instead, for HQ tanks and
HQ-section infantry teams (`team_role` of `HQ Tank` or `Galil HQ team`),
we draw a horizontal black bar inside the quatrefoil at the lobe
junction:

```
M63,63 L137,63   stroke=black, stroke-width=4, no halo
```

The icon coordinate space is 0–200 (viewBox `10.75 10.75 178.5 178.5`),
and the upper lobe junction sits at y≈63. No white halo is needed
because the bar is fully inside the yellow fill.

HQ Transports (e.g. `Transport (HQ M113)`, `Transport (HQ UH-1)`) do
**not** get the bar — they share the APC / utility-helicopter icon with
their non-HQ siblings.

### Library quirks

`military_symbol` v2.0.2 has two issues we work around:

- **`unknown fighter`** returns an SVG with an *open* path (looks like
  a cloud with gaps). Fix: add a trailing `z` to every path's `d`
  attribute, then override the viewBox to `0 0 200 160` because the
  library underestimates the wider aircraft curve and clips the
  wingtips at default bounds.
- **`unknown rockets`** doesn't resolve and silently defaults to a
  generic land unit. Fix: substitute `unknown rocket artillery` for
  MLRS / BM-21.

Both are handled in `get_icon_svg()`.

## team_role → APP-6 description

`role_base_form()` strips:
- `[Para]` / `[Reserve]` paint-distinction suffixes (icon is identical).
- Parenthetical option notes like `(M72 LAW)`, `(Tammuz/Tammuz 2)`.
- Em-dash annotations like `— same model as above`.

`ROLE_DESCRIPTIONS` then maps the cleaned form to the APP-6 description.
See the dict at the top of `generator.py` for the full table.

## `name` column (top label on the sticker)

Each CSV row has a `name` column that drives the sticker's top label.
`derive_name(team_role, unit_name)` is the source of truth and is used
by `python generator.py --update-csv` to fill in any blank `name`
cells; once populated, hand-edits in the CSV win (the generator
reads the column verbatim).

Naming rules:

- **Tanks** — model only, no size descriptor: `Merkava 1/2/3`,
  `Magach 6`, `Magach 6 Blazer`, `Sho't Blazer`. HQ tanks share the
  same name (the icon's HQ bar disambiguates).
- **Helicopters** — model + IDF Hebrew name: `AH-64 Peten` (Apache),
  `AH-1 Tzefa` (Cobra/Viper), `CH-53 Yas'ur` (Sea Stallion). The
  UH-1 was never given a settled IDF name in service so it stays
  bare (`UH-1`). `Transport heli` defaults to `UH-1` if the
  unit_name doesn't name a model; `Transport heli swap (CH-53)` is
  always `CH-53 Yas'ur`.
- **APCs** — chassis + IDF nickname in caps: `M113 Zelda`,
  `Tiran Vayzata` (Achzarit, T-55-derived), `Nagmashot`
  (Nagmasho't already encodes its Sho't/Centurion chassis in the
  name, so no separate prefix). UH-1 transports use `UH-1`.
- **Recce** — vehicle from `unit_name`: `Jeep` / `M113 Zelda` /
  `Rabbi`.
- **Infantry** — main weapon: `Galil` (rifle and HQ team alike),
  `FN MAG`, `RPG-7`, `M47 Dragon`, `52mm`, `Redeye` (MANPADS).
- **Mortars / SP gun / TOW carrier / ATGM tank** — chassis:
  `M125` / `M106` / `M109` / `M150` / `Pereh` / `Jeep` / `Rabbi`.
- **AA / SAM / rockets** — chassis + system, dropping the chassis
  only when it would overflow the 20 mm sticker:
  `M163 VADS`, `ZSU-23-4 Shilka`, `M48 Chaparral`, `M270 MLRS`,
  `BM-21 Grad`.
- **Strike jet** — `A-4 Skyhawk`.
- **Artillery observer** — `M113 OP`.

Names are stored uppercase. `derive_name()` returns uppercase by
default; CSV hand-edits are taken verbatim, so write a mixed-case
override if you want one.

The label sits in its own band above the icon/flag, so it can run
the full sticker width (minus a 0.3 mm side margin) — only the
designation in the lower band has to thread between the icon and
the flag. If a name's natural rendered width would still exceed the
sticker width (rare at the current 2.1 mm size), `build_sticker()`
shrinks the label font-size to fit. We can't use SVG `textLength`
because `rsvg-convert` ignores it. Floor at 1.3 mm font-size to
keep the label legible.

Para / Reserve infantry intentionally share names with Mech (icons are
identical). A `P` / `R` suffix would be the natural future refinement.

## Designation rendering

Designations are 4 chars: `NNN<Hebrew letter>` (Aleph through Tav,
including final forms). Bottom text uses `direction="ltr"` +
`unicode-bidi="bidi-override"` so digits and the Hebrew letter render in
their CSV order — without the bidi override, some renderers reorder a
mixed-script line.

Font stack: `"Fira Code", "IBM Plex Sans Hebrew", "DejaVu Sans Mono",
monospace`. Fira Code carries the Latin glyphs (heavy weight, slashed
zeros). It has no Hebrew, so the renderer falls back glyph-by-glyph to
IBM Plex Sans Hebrew for the Hebrew letter — both fonts are
fontconfig-installed via `apt install fonts-firacode fonts-ibm-plex`
(and DejaVu Sans Mono is the final safety net).

Label uses `font-weight="600"`; designation uses `font-weight="bold"`.

## Israeli flag

Generated locally — `flags/il.svg`, 220 × 160 (11:8). White field, two
blue (`#0038B8`) stripes top/bottom, hollow Star of David centred. The
sticker inlines the same content so it's self-contained.

## Stack

- Python 3.12 (military-symbol 2.x uses 3.12 f-string syntax). Pinned in
  `flake.nix`.
- `military-symbol==2.0.2`, `pyyaml` (its runtime dep), `svgwrite` (kept
  in requirements for now even though we currently build SVG strings
  directly).
- `librsvg` (provides `rsvg-convert`) — only used by `preview.py`. Also
  pulled in by the flake's dev shell.
