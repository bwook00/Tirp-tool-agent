"""Passenger information model and file-based loading."""

import json
import os

from pydantic import BaseModel

from app.core.config import settings


class PassengerInfo(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: str  # YYYY-MM-DD
    email: str
    phone: str
    passport_number: str
    nationality: str  # ISO 3166-1 alpha-2 (e.g. "KR")


def load_passengers() -> list[PassengerInfo]:
    """Load all passenger profiles from JSON files in the passengers directory."""
    passengers_dir = settings.passengers_dir
    if not os.path.isdir(passengers_dir):
        return []
    result: list[PassengerInfo] = []
    for fname in sorted(os.listdir(passengers_dir)):
        if fname.endswith(".json"):
            path = os.path.join(passengers_dir, fname)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result.append(PassengerInfo(**data))
    return result
