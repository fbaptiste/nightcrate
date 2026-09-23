# NightCrate

A free, local application for astrophotographers to plan nights, catalog imaging
projects, and inspect their data. NightCrate connects the files and logs produced
by capture software with the context needed to review and process them.

No account or telemetry. Catalogs and image processing stay on your machine;
forecasts and survey imagery are fetched from external services when needed.

![Target planner](docs/screenshots/planner-tonight.png)

## Features

- **Projects and catalog:** bind folders or archives, classify captures from
  headers, tag rigs/targets, inspect frames, keep notes and finished images.
  Files stay where they are. Rescanning updates the catalog without duplicating
  records within a project. A project can start with a finished image and manual
  sessions; importing raw captures is optional.
- **Sessions and integration:** enter capture batches manually or derive them
  from cataloged lights. View totals by filter and observing night. Duoband
  equipment-filter sessions count toward each passed line and once toward total
  exposure time.
- **Frame quality:** batch HFR, star count, star SNR, and background measurements,
  with progress, cancellation, and sorting to find frames worth inspecting.
- **Planning:** date/location/horizon-aware visibility, rig framing, filter-aware
  target scores, sky tracks, annual visibility, wishlists and calendars.
- **Image analysis:** FITS, XISF, PixInsight projects, PNG/JPEG/TIFF and archive
  entries; auto/manual stretch, histogram, pixel inspection, FITS header editing,
  aberration inspection, plate solving and catalog-object overlays.
- **Guiding:** standalone PHD2 log analysis with time-series and dispersion plots,
  section/selection statistics, calibration geometry and range export.
- **Equipment:** editable component catalog, personal rigs and smart-scope
  presets, filter loadouts, imaging and guiding calculators.
- **Weather:** nightly/hourly forecasts with astronomical context and an
  imaging-quality breakdown. The current model and its limitations are described
  in [the scoring rationale](docs/imaging-quality-model.md).
- **Reference tools:** DSO catalog, locations/custom horizons, astronomy
  calculators, Tonight summary, API documentation and activity console.

![Image analyzer](docs/screenshots/image-analyzer.png)

## Status

Active development. Folder ingestion, derived sessions and frame measurements
are implemented. Calibration coverage UI, guiding association with exposures,
capture-log/autofocus integration and a unified session timeline are planned.
The app has no packaged native installer yet.

Equipment is assigned through declared rigs and folder tags; automatic FITS
equipment inference and integration goals were removed. Derived sessions update
on request. Mixing manual and derived records for the same captures can currently
inflate totals.

See [the active plan](PLAN.md) for remaining work and the
[documentation index](docs/README.md) for code locations and technical references.

## Run locally

Prerequisites: Python 3.14, [uv](https://docs.astral.sh/uv/), Node 20.19+ or 22.12+.
Install [ASTAP](https://www.hnsky.org/astap.htm) and a star database separately if
using plate solving. Intel Macs also need Xcode Command Line Tools for
source-built dependencies (`xcode-select --install`).

```bash
make install    # install backend/frontend dependencies
make dev        # backend :8000, frontend :5173
```

The setup wizard creates or opens a workspace containing `nightcrate.db` and
rendered `project_data/`. Source images remain in their original locations;
copying a workspace does not copy that source library. Admin manages multiple
workspaces and downloads the DSO catalogs.

Other commands: `make backend`, `make frontend`, `make test`, `make test-fast`,
`make lint`, `make format`. Use `make dev BROWSER=none` to suppress browser launch
or `make dev LOG=DEBUG` for diagnostic logs. Developer checks and conventions are
in [CLAUDE.md](CLAUDE.md).

## Stack

Python/FastAPI/Pydantic, SQLite with raw SQL and yoyo migrations; React/TypeScript,
Vite, MUI Community, Zustand, TanStack Query and D3. Astronomy and image work use
astropy, numpy/scipy and sep. Optional mlx (Apple Silicon) or CuPy (CUDA) accelerates
supported operations; numpy is the fallback. Platform paths support Mac, Windows
and Linux.

## Access model

NightCrate trusts the local user and has no authentication. Normal `make dev`
binds the backend to localhost. The file browser can access paths permitted to
the process; this is not a shared or publicly hosted service.

`make dev-lan` enables HTTPS tablet access on a trusted LAN and exposes **both**
servers on the network, with permissive backend CORS. Do not use it on an
untrusted/shared network. Vite uses `frontend/.certs/{cert,key}.pem` if available,
otherwise a self-signed certificate. Never commit certificates or databases.

## License

[MIT](LICENSE). Dependency and data-source acknowledgments follow.

## Open Source Acknowledgments

Libraries and data sources used by NightCrate:

### Backend (Python)

| Library | License | Copyright |
|---|---|---|
| [NumPy](https://numpy.org/) | BSD 3-Clause | Copyright (c) 2005-2025, NumPy Developers |
| [SciPy](https://scipy.org/) | BSD 3-Clause | Copyright (c) 2001-2025, SciPy Developers |
| [Astropy](https://www.astropy.org/) | BSD 3-Clause | Copyright (c) 2011-2025, Astropy Developers |
| [Pillow](https://python-pillow.org/) | HPND (PIL License) | Copyright (c) 1997-2011 by Secret Labs AB; Copyright (c) 1995-2011 by Fredrik Lundh; Copyright (c) 2010-2025 by Jeffrey A. Clark and contributors |
| [FastAPI](https://fastapi.tiangolo.com/) | MIT | Copyright (c) 2018 Sebastián Ramírez |
| [Uvicorn](https://www.uvicorn.org/) | BSD 3-Clause | Copyright (c) 2017-present, Encode OSS Ltd |
| [Pydantic](https://docs.pydantic.dev/) | MIT | Copyright (c) 2017-2025, Samuel Colvin and Pydantic Contributors |
| [httpx](https://www.python-httpx.org/) | BSD 3-Clause | Copyright (c) 2019, Encode OSS Ltd |
| [aiosqlite](https://github.com/omnilib/aiosqlite) | MIT | Copyright (c) Amethyst Reese |
| [yoyo-migrations](https://ollycope.com/software/yoyo/) | Apache 2.0 | Copyright (c) Oliver Mayfield-Sherborne |
| [aiofiles](https://github.com/Tinche/aiofiles) | Apache 2.0 | Copyright (c) Tin Tvrtković |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache 2.0 | Copyright (c) 2012-2013 Andrew Dunham |
| [platformdirs](https://github.com/tox-dev/platformdirs) | MIT | Copyright (c) platformdirs contributors |
| [lz4](https://github.com/python-lz4/python-lz4) | BSD 3-Clause | Copyright (c) 2012-2023, Jonathan Underwood |
| [zstandard](https://github.com/indygreg/python-zstandard) | BSD 3-Clause | Copyright (c) 2016-present, Gregory Szorc |
| [defusedxml](https://github.com/tiran/defusedxml) | PSF-2.0 | Copyright (c) 2013-2023, Christian Heimes |
| [tifffile](https://github.com/cgohlke/tifffile) | BSD 3-Clause | Copyright (c) 2008-2026, Christoph Gohlke |
| [imagecodecs](https://github.com/cgohlke/imagecodecs) | BSD 3-Clause | Copyright (c) 2008-2026, Christoph Gohlke |
| [bottleneck](https://github.com/pydata/bottleneck) | BSD 2-Clause | Copyright (c) 2010-2019, Keith Goodman |
| [sep](https://github.com/kbarbary/sep) | LGPL-3.0 | Copyright (c) 2014, Kyle Barbary |
| [py7zr](https://github.com/miurahr/py7zr) | LGPL-2.1+ | Copyright (c) 2019-2025, Hiroshi Miura |
| [mlx](https://github.com/ml-explore/mlx) | MIT | Copyright (c) 2023-2026, Apple Inc. |
| [timezonefinder](https://github.com/jannikmi/timezonefinder) | MIT | Copyright (c) 2016-2026, Jannik Michelfeit |
| [astropy-healpix](https://github.com/astropy/astropy-healpix) | BSD 3-Clause | Copyright (c) Astropy Developers |

### Frontend (TypeScript / React)

| Library | License | Copyright |
|---|---|---|
| [React](https://react.dev/) | MIT | Copyright (c) Meta Platforms, Inc. and affiliates |
| [MUI](https://mui.com/) (Material UI + X Community) | MIT | Copyright (c) MUI |
| [Emotion](https://emotion.sh/) (@emotion/react, @emotion/styled) | MIT | Copyright (c) Emotion team and other contributors |
| [D3.js](https://d3js.org/) | ISC | Copyright (c) 2010-2025, Michael Bostock |
| [Zustand](https://github.com/pmndrs/zustand) | MIT | Copyright (c) 2019 Paul Henschel |
| [TanStack Query](https://tanstack.com/query) | MIT | Copyright (c) 2021-present Tanner Linsley |
| [React Router](https://reactrouter.com/) | MIT | Copyright (c) React Training LLC 2015-2019; Copyright (c) Remix Software Inc. 2020-2021; Copyright (c) Shopify Inc. 2022-2023 |
| [dnd kit](https://dndkit.com/) (@dnd-kit/core, @dnd-kit/sortable, @dnd-kit/utilities) | MIT | Copyright (c) 2021, Claudéric Demers |
| [KaTeX](https://katex.org/) | MIT | Copyright (c) 2013-2020 Khan Academy and other contributors |
| [react-katex](https://github.com/MatejBransky/react-katex) | MIT | Copyright (c) 2018 Matej Bránsky |
| [react-markdown](https://github.com/remarkjs/react-markdown) | MIT | Copyright (c) Espen Hovlandsdal |
| [remark-gfm](https://github.com/remarkjs/remark-gfm) | MIT | Copyright (c) Titus Wormer |
| [Vite](https://vite.dev/) | MIT | Copyright (c) 2019-present, VoidZero Inc. and Vite contributors |
| [Geist Font](https://vercel.com/font) | SIL OFL 1.1 | Copyright (c) 2023 Vercel |

### External Programs

Invoked across a process boundary; their licenses do not propagate to NightCrate.

| Program | License | Notes |
|---|---|---|
| [ASTAP](https://www.hnsky.org/astap.htm) | GPL-3.0 | Optional external plate solver, invoked via subprocess. Not bundled. |

### Data Sources

| Dataset | License | Attribution |
|---|---|---|
| [OpenNGC](https://github.com/mattiaverga/OpenNGC) | CC-BY-SA-4.0 | Verga, Mattia. OpenNGC — Database of NGC and IC objects. Fetched at runtime from GitHub into the user's app-data folder (`APP_DIR/catalogs/openngc/`); no catalog data is bundled with the repo. OpenNGC aggregates data from NED, SIMBAD, HyperLEDA, and other public astronomical databases. |
| Sharpless 2 (VizieR VII/20) | CDS public | Sharpless, S. 1959, ApJS 4, 257. HII regions, fetched at runtime from CDS VizieR. |
| Barnard (VizieR VII/220A) | CDS public | Barnard, E. E. 1927, *Barnard's Catalogue of 349 Dark Objects in the Sky*. Fetched at runtime from CDS VizieR. |
| [50 MGC](https://github.com/davidohlson/50MGC) | CDS public | Ohlson, D. et al. 2024, AJ 167, 31 (J/AJ/167/31). Galaxy distance augmenter, fetched at runtime from the author's GitHub mirror. |
| [Wikidata](https://www.wikidata.org/) | CC0-1.0 | External reference IDs (Wikipedia, SIMBAD) via SPARQL, fetched at runtime. |
| [Open-Meteo](https://open-meteo.com/) | Attribution required — see [their license](https://open-meteo.com/en/license) | Weather, ECMWF and air-quality forecast data, queried at runtime. |
| [CDS hips2fits / Aladin](https://alasky.cds.unistra.fr/hips-image-services/hips2fits) | CDS terms | DSS2 sky survey imagery for target thumbnails and the FOV simulator, fetched at runtime and cached locally. |
