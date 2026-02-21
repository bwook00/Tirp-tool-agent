import logging

from app.models.schemas import TransitOption, TransportType
from app.tools.omio_search import search_omio

logger = logging.getLogger(__name__)


async def search_trains(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search for train options between two cities via Omio.

    Calls the shared Omio scraper and filters results to trains only.
    The function signature is unchanged so agent/pipeline code needs no updates.
    """
    try:
        all_results = await search_omio(origin, destination, date, time)
        return [r for r in all_results if r.transport_type == TransportType.train]
    except Exception:
        logger.exception("search_trains failed")
        return []
