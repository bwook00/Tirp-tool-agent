import asyncio
import os
import shutil

from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.storage import clear_all_statuses, set_status
from app.main import app

client = TestClient(app)


def setup_function():
    clear_all_statuses()


def teardown_function():
    data_dir = settings.data_dir
    if os.path.isdir(data_dir):
        shutil.rmtree(data_dir)


def test_wait_with_ref_returns_200():
    response = client.get("/wait", params={"ref": "abc123"})
    assert response.status_code == 200
    assert "abc123" in response.text
    assert "처리 중" in response.text


def test_wait_without_ref_no_active_returns_404():
    response = client.get("/wait")
    assert response.status_code == 404
    assert "처리 중인 요청이 없습니다" in response.text


def test_wait_without_ref_finds_active_request():
    asyncio.run(set_status("auto-found-123", status="processing"))
    response = client.get("/wait")
    assert response.status_code == 200
    assert "auto-found-123" in response.text


def test_wait_without_ref_picks_latest_active():
    asyncio.run(set_status("old-req", status="pending"))
    asyncio.run(set_status("new-req", status="processing"))
    response = client.get("/wait")
    assert response.status_code == 200
    assert "new-req" in response.text


def test_wait_without_ref_ignores_done_status():
    asyncio.run(set_status("done-req", status="done", result_id="some-result"))
    response = client.get("/wait")
    assert response.status_code == 404


def test_wait_page_includes_poll_script():
    response = client.get("/wait", params={"ref": "test-id"})
    assert response.status_code == 200
    assert "/static/js/poll.js" in response.text
    assert 'data-response-id="test-id"' in response.text


def test_wait_page_has_spinner():
    response = client.get("/wait", params={"ref": "test-id"})
    assert response.status_code == 200
    assert 'id="spinner"' in response.text


def test_wait_page_has_status_elements():
    response = client.get("/wait", params={"ref": "test-id"})
    body = response.text
    assert 'id="wait-status"' in body
    assert 'id="wait-error"' in body
    assert 'id="wait-title"' in body
