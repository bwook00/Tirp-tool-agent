import pytest
from datetime import datetime

from app.models.schemas import TransitOption, TransportType
from app.tools.train_search import search_trains
from app.tools.flight_search import search_flights
from app.tools.bus_search import search_buses
from app.tools.checkout import get_checkout_link
from app.tools import TOOL_DEFINITIONS, execute_tool


# ---------------------------------------------------------------------------
# search_trains
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_trains_seoul_busan():
    results = await search_trains("서울", "부산", "2026-03-15")
    assert len(results) >= 1
    for opt in results:
        assert isinstance(opt, TransitOption)
        assert opt.transport_type == TransportType.train
        assert opt.duration_minutes > 0
        assert opt.price > 0
        assert opt.currency == "KRW"


@pytest.mark.asyncio
async def test_search_trains_reverse_route():
    results = await search_trains("부산", "서울", "2026-03-15")
    assert len(results) >= 1
    assert all(opt.transport_type == TransportType.train for opt in results)


@pytest.mark.asyncio
async def test_search_trains_with_time():
    results = await search_trains("서울", "대전", "2026-03-15", time="14:00")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_trains_unknown_route():
    results = await search_trains("인천", "속초", "2026-03-15")
    assert isinstance(results, list)
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# search_flights
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
async def test_search_flights_seoul_jeju():
    results = await search_flights("서울", "제주", "2026-03-15")
    assert len(results) >= 2


@pytest.mark.asyncio
async def test_search_flights_unknown_route():
    results = await search_flights("대전", "강릉", "2026-03-15")
    assert isinstance(results, list)
    assert len(results) >= 1


# ---------------------------------------------------------------------------
# search_buses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_buses_seoul_busan():
    results = await search_buses("서울", "부산", "2026-03-15")
    assert len(results) >= 1
    for opt in results:
        assert isinstance(opt, TransitOption)
        assert opt.transport_type == TransportType.bus
        assert opt.duration_minutes > 0
        assert opt.price > 0


@pytest.mark.asyncio
async def test_search_buses_with_time():
    results = await search_buses("서울", "광주", "2026-03-15", time="09:00")
    assert len(results) >= 1


@pytest.mark.asyncio
async def test_search_buses_unknown_route():
    results = await search_buses("춘천", "여수", "2026-03-15")
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
    assert "letskorail" in result["checkout_url"]
    assert result["expires_at"] != ""


@pytest.mark.asyncio
async def test_get_checkout_link_flight():
    option = TransitOption(
        transport_type=TransportType.flight,
        provider="대한항공",
        departure_time=datetime(2026, 3, 15, 14, 0),
        arrival_time=datetime(2026, 3, 15, 15, 5),
        duration_minutes=65,
        price=77000.0,
    )
    result = await get_checkout_link(option)
    assert result["checkout_url"].startswith("https://")
    assert "koreanair" in result["checkout_url"]


@pytest.mark.asyncio
async def test_get_checkout_link_bus():
    option = TransitOption(
        transport_type=TransportType.bus,
        provider="고속버스 우등",
        departure_time=datetime(2026, 3, 15, 8, 0),
        arrival_time=datetime(2026, 3, 15, 12, 20),
        duration_minutes=260,
        price=34200.0,
    )
    result = await get_checkout_link(option)
    assert result["checkout_url"].startswith("https://")
    assert "kobus" in result["checkout_url"]


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
    assert 25 <= diff_minutes <= 35  # ~30 minutes with some tolerance


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


# ---------------------------------------------------------------------------
# execute_tool dispatcher
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_execute_tool_search_trains():
    results = await execute_tool("search_trains", {
        "origin": "서울",
        "destination": "부산",
        "date": "2026-03-15",
    })
    assert isinstance(results, list)
    assert len(results) >= 1
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
async def test_execute_tool_search_buses():
    results = await execute_tool("search_buses", {
        "origin": "서울",
        "destination": "대전",
        "date": "2026-03-15",
    })
    assert isinstance(results, list)
    assert len(results) >= 1


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
