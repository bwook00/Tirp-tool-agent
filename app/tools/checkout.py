import logging
from datetime import datetime, timedelta
from urllib.parse import quote_plus

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
            checkout_url = _build_provider_search_url(
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


def _build_provider_search_url(
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

    if "sncf" in provider_key or "tgv" in provider_key or "ouigo" in provider_key:
        # SNCF Connect app search URL format.
        return (
            "https://www.sncf-connect.com/app/en-en/home/search/od"
            f"?origin={quote_plus(origin_en)}"
            f"&destination={quote_plus(destination_en)}"
            f"&outwardDate={quote_plus(departure_date)}T{quote_plus(time_value)}:00"
        )

    if "db" in provider_key or "deutsche bahn" in provider_key:
        # Bahn search format (fragment based).
        date_parts = departure_date.split("-")
        date_for_db = departure_date
        if len(date_parts) == 3:
            date_for_db = f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]}"
        return (
            "https://int.bahn.de/en/buchung/fahrplan/suche"
            f"#sts=true&so={quote_plus(origin_en)}&zo={quote_plus(destination_en)}"
            f"&kl=2&r={quote_plus(date_for_db)}"
        )

    if "flixbus" in provider_key or "flixtrain" in provider_key:
        return (
            "https://shop.flixbus.com/search"
            f"?departureCity={quote_plus(origin_en)}"
            f"&arrivalCity={quote_plus(destination_en)}"
            f"&rideDate={quote_plus(departure_date)}"
            f"&adult=1&_locale=en_US"
        )

    return _BOOKING_URLS.get(provider, _default_url(transport_type))
