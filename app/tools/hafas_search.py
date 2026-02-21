"""European transit search via DB transport.rest (HAFAS) API.

Free, no API key required, covers most European rail + bus routes.
Endpoint: https://v6.db.transport.rest
"""

import logging
from datetime import datetime

import httpx

from app.models.schemas import TransitOption, TransportType

logger = logging.getLogger(__name__)

_BASE_URL = "https://v6.db.transport.rest"
_TIMEOUT = 20
_MAX_RESULTS = 10

# Location cache: city name -> station ID
_location_cache: dict[str, str] = {}


async def search_hafas(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search European transit options via DB transport.rest API.

    Returns a list of TransitOption including trains and buses.
    """
    try:
        origin_id = await _resolve_location(origin)
        dest_id = await _resolve_location(destination)

        if not origin_id or not dest_id:
            logger.warning("Could not resolve locations: %s, %s", origin, destination)
            return []

        departure_str = f"{date}T{time or '00:00'}"

        return await _fetch_journeys(origin_id, dest_id, departure_str)

    except Exception:
        logger.exception("HAFAS search failed for %s -> %s", origin, destination)
        return []


async def _resolve_location(query: str) -> str | None:
    """Resolve a city name to a HAFAS station ID."""
    if query in _location_cache:
        return _location_cache[query]

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE_URL}/locations",
            params={"query": query, "results": 1, "stops": True, "addresses": False, "poi": False},
        )
        resp.raise_for_status()
        data = resp.json()

    if not data:
        return None

    station = data[0]
    station_id = station.get("id", "")
    if station_id:
        _location_cache[query] = station_id
        logger.debug("Resolved '%s' -> %s (%s)", query, station.get("name"), station_id)

    return station_id or None


async def _fetch_journeys(
    from_id: str,
    to_id: str,
    departure: str,
) -> list[TransitOption]:
    """Fetch journeys from the HAFAS API and parse into TransitOption list."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.get(
            f"{_BASE_URL}/journeys",
            params={
                "from": from_id,
                "to": to_id,
                "departure": departure,
                "results": _MAX_RESULTS,
                "tickets": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    options: list[TransitOption] = []
    for journey in data.get("journeys", []):
        option = _parse_journey(journey)
        if option:
            options.append(option)

    return options


def _parse_journey(journey: dict) -> TransitOption | None:
    """Parse a single HAFAS journey into a TransitOption."""
    legs = journey.get("legs", [])
    if not legs:
        return None

    # Filter out walking legs
    transit_legs = [leg for leg in legs if leg.get("line")]
    if not transit_legs:
        return None

    first_leg = transit_legs[0]
    last_leg = transit_legs[-1]

    # Departure / arrival from the full journey (including walks)
    dep_str = legs[0].get("departure") or legs[0].get("plannedDeparture", "")
    arr_str = legs[-1].get("arrival") or legs[-1].get("plannedArrival", "")
    if not dep_str or not arr_str:
        return None

    try:
        dep_time = datetime.fromisoformat(dep_str)
        arr_time = datetime.fromisoformat(arr_str)
        # Strip timezone for consistency
        dep_time = dep_time.replace(tzinfo=None)
        arr_time = arr_time.replace(tzinfo=None)
    except ValueError:
        return None

    duration_minutes = int((arr_time - dep_time).total_seconds() / 60)
    if duration_minutes <= 0:
        return None

    # Price
    price_info = journey.get("price")
    price = price_info.get("amount", 0) if price_info else 0
    currency = price_info.get("currency", "EUR") if price_info else "EUR"

    # Transport type from the main (longest or first) transit leg
    line = first_leg.get("line", {})
    mode = line.get("mode", "train")
    product = line.get("product", "")
    product_name = line.get("productName", "")

    if mode == "bus" or product in ("bus", "regionalBus"):
        transport_type = TransportType.bus
    else:
        transport_type = TransportType.train

    # Provider / operator
    operator = line.get("operator", {})
    provider = operator.get("name", product_name or "DB")

    # Transfers = number of transit legs - 1
    transfers = max(0, len(transit_legs) - 1)

    # Details: line names of all transit legs
    line_names = [leg.get("line", {}).get("name", "") for leg in transit_legs]
    details = " → ".join(name for name in line_names if name)

    return TransitOption(
        transport_type=transport_type,
        provider=provider,
        departure_time=dep_time,
        arrival_time=arr_time,
        duration_minutes=duration_minutes,
        price=price,
        currency=currency,
        transfers=transfers,
        details=details,
    )
