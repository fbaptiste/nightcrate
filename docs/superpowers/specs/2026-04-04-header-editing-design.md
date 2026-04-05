# FITS Header Editing — Design Spec

**Version:** 0.7.0
**Date:** 2026-04-04

## Summary

Add the ability to edit FITS header keywords in the image viewer — modify existing values, delete keys, and add new ones. Edits are written in place to the original file on disk.

## Scope

- **FITS files only** — XISF, PNG/JPEG/TIFF, and pxiproject are out of scope.
- **Regular files on disk only** — archive virtual paths (`::`) and pxiproject virtual paths are excluded.
- **Structural keywords are protected** — `SIMPLE`, `BITPIX`, `NAXIS`, `NAXIS1`, `NAXIS2`, `NAXIS3`, `EXTEND`, `BZERO`, `BSCALE`, `END`, `COMMENT`, `HISTORY` cannot be edited or deleted.

## API

### `PATCH /api/images/header`

Applies a batch of edit operations to a FITS file's header and returns the updated header cards.

**Request body (JSON):**

```json
{
  "path": "/absolute/path/to/file.fits",
  "hdu": 0,
  "operations": [
    { "op": "update", "key": "OBJECT", "value": "M42", "comment": "Target name" },
    { "op": "add", "key": "OBSERVER", "value": "Fred", "comment": "Observer name" },
    { "op": "delete", "key": "OLDKEY" }
  ]
}
```

**Operations:**

| Op       | Required fields       | Behavior                                    |
|----------|-----------------------|---------------------------------------------|
| `update` | `key`, `value`        | Updates value (and optionally comment) of an existing keyword. |
| `add`    | `key`, `value`        | Adds a new keyword. Fails if key already exists. |
| `delete` | `key`                 | Removes a keyword from the header.          |

- `comment` is optional for `update` and `add`. If omitted on `update`, the existing comment is preserved.

**Response:** `200` with the full updated header card list (same format as `GET /api/images/header`), allowing the frontend to refresh without a second request.

**Error responses:**

| Status | Condition                                        |
|--------|--------------------------------------------------|
| 400    | Path contains `::` (archive/pxiproject)          |
| 400    | Operation targets a structural keyword            |
| 400    | `add` with a key that already exists              |
| 400    | `update` or `delete` with a key that doesn't exist |
| 404    | File not found                                    |
| 422    | File is not a FITS file                           |

## Backend

### `fits_io.update_header()`

New function in `services/fits_io.py`:

- Opens the FITS file with `astropy.io.fits.open(path, mode="update")`
- Validates all operations before applying any (fail-fast, atomic batch)
- Applies operations to the specified HDU's header
- Calls `hdul.flush()` to write changes in place
- Returns the updated header cards (reuses `read_header()` format)

Using `mode="update"` with `flush()` is preferred over `writeto(overwrite=True)` because it modifies only the header block without rewriting the entire file — important for large FITS files (50MB+ subs).

### Cache invalidation

After a successful write, the file's mtime changes. The existing TTL cache in `images.py` uses `(path, mtime)` as the cache key, so stale entries naturally won't match on subsequent requests. No explicit invalidation needed.

### Pydantic models

```python
class HeaderOperation(BaseModel):
    op: Literal["update", "add", "delete"]
    key: str
    value: str | None = None
    comment: str | None = None

class HeaderEditRequest(BaseModel):
    path: str
    hdu: int = 0
    operations: list[HeaderOperation]
```

## Frontend

### Edit mode toggle

- A toggle button ("Edit" / "Done") appears in the header tab toolbar
- Only visible when:
  - The file path contains no `::` (not an archive or pxiproject virtual path)
  - The file is a FITS format (extension `.fits`, `.fit`, or `.fts`)
- Toggling off with pending changes prompts "Discard unsaved changes?"

### Edit mode behavior

**Existing rows:**
- Value and Comment columns become editable (MUI DataGrid inline cell editing)
- Keyword column stays read-only (rename = delete + add)
- Structural keywords are visually distinguished (greyed out) with no edit/delete controls
- Each non-structural row gets a delete icon button

**Adding keywords:**
- An "Add Keyword" row at the bottom of the table with text inputs for key, value, comment and an add button
- New keywords appear in the table immediately (pending state) with a visual highlight

**Change tracking (component state):**
- Modified rows: subtle background highlight
- Deleted rows: strikethrough styling
- Added rows: different highlight color
- All changes are local until Save is clicked

**Action buttons:**
- "Save" button — disabled until there are pending changes; sends batch `PATCH` request
- "Discard" button — clears all pending changes, stays in edit mode

### After save

- React Query cache for `["header", path, hdu]` is invalidated so the table refreshes with the written result
- Edit mode stays active for further edits
- Success/error feedback via a snackbar

## Testing

### Backend tests

- `update` operation changes value and comment
- `update` with `comment: null` preserves existing comment
- `add` operation inserts a new keyword
- `add` with duplicate key returns 400
- `delete` operation removes a keyword
- `delete` non-existent key returns 400
- Structural keyword rejection (edit, delete, add)
- Archive path rejection (path with `::`)
- Non-FITS file rejection
- Multiple operations in a single batch
- File not found returns 404
- Verify file on disk is actually modified (re-read after write)

### Frontend tests

- Edit toggle visibility: shown for regular FITS, hidden for archives/XISF/standard
- Pending change tracking: modify, add, delete
- Save sends correct operations payload
- Discard clears pending changes
