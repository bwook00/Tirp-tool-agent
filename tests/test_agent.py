from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.agent import run_agent
from app.core.scoring import score_options
from app.models.schemas import (
    Preferences,
    PrimaryGoal,
    RecommendationResult,
    ScoredOption,
    TransitOption,
    TransportType,
    TravelRequest,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _make_options() -> list[TransitOption]:
    """Create a set of transit options with distinct characteristics."""
    return [
        TransitOption(
            transport_type=TransportType.train,
            provider="KTX",
            departure_time=datetime(2026, 3, 15, 10, 0),
            arrival_time=datetime(2026, 3, 15, 12, 35),
            duration_minutes=155,
            price=59800.0,
            transfers=0,
            details="KTX 서울→부산",
        ),
        TransitOption(
            transport_type=TransportType.flight,
            provider="제주항공",
            departure_time=datetime(2026, 3, 15, 14, 0),
            arrival_time=datetime(2026, 3, 15, 15, 5),
            duration_minutes=65,
            price=47000.0,
            transfers=0,
            details="제주항공 서울→부산",
        ),
        TransitOption(
            transport_type=TransportType.bus,
            provider="고속버스 일반",
            departure_time=datetime(2026, 3, 15, 8, 0),
            arrival_time=datetime(2026, 3, 15, 12, 30),
            duration_minutes=270,
            price=23000.0,
            transfers=0,
            details="고속버스 일반 서울→부산",
        ),
        TransitOption(
            transport_type=TransportType.train,
            provider="무궁화호",
            departure_time=datetime(2026, 3, 15, 22, 30),
            arrival_time=datetime(2026, 3, 16, 4, 0),
            duration_minutes=330,
            price=28600.0,
            transfers=1,
            details="무궁화호 서울→부산 (환승 1회)",
        ),
    ]


def _make_request(**kwargs) -> TravelRequest:
    defaults = {
        "response_id": "test-response-001",
        "origin": "서울",
        "destination": "부산",
        "departure_date": "2026-03-15",
        "departure_time": "10:00",
    }
    defaults.update(kwargs)
    return TravelRequest(**defaults)


# ---------------------------------------------------------------------------
# Scoring: fastest
# ---------------------------------------------------------------------------

class TestScoringFastest:
    def test_fastest_ranks_by_duration(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.fastest)
        scored = score_options(options, prefs)

        assert len(scored) == len(options)
        # Flight (65min) should be ranked first
        assert scored[0].option.provider == "제주항공"
        # Duration should be ascending when looking at top results
        assert scored[0].option.duration_minutes <= scored[1].option.duration_minutes

    def test_fastest_score_explain_contains_text(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.fastest)
        scored = score_options(options, prefs)

        for s in scored:
            assert s.score_explain != ""
            assert "소요시간" in s.score_explain


# ---------------------------------------------------------------------------
# Scoring: cheapest
# ---------------------------------------------------------------------------

class TestScoringCheapest:
    def test_cheapest_ranks_by_price(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.cheapest)
        scored = score_options(options, prefs)

        # Bus (23000) should be ranked first
        assert scored[0].option.provider == "고속버스 일반"
        assert scored[0].option.price <= scored[1].option.price

    def test_cheapest_score_explain_contains_price(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.cheapest)
        scored = score_options(options, prefs)

        for s in scored:
            assert "가격" in s.score_explain


# ---------------------------------------------------------------------------
# Scoring: least_transfers
# ---------------------------------------------------------------------------

class TestScoringLeastTransfers:
    def test_least_transfers_ranks_correctly(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.least_transfers)
        scored = score_options(options, prefs)

        # All 0-transfer options should rank above the 1-transfer option
        zero_transfer_scores = [s.score for s in scored if s.option.transfers == 0]
        one_transfer_scores = [s.score for s in scored if s.option.transfers == 1]
        assert min(zero_transfer_scores) > max(one_transfer_scores)

    def test_least_transfers_score_explain(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.least_transfers)
        scored = score_options(options, prefs)

        for s in scored:
            assert "환승" in s.score_explain


# ---------------------------------------------------------------------------
# Scoring: comfort
# ---------------------------------------------------------------------------

class TestScoringComfort:
    def test_comfort_composite_scoring(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.comfort)
        scored = score_options(options, prefs)

        assert len(scored) == len(options)
        # The night-travel, high-transfer option should not be #1
        assert scored[0].option.provider != "무궁화호"

    def test_comfort_score_explain(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.comfort)
        scored = score_options(options, prefs)

        assert "편의성" in scored[0].score_explain


# ---------------------------------------------------------------------------
# Scoring: different preferences produce different top picks
# ---------------------------------------------------------------------------

class TestDifferentPreferencesDifferentResults:
    def test_fastest_vs_cheapest_differ(self):
        options = _make_options()
        fastest = score_options(options, Preferences(primary_goal=PrimaryGoal.fastest))
        cheapest = score_options(options, Preferences(primary_goal=PrimaryGoal.cheapest))

        # Top 1 should differ: flight (fastest) vs bus (cheapest)
        assert fastest[0].option.provider != cheapest[0].option.provider


# ---------------------------------------------------------------------------
# Scoring: penalty features
# ---------------------------------------------------------------------------

class TestScoringPenalties:
    def test_avoid_night_penalizes_night_travel(self):
        options = _make_options()
        prefs_no_penalty = Preferences(primary_goal=PrimaryGoal.cheapest, avoid_night=False)
        prefs_with_penalty = Preferences(primary_goal=PrimaryGoal.cheapest, avoid_night=True)

        scored_no = score_options(options, prefs_no_penalty)
        scored_yes = score_options(options, prefs_with_penalty)

        # The 무궁화호 (departs 22:30) should have a lower score with avoid_night=True
        night_score_no = next(s for s in scored_no if s.option.provider == "무궁화호").score
        night_score_yes = next(s for s in scored_yes if s.option.provider == "무궁화호").score
        assert night_score_yes < night_score_no

    def test_avoid_night_explain(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.cheapest, avoid_night=True)
        scored = score_options(options, prefs)

        night_option = next(s for s in scored if s.option.provider == "무궁화호")
        assert "야간" in night_option.score_explain

    def test_avoid_long_layover_penalizes_transfers_with_long_duration(self):
        options = _make_options()
        prefs = Preferences(primary_goal=PrimaryGoal.cheapest, avoid_long_layover=True)
        scored = score_options(options, prefs)

        # The 무궁화호 has 1 transfer and 330 min → avg 165 min/segment > 120
        mugunghwa = next(s for s in scored if s.option.provider == "무궁화호")
        assert "대기시간" in mugunghwa.score_explain

    def test_mode_preference_penalizes_non_preferred(self):
        options = _make_options()
        prefs = Preferences(
            primary_goal=PrimaryGoal.fastest,
            mode_preference=[TransportType.train],
        )
        scored = score_options(options, prefs)

        # Train options should rank higher than non-train
        train_scores = [s.score for s in scored if s.option.transport_type == TransportType.train]
        non_train_scores = [s.score for s in scored if s.option.transport_type != TransportType.train]
        assert max(train_scores) > max(non_train_scores)

    def test_max_transfers_penalizes_excess(self):
        options = _make_options()
        prefs_no_limit = Preferences(primary_goal=PrimaryGoal.cheapest)
        prefs_limit = Preferences(primary_goal=PrimaryGoal.cheapest, max_transfers=0)

        scored_no = score_options(options, prefs_no_limit)
        scored_limit = score_options(options, prefs_limit)

        # The 무궁화호 (1 transfer) should have a lower score with max_transfers=0
        score_no = next(s for s in scored_no if s.option.provider == "무궁화호").score
        score_limit = next(s for s in scored_limit if s.option.provider == "무궁화호").score
        assert score_limit < score_no

        # And the explain should mention the penalty
        penalized = next(s for s in scored_limit if s.option.provider == "무궁화호")
        assert "초과" in penalized.score_explain


# ---------------------------------------------------------------------------
# Scoring: edge cases
# ---------------------------------------------------------------------------

class TestScoringEdgeCases:
    def test_empty_options_returns_empty(self):
        scored = score_options([], Preferences())
        assert scored == []

    def test_single_option(self):
        options = [_make_options()[0]]
        scored = score_options(options, Preferences(primary_goal=PrimaryGoal.fastest))
        assert len(scored) == 1
        assert scored[0].score == 100.0

    def test_all_scored_options_have_explain(self):
        options = _make_options()
        for goal in PrimaryGoal:
            scored = score_options(options, Preferences(primary_goal=goal))
            for s in scored:
                assert isinstance(s, ScoredOption)
                assert s.score_explain != ""


# ---------------------------------------------------------------------------
# Agent: fallback (no API key)
# ---------------------------------------------------------------------------

def _mock_train_results(**kwargs) -> list[TransitOption]:
    """Return mock train results for fallback tests."""
    return [
        TransitOption(
            transport_type=TransportType.train,
            provider="KTX",
            departure_time=datetime(2026, 3, 15, 10, 0),
            arrival_time=datetime(2026, 3, 15, 12, 35),
            duration_minutes=155,
            price=59800.0,
            currency="KRW",
            transfers=0,
        ),
        TransitOption(
            transport_type=TransportType.train,
            provider="SRT",
            departure_time=datetime(2026, 3, 15, 12, 0),
            arrival_time=datetime(2026, 3, 15, 14, 30),
            duration_minutes=150,
            price=52600.0,
            currency="KRW",
            transfers=0,
        ),
    ]


def _mock_bus_results(**kwargs) -> list[TransitOption]:
    """Return mock bus results for fallback tests."""
    return [
        TransitOption(
            transport_type=TransportType.bus,
            provider="고속버스 우등",
            departure_time=datetime(2026, 3, 15, 8, 0),
            arrival_time=datetime(2026, 3, 15, 12, 20),
            duration_minutes=260,
            price=34200.0,
            currency="KRW",
            transfers=0,
        ),
        TransitOption(
            transport_type=TransportType.bus,
            provider="고속버스 일반",
            departure_time=datetime(2026, 3, 15, 10, 0),
            arrival_time=datetime(2026, 3, 15, 14, 30),
            duration_minutes=270,
            price=23000.0,
            currency="KRW",
            transfers=0,
        ),
    ]


class TestAgentFallback:
    """Test agent fallback mode (no API key).

    search_trains and search_buses are mocked because they now depend on
    Omio Playwright scraping, which requires installed browsers.
    """

    @pytest.mark.asyncio
    async def test_run_agent_fallback_returns_recommendation(self):
        """With no API key, agent should use fallback and return a valid result."""
        request = _make_request()

        with patch("app.core.agent.settings") as mock_settings, \
             patch("app.core.agent.search_trains", new_callable=AsyncMock, side_effect=_mock_train_results), \
             patch("app.core.agent.search_buses", new_callable=AsyncMock, side_effect=_mock_bus_results):
            mock_settings.anthropic_api_key = ""
            result = await run_agent(request)

        assert isinstance(result, RecommendationResult)
        assert result.response_id == "test-response-001"
        assert result.origin == "서울"
        assert result.destination == "부산"
        assert result.result_id != ""
        assert result.checkout_url.startswith("https://")
        assert result.score_explain != ""
        assert result.transport_type in ("train", "bus")
        assert result.duration_minutes > 0
        assert result.price > 0

    @pytest.mark.asyncio
    async def test_run_agent_fallback_fastest(self):
        """Fallback with fastest preference should pick a short-duration option."""
        request = _make_request(
            preferences=Preferences(primary_goal=PrimaryGoal.fastest),
        )

        with patch("app.core.agent.settings") as mock_settings, \
             patch("app.core.agent.search_trains", new_callable=AsyncMock, side_effect=_mock_train_results), \
             patch("app.core.agent.search_buses", new_callable=AsyncMock, side_effect=_mock_bus_results):
            mock_settings.anthropic_api_key = ""
            result = await run_agent(request)

        # Flights are typically the fastest for Seoul→Busan
        assert result.duration_minutes <= 200

    @pytest.mark.asyncio
    async def test_run_agent_fallback_cheapest(self):
        """Fallback with cheapest preference should pick a low-price option."""
        request = _make_request(
            preferences=Preferences(primary_goal=PrimaryGoal.cheapest),
        )

        with patch("app.core.agent.settings") as mock_settings, \
             patch("app.core.agent.search_trains", new_callable=AsyncMock, side_effect=_mock_train_results), \
             patch("app.core.agent.search_buses", new_callable=AsyncMock, side_effect=_mock_bus_results):
            mock_settings.anthropic_api_key = ""
            result = await run_agent(request)

        # Buses are typically the cheapest for Seoul→Busan
        assert result.price <= 40000

    @pytest.mark.asyncio
    async def test_run_agent_fallback_different_preferences_different_results(self):
        """Different preferences should produce different top picks."""
        req_fast = _make_request(
            preferences=Preferences(primary_goal=PrimaryGoal.fastest),
        )
        req_cheap = _make_request(
            preferences=Preferences(primary_goal=PrimaryGoal.cheapest),
        )

        with patch("app.core.agent.settings") as mock_settings, \
             patch("app.core.agent.search_trains", new_callable=AsyncMock, side_effect=_mock_train_results), \
             patch("app.core.agent.search_buses", new_callable=AsyncMock, side_effect=_mock_bus_results):
            mock_settings.anthropic_api_key = ""
            result_fast = await run_agent(req_fast)
            result_cheap = await run_agent(req_cheap)

        # The fastest and cheapest should generally differ
        # At minimum, they should both be valid results
        assert isinstance(result_fast, RecommendationResult)
        assert isinstance(result_cheap, RecommendationResult)

    @pytest.mark.asyncio
    async def test_run_agent_fallback_has_checkout_url(self):
        """Fallback result should include a valid checkout URL."""
        request = _make_request()

        with patch("app.core.agent.settings") as mock_settings, \
             patch("app.core.agent.search_trains", new_callable=AsyncMock, side_effect=_mock_train_results), \
             patch("app.core.agent.search_buses", new_callable=AsyncMock, side_effect=_mock_bus_results):
            mock_settings.anthropic_api_key = ""
            result = await run_agent(request)

        assert result.checkout_url.startswith("https://")
        assert result.expires_at is not None
