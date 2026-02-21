from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core.expiration import is_expired
from app.core.storage import load_result

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")


@router.get("/wait")
async def wait_page(request: Request, ref: str | None = None):
    return templates.TemplateResponse(
        request,
        "waiting.html",
        {"request": request, "response_id": ref or ""},
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
