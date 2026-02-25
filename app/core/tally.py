"""Parse Tally webhook payload into a TravelRequest."""

from app.models.schemas import (
    Preferences,
    PrimaryGoal,
    TallyField,
    TallySubmissionData,
    TravelRequest,
)

# Tally field key → internal field name 매핑
# Tally 폼 변경 시 여기만 업데이트.
TALLY_KEY_MAP: dict[str, str] = {
    "question_nGVOax": "origin",
    "question_mOWkbr": "destination",
    "question_3XePVe": "departure_date",
    "question_wQ72Nd": "passenger_count",
    "question_3jPB7E": "email",
    "question_wMEaVL": "departure_time",
    "question_3Nbyp2": "primary_goal",
}


def _find_field_value(fields: list[TallyField], name: str) -> str | None:
    """Find a field by its mapped name and return the string value."""
    for field in fields:
        resolved_key = TALLY_KEY_MAP.get(field.key, field.key)
        if resolved_key == name:
            if field.value is None:
                return None
            if isinstance(field.value, str):
                return field.value
            if isinstance(field.value, (int, float)):
                return str(field.value)
            # Tally option values can be objects with id/name
            if isinstance(field.value, dict):
                return field.value.get("name") or field.value.get("label") or str(field.value)
            if isinstance(field.value, list) and field.value:
                first = field.value[0]
                if isinstance(first, dict):
                    return first.get("name") or first.get("label") or str(first)
                return str(first)
            return str(field.value)
    return None


def parse_travel_request(data: TallySubmissionData) -> TravelRequest:
    """Extract TravelRequest fields from Tally submission data.

    Raises ValueError when required fields (origin, destination, departure_date)
    are missing.
    """
    response_id = data.response_id
    if not response_id:
        raise ValueError("data.responseId is missing")

    fields = data.fields

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
    goal_raw = _find_field_value(fields, "primary_goal")
    primary_goal = PrimaryGoal.fastest
    if goal_raw:
        try:
            primary_goal = PrimaryGoal(goal_raw)
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
