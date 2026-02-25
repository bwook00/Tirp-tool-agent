import base64
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from app.core.config import settings
from app.core.pipeline import process_travel_request
from app.core.storage import set_status
from app.core.tally import parse_travel_request
from app.models.schemas import StatusEnum, TallyWebhookPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhook"])


def _verify_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Verify Tally HMAC-SHA256 webhook signature (base64-encoded)."""
    computed = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).digest()
    expected = base64.b64encode(computed).decode("utf-8")
    return hmac.compare_digest(expected, signature)


@router.post("/tally", status_code=200)
async def receive_tally_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    tally_signature: str | None = Header(None, alias="Tally-Signature"),
) -> dict[str, str]:
    """Receive a Tally webhook, parse it, and store initial pending status."""
    raw_body = await request.body()

    # Verify HMAC signature when a signing secret is configured
    if settings.tally_signing_secret:
        if not tally_signature:
            raise HTTPException(status_code=403, detail="Missing webhook signature")
        if not _verify_signature(raw_body, tally_signature, settings.tally_signing_secret):
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # Parse JSON body
    try:
        payload_json = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        payload = TallyWebhookPayload(**payload_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Payload does not match expected schema")

    if not payload.data.fields:
        raise HTTPException(status_code=400, detail="Missing fields in payload data")

    # Extract TravelRequest from submission data
    try:
        travel_request = parse_travel_request(payload.data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    response_id = travel_request.response_id
    logger.info("Received Tally webhook for response_id=%s", response_id)

    # Store initial pending status
    await set_status(response_id, StatusEnum.pending)

    # Trigger background processing pipeline
    background_tasks.add_task(process_travel_request, travel_request)

    return {"status": "ok", "response_id": response_id}
