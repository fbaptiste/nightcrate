# Sky data sources

`sky.json` is licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
It is an adaptation of HYG and Stellarium data. To rebuild it, fetch the four
local inputs below, unpack d3-celestial, and run from `backend/`:

```sh
uv run python scripts/build_sky_data.py \
  --package-dir /path/to/d3-celestial/package \
  --hyg /path/to/hyg_v44.csv.gz \
  --stellarium-modern /path/to/modern/index.json \
  --star-names /path/to/IAU-CSN.txt
```

The script checks each input against the SHA-256 it pins:

- **d3-celestial 0.7.35:** `npm pack d3-celestial@0.7.35`, then unpack it.
- **HYG v4.4:** `hyg/CURRENT/hyg_v44.csv.gz` from
  <https://codeberg.org/astronexus/hyg>, commit
  `53e3df311869e813ace5f1ad2ec4ce909f13256c` (stored with Git LFS).
- **Stellarium:** `skycultures/modern/index.json` from
  <https://github.com/Stellarium/stellarium>, commit
  `daace2add6a1bf886e8ee1934f51e9c69f818d18`.
- **IAU Catalog of Star Names:**
  <https://www.pas.rochester.edu/~emamajek/WGSN/IAU-CSN.txt>, last updated
  2022-04-04.

## Credits and licences

- **Stars:** HYG v4.4 by David Nash ([astronexus.com](https://astronexus.com/),
  [source](https://codeberg.org/astronexus/hyg)), CC BY-SA 4.0. NightCrate
  rounds positions and magnitudes, limits the list to magnitude 6, merges
  duplicate rounded positions, and retains a fainter star only when an IAU
  figure requires it.
- **Boundaries:** Stellarium's modern sky culture by the Stellarium
  contributors, CC BY-SA 4.0. Its IAU boundaries are Patrick Barbier's
  `edges_18` in B1875 coordinates. NightCrate precesses them to J2000, then
  adaptively fills and simplifies the lines.
- **Star names:** the IAU Catalog of Star Names from the IAU Working Group on
  Star Names ([WGSN information](https://exopla.net/star-names/modern-iau-star-names/)).
  WGSN states that the names are in the public domain; the catalogue file
  states that IAU-produced products are released under Creative Commons
  Attribution. NightCrate matches the names by Hipparcos number.
- **Constellation figures and name positions:** d3-celestial 0.7.35,
  BSD-3-Clause, Copyright © 2015 Olaf Frohn. See
  `LICENSE-d3-celestial.txt`. The stick figures come from IAU constellation
  charts credited to “IAU and Sky & Telescope magazine (Roger Sinnott & Rick
  Fienberg)”, with patterns by Alan MacRobert, under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Olaf Frohn
  modified the lines; NightCrate converts and joins them to its star list.

Star positions and magnitudes originate from ESA's Hipparcos mission.
Credit: ESA (ESA 1997, *The Hipparcos and Tycho Catalogues*, ESA SP-1200).
