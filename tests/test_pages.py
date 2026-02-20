import os
import shutil

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)

SAMPLE_RESULT = {
    "result_id": "",
    "response_id": "resp-page-001",
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
    "score_explain": "Fastest option with no transfers",
}


def teardown_function():
    data_dir = settings.data_dir
    if os.path.isdir(data_dir):
        shutil.rmtree(data_dir)


# --- GET /r/{result_id} ---

def test_result_page_returns_200():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_result_page_contains_origin_destination():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    html = resp.text
    assert "Seoul" in html
    assert "Busan" in html


def test_result_page_contains_provider():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert "KTX" in resp.text


def test_result_page_contains_price():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert "59,800" in resp.text


def test_result_page_contains_duration():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    html = resp.text
    assert "2" in html  # 2 hours
    assert "30" in html  # 30 minutes


def test_result_page_contains_checkout_link():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert "https://example.com/checkout" in resp.text
    assert 'target="_blank"' in resp.text


def test_result_page_contains_score_explain():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert "Fastest option with no transfers" in resp.text


def test_result_page_contains_copy_button():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert "copyLink" in resp.text


def test_result_page_not_found():
    resp = client.get("/r/nonexistent-id")
    assert resp.status_code == 404
    assert "text/html" in resp.headers["content-type"]


def test_error_page_contains_message():
    resp = client.get("/r/nonexistent-id")
    html = resp.text
    assert "404" in html
    assert "결과를 찾을 수 없습니다" in html


def test_result_page_flight_type():
    flight_result = {
        **SAMPLE_RESULT,
        "transport_type": "flight",
        "provider": "Korean Air",
        "price": 125000,
    }
    create_resp = client.post("/api/results", json=flight_result)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    html = resp.text
    assert "Korean Air" in html
    assert "flight" in html


def test_result_page_bus_type():
    bus_result = {
        **SAMPLE_RESULT,
        "transport_type": "bus",
        "provider": "Express Bus",
        "transfers": 1,
    }
    create_resp = client.post("/api/results", json=bus_result)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    html = resp.text
    assert "Express Bus" in html
    assert "1회" in html


def test_result_page_zero_transfers_shows_direct():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/r/{result_id}")
    assert "직통" in resp.text
