# Bundled flag SVGs

Pick a flag with `python generator.py --country IL` (any ISO 3166-1
alpha-2 code that exists in this directory, lowercased), or supply
your own SVG with `--flag PATH`.

## Source

Every ISO 3166-1 flag is vendored verbatim from
[lipis/flag-icons](https://github.com/lipis/flag-icons) (MIT, ultimately
sourced from Wikimedia Commons) — see `LICENSE-lipis`. To refresh:

```sh
git clone --depth 1 --filter=blob:none --sparse https://github.com/lipis/flag-icons.git /tmp/flag-icons
( cd /tmp/flag-icons && git sparse-checkout set flags/4x3 )
cp /tmp/flag-icons/flags/4x3/*.svg flags/
```

The sticker renderer fits whatever's at the path into the 5×3.64 mm
slot with `preserveAspectRatio="none"`, so the upstream 4:3 ratio is
fine even though our slot is 11:8.

## Historical flags (not in lipis, built by `flags/build.py`)

lipis covers current ISO 3166-1 only, so Cold-War-era armies need:

- `dd` East Germany (DDR) — simplified, no emblem
- `su` Soviet Union — simplified, solid red

`cz` is the modern Czech flag, which is identical to the
Czechoslovak flag — fine for both eras.

`python flags/build.py` only writes files that don't already exist,
so hand-edits are safe. Delete a file and re-run to regenerate it
from the script's spec.

## Overrides

`--flag PATH` overrides `--country` and is the escape hatch for a
local SVG (e.g. a unit pennant, or a regional/historical variant not
in the bundled set).
