import logging

from app.models.schemas import TransitOption, TransportType
from app.tools.omio_search import search_omio

logger = logging.getLogger(__name__)


async def search_buses(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search for bus options between two cities via Omio.

    Calls the shared Omio scraper and filters results to buses only.
    The function signature is unchanged so agent/pipeline code needs no updates.
    """
    try:
        all_results = await search_omio(origin, destination, date, time)
        return [r for r in all_results if r.transport_type == TransportType.bus]
    except Exception:
        logger.exception("search_buses failed")
        return []
