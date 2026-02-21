import logging
from datetime import datetime

from app.core.scoring import score_options
from app.core.security import generate_result_id
from app.models.schemas import (
    RecommendationResult,
    TransitOption,
    TravelRequest,
)
from app.tools.bus_search import search_buses
from app.tools.checkout import get_checkout_link
from app.tools.train_search import search_trains

logger = logging.getLogger(__name__)


async def run_agent(request: TravelRequest) -> RecommendationResult:
    """Search trains + buses via HAFAS, score, and return the best option."""
    all_options: list[TransitOption] = []

    trains = await search_trains(
        origin=request.origin,
        destination=request.destination,
        date=request.departure_date,
        time=request.departure_time,
    )
    all_options.extend(trains)

    buses = await search_buses(
        origin=request.origin,
        destination=request.destination,
        date=request.departure_date,
        time=request.departure_time,
    )
    all_options.extend(buses)

    if not all_options:
        raise ValueError("검색 결과가 없습니다. 경로를 확인해 주세요.")

    # Score and rank
    scored = score_options(all_options, request.preferences)
    top = scored[0]

    # Get checkout link
    checkout = await get_checkout_link(top.option)

    expires_at = None
    if checkout.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(checkout["expires_at"])
        except (ValueError, TypeError):
            pass

    return RecommendationResult(
        result_id=generate_result_id(),
        response_id=request.response_id,
        origin=request.origin,
        destination=request.destination,
        transport_type=top.option.transport_type.value,
        provider=top.option.provider,
        departure_time=top.option.departure_time,
        arrival_time=top.option.arrival_time,
        duration_minutes=top.option.duration_minutes,
        price=top.option.price,
        currency=top.option.currency,
        transfers=top.option.transfers,
        checkout_url=checkout.get("checkout_url", ""),
        score_explain=top.score_explain,
        expires_at=expires_at,
        original_request=request,
    )
