import logging

from app.models.schemas import TransitOption, TransportType
from app.tools.hafas_search import search_hafas

logger = logging.getLogger(__name__)


async def search_trains(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search for train options between two cities via DB transport.rest (HAFAS)."""
    try:
        all_results = await search_hafas(origin, destination, date, time)
        return [r for r in all_results if r.transport_type == TransportType.train]
    except Exception:
        logger.exception("search_trains failed")
        return []
