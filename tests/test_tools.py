from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import TransitOption, TransportType
from app.tools.omio_search import (
    _detect_provider,
    _detect_transfers,
    _detect_transport_type,
    _parse_result_card,
)
from app.tools.train_search import search_trains
from app.tools.flight_search import search_flights
from app.tools.bus_search import search_buses
from app.tools.checkout import get_checkout_link
from app.tools import TOOL_DEFINITIONS, execute_tool


# ---------------------------------------------------------------------------
# _parse_result_card (unit tests — no browser needed)
# ---------------------------------------------------------------------------


class TestParseResultCard:

    def test_parses_train_card(self):
        text = "Deutsche Bahn\n14:30  18:45\n4h 15min\n€29\nDirect"
        option = _parse_result_card(text, "2026-03-15")
        assert option is not None
        assert option.transport_type == TransportType.train
        assert option.provider == "Deutsche Bahn"
        assert option.departure_time == datetime(2026, 3, 15, 14, 30)
        assert option.arrival_time == datetime(2026, 3, 15, 18, 45)
        assert option.duration_minutes == 4 * 60 + 15
        assert option.price == 29.0
        assert option.currency == "EUR"
        assert option.transfers == 0

    def test_parses_bus_card(self):
        text = "FlixBus\n08:00  12:30\n4h 30min\n€19\nDirect"
        option = _parse_result_card(text, "2026-03-15")
        assert option is not None
        assert option.transport_type == TransportType.bus
        assert option.provider == "FlixBus"
        assert option.price == 19.0

    def test_parses_card_with_transfer(self):
        text = "SNCF\n06:00  14:00\n8h 0min\n€55\n1 change"
        option = _parse_result_card(text, "2026-03-15")
        assert option is not None
        assert option.transfers == 1

    def test_handles_overnight_journey(self):
        text = "DB\n23:00  06:30\n7h 30min\n€40\nDirect"
        option = _parse_result_card(text, "2026-03-15")
        assert option is not None
        assert option.arrival_time.day == 16  # next day

    def test_returns_none_for_empty_text(self):
        assert _parse_result_card("", "2026-03-15") is None

    def test_returns_none_for_no_price(self):
        text = "DB\n14:30  18:45\n4h 15min\nDirect"
        assert _parse_result_card(text, "2026-03-15") is None

    def test_returns_none_for_single_time(self):
        text = "14:30\n€29"
        assert _parse_result_card(text, "2026-03-15") is None

    def test_parses_decimal_price(self):
        text = "DB\n10:00  14:00\n4h 0min\n€29.90\nDirect"
        option = _parse_result_card(text, "2026-03-15")
        assert option is not None
        assert option.price == 29.90

    def test_parses_hours_only_duration(self):
        text = "ICE\n10:00  14:00\n4h\n€50\nDirect"
        option = _parse_result_card(text, "2026-03-15")
        assert option is not None
        assert option.duration_minutes == 240

    def test_parses_minutes_only_duration(self):
        text = "DB\n10:00  10:45\n45min\n€15\nDirect"
        option = _parse_result_card(text, "2026-03-15")
        assert option is not None
        assert option.duration_minutes == 45


class TestDetectTransportType:

    def test_detects_bus(self):
        assert _detect_transport_type("flixbus direct") == TransportType.bus

    def test_detects_train(self):
        assert _detect_transport_type("ice high-speed train") == TransportType.train

    def test_defaults_to_train(self):
        assert _detect_transport_type("some unknown text") == TransportType.train

    def test_detects_deutsche_bahn(self):
        assert _detect_transport_type("deutsche bahn regional") == TransportType.train


class TestDetectProvider:

    def test_known_provider(self):
        assert _detect_provider("FlixBus Berlin → Munich") == "FlixBus"

    def test_unknown_provider(self):
        assert _detect_provider("Some random text") == "Omio"

    def test_case_insensitive(self):
        assert _detect_provider("deutsche bahn ICE") == "Deutsche Bahn"


class TestDetectTransfers:

    def test_direct(self):
        assert _detect_transfers("direct") == 0

    def test_one_change(self):
        assert _detect_transfers("1 change in hannover") == 1

    def test_two_transfers(self):
        assert _detect_transfers("2 transfers") == 2

    def test_nonstop(self):
        assert _detect_transfers("nonstop service") == 0

    def test_no_info(self):
        assert _detect_transfers("some random text") == 0


# ---------------------------------------------------------------------------
# search_trains / search_buses with mocked Omio scraper
# ---------------------------------------------------------------------------

_MOCK_OMIO_RESULTS = [
    TransitOption(
        transport_type=TransportType.train,
        provider="Deutsche Bahn",
        departure_time=datetime(2026, 3, 15, 10, 0),
        arrival_time=datetime(2026, 3, 15, 14, 0),
        duration_minutes=240,
        price=29.0,
        currency="EUR",
        transfers=0,
        details="DB 10:00-14:00",
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
        details="FlixBus 08:00-14:30",
    ),
    TransitOption(
        transport_type=TransportType.train,
        provider="ICE",
        departure_time=datetime(2026, 3, 15, 12, 0),
        arrival_time=datetime(2026, 3, 15, 16, 0),
        duration_minutes=240,
        price=45.0,
        currency="EUR",
        transfers=0,
        details="ICE 12:00-16:00",
    ),
]


@pytest.mark.asyncio
@patch("app.tools.train_search.search_omio", new_callable=AsyncMock, return_value=_MOCK_OMIO_RESULTS)
async def test_search_trains_filters_trains(mock_omio):
    results = await search_trains("Berlin", "Munich", "2026-03-15")
    assert len(results) == 2
    assert all(r.transport_type == TransportType.train for r in results)
    mock_omio.assert_called_once_with("Berlin", "Munich", "2026-03-15", None)


@pytest.mark.asyncio
@patch("app.tools.bus_search.search_omio", new_callable=AsyncMock, return_value=_MOCK_OMIO_RESULTS)
async def test_search_buses_filters_buses(mock_omio):
    results = await search_buses("Berlin", "Munich", "2026-03-15")
    assert len(results) == 1
    assert all(r.transport_type == TransportType.bus for r in results)


@pytest.mark.asyncio
@patch("app.tools.train_search.search_omio", new_callable=AsyncMock, return_value=[])
async def test_search_trains_empty_results(mock_omio):
    results = await search_trains("Berlin", "Munich", "2026-03-15")
    assert results == []


@pytest.mark.asyncio
@patch("app.tools.bus_search.search_omio", new_callable=AsyncMock, return_value=[])
async def test_search_buses_empty_results(mock_omio):
    results = await search_buses("Berlin", "Munich", "2026-03-15")
    assert results == []


@pytest.mark.asyncio
@patch("app.tools.train_search.search_omio", new_callable=AsyncMock, side_effect=RuntimeError("browser crash"))
async def test_search_trains_handles_error(mock_omio):
    results = await search_trains("Berlin", "Munich", "2026-03-15")
    assert results == []


@pytest.mark.asyncio
@patch("app.tools.bus_search.search_omio", new_callable=AsyncMock, side_effect=RuntimeError("browser crash"))
async def test_search_buses_handles_error(mock_omio):
    results = await search_buses("Berlin", "Munich", "2026-03-15")
    assert results == []


# ---------------------------------------------------------------------------
# search_flights (still mock — unchanged)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_flights_seoul_busan():
    results = await search_flights("서울", "부산", "2026-03-15")
    assert len(results) >= 1
    for opt in results:
        assert isinstance(opt, TransitOption)
        assert opt.transport_type == TransportType.flight
        assert opt.duration_minutes > 0
        assert opt.price > 0


@pytest.mark.asyncio
async def test_search_flights_unknown_route():
    results = await search_flights("대전", "강릉", "2026-03-15")
    assert isinstance(results, list)
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# get_checkout_link
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_checkout_link_train():
    option = TransitOption(
        transport_type=TransportType.train,
        provider="KTX",
        departure_time=datetime(2026, 3, 15, 10, 0),
        arrival_time=datetime(2026, 3, 15, 12, 35),
        duration_minutes=155,
        price=59800.0,
    )
    result = await get_checkout_link(option)
    assert "checkout_url" in result
    assert "expires_at" in result
    assert result["checkout_url"].startswith("https://")
    assert result["expires_at"] != ""


@pytest.mark.asyncio
async def test_get_checkout_link_expiry():
    option = TransitOption(
        transport_type=TransportType.train,
        provider="SRT",
        departure_time=datetime(2026, 3, 15, 10, 0),
        arrival_time=datetime(2026, 3, 15, 12, 30),
        duration_minutes=150,
        price=52600.0,
    )
    result = await get_checkout_link(option)
    expires = datetime.fromisoformat(result["expires_at"])
    now = datetime.utcnow()
    diff_minutes = (expires - now).total_seconds() / 60
    assert 25 <= diff_minutes <= 35


# ---------------------------------------------------------------------------
# TOOL_DEFINITIONS
# ---------------------------------------------------------------------------

def test_tool_definitions_count():
    assert len(TOOL_DEFINITIONS) == 4


def test_tool_definitions_structure():
    for defn in TOOL_DEFINITIONS:
        assert "name" in defn
        assert "description" in defn
        assert "input_schema" in defn
        schema = defn["input_schema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema


def test_tool_definitions_names():
    names = {d["name"] for d in TOOL_DEFINITIONS}
    assert names == {"search_trains", "search_flights", "search_buses", "get_checkout_link"}


def test_tool_descriptions_no_korean_references():
    """Verify tool descriptions no longer reference Korean-specific content."""
    for defn in TOOL_DEFINITIONS:
        desc = defn["description"]
        props = defn["input_schema"]["properties"]
        assert "Korean" not in desc, f"{defn['name']} description still references Korean"
        for prop_name, prop_info in props.items():
            prop_desc = prop_info.get("description", "")
            assert "서울" not in prop_desc, f"{defn['name']}.{prop_name} still references Korean city"


# ---------------------------------------------------------------------------
# execute_tool dispatcher
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("app.tools.train_search.search_omio", new_callable=AsyncMock, return_value=_MOCK_OMIO_RESULTS)
async def test_execute_tool_search_trains(mock_omio):
    results = await execute_tool("search_trains", {
        "origin": "Berlin",
        "destination": "Munich",
        "date": "2026-03-15",
    })
    assert isinstance(results, list)
    assert len(results) == 2
    assert all(isinstance(r, TransitOption) for r in results)


@pytest.mark.asyncio
async def test_execute_tool_search_flights():
    results = await execute_tool("search_flights", {
        "origin": "서울",
        "destination": "제주",
        "date": "2026-03-15",
    })
    assert isinstance(results, list)
    assert len(results) >= 1


@pytest.mark.asyncio
@patch("app.tools.bus_search.search_omio", new_callable=AsyncMock, return_value=_MOCK_OMIO_RESULTS)
async def test_execute_tool_search_buses(mock_omio):
    results = await execute_tool("search_buses", {
        "origin": "Berlin",
        "destination": "Munich",
        "date": "2026-03-15",
    })
    assert isinstance(results, list)
    assert len(results) == 1


@pytest.mark.asyncio
async def test_execute_tool_get_checkout_link():
    result = await execute_tool("get_checkout_link", {
        "transport_type": "train",
        "provider": "KTX",
        "departure_time": "2026-03-15T10:00:00",
        "arrival_time": "2026-03-15T12:35:00",
        "duration_minutes": 155,
        "price": 59800,
    })
    assert "checkout_url" in result
    assert "expires_at" in result


@pytest.mark.asyncio
async def test_execute_tool_unknown():
    with pytest.raises(ValueError, match="Unknown tool"):
        await execute_tool("nonexistent_tool", {})


# ---------------------------------------------------------------------------
# E2E Omio search (requires Playwright browser — skip in CI)
# ---------------------------------------------------------------------------

@pytest.mark.omio
@pytest.mark.asyncio
async def test_omio_search_e2e():
    """E2E test: actually hit Omio. Run with: pytest -m omio"""
    from app.tools.omio_search import search_omio

    results = await search_omio("Berlin", "Munich", "2026-03-20")
    assert isinstance(results, list)
    # We can't guarantee results exist, but it shouldn't error
    for r in results:
        assert isinstance(r, TransitOption)
        assert r.currency == "EUR"
        assert r.price > 0
