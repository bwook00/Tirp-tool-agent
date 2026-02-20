import logging

from app.core.agent import run_agent
from app.core.config import settings
from app.core.storage import save_result, set_status
from app.models.schemas import StatusEnum, TravelRequest

logger = logging.getLogger(__name__)


async def process_travel_request(request: TravelRequest) -> None:
    """Process a travel request by running Omio automation or the LLM agent."""
    response_id = request.response_id

    try:
        await set_status(response_id, StatusEnum.processing)

        result = None

        # Omio automation (when enabled and email is provided)
        if settings.omio_enabled and request.email:
            try:
                from app.automation.omio import book_omio
                from app.models.passenger import load_passengers

                passengers = load_passengers()
                result = await book_omio(
                    request, passengers[: request.passenger_count]
                )
            except Exception:
                logger.exception(
                    "Omio automation failed, falling back to agent"
                )

        # Fallback: LLM agent + mock tools
        if result is None:
            result = await run_agent(request)

        # Save result (generates result_id internally)
        saved_id = await save_result(result)

        # Update status to done
        await set_status(response_id, StatusEnum.done, result_id=saved_id)

        logger.info(
            "Processing complete: response_id=%s, result_id=%s",
            response_id,
            saved_id,
        )

    except Exception:
        logger.exception("Processing failed for response_id=%s", response_id)
        await set_status(response_id, StatusEnum.error)
