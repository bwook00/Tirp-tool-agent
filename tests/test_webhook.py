import base64
import hashlib
import hmac
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.storage import get_status, clear_all_statuses
from app.main import app
from app.models.schemas import TransitOption, TransportType

client = TestClient(app)


def _make_payload(
    response_id: str = "resp_abc123",
    origin: str = "서울",
    destination: str = "부산",
    departure_date: str = "2026-03-01",
    departure_time: str | None = None,
    primary_goal: str | None = None,
    email: str | None = None,
    passenger_count: int | None = None,
) -> dict:
    fields = [
        {"key": "q_origin", "label": "출발지", "type": "INPUT_TEXT", "value": origin},
        {"key": "q_dest", "label": "도착지", "type": "INPUT_TEXT", "value": destination},
        {"key": "q_date", "label": "출발 날짜", "type": "INPUT_DATE", "value": departure_date},
    ]
    if departure_time is not None:
        fields.append({"key": "q_time", "label": "출발 시간", "type": "INPUT_TIME", "value": departure_time})
    if primary_goal is not None:
        fields.append({"key": "q_goal", "label": "우선순위", "type": "INPUT_TEXT", "value": primary_goal})
    if email is not None:
        fields.append({"key": "q_email", "label": "이메일", "type": "INPUT_EMAIL", "value": email})
    if passenger_count is not None:
        fields.append({"key": "q_pax", "label": "승객 수", "type": "INPUT_NUMBER", "value": passenger_count})
    return {
        "eventId": "evt_001",
        "eventType": "FORM_RESPONSE",
        "createdAt": "2026-03-01T10:00:00.000Z",
        "data": {
            "responseId": response_id,
            "submissionId": response_id,
            "respondentId": "respondent_001",
            "formId": "form_001",
            "formName": "Travel Survey",
            "createdAt": "2026-03-01T10:00:00.000Z",
            "fields": fields,
        },
    }


def _mock_train_results(**kwargs):
    return [TransitOption(
        transport_type=TransportType.train, provider="DB",
        departure_time=datetime(2026, 3, 1, 10, 0),
        arrival_time=datetime(2026, 3, 1, 14, 0),
        duration_minutes=240, price=29.0, currency="EUR",
    )]


def _mock_bus_results(**kwargs):
    return [TransitOption(
        transport_type=TransportType.bus, provider="FlixBus",
        departure_time=datetime(2026, 3, 1, 8, 0),
        arrival_time=datetime(2026, 3, 1, 14, 30),
        duration_minutes=390, price=19.0, currency="EUR",
    )]


@pytest.fixture(autouse=True)
def _clear_status_store():
    """Clear the in-memory status store and mock search tools between tests."""
    clear_all_statuses()
    with patch("app.core.agent.search_trains", new_callable=AsyncMock, side_effect=_mock_train_results), \
         patch("app.core.agent.search_buses", new_callable=AsyncMock, side_effect=_mock_bus_results):
        yield
    clear_all_statuses()


class TestTallyWebhook:

    def test_valid_payload_returns_200(self):
        payload = _make_payload()
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["response_id"] == "resp_abc123"

    @pytest.mark.anyio
    async def test_status_stored_after_webhook(self):
        """After webhook + background processing, status should be done."""
        payload = _make_payload(response_id="resp_status_test")
        client.post("/webhook/tally", json=payload)
        status = await get_status("resp_status_test")
        assert status is not None
        # TestClient runs BackgroundTasks synchronously, so pipeline completes
        assert status.status.value == "done"

    def test_missing_origin_returns_422(self):
        payload = _make_payload()
        payload["data"]["fields"] = [
            f for f in payload["data"]["fields"]
            if f["label"] != "출발지"
        ]
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 422

    def test_missing_destination_returns_422(self):
        payload = _make_payload()
        payload["data"]["fields"] = [
            f for f in payload["data"]["fields"]
            if f["label"] != "도착지"
        ]
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 422

    def test_missing_departure_date_returns_422(self):
        payload = _make_payload()
        payload["data"]["fields"] = [
            f for f in payload["data"]["fields"]
            if f["label"] != "출발 날짜"
        ]
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 422

    def test_empty_data_returns_400(self):
        payload = {"eventId": "e1", "eventType": "FORM_RESPONSE", "data": {}}
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 400

    def test_missing_data_returns_400(self):
        payload = {"eventId": "e1", "eventType": "FORM_RESPONSE"}
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 400

    def test_invalid_json_returns_400(self):
        resp = client.post(
            "/webhook/tally",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_optional_departure_time_parsed(self):
        payload = _make_payload(departure_time="14:00")
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200

    def test_optional_primary_goal_parsed(self):
        payload = _make_payload(primary_goal="cheapest")
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200

    def test_email_parsed(self):
        payload = _make_payload(email="user@example.com")
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200

    def test_passenger_count_parsed(self):
        payload = _make_payload(passenger_count=3)
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200

    def test_dropdown_choice_with_options(self):
        """Tally dropdown/choice fields return UUID list + options array."""
        payload = _make_payload()
        payload["data"]["fields"].append({
            "key": "q_goal",
            "label": "우선순위",
            "type": "MULTIPLE_CHOICE",
            "value": ["opt-uuid-1"],
            "options": [
                {"id": "opt-uuid-1", "text": "cheapest"},
                {"id": "opt-uuid-2", "text": "fastest"},
            ],
        })
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200


class TestTallyHmacSignature:

    def _sign(self, body: bytes, secret: str) -> str:
        digest = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        return base64.b64encode(digest).decode()

    def test_valid_signature_accepted(self, monkeypatch):
        monkeypatch.setattr("app.routers.webhook.settings.tally_signing_secret", "test-secret")
        payload = _make_payload()
        body = json.dumps(payload).encode()
        sig = self._sign(body, "test-secret")
        resp = client.post(
            "/webhook/tally",
            content=body,
            headers={"Content-Type": "application/json", "Tally-Signature": sig},
        )
        assert resp.status_code == 200

    def test_invalid_signature_rejected(self, monkeypatch):
        monkeypatch.setattr("app.routers.webhook.settings.tally_signing_secret", "test-secret")
        payload = _make_payload()
        body = json.dumps(payload).encode()
        resp = client.post(
            "/webhook/tally",
            content=body,
            headers={"Content-Type": "application/json", "Tally-Signature": "invalid-sig"},
        )
        assert resp.status_code == 403

    def test_missing_signature_rejected(self, monkeypatch):
        monkeypatch.setattr("app.routers.webhook.settings.tally_signing_secret", "test-secret")
        payload = _make_payload()
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 403

    def test_no_secret_skips_verification(self, monkeypatch):
        monkeypatch.setattr("app.routers.webhook.settings.tally_signing_secret", "")
        payload = _make_payload()
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200
