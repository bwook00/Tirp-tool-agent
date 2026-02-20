import os
import shutil
from datetime import datetime

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.storage import clear_all_statuses
from app.main import app

client = TestClient(app)

SAMPLE_RESULT = {
    "result_id": "",
    "response_id": "resp-001",
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


def setup_function():
    clear_all_statuses()


def teardown_function():
    data_dir = settings.data_dir
    if os.path.isdir(data_dir):
        shutil.rmtree(data_dir)


# --- POST /api/results ---

def test_create_result_returns_201():
    resp = client.post("/api/results", json=SAMPLE_RESULT)
    assert resp.status_code == 201
    body = resp.json()
    assert "result_id" in body
    assert len(body["result_id"]) > 0


def test_create_result_writes_json_file():
    resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = resp.json()["result_id"]
    path = os.path.join(settings.data_dir, f"{result_id}.json")
    assert os.path.isfile(path)


# --- GET /api/results/{result_id} ---

def test_get_result_returns_saved_data():
    create_resp = client.post("/api/results", json=SAMPLE_RESULT)
    result_id = create_resp.json()["result_id"]

    resp = client.get(f"/api/results/{result_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["result_id"] == result_id
    assert body["origin"] == "Seoul"
    assert body["destination"] == "Busan"
    assert body["transport_type"] == "train"
    assert body["price"] == 59800


def test_get_result_not_found():
    resp = client.get("/api/results/nonexistent-id")
    assert resp.status_code == 404


# --- GET /api/status/{response_id} ---

def test_status_not_found():
    resp = client.get("/api/status/unknown-response")
    assert resp.status_code == 404


def test_status_after_set():
    from app.core.storage import set_status
    import asyncio

    asyncio.run(set_status("resp-100", status="pending"))
    resp = client.get("/api/status/resp-100")
    assert resp.status_code == 200
    body = resp.json()
    assert body["response_id"] == "resp-100"
    assert body["status"] == "pending"
    assert body["result_id"] is None


def test_status_done_with_result_id():
    from app.core.storage import set_status
    import asyncio

    asyncio.run(set_status("resp-200", status="done", result_id="some-result-id"))
    resp = client.get("/api/status/resp-200")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["result_id"] == "some-result-id"


# --- Directory auto-creation ---

def test_data_dir_auto_created():
    data_dir = settings.data_dir
    if os.path.isdir(data_dir):
        shutil.rmtree(data_dir)
    assert not os.path.isdir(data_dir)

    client.post("/api/results", json=SAMPLE_RESULT)
    assert os.path.isdir(data_dir)
