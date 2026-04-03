# FITS Header Ingestion Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Normalize FITS header keywords from multiple capture/processing apps (N.I.N.A., ASIAIR, SGPro, MaxIm DL, SharpCap, PixInsight) to canonical field names with short descriptions, and surface those descriptions in both the header grid and image info sidebar.

**Architecture:** A new `services/fits_header_map.py` module holds the alias map, priority rules, and normalization functions — pure data, no I/O. The existing `fits_io.read_header()` gains an optional `descriptions=True` parameter to annotate each card. The API `/header` endpoint returns an optional `description` field per card. The frontend header grid shows a Description column; the Image Info sidebar resolves keywords canonically so it works regardless of capture software. Non-FITS formats (XISF, pxiproject, standard) also benefit from descriptions since they emit FITS-style keyword cards.

**Tech Stack:** Python (astropy, pydantic), React/TypeScript (MUI DataGrid)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/src/nightcrate/services/fits_header_map.py` | Alias map, priority, normalization, extraction |
| Create | `backend/tests/test_fits_header_map.py` | Unit tests for map, normalization, extraction |
| Modify | `backend/src/nightcrate/services/fits_io.py:30-37` | Annotate header cards with descriptions |
| Modify | `backend/src/nightcrate/api/images.py:109-127` | Pass description flag to readers |
| Modify | `frontend/src/api/images.ts:12-16` | Add `description` field to `HeaderCard` |
| Modify | `frontend/src/components/fits/FitsHeaderTable.tsx` | Add Description column |
| Modify | `frontend/src/pages/ImageViewerPage.tsx:514-540` | Use canonical field resolution for Image Info |

---

### Task 1: Create the header map module

**Files:**
- Create: `backend/src/nightcrate/services/fits_header_map.py`

Copy the content from `instructions/fits_header_map.py` to `backend/src/nightcrate/services/fits_header_map.py` with one fix: remove the `HISTORY` entry from `FITS_KEYWORD_MAP` (HISTORY is a repeatable free-text card — mapping it to a single canonical field loses data).

- [ ] **Step 1: Create `fits_header_map.py`**

Copy from `instructions/fits_header_map.py` to `backend/src/nightcrate/services/fits_header_map.py`. Remove the `HISTORY` line from `FITS_KEYWORD_MAP`:

```python
# REMOVE this line:
"HISTORY":     ("history",           "Processing history"),
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `cd backend && uv run python -c "from nightcrate.services.fits_header_map import FITS_KEYWORD_MAP, extract_metadata; print(f'{len(FITS_KEYWORD_MAP)} keywords mapped')"`

Expected: `~90+ keywords mapped` (no import errors)

- [ ] **Step 3: Run ruff**

Run: `cd backend && uv run ruff check src/nightcrate/services/fits_header_map.py && uv run ruff format src/nightcrate/services/fits_header_map.py`

Fix any issues.

---

### Task 2: Tests for header map module

**Files:**
- Create: `backend/tests/test_fits_header_map.py`

- [ ] **Step 1: Write tests for normalization functions**

Create `backend/tests/test_fits_header_map.py`:

```python
"""Tests for FITS header keyword alias map and normalization."""

from nightcrate.services.fits_header_map import (
    FITS_KEYWORD_ALIASES,
    FITS_KEYWORD_MAP,
    KEYWORD_PRIORITY,
    extract_metadata,
    get_keyword_description,
    normalize_filter_name,
    normalize_frame_type,
    resolve_header,
)


class TestResolveHeader:
    def test_standard_keyword(self):
        assert resolve_header("EXPTIME") == "exposure_time"

    def test_case_insensitive(self):
        assert resolve_header("exptime") == "exposure_time"

    def test_unknown_keyword(self):
        assert resolve_header("MADEUPKEY") is None

    def test_vendor_keyword(self):
        assert resolve_header("SSWEIGHT") == "pi_ssweight"


class TestGetKeywordDescription:
    def test_known_keyword(self):
        assert get_keyword_description("EXPTIME") == "Exposure time (sec)"

    def test_sensor_temp(self):
        assert get_keyword_description("CCD-TEMP") == "Sensor temp (C)"

    def test_pi_keyword(self):
        assert get_keyword_description("SSWEIGHT") == "PI: SubframeSel weight"

    def test_unknown_keyword(self):
        assert get_keyword_description("MADEUPKEY") is None


class TestNormalizeFrameType:
    def test_iraf_short_form(self):
        assert normalize_frame_type("LIGHT") == "light"
        assert normalize_frame_type("DARK") == "dark"
        assert normalize_frame_type("FLAT") == "flat"
        assert normalize_frame_type("BIAS") == "bias"

    def test_sbfitsext_long_form(self):
        assert normalize_frame_type("Light Frame") == "light"
        assert normalize_frame_type("Dark Frame") == "dark"
        assert normalize_frame_type("Flat Field") == "flat"
        assert normalize_frame_type("Bias Frame") == "bias"

    def test_other_conventions(self):
        assert normalize_frame_type("OBJECT") == "light"
        assert normalize_frame_type("SCIENCE") == "light"
        assert normalize_frame_type("ZERO") == "bias"

    def test_whitespace_handling(self):
        assert normalize_frame_type("  LIGHT  ") == "light"

    def test_unknown_type(self):
        assert normalize_frame_type("MYSTERY") is None


class TestNormalizeFilterName:
    def test_luminance_variants(self):
        assert normalize_filter_name("Luminance") == "Lum"
        assert normalize_filter_name("L") == "Lum"
        assert normalize_filter_name("LUM") == "Lum"

    def test_narrowband(self):
        assert normalize_filter_name("H-Alpha") == "Ha"
        assert normalize_filter_name("Hydrogen Alpha") == "Ha"
        assert normalize_filter_name("OIII") == "Oiii"
        assert normalize_filter_name("Sulfur-II") == "Sii"

    def test_rgb(self):
        assert normalize_filter_name("RED") == "Red"
        assert normalize_filter_name("GREEN") == "Green"
        assert normalize_filter_name("BLUE") == "Blue"

    def test_passthrough_unknown(self):
        assert normalize_filter_name("L-eXtreme") == "L-eXtreme"
        assert normalize_filter_name("NBZ") == "NBZ"

    def test_whitespace_stripped(self):
        assert normalize_filter_name("  Ha  ") == "Ha"


class TestExtractMetadata:
    def test_nina_header(self):
        header = {
            "EXPTIME": 120.0, "EXPOSURE": 120.0,
            "IMAGETYP": "LIGHT", "OBJECT": "M101",
            "FILTER": "Ha", "GAIN": 100,
            "CCD-TEMP": -10.0, "SET-TEMP": -10.0,
            "INSTRUME": "ZWO ASI2600MM Pro",
            "TELESCOP": "Celestron C11",
            "FOCALLEN": 1960.0,
            "RA": 210.802, "DEC": 54.349,
            "OBJCTRA": "14 03 12.6", "OBJCTDEC": "+54 20 56.7",
            "SWCREATE": "N.I.N.A.",
            "FOCPOS": 12450, "FOCUSPOS": 12450,
        }
        result = extract_metadata(header)
        assert result["exposure_time"] == 120.0
        assert result["frame_type"] == "light"
        assert result["filter_name"] == "Ha"
        assert result["gain"] == 100
        assert result["sensor_temp"] == -10.0
        assert result["camera_name"] == "ZWO ASI2600MM Pro"
        assert result["software_creator"] == "N.I.N.A."
        assert result["ra"] == 210.802

    def test_asiair_header(self):
        header = {
            "EXPTIME": 300.0, "IMAGETYP": "LIGHT",
            "OBJECT": "NGC 7000", "FILTER": "Ha",
            "GAIN": 100, "CCD-TEMP": -10.0,
            "INSTRUME": "ZWO ASI2600MM Pro",
            "RA": 314.678, "DEC": 44.345,
        }
        result = extract_metadata(header)
        assert result["exposure_time"] == 300.0
        assert result["object_name"] == "NGC 7000"
        assert "telescope_name" not in result

    def test_maxim_dl_long_frame_type(self):
        header = {
            "IMAGETYP": "Dark Frame", "EXPTIME": 120.0,
            "INSTRUME": "ZWO ASI2600MM Pro",
        }
        result = extract_metadata(header)
        assert result["frame_type"] == "dark"

    def test_sgpro_keywords(self):
        header = {
            "CREATOR": "Sequence Generator Pro",
            "EXPOSURE": 180.0, "IMAGETYP": "LIGHT",
            "OBJECT": "IC 1396", "FILTER": "Sii",
            "TEMPERAT": -10.0,
            "CCDXBIN": 1, "CCDYBIN": 1, "GAIN": 100,
        }
        result = extract_metadata(header)
        assert result["exposure_time"] == 180.0
        assert result["software_creator"] == "Sequence Generator Pro"
        assert result["sensor_temp"] == -10.0
        assert result["binning_x"] == 1

    def test_pixinsight_quality_keywords(self):
        header = {
            "EXPTIME": 120.0, "IMAGETYP": "LIGHT",
            "FILTER": "Ha",
            "SSWEIGHT": 0.847,
            "PSFSIGNAL": 1.234,
            "PSFFWHM": 2.85,
            "PSFECCENTR": 0.31,
            "NOISE00": 0.000234,
        }
        result = extract_metadata(header)
        assert result["pi_ssweight"] == 0.847
        assert result["pi_psf_signal"] == 1.234
        assert result["pi_psf_fwhm"] == 2.85
        assert result["pi_psf_eccen"] == 0.31
        assert result["pi_noise_layer0"] == 0.000234

    def test_priority_exptime_over_exposure(self):
        header = {"EXPTIME": 120.0, "EXPOSURE": 999.0}
        result = extract_metadata(header)
        assert result["exposure_time"] == 120.0

    def test_priority_ccd_temp_over_temperat(self):
        header = {"CCD-TEMP": -10.0, "TEMPERAT": -5.0}
        result = extract_metadata(header)
        assert result["sensor_temp"] == -10.0

    def test_empty_string_values_skipped(self):
        header = {"OBJECT": "", "EXPTIME": 120.0}
        result = extract_metadata(header)
        assert "object_name" not in result
        assert result["exposure_time"] == 120.0

    def test_none_values_skipped(self):
        header = {"OBJECT": None, "EXPTIME": 120.0}
        result = extract_metadata(header)
        assert "object_name" not in result

    def test_insflnam_filter(self):
        header = {"INSFLNAM": "Oiii", "EXPTIME": 60.0}
        result = extract_metadata(header)
        assert result["filter_name"] == "Oiii"

    def test_filter_priority_filter_over_insflnam(self):
        header = {"FILTER": "Ha", "INSFLNAM": "Oiii"}
        result = extract_metadata(header)
        assert result["filter_name"] == "Ha"


class TestMapConsistency:
    def test_all_priority_fields_have_aliases(self):
        """Every keyword in KEYWORD_PRIORITY must exist in the alias map."""
        for field, keywords in KEYWORD_PRIORITY.items():
            for kw in keywords:
                assert kw in FITS_KEYWORD_ALIASES, f"{kw} in priority for {field} but not in alias map"

    def test_all_priority_keywords_map_to_declared_field(self):
        """Each keyword in a priority list must map to that list's canonical field."""
        for field, keywords in KEYWORD_PRIORITY.items():
            for kw in keywords:
                assert FITS_KEYWORD_ALIASES[kw] == field, (
                    f"{kw} maps to {FITS_KEYWORD_ALIASES[kw]} but is in priority list for {field}"
                )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_fits_header_map.py -v`

Expected: all tests PASS

- [ ] **Step 3: Run ruff**

Run: `cd backend && uv run ruff check tests/test_fits_header_map.py && uv run ruff format tests/test_fits_header_map.py`

---

### Task 3: Annotate header cards with descriptions

**Files:**
- Modify: `backend/src/nightcrate/services/fits_io.py:30-37`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_fits_io.py` in `TestReadHeader`:

```python
def test_cards_have_description(self, tmp_fits_mono: Path):
    cards = read_header(tmp_fits_mono)
    exptime = next(c for c in cards if c["key"] == "EXPTIME")
    assert exptime["description"] == "Exposure time (sec)"

def test_unknown_keyword_description_is_none(self, tmp_fits_mono: Path):
    cards = read_header(tmp_fits_mono)
    # SIMPLE is a structural keyword not in the alias map
    simple = next(c for c in cards if c["key"] == "SIMPLE")
    assert simple["description"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_fits_io.py::TestReadHeader::test_cards_have_description tests/test_fits_io.py::TestReadHeader::test_unknown_keyword_description_is_none -v`

Expected: FAIL (KeyError: 'description')

- [ ] **Step 3: Update `fits_io.read_header` to include descriptions**

Edit `backend/src/nightcrate/services/fits_io.py`:

```python
from nightcrate.services.fits_header_map import get_keyword_description


def read_header(file_path: Path, hdu: int = 0) -> list[dict]:
    """Return all header cards for the given HDU as {key, value, comment, description} dicts."""
    with fits.open(file_path, memmap=False) as hdul:
        target = _hdu_index(hdul, hdu)
        return [
            {
                "key": card.keyword,
                "value": str(card.value),
                "comment": card.comment,
                "description": get_keyword_description(card.keyword),
            }
            for card in target.header.cards
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_fits_io.py::TestReadHeader -v`

Expected: all PASS

---

### Task 4: Add descriptions to XISF, pxiproject, and standard_io readers

**Files:**
- Modify: `backend/src/nightcrate/services/xisf_io.py`
- Modify: `backend/src/nightcrate/services/pxiproject_io.py`
- Modify: `backend/src/nightcrate/services/standard_io.py`

All three `read_header()` functions return `list[dict]` with `{key, value, comment}`. Each needs a `description` field added.

- [ ] **Step 1: Update `xisf_io.read_header`**

In `backend/src/nightcrate/services/xisf_io.py`, add import at top:

```python
from nightcrate.services.fits_header_map import get_keyword_description
```

Then in `read_header()`, add `"description": get_keyword_description(...)` to every dict that constructs a card. There are two places cards are created:
1. From `<FITSKeyword>` elements — add `"description": get_keyword_description(name)`
2. From XISF property → FITS mapping — add `"description": get_keyword_description(fits_kw)`

- [ ] **Step 2: Update `pxiproject_io.read_header`**

In `backend/src/nightcrate/services/pxiproject_io.py`, add import at top:

```python
from nightcrate.services.fits_header_map import get_keyword_description
```

Then in `read_header()`, add to the card dict:

```python
cards.append({
    "key": kw.get("name", ""),
    "value": kw.get("value", ""),
    "comment": kw.get("comment", ""),
    "description": get_keyword_description(kw.get("name", "")),
})
```

- [ ] **Step 3: Update `standard_io.read_header`**

In `backend/src/nightcrate/services/standard_io.py`, add import and add `"description": get_keyword_description(key)` to each card dict. Standard images use pseudo-keys like "Format", "Width", "Height" — these will correctly return `None` since they're not FITS keywords.

- [ ] **Step 4: Run all existing tests**

Run: `cd backend && uv run pytest -v`

Expected: all tests PASS (existing tests should still work since the extra field is additive)

---

### Task 5: Add canonical metadata extraction to header endpoint

**Files:**
- Modify: `backend/src/nightcrate/api/images.py:109-127`

Add a new endpoint that returns extracted canonical metadata for the Image Info sidebar, plus an `unrecognized_keywords` list for logging/diagnostics.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_api.py`:

```python
@pytest.mark.anyio
async def test_header_metadata_endpoint(client, tmp_fits_mono):
    resp = await client.get("/api/images/metadata", params={"path": str(tmp_fits_mono)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["canonical"]["object_name"] == "TestTarget"
    assert data["canonical"]["exposure_time"] == 300.0
    assert data["canonical"]["filter_name"] == "Ha"
    assert data["canonical"]["sensor_temp"] == -10.0
    assert isinstance(data["unrecognized_keywords"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_api.py::test_header_metadata_endpoint -v`

Expected: FAIL (404 Not Found)

- [ ] **Step 3: Add the endpoint**

Add to `backend/src/nightcrate/api/images.py`:

```python
from nightcrate.services.fits_header_map import (
    FITS_KEYWORD_ALIASES,
    extract_metadata,
)

STRUCTURAL_KEYWORDS = {
    "SIMPLE", "NAXIS", "NAXIS1", "NAXIS2", "NAXIS3",
    "EXTEND", "BZERO", "BSCALE", "COMMENT", "HISTORY", "END", "",
    "BITPIX",
}


@router.get("/metadata")
async def get_metadata(
    path: str = Query(..., description="Absolute path to image file"),
    hdu: int = Query(0, description="Extension index"),
) -> dict:
    """Return canonical metadata and unrecognized keywords for a file."""
    p, ft, idx = _resolve_path(path)
    try:
        if ft == "pxiproject":
            cards = pxiproject_io.read_header(p, idx)
        elif ft == "fits":
            cards = fits_io.read_header(p, hdu)
        elif ft == "xisf":
            cards = xisf_io.read_header(p, hdu)
        else:
            cards = standard_io.read_header(p)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal processing error") from exc

    # Build a raw header dict from cards (first occurrence wins for dupes)
    raw_header: dict[str, str] = {}
    for card in cards:
        if card["key"] and card["key"] not in raw_header:
            raw_header[card["key"]] = card["value"]

    canonical = extract_metadata(raw_header)

    recognized = set(FITS_KEYWORD_ALIASES.keys())
    unrecognized = [
        k for k in raw_header
        if k.upper() not in recognized and k.upper() not in STRUCTURAL_KEYWORDS
        and not k.upper().startswith("NAXIS")
    ]

    return {
        "canonical": canonical,
        "unrecognized_keywords": unrecognized,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_api.py::test_header_metadata_endpoint -v`

Expected: PASS

---

### Task 6: Frontend — add Description column to header grid

**Files:**
- Modify: `frontend/src/api/images.ts:12-16`
- Modify: `frontend/src/components/fits/FitsHeaderTable.tsx`

- [ ] **Step 1: Update `HeaderCard` type**

In `frontend/src/api/images.ts`, add the `description` field:

```typescript
export interface HeaderCard {
  key: string;
  value: string;
  comment: string;
  description: string | null;
}
```

- [ ] **Step 2: Add Description column to `FitsHeaderTable`**

In `frontend/src/components/fits/FitsHeaderTable.tsx`, add a Description column after Keyword:

```typescript
const columns: GridColDef[] = [
  {
    field: "key",
    headerName: "Keyword",
    width: 120,
    renderCell: (params) => (
      <Box component="span" sx={{ fontFamily: "monospace", fontSize: "0.8rem", fontWeight: 600 }}>
        {params.value}
      </Box>
    ),
  },
  {
    field: "description",
    headerName: "Description",
    width: 180,
    renderCell: (params) => (
      <Box component="span" sx={{ fontSize: "0.8rem", color: "text.secondary" }}>
        {params.value ?? ""}
      </Box>
    ),
  },
  {
    field: "value",
    headerName: "Value",
    width: 200,
    renderCell: (params) => (
      <Box component="span" sx={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
        {params.value}
      </Box>
    ),
  },
  {
    field: "comment",
    headerName: "Comment",
    flex: 1,
    renderCell: (params) => (
      <Box component="span" sx={{ fontSize: "0.8rem", color: "text.secondary" }}>
        {params.value}
      </Box>
    ),
  },
];
```

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npm run build`

Expected: Build succeeds

---

### Task 7: Frontend — Use canonical fields for Image Info sidebar

**Files:**
- Modify: `frontend/src/api/images.ts` (add `fetchMetadata`)
- Modify: `frontend/src/pages/ImageViewerPage.tsx:514-540`

The Image Info sidebar currently hardcodes raw FITS keywords (`OBJECT`, `INSTRUME`, etc.). This fails for files from ASIAIR or SGPro that use different keywords. Replace with canonical metadata lookup.

- [ ] **Step 1: Add `fetchMetadata` API function**

Add to `frontend/src/api/images.ts`:

```typescript
export interface ImageMetadata {
  canonical: Record<string, string | number | null>;
  unrecognized_keywords: string[];
}

export function fetchMetadata(path: string, hdu: number): Promise<ImageMetadata> {
  return apiFetch<ImageMetadata>(`/images/metadata?path=${encodeURIComponent(path)}&hdu=${hdu}`);
}
```

- [ ] **Step 2: Add metadata query to ImageViewerPage**

In `frontend/src/pages/ImageViewerPage.tsx`, add alongside the existing queries:

```typescript
import { fetchMetadata, type ImageMetadata } from "@/api/images";

// Add query (near other useQuery calls ~line 142):
const metadataQuery = useQuery({
  queryKey: ["metadata", activePath, selectedHdu],
  queryFn: () => fetchMetadata(activePath, selectedHdu),
  enabled: activePath !== "",
});
```

- [ ] **Step 3: Replace hardcoded Image Info with canonical fields**

Replace the Image Info section (lines ~514-540) with:

```typescript
<SidebarSection label="Image Info" />
{(() => {
  const meta = metadataQuery.data?.canonical;
  if (!meta || Object.keys(meta).length === 0) {
    return (
      <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, py: 0.5, fontSize: "0.65rem" }}>
        No metadata available
      </Typography>
    );
  }
  // Display fields in this order, using human-readable labels
  const displayFields: [string, string][] = [
    ["object_name", "Object"],
    ["filter_name", "Filter"],
    ["exposure_time", "Exposure"],
    ["gain", "Gain"],
    ["sensor_temp", "Sensor"],
    ["camera_name", "Camera"],
    ["telescope_name", "Telescope"],
    ["focal_length", "Focal Len"],
    ["frame_type", "Type"],
  ];
  const rows = displayFields
    .filter(([key]) => meta[key] != null && String(meta[key]).trim() !== "")
    .map(([key, label]) => {
      let val = String(meta[key]);
      // Format specific fields
      if (key === "exposure_time") val = `${meta[key]}s`;
      if (key === "sensor_temp") val = `${meta[key]}°C`;
      if (key === "focal_length") val = `${Number(meta[key]).toFixed(0)} mm`;
      return [label, val] as [string, string];
    });
  return rows.length > 0 ? (
    <Box sx={{ px: 1.5, py: 0.5 }}>
      <table style={{ borderCollapse: "collapse", fontSize: "0.65rem", fontFamily: monoFontFamily }}>
        <tbody>
          {rows.map(([label, val]) => (
            <tr key={label}>
              <td style={{ color: "var(--mui-palette-text-secondary)", paddingRight: 8, whiteSpace: "nowrap" }}>{label}</td>
              <td>{val}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Box>
  ) : (
    <Typography variant="caption" color="text.secondary" sx={{ px: 1.5, py: 0.5, fontSize: "0.65rem" }}>
      No metadata available
    </Typography>
  );
})()}
```

Note: This replaces the `keyFields` / `cardMap` / `flatMap` approach that matched raw FITS keywords. Now it uses canonical field names, so `INSTRUME` and `CREATOR` both resolve correctly regardless of capture software.

- [ ] **Step 4: Build frontend**

Run: `cd frontend && npm run build`

Expected: Build succeeds

---

### Task 8: Run all checks

- [ ] **Step 1: Backend lint + format**

Run: `cd backend && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`

- [ ] **Step 2: Backend security scan**

Run: `cd backend && uv run bandit -r src/`

- [ ] **Step 3: Backend tests**

Run: `cd backend && uv run pytest -v`

Expected: all PASS

- [ ] **Step 4: Frontend build**

Run: `cd frontend && npm run build`

Expected: Build succeeds

---

### Task 9: Update PLAN.md — Future Features entry

**Files:**
- Modify: `PLAN.md`

- [ ] **Step 1: Add database storage entry to Future Features**

Add a new subsection under `## Future Features to Consider`:

```markdown
### FITS Header Database Storage (Ingestion Pipeline)

- **Canonical metadata in typed columns:** Store normalized values (object_name, exposure_time, filter_name, gain, sensor_temp, etc.) in dedicated database columns for fast queries and calibration frame matching.
- **Raw FITS header as JSON:** Store the full raw header as a JSON column — escape hatch for re-extraction when new keywords are added to the alias map.
- **PixInsight quality metrics:** Dedicated nullable columns for pi_ssweight, pi_psf_fwhm, pi_psf_eccen, pi_noise_layer0, etc. — populated only for files processed through PixInsight.
- **Calibration key indexes:** Index on (camera_name, gain, sensor_temp, exposure_time, binning_x, binning_y, filter_name, frame_type) for fast calibration frame matching (darks, flats, bias).
- **Unrecognized keyword frequency table:** Track keyword frequency across all ingested files. When a new keyword appears frequently, it signals a new alias to add to the map.
- **Coordinate validation:** Parse and validate RA/DEC values (ASIAIR writes nonsensical coordinates in dark frame headers). Use astropy.coordinates.Angle for format handling.
- **IMAGETYP filename fallback:** When IMAGETYP is missing (some SharpCap versions), fall back to filename pattern matching (e.g., `Dark_10.0s_...` or path containing `/darks/`).
```
