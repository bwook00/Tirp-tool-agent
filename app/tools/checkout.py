import logging
import uuid
from datetime import datetime, timedelta
from urllib.parse import quote

from app.models.schemas import TransitOption, TransportType

logger = logging.getLogger(__name__)

_BOOKING_URLS: dict[str, str] = {
    # European train operators
    "Deutsche Bahn": "https://www.bahn.de/buchung/start",
    "DB": "https://www.bahn.de/buchung/start",
    "ICE": "https://www.bahn.de/buchung/start",
    "SNCF": "https://www.sncf-connect.com/en-en/train-booking",
    "TGV": "https://www.sncf-connect.com/en-en/train-booking",
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


async def get_checkout_link(option: TransitOption) -> dict:
    """Generate a checkout/booking link for the given transit option.

    If the option's `details` field contains a deep link (from the API),
    use it directly.  Otherwise construct a booking URL from the provider.

    Returns a dict with:
        - checkout_url: a booking URL for the provider
        - expires_at: ISO-format datetime string, 30 minutes from now
    """
    try:
        # Prefer deep link from Omio API
        if option.details and option.details.startswith("http"):
            checkout_url = option.details
        else:
            base_url = _BOOKING_URLS.get(
                option.provider,
                _default_url(option.transport_type),
            )
            booking_ref = uuid.uuid4().hex[:12]
            dep_str = option.departure_time.strftime("%Y%m%dT%H%M")
            checkout_url = f"{base_url}?ref={booking_ref}&dep={quote(dep_str)}"

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
