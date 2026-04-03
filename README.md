# NightCrate

A desktop application for astrophotographers to catalog, organize, and analyze imaging sessions.

NightCrate ingests raw imaging data directories and associated log files — from N.I.N.A., ASIAIR, and PHD2 — automatically extracting metadata and building a searchable, organized library of all your imaging work.

## What it does

- **Catalog sub frames** from FITS headers: filter, exposure, gain, temperature, camera, telescope, coordinates, timestamp
- **Ingest session logs** from N.I.N.A. and ASIAIR: autofocus events, plate solve results, meridian flips, filter changes
- **Ingest PHD2 guiding logs** and associate guiding quality with individual sub frames by timestamp
- **Analyze guiding** — RA/Dec error graphs with dither points, RMS stats for selected time ranges, preview the sub corresponding to any point on the guiding timeline
- **Track integration time** per target, per filter, across sessions and nights
- **Manage calibration frames** — match darks/flats/bias to sessions by camera, gain, temperature, and exposure
- **Multi-night project support** — same target imaged across many nights is one project, not many
- **File management** — catalog in place by reference (no files moved by default), with optional copy/reorganize

## Stack

- **Backend:** Python 3.14 + FastAPI + SQLite (via aiosqlite, raw SQL) + Pydantic
- **Frontend:** React + TypeScript + Vite + MUI + Zustand + TanStack Query
- **Key libs:** astropy, Pillow, lz4, zstandard, defusedxml, D3.js

## Status

Early development. See [PLAN.md](PLAN.md) for the current version plan.

## License

NightCrate is licensed under the [GNU General Public License v3.0](LICENSE).

---

## Open Source Acknowledgments

NightCrate is built with the following open-source libraries. We are grateful to their authors and contributors.

### Backend (Python)

| Library | License | Copyright |
|---|---|---|
| [NumPy](https://numpy.org/) | BSD 3-Clause | Copyright (c) 2005-2025, NumPy Developers |
| [Astropy](https://www.astropy.org/) | BSD 3-Clause | Copyright (c) 2011-2025, Astropy Developers |
| [Pillow](https://python-pillow.org/) | HPND (PIL License) | Copyright (c) 1997-2011 by Secret Labs AB; Copyright (c) 1995-2011 by Fredrik Lundh; Copyright (c) 2010-2025 by Jeffrey A. Clark and contributors |
| [FastAPI](https://fastapi.tiangolo.com/) | MIT | Copyright (c) 2018 Sebastián Ramírez |
| [Uvicorn](https://www.uvicorn.org/) | BSD 3-Clause | Copyright (c) 2017-present, Encode OSS Ltd |
| [Pydantic](https://docs.pydantic.dev/) | MIT | Copyright (c) 2017-2025, Samuel Colvin and Pydantic Contributors |
| [aiosqlite](https://github.com/omnilib/aiosqlite) | MIT | Copyright (c) Amethyst Reese |
| [yoyo-migrations](https://ollycope.com/software/yoyo/) | Apache 2.0 | Copyright (c) Oliver Mayfield-Sherborne |
| [aiofiles](https://github.com/Tinche/aiofiles) | Apache 2.0 | Copyright (c) Tin Tvrtković |
| [platformdirs](https://github.com/tox-dev/platformdirs) | MIT | Copyright (c) platformdirs contributors |
| [lz4](https://github.com/python-lz4/python-lz4) | BSD 3-Clause | Copyright (c) 2012-2023, Jonathan Underwood |
| [zstandard](https://github.com/indygreg/python-zstandard) | BSD 3-Clause | Copyright (c) 2016-present, Gregory Szorc |
| [defusedxml](https://github.com/tiran/defusedxml) | PSF-2.0 | Copyright (c) 2013-2023, Christian Heimes |
| [tifffile](https://github.com/cgohlke/tifffile) | BSD 3-Clause | Copyright (c) 2008-2026, Christoph Gohlke |
| [sep](https://github.com/kbarbary/sep) | LGPL-3.0 | Copyright (c) 2014, Kyle Barbary |
| [py7zr](https://github.com/miurahr/py7zr) | LGPL-2.1+ | Copyright (c) 2019-2025, Hiroshi Miura |

### Frontend (TypeScript / React)

| Library | License | Copyright |
|---|---|---|
| [React](https://react.dev/) | MIT | Copyright (c) Meta Platforms, Inc. and affiliates |
| [MUI](https://mui.com/) (Material UI + X Community) | MIT | Copyright (c) MUI |
| [Zustand](https://github.com/pmndrs/zustand) | MIT | Copyright (c) 2019 Paul Henschel |
| [TanStack Query](https://tanstack.com/query) | MIT | Copyright (c) 2021-present Tanner Linsley |
| [React Router](https://reactrouter.com/) | MIT | Copyright (c) React Training LLC 2015-2019; Copyright (c) Remix Software Inc. 2020-2021; Copyright (c) Shopify Inc. 2022-2023 |
| [Vite](https://vite.dev/) | MIT | Copyright (c) 2019-present, VoidZero Inc. and Vite contributors |
| [Geist Font](https://vercel.com/font) | SIL OFL 1.1 | Copyright (c) 2023 Vercel |
