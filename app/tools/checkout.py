import logging
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import httpx

from app.models.schemas import TransitOption, TransportType
from app.tools.hafas_search import _normalize_city

logger = logging.getLogger(__name__)

_BOOKING_URLS: dict[str, str] = {
    # European train operators
    "Deutsche Bahn": "https://www.bahn.de/buchung/start",
    "DB": "https://www.bahn.de/buchung/start",
    "ICE": "https://www.bahn.de/buchung/start",
    "SNCF": "https://www.sncf-connect.com/en-en",
    "TGV": "https://www.sncf-connect.com/en-en",
    "OUIGO": "https://www.ouigo.com/en/search",
    "Trenitalia": "https://www.trenitalia.com/en/buying-your-ticket.html",
    "Frecciarossa": "https://www.trenitalia.com/en/buying-your-ticket.html",
    "Italo": "https://www.italotreno.it/en/booking",
    "Renfe": "https://www.renfe.com/en/en/booking",
    "Eurostar": "https://www.eurostar.com/en-gb/booking",
    "Thalys": "https://www.thalys.com/en/booking",
    "SBB": "https://www.sbb.ch/en/buying/pages/fahrplan/fahrplan.xhtml",
    "OBB": "https://shop.oebb.at/en/ticket",
    "RailJet": "https://shop.oebb.at/en/ticket",
    "NS": "https://www.ns.nl/en/journeyplanner",
    "PKP": "https://www.intercity.pl/en/booking",
    "Czech Railways": "https://www.cd.cz/en/booking",
    "RegioJet": "https://www.regiojet.com/search",
    # European bus operators
    "FlixBus": "https://www.flixbus.com/bus-routes",
    "FlixTrain": "https://www.flixtrain.com/train-routes",
    "BlaBlaBus": "https://www.blablacar.com/bus",
    # Default
    "Omio": "https://www.omio.com/search",
}

_CHECKOUT_EXPIRY_MINUTES = 30
_HTTP_TIMEOUT_SECONDS = 10
_DB_BASE_URL = "https://v6.db.transport.rest"
_FLIX_CITY_API = "https://global.api.flixbus.com/search/autocomplete/cities"
_FLIX_STATION_API = "https://global.api.flixbus.com/search/autocomplete/stations"

_db_stop_cache: dict[str, str] = {}
_flix_city_cache: dict[str, tuple[str, int]] = {}
_flix_station_cache: dict[str, tuple[str | None, int | None]] = {}


async def get_checkout_link(
    option: TransitOption,
    origin: str,
    destination: str,
    departure_date: str,
    departure_time: str | None = None,
) -> dict:
    """Generate a checkout/booking link for the given transit option.

    If the option's `details` field contains a deep link (from the API),
    use it directly. Otherwise construct a provider search URL prefilled
    with origin/destination/date.

    Returns a dict with:
        - checkout_url: a booking URL for the provider
        - expires_at: ISO-format datetime string, 30 minutes from now
    """
    try:
        # Prefer deep link from Omio API
        if option.details and option.details.startswith("http"):
            checkout_url = option.details
        else:
            checkout_url = await _build_provider_search_url(
                option.provider,
                option.transport_type,
                origin,
                destination,
                departure_date,
                departure_time,
            )

        expires_at = datetime.utcnow() + timedelta(minutes=_CHECKOUT_EXPIRY_MINUTES)

        return {
            "checkout_url": checkout_url,
            "expires_at": expires_at.isoformat(),
        }

    except Exception:
        logger.exception("get_checkout_link failed")
        return {
            "checkout_url": "",
            "expires_at": "",
        }


def _default_url(transport_type: TransportType) -> str:
    defaults = {
        TransportType.train: "https://www.omio.com/trains",
        TransportType.bus: "https://www.omio.com/buses",
        TransportType.flight: "https://www.omio.com/flights",
    }
    return defaults.get(transport_type, "https://www.omio.com/search")


async def _build_provider_search_url(
    provider: str,
    transport_type: TransportType,
    origin: str,
    destination: str,
    departure_date: str,
    departure_time: str | None,
) -> str:
    provider_key = provider.lower()
    origin_en = _normalize_city(origin)
    destination_en = _normalize_city(destination)
    time_value = departure_time or "09:00"

    if (
        "sncf" in provider_key
        or "tgv" in provider_key
        or "ouigo" in provider_key
        or "eurostar" in provider_key
    ):
        # SNCF Connect web search route.
        # Keep format strict to reduce "error" page probability.
        outward_dt = f"{departure_date}T{time_value}:00"
        return (
            "https://www.sncf-connect.com/en-en/home/search/od"
            f"?origin={quote_plus(origin_en)}"
            f"&destination={quote_plus(destination_en)}"
            f"&outwardDate={quote_plus(outward_dt)}"
        )

    if "db" in provider_key or "deutsche bahn" in provider_key:
        # Bahn search format (fragment based).
        resolved_origin = await _resolve_db_stop_name(origin_en)
        resolved_destination = await _resolve_db_stop_name(destination_en)
        date_parts = departure_date.split("-")
        date_for_db = departure_date
        if len(date_parts) == 3:
            date_for_db = f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]}"
        return (
            "https://int.bahn.de/en/buchung/fahrplan/suche"
            f"#sts=true&so={quote_plus(resolved_origin)}&zo={quote_plus(resolved_destination)}"
            f"&kl=2&r={quote_plus(date_for_db)}"
        )

    if "flixbus" in provider_key or "flixtrain" in provider_key:
        flix = await _resolve_flix_ids(origin_en, destination_en)
        if flix:
            return (
                "https://shop.global.flixbus.com/search"
                f"?departureCity={quote_plus(flix['departure_city'])}"
                f"&arrivalCity={quote_plus(flix['arrival_city'])}"
                f"&rideDate={quote_plus(departure_date)}"
                f"&adult=1&_locale=en_US"
                + (
                    f"&departureStation={quote_plus(str(flix['departure_station']))}"
                    if flix["departure_station"] is not None
                    else ""
                )
                + (
                    f"&arrivalStation={quote_plus(str(flix['arrival_station']))}"
                    if flix["arrival_station"] is not None
                    else ""
                )
            )

        # Fallback to city-name query if ID resolution fails.
        return (
            "https://shop.global.flixbus.com/search"
            f"?departureCity={quote_plus(origin_en)}"
            f"&arrivalCity={quote_plus(destination_en)}"
            f"&rideDate={quote_plus(departure_date)}"
            f"&adult=1&_locale=en_US"
        )

    return _BOOKING_URLS.get(provider, _default_url(transport_type))


async def _resolve_db_stop_name(query: str) -> str:
    if query in _db_stop_cache:
        return _db_stop_cache[query]

    params = {
        "query": query,
        "results": 1,
        "stops": True,
        "addresses": False,
        "poi": False,
        "profile": "db",
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(f"{_DB_BASE_URL}/locations", params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("DB stop resolve failed for '%s', using original", query)
        return query

    if not data:
        return query

    resolved = data[0].get("name") or query
    _db_stop_cache[query] = resolved
    return resolved


async def _resolve_flix_ids(origin: str, destination: str) -> dict[str, str | int | None] | None:
    origin_city = await _resolve_flix_city(origin)
    destination_city = await _resolve_flix_city(destination)
    if not origin_city or not destination_city:
        return None

    origin_station = await _resolve_flix_station(origin, int(origin_city[1]))
    destination_station = await _resolve_flix_station(destination, int(destination_city[1]))

    return {
        "departure_city": origin_city[0],
        "arrival_city": destination_city[0],
        "departure_station": origin_station[0] if origin_station else None,
        "arrival_station": destination_station[0] if destination_station else None,
    }


async def _resolve_flix_city(query: str) -> tuple[str, int] | None:
    if query in _flix_city_cache:
        return _flix_city_cache[query]

    params = {"locale": "en", "q": query}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(_FLIX_CITY_API, params=params)
            resp.raise_for_status()
            items = resp.json()
    except Exception:
        logger.warning("Flix city resolve failed for '%s'", query)
        return None

    if not items:
        return None

    top = items[0]
    city_uuid = top.get("id")
    legacy_id = top.get("legacy_id")
    if not city_uuid or legacy_id is None:
        return None

    resolved = (str(city_uuid), int(legacy_id))
    _flix_city_cache[query] = resolved
    return resolved


async def _resolve_flix_station(query: str, city_legacy_id: int) -> tuple[str | None, int | None] | None:
    cache_key = f"{query}:{city_legacy_id}"
    if cache_key in _flix_station_cache:
        return _flix_station_cache[cache_key]

    params = {"locale": "en", "q": query}
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(_FLIX_STATION_API, params=params)
            resp.raise_for_status()
            items = resp.json()
    except Exception:
        logger.warning("Flix station resolve failed for '%s'", query)
        return None

    if not items:
        return None

    matching = [item for item in items if item.get("city", {}).get("legacy_id") == city_legacy_id]
    top = matching[0] if matching else items[0]

    station_uuid = top.get("id")
    station_legacy = top.get("legacy_id")
    resolved = (
        str(station_uuid) if station_uuid else None,
        int(station_legacy) if station_legacy is not None else None,
    )
    _flix_station_cache[cache_key] = resolved
    return resolved
