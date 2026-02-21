import logging

from app.models.schemas import TransitOption, TransportType
from app.tools.hafas_search import search_hafas
from app.tools.omio_search import search_omio

logger = logging.getLogger(__name__)


async def search_buses(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search for bus options between two cities.

    Tries Omio first, falls back to DB transport.rest (HAFAS) API.
    """
    # 1) Try Omio
    try:
        all_results = await search_omio(origin, destination, date, time)
        buses = [r for r in all_results if r.transport_type == TransportType.bus]
        if buses:
            return buses
    except Exception:
        logger.info("Omio search_buses failed, trying HAFAS")

    # 2) Fallback: HAFAS (DB transport.rest)
    try:
        all_results = await search_hafas(origin, destination, date, time)
        buses = [r for r in all_results if r.transport_type == TransportType.bus]
        if buses:
            logger.info("HAFAS returned %d bus results", len(buses))
            return buses
    except Exception:
        logger.exception("HAFAS search_buses also failed")

    return []
