from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_wait_with_ref_returns_200():
    response = client.get("/wait", params={"ref": "abc123"})
    assert response.status_code == 200
    assert "abc123" in response.text
    assert "처리 중" in response.text


def test_wait_without_ref_returns_400():
    response = client.get("/wait")
    assert response.status_code == 400
    assert "response_id가 필요합니다" in response.text


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
