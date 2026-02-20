import hashlib
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.core.config import settings
from app.core.pipeline import process_travel_request
from app.core.storage import set_status
from app.core.typeform import parse_travel_request
from app.models.schemas import StatusEnum, TypeformWebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _verify_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Verify Typeform HMAC-SHA256 webhook signature."""
    digest = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    expected = f"sha256={digest}"
    return hmac.compare_digest(expected, signature)


@router.post("/typeform", status_code=200)
async def receive_typeform_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_typeform_signature: str | None = Header(None, alias="Typeform-Signature"),
) -> dict[str, str]:
    """Receive a Typeform webhook, parse it, and store initial pending status."""
    raw_body = await request.body()

    # Verify HMAC signature when a secret is configured
    if settings.typeform_secret:
        if not x_typeform_signature:
            raise HTTPException(status_code=403, detail="Missing webhook signature")
        if not _verify_signature(raw_body, x_typeform_signature, settings.typeform_secret):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # Parse JSON body
    try:
        payload_json = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        payload = TypeformWebhookPayload(**payload_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Payload does not match expected schema")

    if not payload.form_response:
        raise HTTPException(status_code=400, detail="Missing form_response in payload")

    # Extract TravelRequest from form_response
    try:
        travel_request = parse_travel_request(payload.form_response)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    response_id = travel_request.response_id
    logger.info("Received Typeform webhook for response_id=%s", response_id)

    # Store initial pending status
    await set_status(response_id, StatusEnum.pending)

    # Trigger background processing pipeline
    background_tasks.add_task(process_travel_request, travel_request)

    return {"status": "ok", "response_id": response_id}
