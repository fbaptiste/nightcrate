# NightCrate Guidescope Suitability — Implementation Spec

This spec adds a guidescope suitability calculation to the rig calculator panel, comparable in intent to the astronomy.tools "Guidescope Suitability" calculator but extended to handle both guide-scope and OAG configurations and to surface the practical "will my guide errors show up as elongated stars" question rather than only the raw G-ratio.

It is a focused additive change layered on top of the rig builder spec (`2026-04-15-rig-builder-design.md`). It replaces §5.6 of that spec and extends `RigCalculators` and the rig calculator panel UI. There are no schema changes.

**Implementation status:** Shipped as part of v0.12.0 (rig builder branch).

**Dependencies:**
- Rig builder schema, API, and UI (v0.12.0)
- `guide_scope` table with `aperture_mm` and `focal_length_mm`
- `camera` and `sensor` tables (imaging + guide)
- Rig calculator panel infrastructure (`/api/rigs/{rig_id}/calculators` endpoint and `CalculatorPanel` React component)

**Out of scope:**
- Guide star detection / availability calculations
- Differential flexure modeling (surfaced as static caveat only)
- Dithering recommendations
- Sub-exposure length recommendations
- Any persisted calibration / RMS-from-history features

---

## 1. Design decisions

### 1.1 Two metrics surfaced together

Lead with **effective guide precision** (arcsec) = `guide_scale × centroid_accuracy_pixels`, plus **G-ratio** (dimensionless) for community comparability. Default centroid accuracy is 0.2 px.

### 1.2 OAG and guide-scope both supported

- Guide-scope mode (`guide_scope_id` + `guide_camera_id`): focal length comes from the guide scope.
- OAG mode (`oag_id` + `guide_camera_id`, no guide scope): focal length comes from the main scope's effective focal length.

Both share the same math; only the focal-length source and the caveat text differ.

### 1.3 Hard cap at 6″/pixel

Beyond the G-ratio, a `guide_scale > 6.0″/pixel` forces the rating to **Poor** regardless of ratio, because PHD2 centroiding becomes unreliable at coarser scales. The cap applies to the **binned** scale.

### 1.4 Centroid accuracy is a calculator knob with 0.2 px default

0.2 px is the realistic working default per PHD2 community guidance. Users can adjust via a slider (0.05–0.50) in an "Advanced" disclosure. Not persisted on the rig.

### 1.5 No schema changes

All data derives from existing rig + equipment fields.

### 1.6 Colorblind-safe palette

All visualizations use blue/orange (never red/green). Four-tier ratings use blue → light blue → light orange → solid orange (excellent / good / marginal / poor).

### 1.7 Guide-binning is a calculator parameter

Like imaging-camera binning, guide-binning is a transient runtime parameter (default 1, range 1–4). Multiplies pixel size and therefore `guide_scale`, `effective_guide_precision`, `g_ratio`, and `effective_error_main_pixels` by the binning factor. Does **not** change FOV (sensor's physical dimensions are the same).

---

## 2. The math

`206.265` is the radian-to-arcsecond conversion constant.

### 2.1 Focal length resolution

- `guide_scope_id` set → `guide_focal_length_mm = guide_scope.focal_length_mm`
- Else `oag_id` set → `guide_focal_length_mm = telescope_configuration.effective_focal_length_mm`
- Else return `None`

If `guide_scope_focal_length_mm` is `NULL`, return `None` and surface the "missing focal length" warning.

### 2.2 Guide image scale (with binning)

```
effective_guide_pixel_size_um = guide_pixel_size_um × guide_binning
guide_scale_arcsec_per_pixel = (effective_guide_pixel_size_um / guide_focal_length_mm) × 206.265
unbinned_guide_scale_arcsec_per_pixel = (guide_pixel_size_um / guide_focal_length_mm) × 206.265
```

### 2.3 Effective guide precision

```
effective_guide_precision_arcsec = guide_scale × centroid_accuracy_pixels
```

### 2.4 G-ratio and effective error in main pixels

```
main_scale = (main_pixel_size_um / main_focal_length_mm) × 206.265
g_ratio = guide_scale / main_scale
effective_error_main_pixels = g_ratio × centroid_accuracy_pixels
```

### 2.5 Guide FOV

```
guide_fov_width_arcmin = (guide_resolution_x × unbinned_guide_scale) / 60
guide_fov_height_arcmin = (guide_resolution_y × unbinned_guide_scale) / 60
```

FOV uses the **unbinned** resolution and pixel size — the physical sensor area is unchanged by binning.

---

## 3. Rating bands

Cascade of (a) G-ratio band on `effective_error_main_pixels` and (b) 6″/pixel absolute scale cap. Worse of the two wins. When both fail, `rating_reason = "scale_cap"` (the cap is the more fundamental failure).

| Band | `effective_error_main_pixels` | Verdict |
|---|---|---|
| Excellent | ≤ 0.6 | Guide errors well below imaging resolution |
| Good | ≤ 1.0 | Within the ≤1 main-pixel standard |
| Marginal | ≤ 1.2 | Borderline — may show on demanding targets |
| Poor | > 1.2 | Guide errors will show as elongated stars |

Hard-cap rule: `guide_scale_arcsec_per_pixel > 6.0` → `rating = "poor"`, `rating_reason = "scale_cap"`.

Recommendation text is composed per rating (see §3.3 of original spec for verbatim strings). Mode-specific caveats appended:

- Guide-scope: differential-flexure note
- OAG: off-axis star-quality note

---

## 4. API shape

### 4.1 Breaking change

`RigCalculators` top-level guide fields removed:
- `guide_image_scale_arcsec_per_pixel: float | None` (removed)
- `guide_field_of_view_arcmin: tuple[float, float] | None` (removed)

Replaced with nested:
- `guide_suitability: GuideSuitability | None` (added)

### 4.2 `GuideSuitability` model (17 fields)

```
mode: "guide_scope" | "oag"
guide_focal_length_mm: float
guide_pixel_size_um: float
guide_binning: int
effective_guide_pixel_size_um: float
unbinned_guide_scale_arcsec_per_pixel: float
guide_scale_arcsec_per_pixel: float
guide_fov_width_arcmin: float
guide_fov_height_arcmin: float
centroid_accuracy_pixels: float
effective_guide_precision_arcsec: float
g_ratio: float
effective_error_main_pixels: float
rating: "excellent" | "good" | "marginal" | "poor"
rating_reason: "ratio" | "scale_cap"
recommendation: str
caveat: str
```

### 4.3 New query params on `GET /api/rigs/{rig_id}/calculators`

- `guide_binning: int` in `[1, 4]`, default `1`.
- `centroid_accuracy_pixels: float` in `[0.05, 0.5]`, default `0.2`.

Out-of-range values return `422`.

### 4.4 New warnings (both attached to `RigOut.warnings`)

- `guide_scope_id` set but `guide_scope.focal_length_mm IS NULL` → "Guide scope has no focal length on file — cannot compute guide suitability."
- `guide_camera_id` set with no `guide_scope_id` and no `oag_id` → "Guide camera is assigned but no guide scope or OAG is."

---

## 5. UI

- **Guide System** section below the Sampling Assessment, only rendered when `guide_suitability` is non-null (or the guide camera exists but lacks a path — then it shows a friendly empty-state message).
- Mode-aware header subtitle.
- Binning `ToggleButtonGroup` (1×–4×) in the header row.
- Metrics table: focal length, image scale (with unbinned value when binning > 1), FOV, effective guide precision, main image scale, effective error in main pixels, G-ratio as `1 : N`.
- Rating `Chip` using `ratingColor`/`ratingTextColor` from `lib/rigColors.ts`.
- Recommendation paragraph + muted caveat.
- `GuideSuitabilityChart` (D3): two-row horizontal bar chart (main pixel reference vs. guide error), threshold dashed lines at 0.6/1.0/1.2. When `rating_reason === "scale_cap"`, annotate with "Guide scale exceeds 6″/pixel hard cap".
- Advanced disclosure (`Collapse`): centroid-accuracy slider (0.05–0.50 step 0.05, default 0.2), 300 ms debounce. Binning toggle has 150 ms debounce.

---

## 6. Testing

### 6.1 Backend unit tests (`test_rig_calculators.py`)

- Mode resolution (guide_scope, OAG, neither)
- Binning scales all derived metrics linearly except FOV
- Scale cap forces `rating="poor"` + `rating_reason="scale_cap"`
- Cap wins when both fail
- Centroid accuracy sweeps change precision/error linearly, G-ratio invariant
- Rating-band sweep at `effective_error_main_pixels` = 0.5 / 0.8 / 1.1 / 1.5
- Fred's Askar V, C11 OAG, 30mm counter-example, 50mm borderline, combined binning + centroid

### 6.2 Backend API tests (`test_rig_api.py`)

- Guide-scope mode happy path (returns populated `guide_suitability`)
- `guide_binning=2, centroid_accuracy_pixels=0.3` returns matching values
- `guide_binning=5` → 422
- `centroid_accuracy_pixels=0.8` → 422
- No guide camera → `guide_suitability is None`
- Orphan guide camera → warning emitted
- Guide scope missing focal length → warning emitted + `guide_suitability is None`

### 6.3 Frontend

- `npm run build` passes (no component tests per project convention).

---

## 7. Source of truth

- Service: `backend/src/nightcrate/services/rig_calculators.py` (`compute_guide_suitability`)
- Pydantic: `backend/src/nightcrate/api/rig_models.py` (`GuideSuitability`, `RigCalculators`)
- API endpoint: `backend/src/nightcrate/api/rigs.py` (`get_calculators`, `_build_calculators`, `_check_warnings`)
- Frontend types + fetch: `frontend/src/api/rigs.ts`
- Color palette: `frontend/src/lib/rigColors.ts`
- UI panel: `frontend/src/components/rigs/GuideSuitabilityPanel.tsx`
- UI chart: `frontend/src/components/rigs/GuideSuitabilityChart.tsx`
- Integration: `frontend/src/components/rigs/CalculatorPanel.tsx`
