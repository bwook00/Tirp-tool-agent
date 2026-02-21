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

# Korean → English city name mapping (HAFAS only understands Latin names)
_CITY_TRANSLATE: dict[str, str] = {
    "파리": "Paris",
    "베를린": "Berlin",
    "뮌헨": "Munich",
    "함부르크": "Hamburg",
    "프랑크푸르트": "Frankfurt",
    "암스테르담": "Amsterdam",
    "브뤼셀": "Brussels",
    "런던": "London",
    "로마": "Rome",
    "밀라노": "Milan",
    "바르셀로나": "Barcelona",
    "마드리드": "Madrid",
    "비엔나": "Vienna",
    "빈": "Vienna",
    "취리히": "Zurich",
    "프라하": "Prague",
    "바르샤바": "Warsaw",
    "부다페스트": "Budapest",
    "바젤": "Basel",
    "쾰른": "Cologne",
    "뒤셀도르프": "Dusseldorf",
    "슈투트가르트": "Stuttgart",
    "드레스덴": "Dresden",
    "라이프치히": "Leipzig",
    "리옹": "Lyon",
    "마르세유": "Marseille",
    "니스": "Nice",
    "스트라스부르": "Strasbourg",
    "제네바": "Geneva",
    "베른": "Bern",
    "루체른": "Lucerne",
    "인터라켄": "Interlaken",
    "피렌체": "Florence",
    "베네치아": "Venice",
    "나폴리": "Naples",
    "리스본": "Lisbon",
    "포르투": "Porto",
    "코펜하겐": "Copenhagen",
    "스톡홀름": "Stockholm",
    "오슬로": "Oslo",
    "헬싱키": "Helsinki",
    "뉘른베르크": "Nuremberg",
    "잘츠부르크": "Salzburg",
    "인스브루크": "Innsbruck",
    "그라츠": "Graz",
    "브라티슬라바": "Bratislava",
    "크라쿠프": "Krakow",
    "부쿠레슈티": "Bucharest",
    "소피아": "Sofia",
    "아테네": "Athens",
    "이스탄불": "Istanbul",
}

# Location cache: city name -> station ID
_location_cache: dict[str, str] = {}


def _normalize_city(name: str) -> str:
    """Translate Korean city names to English for HAFAS lookup."""
    return _CITY_TRANSLATE.get(name.strip(), name.strip())


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
        origin_id = await _resolve_location(_normalize_city(origin))
        dest_id = await _resolve_location(_normalize_city(destination))

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
