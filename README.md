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

- **Backend:** Python 3.14 + FastAPI + SQLite + SQLAlchemy
- **Frontend:** React + TypeScript + Vite + Tailwind CSS + shadcn/ui
- **Key libs:** astropy, fitsio, astroquery, D3.js

## Status

Early development. See [PLAN.md](PLAN.md) for the current version plan.
