from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.core.pipeline import process_travel_request
from app.core.storage import get_latest_active_response_id, get_status, load_result, save_result
from app.models.schemas import RecommendationResult, TravelRequest

router = APIRouter(prefix="/api", tags=["api"])


@router.post("/results", status_code=201)
async def create_result(result: RecommendationResult) -> dict[str, str]:
    result_id = await save_result(result)
    return {"result_id": result_id}


@router.get("/results/{result_id}")
async def get_result(result_id: str) -> RecommendationResult:
    result = await load_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


@router.get("/status/latest")
async def get_latest_status():
    response_id = await get_latest_active_response_id()
    if response_id is None:
        raise HTTPException(status_code=404, detail="No active request found")
    status = await get_status(response_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Status not found")
    return status


@router.get("/status/{response_id}")
async def get_processing_status(response_id: str):
    status = await get_status(response_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Status not found")
    return status


@router.post("/results/{result_id}/regenerate")
async def regenerate_result(result_id: str, background_tasks: BackgroundTasks):
    result = await load_result(result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")

    if result.original_request:
        travel_request = result.original_request
    else:
        # Fallback for old results without stored request
        travel_request = TravelRequest(
            response_id=result.response_id,
            origin=result.origin,
            destination=result.destination,
            departure_date=result.departure_time.strftime("%Y-%m-%d"),
            departure_time=result.departure_time.strftime("%H:%M"),
        )

    background_tasks.add_task(process_travel_request, travel_request)

    return {"status": "regenerating", "response_id": travel_request.response_id}
