import logging

from app.core.agent import run_agent
from app.core.storage import save_result, set_status
from app.models.schemas import StatusEnum, TravelRequest

logger = logging.getLogger(__name__)


async def process_travel_request(request: TravelRequest) -> None:
    """Process a travel request by running the agent (HAFAS search + scoring)."""
    response_id = request.response_id

    try:
        await set_status(response_id, StatusEnum.processing)

        result = await run_agent(request)

        saved_id = await save_result(result)
        await set_status(response_id, StatusEnum.done, result_id=saved_id)

        logger.info(
            "Processing complete: response_id=%s, result_id=%s",
            response_id,
            saved_id,
        )

    except Exception:
        logger.exception("Processing failed for response_id=%s", response_id)
        await set_status(response_id, StatusEnum.error)
