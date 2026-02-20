import os
import shutil
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.pipeline import process_travel_request
from app.core.storage import clear_all_statuses, get_status, load_result
from app.main import app
from app.models.schemas import StatusEnum, TravelRequest

client = TestClient(app)


def _make_travel_request(
    response_id: str = "resp_pipeline_test",
    origin: str = "서울",
    destination: str = "부산",
) -> TravelRequest:
    return TravelRequest(
        response_id=response_id,
        origin=origin,
        destination=destination,
        departure_date="2026-03-01",
    )


def _make_webhook_payload(
    token: str = "resp_e2e_test",
    origin: str = "서울",
    destination: str = "부산",
    departure_date: str = "2026-03-01",
) -> dict:
    return {
        "event_id": "evt_001",
        "event_type": "form_response",
        "form_response": {
            "token": token,
            "submitted_at": "2026-03-01T10:00:00Z",
            "answers": [
                {"field": {"ref": "origin"}, "type": "text", "text": origin},
                {"field": {"ref": "destination"}, "type": "text", "text": destination},
                {"field": {"ref": "departure_date"}, "type": "date", "date": departure_date},
            ],
        },
    }


@pytest.fixture(autouse=True)
def _clean_state():
    """Clear in-memory status store and data directory between tests."""
    clear_all_statuses()
    yield
    clear_all_statuses()
    data_dir = settings.data_dir
    if os.path.isdir(data_dir):
        shutil.rmtree(data_dir)


class TestAgentProcessing:
    """Test that the pipeline processes requests via the real agent."""

    @pytest.mark.anyio
    async def test_status_transitions_to_done(self):
        request = _make_travel_request()
        await process_travel_request(request)

        status = await get_status("resp_pipeline_test")
        assert status is not None
        assert status.status == StatusEnum.done
        assert status.result_id is not None

    @pytest.mark.anyio
    async def test_result_file_created(self):
        request = _make_travel_request()
        await process_travel_request(request)

        status = await get_status("resp_pipeline_test")
        result = await load_result(status.result_id)
        assert result is not None
        assert result.origin == "서울"
        assert result.destination == "부산"
        assert result.response_id == "resp_pipeline_test"

    @pytest.mark.anyio
    async def test_result_has_valid_fields(self):
        request = _make_travel_request()
        await process_travel_request(request)

        status = await get_status("resp_pipeline_test")
        result = await load_result(status.result_id)
        assert result.transport_type in ("train", "flight", "bus")
        assert result.provider != ""
        assert result.price > 0
        assert result.currency == "KRW"
        assert result.transfers >= 0
        assert result.duration_minutes > 0
        assert result.checkout_url != ""
        assert result.score_explain != ""
        assert result.expires_at is not None

    @pytest.mark.anyio
    async def test_different_routes_produce_results(self):
        request = _make_travel_request(
            response_id="resp_route_test",
            origin="대전",
            destination="광주",
        )
        await process_travel_request(request)

        status = await get_status("resp_route_test")
        assert status.status == StatusEnum.done
        result = await load_result(status.result_id)
        assert result is not None
        assert result.origin == "대전"
        assert result.destination == "광주"


class TestErrorHandling:
    """Test that processing errors result in error status."""

    @pytest.mark.anyio
    async def test_status_set_to_error_on_failure(self):
        request = _make_travel_request(response_id="resp_error_test")

        with patch("app.core.pipeline.run_agent", new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = RuntimeError("Simulated failure")
            await process_travel_request(request)

        status = await get_status("resp_error_test")
        assert status is not None
        assert status.status == StatusEnum.error

    @pytest.mark.anyio
    async def test_status_processing_before_error(self):
        """Verify status goes through processing before error."""
        request = _make_travel_request(response_id="resp_proc_err")
        statuses_seen: list[StatusEnum] = []

        from app.core import storage as storage_mod

        original_set_status = storage_mod.set_status

        async def tracking_set_status(response_id, status, **kwargs):
            statuses_seen.append(status)
            return await original_set_status(response_id, status, **kwargs)

        with patch("app.core.pipeline.run_agent", new_callable=AsyncMock) as mock_agent:
            mock_agent.side_effect = RuntimeError("Simulated failure")
            with patch("app.core.pipeline.set_status", side_effect=tracking_set_status):
                await process_travel_request(request)

        assert StatusEnum.processing in statuses_seen
        assert StatusEnum.error in statuses_seen


class TestWebhookTriggersBackground:
    """Test that the webhook endpoint triggers background processing."""

    def test_webhook_returns_200_and_triggers_processing(self):
        """Webhook should return 200 immediately; background task runs after."""
        payload = _make_webhook_payload(token="resp_bg_test")
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200
        assert resp.json()["response_id"] == "resp_bg_test"

    def test_webhook_background_task_completes(self):
        """After webhook + background task, status should be done."""
        payload = _make_webhook_payload(token="resp_bg_done")
        # TestClient runs background tasks synchronously
        resp = client.post("/webhook/typeform", json=payload)
        assert resp.status_code == 200

        # TestClient executes BackgroundTasks synchronously, so status should be done
        status_resp = client.get("/api/status/resp_bg_done")
        assert status_resp.status_code == 200
        body = status_resp.json()
        assert body["status"] == "done"
        assert body["result_id"] is not None


class TestFullE2EFlow:
    """Test the complete flow: webhook -> status polling -> result retrieval."""

    def test_full_flow_webhook_to_result(self):
        """End-to-end: webhook -> status done -> result available."""
        token = "resp_e2e_full"
        payload = _make_webhook_payload(token=token)

        # Step 1: Webhook receives payload
        webhook_resp = client.post("/webhook/typeform", json=payload)
        assert webhook_resp.status_code == 200

        # Step 2: Poll status (TestClient runs background tasks synchronously)
        status_resp = client.get(f"/api/status/{token}")
        assert status_resp.status_code == 200
        status_body = status_resp.json()
        assert status_body["status"] == "done"

        result_id = status_body["result_id"]
        assert result_id is not None

        # Step 3: Fetch the result
        result_resp = client.get(f"/api/results/{result_id}")
        assert result_resp.status_code == 200
        result_body = result_resp.json()
        assert result_body["origin"] == "서울"
        assert result_body["destination"] == "부산"
        assert result_body["response_id"] == token
        assert result_body["transport_type"] in ("train", "flight", "bus")
        assert result_body["result_id"] == result_id
