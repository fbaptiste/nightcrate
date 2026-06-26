# NightCrate — Project Brief

## Overview

**NightCrate** is a desktop application for astrophotographers to record, organize, catalog, and analyze their imaging sessions. The app ingests raw imaging data directories and associated log files, automatically extracting metadata and building a searchable, organized library of all imaging work.

- **Name:** NightCrate

This is a free, open-source (MIT) project. The goal is simply to build a genuinely useful tool for the astrophotography community — a niche that's underserved by existing software.

---

## Why This Product

There is no existing tool that comprehensively handles session organization and cataloging for astrophotographers. The current landscape:

- **N.I.N.A., ASIAir, SGPro** — capture/sequencing software. They produce data but don't help organize or catalog it after the fact.
- **PixInsight, Siril** — processing software. They work on individual images, not session management.
- **Astrobin** — social sharing platform for finished images with basic metadata. Not a workflow or cataloging tool.
- **PHD2 Log Viewer** — standalone guiding log viewer, disconnected from image data.
- **NINA Log Analyzer** — browser-based tool that visualizes NINA logs as Gantt timelines. Simple, standalone, validates demand but very limited in scope.
- **LightBucket** — NINA plugin that logs session data to a web dashboard showing what was imaged, RMS, HFR, and basic session stats. Closest existing tool to NightCrate's concept, but it's cloud-only, NINA-only, limited in scope (no local cataloging, no PHD2 analysis, no file management, no calibration frame tracking).
- **Spreadsheets/folder structures** — what most people actually use, which is fragile, manual, and unsearchable.

Nobody is combining FITS header metadata, guiding logs, and session logs into a unified, searchable catalog. NightCrate does that.

---

## Target Users

- Serious amateur astrophotographers using dedicated imaging rigs (mount + scope + camera + guide scope)
- Users of N.I.N.A. and ASIAir initially, expanding to smart scope users (Seestar, Dwarflab) later
- The market is small (low hundreds of thousands globally) but passionate and underserved by existing tools

---

## Technical Architecture

### Stack

- **Backend:** Python (FastAPI)
  - Leverages the astronomy Python ecosystem: astropy, fitsio, astroquery, and plate solving libraries
  - Fred's primary language and area of expertise
  - Handles all computation: FITS header parsing, plate solving, log ingestion, database queries, file management

- **Frontend:** React
  - Claude Code will handle the bulk of React/JS development
  - Fred can read and understand the code but is not a JS/React developer

- **Database:** PostgreSQL (Fred's area of expertise) or SQLite for local-first simplicity — TBD

- **Desktop packaging approach:** Start as a local web app (Option C)
  - Phase 1: FastAPI serves the React frontend, runs locally. User accesses via browser or a lightweight wrapper like pywebview.
  - Phase 2: If the product takes off and users want a proper .dmg/.exe, wrap in Tauri (Rust-based desktop framework that uses native OS webview). The React frontend doesn't change — only the container changes.
  - This approach avoids premature desktop packaging complexity and lets development focus on the actual product.

### Why not Electron?

Heavy (bundles entire Chromium, 100MB+ installers, hundreds of MB RAM). Tauri is the modern alternative if a native wrapper is ever needed — it uses the OS's native webview (WKWebView on Mac), resulting in ~10MB app size and ~30-40MB RAM usage.

### Platform

- Fred's imaging rig runs Windows with N.I.N.A. and a mini-PC at the scope
- Fred's primary computer is a Mac, where all processing happens (PixInsight)
- The app lives on the Mac side of the workflow — organizing and reviewing data after capture
- Mac-first, but the local web app approach is inherently cross-platform

---

## Fred's Background

- Primary expertise: Python, PostgreSQL, data modeling, cybersecurity
- Software engineer by profession
- Active astrophotographer using N.I.N.A. for capture and PixInsight for processing
- Will heavily leverage Claude Code for development, particularly on the React frontend

---

## MVP Features

### Core Data Ingestion

- **Point app at a directory of raw imaging data** — user creates a new project by selecting their data directory
- **Auto-detect and catalog sub frames from FITS headers** — extract filter, exposure time, gain, sensor temperature, camera model, telescope/scope info, date/time, sky coordinates, and any other available metadata
- **Ingest N.I.N.A. session logs** — parse sequence timeline including autofocus events/results (from JSON autofocus files), errors, plate solve results, meridian flips, filter changes, slew events, dither timing
- **Ingest ASIAir session logs** — equivalent parsing for ASIAir's log format
- **Ingest PHD2 guiding logs** — parse guiding data and associate with relevant subs by timestamp
- **Plate solve subs** to identify targets and sky coordinates (using existing solvers like ASTAP or astrometry.net)

### PHD2 Guiding Analysis

- Display guiding graph with RA/Dec error over time
- Show dither points on the graph
- Preview the raw sub frame (with auto screen stretch) corresponding to any point on the guiding timeline
- Select/highlight a portion of the guiding graph and get stats for just that selection (RMS, peak error, etc.)
- Associate guiding quality data with individual sub frames by timestamp

### Session & Project Organization

- **Multi-night session support** — same target across multiple nights treated as one project
- **Mosaic project support** — multiple panels as part of one larger project
- **Search/query across all projects** — e.g., "show me everything I've imaged containing M31"
- **Attach processed/final images** to a project alongside the raw data

### File Management

- **Catalog in place by default** — store references/links to source data files, don't move anything
- **Optional reorganize/copy** to a user-specified target location
  - User chooses what to include (raw subs, calibration frames, processed images, etc.)
  - Option to compress/zip raw subs during the copy to save disk space
  - App defines an organized folder structure for the destination

### Calibration Frame Management

- Track dark, flat, and bias frame libraries
- Match calibration frames to sessions by camera, gain, sensor temperature, and exposure time
- Answer "do I have darks that match this session?" at a glance

### Dashboards & Visualization

- **Integration time dashboard** — total integration time per target, per filter, across all sessions. "I have 4 hours of Ha on the Elephant Trunk but only 90 minutes of OIII."
- **Session timeline visualization** — visual timeline of a night showing what was captured when, overlaid with guiding RMS, target altitude, meridian flip timing. A retrospective view of how the night went.
- **RA altitude chart with moon position** — for session coordinates, similar to what Telescopius provides. Shows target altitude over the session and moon proximity/phase.
- **Auto-detect Bortle class** from session location coordinates, with manual override

### Equipment Management

- **Equipment profile management** — define imaging rigs (scope + camera + filter wheel + mount combos)
- **Auto-detect which rig was used** from FITS header metadata
- Track usage across rigs (e.g., total shutter count per camera)

---

## Future Features (Post-MVP)

### Additional Platform Support
- Seestar session log support
- Dwarflab session log support
- Other smart scope support

### Sharing & Integration
- Export/sharing: generate session summary cards (equipment, integration time, conditions)
- Astrobin integration (post sessions, sync metadata)
- Telescopius integration

### Advanced Processing Tools
- Color blindness assistance tools for astrophotography post-processing
- Neural network-based image stretching

---

## Open Design Questions

- **Database choice:** PostgreSQL (Fred's strength, more powerful) vs SQLite (simpler deployment, no separate server process, better for a local desktop app). Leaning SQLite for MVP simplicity.
- **Plate solving approach:** Bundle ASTAP locally? Call astrometry.net API? Allow user to configure their preferred solver?
- **FITS thumbnail/preview generation:** Generate and cache thumbnails on ingest for fast browsing? How to handle the screen stretch for preview display?
- **Data model details:** How to represent the hierarchy of projects → sessions → panels (for mosaics) → sub frames? How to link calibration frames?
- **Smart scope data formats:** What metadata and log formats do Seestar and Dwarflab scopes produce? Research needed before implementation.
- **ASIAir log format:** Needs research — what exactly does ASIAir produce and where?
