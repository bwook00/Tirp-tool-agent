import json
import logging
from datetime import datetime

import anthropic

from app.core.config import settings
from app.core.scoring import score_options
from app.core.security import generate_result_id
from app.models.schemas import (
    RecommendationResult,
    TransitOption,
    TravelRequest,
)
from app.tools import TOOL_DEFINITIONS, execute_tool
from app.tools.bus_search import search_buses
from app.tools.checkout import get_checkout_link
from app.tools.train_search import search_trains

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "당신은 유럽 긴급 교통편 추천 에이전트입니다. "
    "사용자의 여행 정보를 바탕으로 Omio에서 열차와 버스를 검색하여 최적의 대안을 찾아주세요. "
    "반드시 search_trains, search_buses 도구를 모두 호출하여 가능한 모든 옵션을 수집하세요."
)

_MAX_TOOL_ROUNDS = 10


def _build_user_message(request: TravelRequest) -> str:
    parts = [
        f"출발지: {request.origin}",
        f"도착지: {request.destination}",
        f"출발일: {request.departure_date}",
    ]
    if request.departure_time:
        parts.append(f"희망 출발시간: {request.departure_time}")
    parts.append(f"우선순위: {request.preferences.primary_goal.value}")
    if request.preferences.avoid_night:
        parts.append("야간 이동 회피 희망")
    if request.preferences.avoid_long_layover:
        parts.append("긴 대기시간 회피 희망")
    if request.preferences.mode_preference:
        modes = ", ".join(m.value for m in request.preferences.mode_preference)
        parts.append(f"선호 교통수단: {modes}")
    if request.preferences.max_transfers is not None:
        parts.append(f"최대 환승 횟수: {request.preferences.max_transfers}회")

    return (
        "아래 여행 정보를 바탕으로 대체 교통편을 검색해 주세요.\n\n"
        + "\n".join(parts)
    )


def _serialize_tool_result(result: object) -> str:
    """Serialize a tool result to JSON string for the Claude API."""
    if isinstance(result, list):
        return json.dumps(
            [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in result],
            ensure_ascii=False,
            default=str,
        )
    if isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False, default=str)
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, default=str)
    return json.dumps(result, ensure_ascii=False, default=str)


async def _run_with_llm(request: TravelRequest) -> list[TransitOption]:
    """Run the Claude tool-use loop and collect all TransitOption results."""
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages: list[dict] = [
        {"role": "user", "content": _build_user_message(request)},
    ]

    all_options: list[TransitOption] = []

    for _ in range(_MAX_TOOL_ROUNDS):
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "tool_use":
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await execute_tool(block.name, block.input)
                    # Collect TransitOption results from search tools
                    if isinstance(result, list):
                        for item in result:
                            if isinstance(item, TransitOption):
                                all_options.append(item)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _serialize_tool_result(result),
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            break

    return all_options


async def _run_fallback(request: TravelRequest) -> list[TransitOption]:
    """Fallback: directly call search tools without LLM (trains + buses only)."""
    all_options: list[TransitOption] = []

    trains = await search_trains(
        origin=request.origin,
        destination=request.destination,
        date=request.departure_date,
        time=request.departure_time,
    )
    all_options.extend(trains)

    buses = await search_buses(
        origin=request.origin,
        destination=request.destination,
        date=request.departure_date,
        time=request.departure_time,
    )
    all_options.extend(buses)

    return all_options


async def run_agent(request: TravelRequest) -> RecommendationResult:
    """Run the LLM agent to find the best transit option.

    Falls back to direct tool calls if ANTHROPIC_API_KEY is not set.
    """
    # Collect options via LLM or fallback
    if settings.anthropic_api_key:
        try:
            all_options = await _run_with_llm(request)
        except Exception:
            logger.exception("LLM agent failed, falling back to direct search")
            all_options = await _run_fallback(request)
    else:
        all_options = await _run_fallback(request)

    if not all_options:
        raise ValueError("검색 결과가 없습니다. 경로를 확인해 주세요.")

    # Score and rank
    scored = score_options(all_options, request.preferences)
    top = scored[0]

    # Get checkout link
    checkout = await get_checkout_link(top.option)

    expires_at = None
    if checkout.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(checkout["expires_at"])
        except (ValueError, TypeError):
            pass

    return RecommendationResult(
        result_id=generate_result_id(),
        response_id=request.response_id,
        origin=request.origin,
        destination=request.destination,
        transport_type=top.option.transport_type.value,
        provider=top.option.provider,
        departure_time=top.option.departure_time,
        arrival_time=top.option.arrival_time,
        duration_minutes=top.option.duration_minutes,
        price=top.option.price,
        currency=top.option.currency,
        transfers=top.option.transfers,
        checkout_url=checkout.get("checkout_url", ""),
        score_explain=top.score_explain,
        expires_at=expires_at,
        original_request=request,
    )
