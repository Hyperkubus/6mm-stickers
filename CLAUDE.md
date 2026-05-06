# 6mm IDF Sticker Generator — design notes

Hobby project: prints unit-ID stickers for a 6mm Team Yankee Israeli army.
One sticker per base (1979 across 8 formations + support pool).

## Pipeline

1. `lists/israeli_full.csv` — inventory (one row per base).
2. `generator.py` reads it and writes `out/{designation}.svg`, one per row.
3. `preview.py` renders one sample sticker per unique (icon, label, width)
   tuple to `preview.html` (PNG via rsvg-convert, embedded as base64 data
   URIs, so the file is fully self-contained).

`out/` is gitignored — fully regenerable from the CSV + generator.

## Sticker layout

8 mm tall, the lower 8 mm of the unit's base. Two physical widths:
- `40x20` base → 40 × 8 mm sticker (larger fonts, ≤12-char top label).
- everything else (`20x20`, `20x30`, `20x40`) → 20 × 8 mm sticker (≤8-char
  top label).

Left → right inside the sticker:
- 4×4 mm APP-6 unit icon (left).
- Top text — short type label (e.g. `Mk3`, `MAG`, `AH-64`).
- Bottom text — designation, prominent, centered (e.g. `001א`).
- 4×4 mm Israeli flag with thin black border (right).

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

## Short label heuristic

`short_label()` prefers specific equipment over generic role:

- **Tanks** — model from `unit_name`: `Mk1` / `Mk2` / `Mk3` / `M6` /
  `M6B` / `Sho't`. HQ tanks: `HQ Mk3` etc.
- **Helicopters** — from `unit_name`: `AH-64`, `AH-1`, `CH-53`, `UH-1`.
  `Transport heli` rows whose `unit_name` doesn't name the model
  default to `UH-1`. `Transport heli swap (CH-53)` is always `CH-53`.
- **APCs** — variant from `team_role` parenthetical: `M113`, `Vayzata`,
  `Nagmash` (truncated from `Nagmasho't`).
- **Recce** — vehicle from `unit_name`: `Jeep` / `M113` / `Rabbi`.
- **Infantry** — `Galil` / `MAG` / `RPG` / `Dragon` / `52mm` / `Redeye`.
- **HQ infantry** — `HQ`.
- **Self-propelled / vehicles** — `M109` / `MLRS` / `BM-21` / `VADS` /
  `Shilka` / `Chap` (Chaparral).
- **Strike jet** — `A-4`.
- Fall-through: first word of `team_role` truncated to `max_label`.

Para / Reserve infantry intentionally share names with Mech (icons are
identical anyway). A `P` / `R` suffix would be the natural future
refinement.

## Designation rendering

Designations are 4 chars: `NNN<Hebrew letter>` (Aleph through Tav,
including final forms). Bottom text uses `direction="ltr"` +
`unicode-bidi="bidi-override"` so digits and the Hebrew letter render in
their CSV order — without the bidi override, some renderers reorder a
mixed-script line.

Font stack: `"RobotoMono Nerd Font", "DejaVu Sans Mono", monospace`.
DejaVu Sans Mono is in most Linux distros and contains Hebrew, so it's
the dependable fallback for `rsvg-convert`.

## Israeli flag

Generated locally — `flags/il.svg`, 220 × 160 (11:8). White field, two
blue (`#0038B8`) stripes top/bottom, hollow Star of David centred. The
sticker inlines the same content so it's self-contained.

## Stack

- Python 3.12 (military-symbol 2.x uses 3.12 f-string syntax).
- `military-symbol==2.0.2`, `pyyaml` (its runtime dep), `svgwrite` (kept
  in requirements for now even though we currently build SVG strings
  directly).
- `librsvg2-bin` (for `rsvg-convert`) — only used by `preview.py`.
