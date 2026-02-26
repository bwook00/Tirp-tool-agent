from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.tools import hafas_search


def _response(status_code: int, body: dict | list | None = None) -> httpx.Response:
    req = httpx.Request("GET", "https://example.test")
    return httpx.Response(status_code=status_code, json=body, request=req)


class _FakeClient:
    def __init__(self, responses: list[httpx.Response]):
        self._responses = responses
        self.calls = 0

    async def get(self, url: str, params: dict):  # noqa: ARG002
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


@pytest.mark.asyncio
async def test_resolve_location_uses_profile_db():
    fake_resp = _response(
        200,
        [{"id": "8011160", "name": "Berlin Hbf"}],
    )
    fake_get = AsyncMock(return_value=fake_resp)

    with patch("app.tools.hafas_search._get_with_retries", fake_get):
        with patch("app.tools.hafas_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            station_id = await hafas_search._resolve_location("Berlin")

    assert station_id == "8011160"
    _, kwargs = fake_get.call_args
    assert kwargs["params"]["profile"] == "db"


@pytest.mark.asyncio
async def test_fetch_journeys_uses_profile_db():
    fake_resp = _response(200, {"journeys": []})
    fake_get = AsyncMock(return_value=fake_resp)

    with patch("app.tools.hafas_search._get_with_retries", fake_get):
        with patch("app.tools.hafas_search.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            result = await hafas_search._fetch_journeys("8011160", "8000261", "2026-03-15T10:00")

    assert result == []
    _, kwargs = fake_get.call_args
    assert kwargs["params"]["profile"] == "db"


@pytest.mark.asyncio
async def test_get_with_retries_retries_503_then_succeeds():
    client = _FakeClient([_response(503), _response(200, {"ok": True})])

    with patch("app.tools.hafas_search.asyncio.sleep", AsyncMock()):
        resp = await hafas_search._get_with_retries(client, "https://example.test", {"q": "x"})

    assert resp.status_code == 200
    assert client.calls == 2


@pytest.mark.asyncio
async def test_get_with_retries_raises_after_exhausting_retries():
    client = _FakeClient([_response(503), _response(503), _response(503)])

    with patch("app.tools.hafas_search.asyncio.sleep", AsyncMock()):
        with pytest.raises(httpx.HTTPStatusError):
            await hafas_search._get_with_retries(client, "https://example.test", {"q": "x"})

