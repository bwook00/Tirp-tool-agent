"""Parse Tally.so webhook payload into a TravelRequest."""

from typing import Any

from app.models.schemas import Preferences, PrimaryGoal, TravelRequest

# Tally field label → internal field name 매핑
# Tally 폼의 질문 라벨 기준. 폼 변경 시 여기만 업데이트.
TALLY_LABEL_MAP: dict[str, str] = {
    # Tally 폼 (5BzVNM) 실제 라벨
    "What is your departure location?": "origin",
    "What is your destination?": "destination",
    "What is your preferred date of travel?": "departure_date",
    "What departure time would you like?": "departure_time",
    "How many people are traveling?": "passenger_count",
    "what is your name?": "name",
    "What is the most important factor when choosing an alternative mode of transportation?": "primary_goal",
    # 한국어 폴백
    "출발지": "origin",
    "도착지": "destination",
    "출발 날짜": "departure_date",
    "출발 시간": "departure_time",
    "승객 수": "passenger_count",
    "이메일": "email",
    "우선순위": "primary_goal",
}


def _find_field_value(fields: list[dict[str, Any]], name: str) -> str | None:
    """Find a field value by its mapped internal name."""
    for field in fields:
        label = field.get("label", "")
        mapped_name = TALLY_LABEL_MAP.get(label, "")
        if mapped_name == name:
            value = field.get("value")
            if value is None:
                return None
            # MULTIPLE_CHOICE / DROPDOWN return list of UUIDs — resolve via options
            if isinstance(value, list) and field.get("options"):
                options_map = {opt["id"]: opt["text"] for opt in field["options"]}
                resolved = [options_map.get(v, v) for v in value]
                return resolved[0] if resolved else None
            return str(value)
    return None


def parse_travel_request(data: dict[str, Any]) -> TravelRequest:
    """Extract TravelRequest fields from a Tally webhook data dict.

    Expects the `data` object from Tally's webhook payload
    (i.e. payload["data"]).

    Raises ValueError when required fields (origin, destination, departure_date)
    are missing.
    """
    response_id: str = data.get("responseId", "")
    if not response_id:
        response_id = data.get("submissionId", "")
    if not response_id:
        raise ValueError("data.responseId is missing")

    fields: list[dict[str, Any]] = data.get("fields", [])

    origin = _find_field_value(fields, "origin")
    destination = _find_field_value(fields, "destination")
    departure_date = _find_field_value(fields, "departure_date")

    if not origin:
        raise ValueError("Required field 'origin' is missing from fields")
    if not destination:
        raise ValueError("Required field 'destination' is missing from fields")
    if not departure_date:
        raise ValueError("Required field 'departure_date' is missing from fields")

    departure_time = _find_field_value(fields, "departure_time")

    # Parse optional preferences
    # Tally options may look like "fastest — 가장 빠른 도착"; extract the key before "—"
    goal_raw = _find_field_value(fields, "primary_goal")
    primary_goal = PrimaryGoal.fastest
    if goal_raw:
        goal_key = goal_raw.split("—")[0].split("-")[0].strip().lower()
        try:
            primary_goal = PrimaryGoal(goal_key)
        except ValueError:
            pass  # fall back to default

    preferences = Preferences(primary_goal=primary_goal)

    # Parse optional email and passenger count
    email = _find_field_value(fields, "email") or ""
    passenger_count_raw = _find_field_value(fields, "passenger_count")
    passenger_count = int(passenger_count_raw) if passenger_count_raw else 1

    return TravelRequest(
        response_id=response_id,
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        departure_time=departure_time,
        preferences=preferences,
        email=email,
        passenger_count=passenger_count,
    )
