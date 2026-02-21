import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from app.core.storage import get_status, clear_all_statuses
from app.main import app

client = TestClient(app)


def _make_payload(
    token: str = "resp_abc123",
    origin: str = "서울",
    destination: str = "부산",
    departure_date: str = "2026-03-01",
    departure_time: str | None = None,
    primary_goal: str | None = None,
    email: str | None = None,
    passenger_count: int | None = None,
) -> dict:
    answers = [
        {"field": {"ref": "origin"}, "type": "text", "text": origin},
        {"field": {"ref": "destination"}, "type": "text", "text": destination},
        {"field": {"ref": "departure_date"}, "type": "date", "date": departure_date},
    ]
    if departure_time is not None:
        answers.append({"field": {"ref": "departure_time"}, "type": "text", "text": departure_time})
    if primary_goal is not None:
        answers.append({"field": {"ref": "primary_goal"}, "type": "text", "text": primary_goal})
    if email is not None:
        answers.append({"field": {"ref": "email"}, "type": "email", "email": email})
    if passenger_count is not None:
        answers.append({"field": {"ref": "passenger_count"}, "type": "number", "number": passenger_count})
    return {
        "event_id": "evt_001",
        "event_type": "form_response",
        "form_response": {
            "token": token,
            "submitted_at": "2026-03-01T10:00:00Z",
            "answers": answers,
        },
    }


@pytest.fixture(autouse=True)
def _clear_status_store():
    """Clear the in-memory status store between tests."""
    clear_all_statuses()
    yield
    clear_all_statuses()


class TestTypeformWebhook:

    def test_valid_payload_returns_200(self):
        payload = _make_payload()
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["response_id"] == "resp_abc123"

    @pytest.mark.anyio
    async def test_status_stored_after_webhook(self):
        """After webhook + background processing, status should be done."""
        payload = _make_payload(token="resp_status_test")
        client.post("/webhook/typeform", json=payload)
        status = await get_status("resp_status_test")
        assert status is not None
        # TestClient runs BackgroundTasks synchronously, so pipeline completes
        assert status.status.value == "done"

    def test_missing_origin_returns_422(self):
        payload = _make_payload()
        # Remove origin answer
        payload["form_response"]["answers"] = [
            a for a in payload["form_response"]["answers"]
            if a["field"]["ref"] != "origin"
        ]
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 422

    def test_missing_destination_returns_422(self):
        payload = _make_payload()
        payload["form_response"]["answers"] = [
            a for a in payload["form_response"]["answers"]
            if a["field"]["ref"] != "destination"
        ]
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 422

    def test_missing_departure_date_returns_422(self):
        payload = _make_payload()
        payload["form_response"]["answers"] = [
            a for a in payload["form_response"]["answers"]
            if a["field"]["ref"] != "departure_date"
        ]
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 422

    def test_empty_form_response_returns_400(self):
        payload = {"event_id": "e1", "event_type": "form_response", "form_response": {}}
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 400

    def test_missing_form_response_returns_400(self):
        payload = {"event_id": "e1", "event_type": "form_response"}
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 400

    def test_invalid_json_returns_400(self):
        resp = client.post(
            "/webhook/typeform",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_optional_departure_time_parsed(self):
        payload = _make_payload(departure_time="14:00")
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200

    def test_optional_primary_goal_parsed(self):
        payload = _make_payload(primary_goal="cheapest")
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200

    def test_email_parsed(self):
        payload = _make_payload(email="user@example.com")
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200

    def test_passenger_count_parsed(self):
        payload = _make_payload(passenger_count=3)
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200

    def test_email_and_passenger_count_parsed(self):
        payload = _make_payload(email="user@example.com", passenger_count=2)
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200

    def test_choice_type_answer(self):
        """Typeform choice-type answers should be parsed correctly."""
        payload = _make_payload()
        # Replace origin with a choice-type answer
        payload["form_response"]["answers"][0] = {
            "field": {"ref": "origin"},
            "type": "choice",
            "choice": {"label": "서울"},
        }
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200


class TestHmacSignature:

    def _sign(self, body: bytes, secret: str) -> str:
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def test_valid_signature_accepted(self, monkeypatch):
        monkeypatch.setattr("app.routers.webhook.settings.typeform_secret", "test-secret")
        payload = _make_payload()
        import json
        body = json.dumps(payload).encode()
        sig = self._sign(body, "test-secret")
        resp = client.post(
            "/webhook/typeform",
            content=body,
            headers={"Content-Type": "application/json", "Typeform-Signature": sig},
        )
        assert resp.status_code == 200

    def test_invalid_signature_rejected(self, monkeypatch):
        monkeypatch.setattr("app.routers.webhook.settings.typeform_secret", "test-secret")
        payload = _make_payload()
        import json
        body = json.dumps(payload).encode()
        resp = client.post(
            "/webhook/typeform",
            content=body,
            headers={"Content-Type": "application/json", "Typeform-Signature": "sha256=invalid"},
        )
        assert resp.status_code == 403

    def test_missing_signature_rejected(self, monkeypatch):
        monkeypatch.setattr("app.routers.webhook.settings.typeform_secret", "test-secret")
        payload = _make_payload()
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 403

    def test_no_secret_skips_verification(self, monkeypatch):
        monkeypatch.setattr("app.routers.webhook.settings.typeform_secret", "")
        payload = _make_payload()
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200


class TestRealTypeformUuidRefs:
    """실제 Typeform UUID ref가 올바르게 매핑되는지 검증."""

    def test_uuid_refs_parsed(self):
        payload = {
            "event_id": "evt_real",
            "event_type": "form_response",
            "form_response": {
                "token": "resp_uuid_test",
                "submitted_at": "2026-03-01T10:00:00Z",
                "answers": [
                    {"field": {"ref": "266b4321-10e3-41c7-b57a-3e4580e0d2ee"}, "type": "text", "text": "Berlin"},
                    {"field": {"ref": "7b71eb98-4948-4512-a163-81990eb0ae27"}, "type": "text", "text": "Munich"},
                    {"field": {"ref": "f6450ff4-84de-42fe-b6be-d6939d607460"}, "type": "date", "date": "2026-04-01"},
                    {"field": {"ref": "9cd84c38-78f8-4657-bfd8-e8c96be31b08"}, "type": "number", "number": 2},
                    {"field": {"ref": "caf55741-e5f8-4a2d-a853-27e7daa940e3"}, "type": "email", "email": "test@example.com"},
                    {"field": {"ref": "9d20f008-2eef-45b6-8b1a-f2f47edc7520"}, "type": "text", "text": "14:00"},
                    {"field": {"ref": "d978dc48-4477-40f5-974c-b326625d783b"}, "type": "choice", "choice": {"label": "cheapest"}},
                ],
            },
        }
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["response_id"] == "resp_uuid_test"

    def test_uuid_refs_missing_required_field(self):
        """UUID ref payload에서 필수 필드 누락 시 422 반환."""
        payload = {
            "event_id": "evt_real",
            "event_type": "form_response",
            "form_response": {
                "token": "resp_uuid_missing",
                "submitted_at": "2026-03-01T10:00:00Z",
                "answers": [
                    {"field": {"ref": "266b4321-10e3-41c7-b57a-3e4580e0d2ee"}, "type": "text", "text": "Berlin"},
                    # destination 누락
                    {"field": {"ref": "f6450ff4-84de-42fe-b6be-d6939d607460"}, "type": "date", "date": "2026-04-01"},
                ],
            },
        }
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 422
