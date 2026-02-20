import os
import shutil
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.expiration import is_expired
from app.core.storage import clear_all_statuses
from app.main import app
from app.models.schemas import Preferences, PrimaryGoal, RecommendationResult, TravelRequest

client = TestClient(app)

SAMPLE_RESULT = {
    "result_id": "",
    "response_id": "resp-exp-001",
    "origin": "Seoul",
    "destination": "Busan",
    "transport_type": "train",
    "provider": "KTX",
    "departure_time": "2026-03-01T08:00:00",
    "arrival_time": "2026-03-01T10:30:00",
    "duration_minutes": 150,
    "price": 59800,
    "currency": "KRW",
    "transfers": 0,
    "checkout_url": "https://example.com/checkout",
    "score_explain": "Fastest option",
}


def setup_function():
    clear_all_statuses()


def teardown_function():
    data_dir = settings.data_dir
    if os.path.isdir(data_dir):
        shutil.rmtree(data_dir)


# --- is_expired utility ---


def test_is_expired_returns_false_when_no_expires_at():
    result = RecommendationResult(**{**SAMPLE_RESULT, "expires_at": None})
    assert is_expired(result) is False


def test_is_expired_returns_false_when_not_expired():
    future = datetime.utcnow() + timedelta(hours=1)
    result = RecommendationResult(**{**SAMPLE_RESULT, "expires_at": future})
    assert is_expired(result) is False


def test_is_expired_returns_true_when_expired():
    past = datetime.utcnow() - timedelta(hours=1)
    result = RecommendationResult(**{**SAMPLE_RESULT, "expires_at": past})
    assert is_expired(result) is True


# --- Result page expiration display ---


def test_result_page_expired_shows_badge():
    expired_result = {
        **SAMPLE_RESULT,
        "expires_at": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
    }
    create_resp = client.post("/api/results", json=expired_result)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert resp.status_code == 200
    html = resp.text
    assert "만료됨" in html
    assert "다시 검색" in html
    # Checkout button should not appear
    assert "예매하기" not in html


def test_result_page_valid_does_not_show_expired_badge():
    valid_result = {
        **SAMPLE_RESULT,
        "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
    }
    create_resp = client.post("/api/results", json=valid_result)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert resp.status_code == 200
    html = resp.text
    assert "만료됨" not in html
    assert "다시 검색" not in html
    assert "예매하기" in html


def test_result_page_no_expires_at_shows_checkout():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert resp.status_code == 200
    html = resp.text
    assert "만료됨" not in html
    assert "예매하기" in html


# --- POST /api/results/{result_id}/regenerate ---


def test_regenerate_returns_200_with_response_id():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    with patch("app.routers.api.process_travel_request", new_callable=AsyncMock):
        resp = client.post(f"/api/results/{result_id}/regenerate")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "regenerating"
    assert body["response_id"] == "resp-exp-001"


def test_regenerate_not_found():
    resp = client.post("/api/results/nonexistent-id/regenerate")
    assert resp.status_code == 404


def test_regenerate_triggers_background_task():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    with patch("app.routers.api.process_travel_request", new_callable=AsyncMock) as mock_process:
        client.post(f"/api/results/{result_id}/regenerate")
        mock_process.assert_called_once()
        call_args = mock_process.call_args[0][0]
        assert call_args.origin == "Seoul"
        assert call_args.destination == "Busan"
        assert call_args.response_id == "resp-exp-001"


# --- original_request preservation ---


def test_regenerate_preserves_preferences():
    """Regenerate should use original_request preferences, not defaults."""
    original_req = TravelRequest(
        response_id="resp-exp-001",
        origin="Seoul",
        destination="Busan",
        departure_date="2026-03-01",
        departure_time="08:00",
        preferences=Preferences(
            primary_goal=PrimaryGoal.cheapest,
            avoid_night=True,
            max_transfers=1,
        ),
    )
    result_with_request = {
        **SAMPLE_RESULT,
        "original_request": original_req.model_dump(),
    }
    create_resp = client.post("/api/results", json=result_with_request)
    result_id = create_resp.json()["result_id"]

    with patch("app.routers.api.process_travel_request", new_callable=AsyncMock) as mock_process:
        client.post(f"/api/results/{result_id}/regenerate")
        mock_process.assert_called_once()
        call_args = mock_process.call_args[0][0]
        assert call_args.preferences.primary_goal == PrimaryGoal.cheapest
        assert call_args.preferences.avoid_night is True
        assert call_args.preferences.max_transfers == 1


def test_regenerate_fallback_without_original_request():
    """Regenerate should fall back to reconstructing TravelRequest when original_request is None."""
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    with patch("app.routers.api.process_travel_request", new_callable=AsyncMock) as mock_process:
        client.post(f"/api/results/{result_id}/regenerate")
        mock_process.assert_called_once()
        call_args = mock_process.call_args[0][0]
        assert call_args.origin == "Seoul"
        assert call_args.destination == "Busan"
        # Without original_request, preferences should be defaults
        assert call_args.preferences.primary_goal == PrimaryGoal.fastest
