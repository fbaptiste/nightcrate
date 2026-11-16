# Canonical licence texts

This directory vendors the canonical SPDX licence and exception texts needed
when a shipped package declares an accepted licence but does not include its own
licence file. The source is the SPDX license-list-data repository's plain-text
directory, pinned to tag `v3.27.0`:

https://github.com/spdx/license-list-data/tree/v3.27.0/text

Populate or refresh the committed text files from the repository root with:

```bash
uv run --project backend python packaging/fetch_licence_texts.py
```

The fetch is intentionally a maintainer operation, not part of a release build.
Release rendering is offline and fails closed if a required canonical text is
not committed here.
