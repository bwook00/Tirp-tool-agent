"""Parse Typeform webhook payload into a TravelRequest."""

from typing import Any

from app.models.schemas import Preferences, PrimaryGoal, TravelRequest

# Typeform field ref → internal field name 매핑
# Typeform QF2JWE4B 기준. 폼 변경 시 여기만 업데이트.
TYPEFORM_REF_MAP: dict[str, str] = {
    "266b4321-10e3-41c7-b57a-3e4580e0d2ee": "origin",
    "7b71eb98-4948-4512-a163-81990eb0ae27": "destination",
    "f6450ff4-84de-42fe-b6be-d6939d607460": "departure_date",
    "9cd84c38-78f8-4657-bfd8-e8c96be31b08": "passenger_count",
    "caf55741-e5f8-4a2d-a853-27e7daa940e3": "email",
    "9d20f008-2eef-45b6-8b1a-f2f47edc7520": "departure_time",
    "d978dc48-4477-40f5-974c-b326625d783b": "primary_goal",
}


def _find_answer(answers: list[dict[str, Any]], ref: str) -> str | None:
    """Find an answer by its field ref and return the text value."""
    for answer in answers:
        field = answer.get("field", {})
        raw_ref = field.get("ref", "")
        resolved_ref = TYPEFORM_REF_MAP.get(raw_ref, raw_ref)
        if resolved_ref == ref:
            # Typeform answers vary by type: text, choice, date, number, etc.
            if answer.get("type") == "text":
                return answer.get("text")
            if answer.get("type") == "choice":
                choice = answer.get("choice", {})
                return choice.get("label") or choice.get("other")
            if answer.get("type") == "date":
                return answer.get("date")
            if answer.get("type") == "number":
                return str(answer.get("number"))
            # Fallback: try common value keys
            for key in ("text", "date", "number", "boolean", "email", "url"):
                if key in answer:
                    return str(answer[key])
    return None


def parse_travel_request(form_response: dict[str, Any]) -> TravelRequest:
    """Extract TravelRequest fields from a Typeform form_response dict.

    Raises ValueError when required fields (origin, destination, departure_date)
    are missing.
    """
    token: str = form_response.get("token", "")
    if not token:
        raise ValueError("form_response.token is missing")

    answers: list[dict[str, Any]] = form_response.get("answers", [])

    origin = _find_answer(answers, "origin")
    destination = _find_answer(answers, "destination")
    departure_date = _find_answer(answers, "departure_date")

    if not origin:
        raise ValueError("Required field 'origin' is missing from answers")
    if not destination:
        raise ValueError("Required field 'destination' is missing from answers")
    if not departure_date:
        raise ValueError("Required field 'departure_date' is missing from answers")

    departure_time = _find_answer(answers, "departure_time")

    # Parse optional preferences
    goal_raw = _find_answer(answers, "primary_goal")
    primary_goal = PrimaryGoal.fastest
    if goal_raw:
        try:
            primary_goal = PrimaryGoal(goal_raw)
        except ValueError:
            pass  # fall back to default

    preferences = Preferences(primary_goal=primary_goal)

    # Parse optional email and passenger count
    email = _find_answer(answers, "email") or ""
    passenger_count_raw = _find_answer(answers, "passenger_count")
    passenger_count = int(passenger_count_raw) if passenger_count_raw else 1

    return TravelRequest(
        response_id=token,
        origin=origin,
        destination=destination,
        departure_date=departure_date,
        departure_time=departure_time,
        preferences=preferences,
        email=email,
        passenger_count=passenger_count,
    )
