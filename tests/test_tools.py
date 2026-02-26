from datetime import datetime
from urllib.parse import parse_qs, urlparse
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import TransitOption, TransportType
from app.tools.train_search import search_trains
from app.tools.bus_search import search_buses
from app.tools.checkout import get_checkout_link


# ---------------------------------------------------------------------------
# Mock HAFAS results for search tests
# ---------------------------------------------------------------------------

_MOCK_HAFAS_RESULTS = [
    TransitOption(
        transport_type=TransportType.train,
        provider="DB Fernverkehr AG",
        departure_time=datetime(2026, 3, 15, 10, 0),
        arrival_time=datetime(2026, 3, 15, 14, 0),
        duration_minutes=240,
        price=29.0,
        currency="EUR",
        transfers=0,
        details="ICE 1591",
    ),
    TransitOption(
        transport_type=TransportType.bus,
        provider="FlixBus",
        departure_time=datetime(2026, 3, 15, 8, 0),
        arrival_time=datetime(2026, 3, 15, 14, 30),
        duration_minutes=390,
        price=19.0,
        currency="EUR",
        transfers=0,
        details="Bus 100",
    ),
    TransitOption(
        transport_type=TransportType.train,
        provider="SNCF",
        departure_time=datetime(2026, 3, 15, 12, 0),
        arrival_time=datetime(2026, 3, 15, 16, 0),
        duration_minutes=240,
        price=45.0,
        currency="EUR",
        transfers=0,
        details="TGV 9573",
    ),
]


# ---------------------------------------------------------------------------
# search_trains / search_buses with mocked HAFAS
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.tools.train_search.search_hafas", new_callable=AsyncMock, return_value=_MOCK_HAFAS_RESULTS)
async def test_search_trains_filters_trains(mock_hafas):
    results = await search_trains("Berlin", "Munich", "2026-03-15")
    assert len(results) == 2
    assert all(r.transport_type == TransportType.train for r in results)
    mock_hafas.assert_called_once_with("Berlin", "Munich", "2026-03-15", None)


@pytest.mark.asyncio
@patch("app.tools.bus_search.search_hafas", new_callable=AsyncMock, return_value=_MOCK_HAFAS_RESULTS)
async def test_search_buses_filters_buses(mock_hafas):
    results = await search_buses("Berlin", "Munich", "2026-03-15")
    assert len(results) == 1
    assert all(r.transport_type == TransportType.bus for r in results)


@pytest.mark.asyncio
@patch("app.tools.train_search.search_hafas", new_callable=AsyncMock, return_value=[])
async def test_search_trains_empty_results(mock_hafas):
    results = await search_trains("Berlin", "Munich", "2026-03-15")
    assert results == []


@pytest.mark.asyncio
@patch("app.tools.bus_search.search_hafas", new_callable=AsyncMock, return_value=[])
async def test_search_buses_empty_results(mock_hafas):
    results = await search_buses("Berlin", "Munich", "2026-03-15")
    assert results == []


@pytest.mark.asyncio
@patch("app.tools.train_search.search_hafas", new_callable=AsyncMock, side_effect=RuntimeError("API down"))
async def test_search_trains_handles_error(mock_hafas):
    results = await search_trains("Berlin", "Munich", "2026-03-15")
    assert results == []


@pytest.mark.asyncio
@patch("app.tools.bus_search.search_hafas", new_callable=AsyncMock, side_effect=RuntimeError("API down"))
async def test_search_buses_handles_error(mock_hafas):
    results = await search_buses("Berlin", "Munich", "2026-03-15")
    assert results == []


# ---------------------------------------------------------------------------
# get_checkout_link
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_checkout_link_train():
    option = TransitOption(
        transport_type=TransportType.train,
        provider="Deutsche Bahn",
        departure_time=datetime(2026, 3, 15, 10, 0),
        arrival_time=datetime(2026, 3, 15, 12, 35),
        duration_minutes=155,
        price=59.90,
    )
    with patch("app.tools.checkout._resolve_db_stop_name", new_callable=AsyncMock) as mock_db_resolve:
        mock_db_resolve.side_effect = ["Berlin Hbf", "Muenchen Hbf"]
        result = await get_checkout_link(
            option,
            origin="Berlin",
            destination="Munich",
            departure_date="2026-03-15",
            departure_time="10:00",
        )
    assert "checkout_url" in result
    assert "expires_at" in result
    assert result["checkout_url"].startswith("https://")
    assert "so=Berlin+Hbf" in result["checkout_url"]
    assert "zo=Muenchen+Hbf" in result["checkout_url"]
    assert result["expires_at"] != ""


@pytest.mark.asyncio
async def test_get_checkout_link_expiry():
    option = TransitOption(
        transport_type=TransportType.train,
        provider="SNCF",
        departure_time=datetime(2026, 3, 15, 10, 0),
        arrival_time=datetime(2026, 3, 15, 12, 30),
        duration_minutes=150,
        price=52.60,
    )
    result = await get_checkout_link(
        option,
        origin="Paris",
        destination="Lyon",
        departure_date="2026-03-15",
        departure_time="10:00",
    )
    parsed = urlparse(result["checkout_url"])
    query = parse_qs(parsed.query)
    assert parsed.netloc == "www.sncf-connect.com"
    assert query["origin"] == ["Paris"]
    assert query["destination"] == ["Lyon"]
    expires = datetime.fromisoformat(result["expires_at"])
    now = datetime.utcnow()
    diff_minutes = (expires - now).total_seconds() / 60
    assert 25 <= diff_minutes <= 35


@pytest.mark.asyncio
async def test_get_checkout_link_deep_link():
    """If option has a deep link URL in details, use it directly."""
    option = TransitOption(
        transport_type=TransportType.train,
        provider="DB Fernverkehr AG",
        departure_time=datetime(2026, 3, 15, 10, 0),
        arrival_time=datetime(2026, 3, 15, 14, 0),
        duration_minutes=240,
        price=56.99,
        details="https://www.omio.com/booking/12345",
    )
    result = await get_checkout_link(
        option,
        origin="Berlin",
        destination="Munich",
        departure_date="2026-03-15",
        departure_time="10:00",
    )
    assert result["checkout_url"] == "https://www.omio.com/booking/12345"


@pytest.mark.asyncio
async def test_get_checkout_link_flix_uses_resolved_ids():
    option = TransitOption(
        transport_type=TransportType.bus,
        provider="FlixBus",
        departure_time=datetime(2026, 3, 15, 10, 0),
        arrival_time=datetime(2026, 3, 15, 12, 30),
        duration_minutes=150,
        price=22.50,
    )
    with patch("app.tools.checkout._resolve_flix_ids", new_callable=AsyncMock) as mock_flix:
        mock_flix.return_value = {
            "departure_city": "40de8964-8646-11e6-9066-549f350fcb0c",
            "arrival_city": "40de3026-8646-11e6-9066-549f350fcb0c",
            "departure_station": "7f6214cd-95d7-4bbf-8283-55af226fa33a",
            "arrival_station": "dcbc827f-9603-11e6-9066-549f350fcb0c",
        }
        result = await get_checkout_link(
            option,
            origin="Paris",
            destination="Basel",
            departure_date="2026-03-03",
            departure_time="08:00",
        )

    assert "shop.global.flixbus.com/search" in result["checkout_url"]
    assert "departureCity=40de8964-8646-11e6-9066-549f350fcb0c" in result["checkout_url"]
    assert "arrivalCity=40de3026-8646-11e6-9066-549f350fcb0c" in result["checkout_url"]
