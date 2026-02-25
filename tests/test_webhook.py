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
        {"key": "origin", "label": "Origin", "type": "INPUT_TEXT", "value": origin},
        {"key": "destination", "label": "Destination", "type": "INPUT_TEXT", "value": destination},
        {"key": "departure_date", "label": "Departure Date", "type": "INPUT_DATE", "value": departure_date},
    ]
    if departure_time is not None:
        fields.append({"key": "departure_time", "label": "Departure Time", "type": "INPUT_TEXT", "value": departure_time})
    if primary_goal is not None:
        fields.append({"key": "primary_goal", "label": "Primary Goal", "type": "INPUT_TEXT", "value": primary_goal})
    if email is not None:
        fields.append({"key": "email", "label": "Email", "type": "INPUT_EMAIL", "value": email})
    if passenger_count is not None:
        fields.append({"key": "passenger_count", "label": "Passenger Count", "type": "INPUT_NUMBER", "value": passenger_count})
    return {
        "eventId": "evt_001",
        "eventType": "FORM_RESPONSE",
        "createdAt": "2026-03-01T10:00:00Z",
        "data": {
            "responseId": response_id,
            "submissionId": "sub_001",
            "respondentId": "rsp_001",
            "formId": "form_001",
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
            if f["key"] != "origin"
        ]
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 422

    def test_missing_destination_returns_422(self):
        payload = _make_payload()
        payload["data"]["fields"] = [
            f for f in payload["data"]["fields"]
            if f["key"] != "destination"
        ]
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 422

    def test_missing_departure_date_returns_422(self):
        payload = _make_payload()
        payload["data"]["fields"] = [
            f for f in payload["data"]["fields"]
            if f["key"] != "departure_date"
        ]
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 422

    def test_empty_fields_returns_400(self):
        payload = {
            "eventId": "e1",
            "eventType": "FORM_RESPONSE",
            "createdAt": "2026-03-01T10:00:00Z",
            "data": {
                "responseId": "resp_001",
                "submissionId": "sub_001",
                "respondentId": "rsp_001",
                "formId": "form_001",
                "fields": [],
            },
        }
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 400

    def test_missing_data_returns_422(self):
        """Missing responseId in data causes a 422 from parser."""
        payload = {
            "eventId": "e1",
            "eventType": "FORM_RESPONSE",
            "createdAt": "2026-03-01T10:00:00Z",
            "data": {
                "responseId": "",
                "submissionId": "",
                "respondentId": "",
                "formId": "",
                "fields": [
                    {"key": "origin", "label": "Origin", "type": "INPUT_TEXT", "value": "서울"},
                    {"key": "destination", "label": "Destination", "type": "INPUT_TEXT", "value": "부산"},
                    {"key": "departure_date", "label": "Date", "type": "INPUT_DATE", "value": "2026-03-01"},
                ],
            },
        }
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 422

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

    def test_email_and_passenger_count_parsed(self):
        payload = _make_payload(email="user@example.com", passenger_count=2)
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200

    def test_option_value_as_dict(self):
        """Tally option-type values (dict with name) should be parsed correctly."""
        payload = _make_payload()
        # Replace origin with a dict option value
        payload["data"]["fields"][0] = {
            "key": "origin",
            "label": "Origin",
            "type": "MULTIPLE_CHOICE",
            "value": {"id": "opt_1", "name": "서울"},
        }
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


class TestTallyKeyMapping:
    """실제 Tally question key가 올바르게 매핑되는지 검증."""

    def test_tally_keys_parsed(self):
        payload = {
            "eventId": "evt_real",
            "eventType": "FORM_RESPONSE",
            "createdAt": "2026-03-01T10:00:00Z",
            "data": {
                "responseId": "resp_key_test",
                "submissionId": "sub_002",
                "respondentId": "rsp_002",
                "formId": "form_002",
                "fields": [
                    {"key": "question_nGVOax", "label": "Origin", "type": "INPUT_TEXT", "value": "Berlin"},
                    {"key": "question_mOWkbr", "label": "Destination", "type": "INPUT_TEXT", "value": "Munich"},
                    {"key": "question_3XePVe", "label": "Date", "type": "INPUT_DATE", "value": "2026-04-01"},
                    {"key": "question_wQ72Nd", "label": "Passengers", "type": "INPUT_NUMBER", "value": 2},
                    {"key": "question_3jPB7E", "label": "Email", "type": "INPUT_EMAIL", "value": "test@example.com"},
                    {"key": "question_wMEaVL", "label": "Time", "type": "INPUT_TEXT", "value": "14:00"},
                    {"key": "question_3Nbyp2", "label": "Goal", "type": "MULTIPLE_CHOICE", "value": "cheapest"},
                ],
            },
        }
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["response_id"] == "resp_key_test"

    def test_tally_keys_missing_required_field(self):
        """Tally key payload에서 필수 필드 누락 시 422 반환."""
        payload = {
            "eventId": "evt_real",
            "eventType": "FORM_RESPONSE",
            "createdAt": "2026-03-01T10:00:00Z",
            "data": {
                "responseId": "resp_key_missing",
                "submissionId": "sub_003",
                "respondentId": "rsp_003",
                "formId": "form_003",
                "fields": [
                    {"key": "question_nGVOax", "label": "Origin", "type": "INPUT_TEXT", "value": "Berlin"},
                    # destination 누락
                    {"key": "question_3XePVe", "label": "Date", "type": "INPUT_DATE", "value": "2026-04-01"},
                ],
            },
        }
        resp = client.post("/webhook/tally", json=payload)
        assert resp.status_code == 422
