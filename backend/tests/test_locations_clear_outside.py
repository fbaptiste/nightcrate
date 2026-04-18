"""Tests for the Clear Outside scraper endpoint + geo_timezone override behavior."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from nightcrate.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers for mocking httpx.AsyncClient
# ---------------------------------------------------------------------------


def _mock_response(text: str, status_code: int = 200) -> MagicMock:
    """Build a MagicMock that quacks like an httpx.Response for our code path."""
    response = MagicMock()
    response.text = text
    response.status_code = status_code

    def raise_for_status() -> None:
        if status_code >= 400:
            # Build a real HTTPStatusError so the `except httpx.HTTPError` path fires.
            request = httpx.Request("GET", "https://clearoutside.com/test")
            real_response = httpx.Response(status_code, request=request)
            raise httpx.HTTPStatusError(
                f"Server error {status_code}",
                request=request,
                response=real_response,
            )

    response.raise_for_status = MagicMock(side_effect=raise_for_status)
    return response


def _mock_async_client_factory(response_or_exc):
    """Build a replacement for `httpx.AsyncClient` that yields our mock response.

    `response_or_exc` is either a pre-built mock response (returned from `.get`)
    or an exception instance (raised by `.get`).
    """
    mock_client = MagicMock()
    if isinstance(response_or_exc, BaseException):
        mock_client.get = AsyncMock(side_effect=response_or_exc)
    else:
        mock_client.get = AsyncMock(return_value=response_or_exc)

    async_cm = MagicMock()
    async_cm.__aenter__ = AsyncMock(return_value=mock_client)
    async_cm.__aexit__ = AsyncMock(return_value=None)

    return MagicMock(return_value=async_cm)


# ---------------------------------------------------------------------------
# GET /api/locations/clear-outside — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_clear_outside_happy_path_real_fragment(client):
    """The real-world Clear Outside fragment yields the expected SQM and Bortle."""
    html_body = (
        '<div class="fc_sky_quality">'
        "Est. Sky Quality: &nbsp;<strong>17.16</strong> Magnitude. "
        "&nbsp;<strong>Class 9</strong> Bortle."
        "</div>"
    )
    mock_response = _mock_response(html_body)
    factory = _mock_async_client_factory(mock_response)

    with patch("nightcrate.services.http_client.httpx.AsyncClient", factory):
        resp = await client.get("/api/locations/clear-outside?latitude=40.75&longitude=-74.00")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sqm"] == 17.16
    assert data["bortle"] == 9
    assert "40.75" in data["source_url"]
    assert "-74.00" in data["source_url"]
    assert data["source_url"].startswith("https://clearoutside.com/forecast/")


@pytest.mark.anyio
async def test_clear_outside_handles_whitespace_and_entities(client):
    """Extra whitespace and &nbsp; between label and value must still match."""
    html_body = (
        "<p>Sky Quality:  &nbsp;  <strong>21.89</strong>  Magnitude.  "
        "<strong>Class 3</strong>  Bortle</p>"
    )
    mock_response = _mock_response(html_body)
    factory = _mock_async_client_factory(mock_response)

    with patch("nightcrate.services.http_client.httpx.AsyncClient", factory):
        resp = await client.get("/api/locations/clear-outside?latitude=33.45&longitude=-112.07")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sqm"] == 21.89
    assert data["bortle"] == 3


@pytest.mark.anyio
async def test_clear_outside_partial_bortle_only(client):
    """Page with Bortle info but no SQM returns sqm=None, bortle=<n>."""
    html_body = "<p>Some unrelated text. <strong>Class 9</strong> Bortle and more.</p>"
    mock_response = _mock_response(html_body)
    factory = _mock_async_client_factory(mock_response)

    with patch("nightcrate.services.http_client.httpx.AsyncClient", factory):
        resp = await client.get("/api/locations/clear-outside?latitude=40.0&longitude=-74.0")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sqm"] is None
    assert data["bortle"] == 9


@pytest.mark.anyio
async def test_clear_outside_partial_sqm_only(client):
    """Page with SQM info but no Bortle returns bortle=None, sqm=<n>."""
    html_body = "<p>Est. Sky Quality: &nbsp;<strong>20.50</strong> Magnitude.</p>"
    mock_response = _mock_response(html_body)
    factory = _mock_async_client_factory(mock_response)

    with patch("nightcrate.services.http_client.httpx.AsyncClient", factory):
        resp = await client.get("/api/locations/clear-outside?latitude=40.0&longitude=-74.0")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sqm"] == 20.50
    assert data["bortle"] is None


@pytest.mark.anyio
async def test_clear_outside_no_matches(client):
    """Page with neither SQM nor Bortle returns both fields as None."""
    html_body = "<p>Nothing useful here. Just a placeholder page.</p>"
    mock_response = _mock_response(html_body)
    factory = _mock_async_client_factory(mock_response)

    with patch("nightcrate.services.http_client.httpx.AsyncClient", factory):
        resp = await client.get("/api/locations/clear-outside?latitude=40.0&longitude=-74.0")

    assert resp.status_code == 200
    data = resp.json()
    assert data["sqm"] is None
    assert data["bortle"] is None


# ---------------------------------------------------------------------------
# GET /api/locations/clear-outside — error paths
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_clear_outside_network_error(client):
    """A network failure surfaces as 502 with our friendly detail."""
    factory = _mock_async_client_factory(httpx.ConnectError("connection refused"))

    with patch("nightcrate.services.http_client.httpx.AsyncClient", factory):
        resp = await client.get("/api/locations/clear-outside?latitude=40.0&longitude=-74.0")

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Could not reach Clear Outside"


@pytest.mark.anyio
async def test_clear_outside_non_2xx_response(client):
    """Upstream 503 surfaces as 502 because raise_for_status raises an HTTPError."""
    mock_response = _mock_response("<p>Server is down</p>", status_code=503)
    factory = _mock_async_client_factory(mock_response)

    with patch("nightcrate.services.http_client.httpx.AsyncClient", factory):
        resp = await client.get("/api/locations/clear-outside?latitude=40.0&longitude=-74.0")

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Could not reach Clear Outside"


@pytest.mark.anyio
async def test_clear_outside_timeout_error(client):
    """Timeouts are HTTPError subclasses — also surface as 502."""
    factory = _mock_async_client_factory(httpx.ReadTimeout("timed out"))

    with patch("nightcrate.services.http_client.httpx.AsyncClient", factory):
        resp = await client.get("/api/locations/clear-outside?latitude=40.0&longitude=-74.0")

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Could not reach Clear Outside"


# ---------------------------------------------------------------------------
# GET /api/locations/clear-outside — query validation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_clear_outside_rejects_out_of_range_latitude(client):
    """FastAPI Query(ge=-90, le=90) returns 422 for lat=95."""
    resp = await client.get("/api/locations/clear-outside?latitude=95&longitude=0")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_clear_outside_rejects_out_of_range_longitude(client):
    """FastAPI Query(ge=-180, le=180) returns 422 for lon=200."""
    resp = await client.get("/api/locations/clear-outside?latitude=0&longitude=200")
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# geo_timezone override on POST /api/locations
# ---------------------------------------------------------------------------


_BASE_LOCATION = {
    "name": "Test Site",
    "latitude": 33.4484,  # Phoenix
    "longitude": -112.0740,
    "elevation_m": 330.0,
    "timezone": "America/Phoenix",
}


@pytest.mark.anyio
async def test_create_location_respects_explicit_geo_timezone_override(client):
    """Explicit geo_timezone in POST body wins over timezonefinder lookup."""
    payload = {**_BASE_LOCATION, "name": "Override Site", "geo_timezone": "UTC"}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # Explicit override should be stored verbatim, NOT America/Phoenix.
    assert data["geo_timezone"] == "UTC"


@pytest.mark.anyio
async def test_create_location_auto_derives_geo_timezone_when_omitted(client):
    """When geo_timezone is not supplied, server derives from coords."""
    payload = {**_BASE_LOCATION, "name": "Auto-derived Site"}
    resp = await client.post("/api/locations", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    # For Phoenix coords, timezonefinder resolves to America/Phoenix.
    assert data["geo_timezone"] == "America/Phoenix"


# ---------------------------------------------------------------------------
# geo_timezone override on PUT /api/locations/{id}
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_update_coords_without_geo_timezone_recomputes(client):
    """PATCH coords only — server must recompute geo_timezone from new coords."""
    # Start in Phoenix
    start = await client.post(
        "/api/locations",
        json={**_BASE_LOCATION, "name": "Recompute Me"},
    )
    loc_id = start.json()["id"]
    assert start.json()["geo_timezone"] == "America/Phoenix"

    # Move to Tokyo without supplying geo_timezone
    resp = await client.put(
        f"/api/locations/{loc_id}",
        json={"latitude": 35.6762, "longitude": 139.6503},
    )
    assert resp.status_code == 200
    assert resp.json()["geo_timezone"] == "Asia/Tokyo"


@pytest.mark.anyio
async def test_update_coords_with_explicit_geo_timezone_is_preserved(client):
    """PATCH coords WITH explicit geo_timezone — server keeps user-supplied value."""
    start = await client.post(
        "/api/locations",
        json={**_BASE_LOCATION, "name": "Keep My Override"},
    )
    loc_id = start.json()["id"]
    assert start.json()["geo_timezone"] == "America/Phoenix"

    # Move to Tokyo but explicitly say geo_timezone is UTC — override must win.
    resp = await client.put(
        f"/api/locations/{loc_id}",
        json={"latitude": 35.6762, "longitude": 139.6503, "geo_timezone": "UTC"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["geo_timezone"] == "UTC"
    # Sanity: the coords really did change
    assert data["latitude"] == 35.6762
    assert data["longitude"] == 139.6503


@pytest.mark.anyio
async def test_update_geo_timezone_alone_stores_supplied_value(client):
    """PATCH only geo_timezone (no coord change) — server stores the supplied value."""
    start = await client.post(
        "/api/locations",
        json={**_BASE_LOCATION, "name": "Timezone-only Update"},
    )
    loc_id = start.json()["id"]
    assert start.json()["geo_timezone"] == "America/Phoenix"

    resp = await client.put(f"/api/locations/{loc_id}", json={"geo_timezone": "UTC"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["geo_timezone"] == "UTC"
    # Coordinates untouched
    assert data["latitude"] == _BASE_LOCATION["latitude"]
    assert data["longitude"] == _BASE_LOCATION["longitude"]
