"""Tests for Omio automation.

Unit tests run without a browser. E2E tests (marked @pytest.mark.omio) require Playwright.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.passenger import PassengerInfo
from app.models.schemas import PrimaryGoal, Preferences, TravelRequest


def _make_passenger(**overrides) -> PassengerInfo:
    defaults = {
        "first_name": "길동",
        "last_name": "홍",
        "date_of_birth": "1990-01-15",
        "email": "gildong@example.com",
        "phone": "+82-10-1234-5678",
        "passport_number": "M12345678",
        "nationality": "KR",
    }
    defaults.update(overrides)
    return PassengerInfo(**defaults)


def _make_request(**overrides) -> TravelRequest:
    defaults = {
        "response_id": "resp_omio_test",
        "origin": "Berlin",
        "destination": "Munich",
        "departure_date": "2026-03-15",
        "email": "test@example.com",
        "passenger_count": 1,
    }
    defaults.update(overrides)
    return TravelRequest(**defaults)


class TestMinDepartureTime:

    def test_future_date_returns_start_of_day(self):
        from app.automation.omio import _min_departure_time

        future = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
        result = _min_departure_time(future)
        assert result.hour == 0
        assert result.minute == 0

    def test_today_returns_now_plus_buffer(self):
        from app.automation.omio import _min_departure_time, _BUFFER_HOURS

        today = datetime.now().strftime("%Y-%m-%d")
        result = _min_departure_time(today)
        expected_min = datetime.now() + timedelta(hours=_BUFFER_HOURS) - timedelta(seconds=5)
        assert result >= expected_min


class TestBookOmioValidation:

    @pytest.mark.anyio
    async def test_empty_passengers_raises(self):
        from app.automation.omio import book_omio

        request = _make_request()
        with pytest.raises(ValueError, match="At least one passenger"):
            await book_omio(request, [])


class TestPipelineOmioFallback:
    """Test that pipeline falls back to agent when Omio fails."""

    @pytest.mark.anyio
    async def test_omio_failure_falls_back_to_agent(self, monkeypatch):
        """When Omio automation fails, pipeline should use the existing agent."""
        monkeypatch.setattr("app.core.pipeline.settings.omio_enabled", True)

        request = _make_request(response_id="resp_fallback_test")

        with patch("app.core.pipeline.set_status", new_callable=AsyncMock) as mock_status, \
             patch("app.core.pipeline.save_result", new_callable=AsyncMock, return_value="res_123") as mock_save, \
             patch("app.automation.omio.book_omio", new_callable=AsyncMock, side_effect=RuntimeError("Omio down")), \
             patch("app.core.pipeline.run_agent", new_callable=AsyncMock) as mock_agent:

            from app.models.schemas import RecommendationResult
            mock_agent.return_value = RecommendationResult(
                result_id="res_123",
                origin="Berlin",
                destination="Munich",
                transport_type="train",
                departure_time=datetime.now(),
                arrival_time=datetime.now(),
                duration_minutes=240,
                price=50.0,
            )

            from app.core.pipeline import process_travel_request
            await process_travel_request(request)

            mock_agent.assert_called_once()

    @pytest.mark.anyio
    async def test_omio_disabled_uses_agent(self, monkeypatch):
        """When OMIO_ENABLED=false, pipeline should skip Omio entirely."""
        monkeypatch.setattr("app.core.pipeline.settings.omio_enabled", False)

        request = _make_request(response_id="resp_disabled_test")

        with patch("app.core.pipeline.set_status", new_callable=AsyncMock), \
             patch("app.core.pipeline.save_result", new_callable=AsyncMock, return_value="res_456"), \
             patch("app.core.pipeline.run_agent", new_callable=AsyncMock) as mock_agent:

            mock_agent.return_value = MagicMock()

            from app.core.pipeline import process_travel_request
            await process_travel_request(request)

            mock_agent.assert_called_once()
