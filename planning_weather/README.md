# Imaging-quality redesign — original handoff

The design work behind the v0.41.4 imaging-quality model, produced by Fable from
a brief describing the bug (an overcast hour scoring 46/100) and the constraints.
Kept as delivered.

| File | What it is |
|---|---|
| `imaging_quality_redesign.md` | The design document: the model, the sourcing, and every judgement call labelled as one |
| `imaging_quality.py` | Reference implementation, standalone and runnable |
| `imaging_quality_examples.py` | Old-vs-new comparison harness and a monotonicity sweep |

## Relationship to the shipped code

**Do not edit these files.** They are a record of what was handed over, not a
source the app builds from.

- `docs/imaging-quality-model.md` is the maintained descendant of the design
  document. It carries the same body plus a §7 on the forecast source added in
  v0.41.5. Read that one for current truth.
- `backend/src/nightcrate/services/imaging_quality.py` is the shipped model. It
  follows the reference implementation with three corrections made during the
  port, recorded in the v0.41.4 commit: `expected_useful_hours` summed the
  rounded integer score, missing cloud data raised into the request, and the
  wind-calm curve jumped from 8 to 0 at exactly 30 km/h.
- The §4 worked examples are reproduced as pinned tests in
  `backend/tests/test_imaging_quality.py`, and the harness was run against the
  ported module as the acceptance check — it reproduces the §4 tables exactly.

## What was designed and has not been built

The document's §3 "UI implications" lists more than v0.41.4 and v0.41.5
delivered. The model returns these and the API passes them through, but nothing
renders them:

- **`flags[]`** — `high_cloud_only`, `overcast`, `total_estimated`,
  `layers_unavailable`, `dew_risk`, and the gate flags. The document singles out
  `high_cloud_only` as the one deserving a call to action: a full-cirrus forecast
  is a lost night about nine times in ten, and the flag exists so the tenth can be
  checked against satellite imagery rather than written off.
- **`availability` and `quality` shown separately.** The split is the point of the
  model — "0, though the data would have been 67" is what a cirrus night should
  say — and only the product is displayed.
- **Grouping or colouring the factor rows by `Role`**, and hiding gate rows that
  did not apply.

These are listed in PLAN.md under "Deferred — known work not yet versioned".
