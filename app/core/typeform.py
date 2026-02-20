"""Parse Typeform webhook payload into a TravelRequest."""

from typing import Any

from app.models.schemas import Preferences, PrimaryGoal, TravelRequest


def _find_answer(answers: list[dict[str, Any]], ref: str) -> str | None:
    """Find an answer by its field ref and return the text value."""
    for answer in answers:
        field = answer.get("field", {})
        if field.get("ref") == ref:
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
