# 6mm-Modern Unit-Sticker Generator
This script generates unit stickers for my 6mm unit-bases which can be found [here](about:blank). We use them for Team Yankee but use them for what ever pleases you.

## Requirements
- Python
- PIP
- [RobotoMono Nerd Font](https://www.nerdfonts.com/font-downloads)

## Usage
Enter your unit data into `input.csv`

- designation: Unit designation e.g. "A-01", "114" - I would advise against more then 4 characters
- name: Unit name e.g. "LEOPARD 2" - this depends a bit on base size: Vehicle and Small bases don't work with more than 10 characters, medium with 15, and large with 20.
- allegiance: one of `NATO`, `PACT`, `UNK:<hexcolourcode>`, `CIV:<hexcolourcode>`, modifies icon and background colour
- icon: Icon file to use they can be found in `icons/` only the identifier part should be used e.g. `armor_hq` for `icons/armor_hq_friendly.svg`
- flag: ISO 3166-1 alpha-2 designation of Units country matching flag should be present under `flags/`
- type: `armour`, `small` ,`medium` ,`large` pretty self explanatory

then run `python main.py` to generate files in `out/`

