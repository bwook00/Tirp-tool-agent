from app.models.schemas import (
    Preferences,
    PrimaryGoal,
    ScoredOption,
    TransitOption,
)


def _is_night_time(hour: int) -> bool:
    """Return True if the hour falls in the night window (22:00-05:59)."""
    return hour >= 22 or hour < 6


def score_options(
    options: list[TransitOption],
    preferences: Preferences,
) -> list[ScoredOption]:
    """Score and rank transit options based on user preferences.

    Returns a list of ScoredOption sorted by score descending (best first).
    """
    if not options:
        return []

    goal = preferences.primary_goal

    # Collect raw values for normalization
    durations = [o.duration_minutes for o in options]
    prices = [o.price for o in options]
    transfers_list = [o.transfers for o in options]

    max_duration = max(durations) if durations else 1
    min_duration = min(durations) if durations else 0
    max_price = max(prices) if prices else 1
    min_price = min(prices) if prices else 0
    max_transfers = max(transfers_list) if transfers_list else 0

    duration_range = max_duration - min_duration if max_duration != min_duration else 1
    price_range = max_price - min_price if max_price != min_price else 1
    transfers_range = max_transfers if max_transfers > 0 else 1

    scored: list[ScoredOption] = []

    for option in options:
        score = 0.0
        reasons: list[str] = []

        # Base score by primary goal
        if goal == PrimaryGoal.fastest:
            score = 100.0 * (1.0 - (option.duration_minutes - min_duration) / duration_range)
            reasons.append(f"소요시간 {option.duration_minutes}분")

        elif goal == PrimaryGoal.cheapest:
            score = 100.0 * (1.0 - (option.price - min_price) / price_range)
            reasons.append(f"가격 {option.price:,.0f}원")

        elif goal == PrimaryGoal.least_transfers:
            score = 100.0 * (1.0 - option.transfers / transfers_range)
            reasons.append(f"환승 {option.transfers}회")

        elif goal == PrimaryGoal.comfort:
            # Composite: weight duration (40%), price (20%), transfers (40%)
            dur_score = 1.0 - (option.duration_minutes - min_duration) / duration_range
            price_score = 1.0 - (option.price - min_price) / price_range
            transfer_score = 1.0 - option.transfers / transfers_range
            score = 100.0 * (0.4 * dur_score + 0.2 * price_score + 0.4 * transfer_score)
            reasons.append("편의성 종합 평가")

        # Penalty: avoid_night
        if preferences.avoid_night:
            dep_hour = option.departure_time.hour
            arr_hour = option.arrival_time.hour
            if _is_night_time(dep_hour) or _is_night_time(arr_hour):
                score -= 30.0
                reasons.append("야간 이동 감점")

        # Penalty: avoid_long_layover
        if preferences.avoid_long_layover and option.transfers > 0:
            avg_segment = option.duration_minutes / (option.transfers + 1)
            if avg_segment > 120:
                score -= 20.0
                reasons.append("긴 대기시간 감점")

        # Filter by mode preference
        if preferences.mode_preference and option.transport_type not in preferences.mode_preference:
            score -= 50.0
            reasons.append(f"{option.transport_type.value} 비선호 교통수단 감점")

        # Filter by max_transfers
        if preferences.max_transfers is not None and option.transfers > preferences.max_transfers:
            score -= 40.0
            reasons.append(f"환승 {option.transfers}회 (최대 {preferences.max_transfers}회 초과)")

        scored.append(
            ScoredOption(
                option=option,
                score=round(score, 2),
                score_explain=" | ".join(reasons),
            )
        )

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored
