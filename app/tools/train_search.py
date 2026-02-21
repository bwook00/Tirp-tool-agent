import logging

from app.models.schemas import TransitOption, TransportType
from app.tools.hafas_search import search_hafas
from app.tools.omio_search import search_omio

logger = logging.getLogger(__name__)


async def search_trains(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search for train options between two cities.

    Tries Omio first, falls back to DB transport.rest (HAFAS) API.
    """
    # 1) Try Omio
    try:
        all_results = await search_omio(origin, destination, date, time)
        trains = [r for r in all_results if r.transport_type == TransportType.train]
        if trains:
            return trains
    except Exception:
        logger.info("Omio search_trains failed, trying HAFAS")

    # 2) Fallback: HAFAS (DB transport.rest)
    try:
        all_results = await search_hafas(origin, destination, date, time)
        trains = [r for r in all_results if r.transport_type == TransportType.train]
        if trains:
            logger.info("HAFAS returned %d train results", len(trains))
            return trains
    except Exception:
        logger.exception("HAFAS search_trains also failed")

    return []
