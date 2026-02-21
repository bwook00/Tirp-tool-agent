from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core.expiration import is_expired
from app.core.storage import get_latest_active_response_id, load_result

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("/wait")
async def wait_page(request: Request, ref: str | None = None):
    response_id = ref
    if not response_id:
        response_id = await get_latest_active_response_id()
    if not response_id:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"request": request, "message": "처리 중인 요청이 없습니다", "code": 404},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "waiting.html",
        {"request": request, "response_id": response_id},
    )


@router.get("/r/{result_id}")
async def result_page(request: Request, result_id: str):
    result = await load_result(result_id)
    if result is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"request": request, "message": "결과를 찾을 수 없습니다", "code": 404},
            status_code=404,
        )
    expired = is_expired(result)

    return templates.TemplateResponse(
        request,
        "result.html",
        {"request": request, "result": result, "is_expired": expired},
    )
