import json
import os
import tempfile

import pytest
from pydantic import ValidationError

from app.models.passenger import PassengerInfo, load_passengers


class TestPassengerInfo:

    def test_valid_passenger(self):
        p = PassengerInfo(
            first_name="길동",
            last_name="홍",
            date_of_birth="1990-01-15",
            email="gildong@example.com",
            phone="+82-10-1234-5678",
            passport_number="M12345678",
            nationality="KR",
        )
        assert p.first_name == "길동"
        assert p.nationality == "KR"

    def test_load_passenger_from_json(self, tmp_path):
        data = {
            "first_name": "길동",
            "last_name": "홍",
            "date_of_birth": "1990-01-15",
            "email": "gildong@example.com",
            "phone": "+82-10-1234-5678",
            "passport_number": "M12345678",
            "nationality": "KR",
        }
        path = tmp_path / "passenger1.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        p = PassengerInfo(**loaded)
        assert p.first_name == "길동"
        assert p.email == "gildong@example.com"

    def test_load_passengers_from_dir(self, tmp_path, monkeypatch):
        for i, name in enumerate(["Alice", "Bob"]):
            data = {
                "first_name": name,
                "last_name": "Test",
                "date_of_birth": f"199{i}-01-01",
                "email": f"{name.lower()}@example.com",
                "phone": "+1-000-000-0000",
                "passport_number": f"P0000000{i}",
                "nationality": "US",
            }
            (tmp_path / f"p{i}.json").write_text(json.dumps(data), encoding="utf-8")

        monkeypatch.setattr("app.models.passenger.settings.passengers_dir", str(tmp_path))
        passengers = load_passengers()
        assert len(passengers) == 2
        assert passengers[0].first_name == "Alice"
        assert passengers[1].first_name == "Bob"

    def test_load_passengers_empty_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("app.models.passenger.settings.passengers_dir", str(tmp_path))
        passengers = load_passengers()
        assert passengers == []

    def test_load_passengers_nonexistent_dir(self, monkeypatch):
        monkeypatch.setattr("app.models.passenger.settings.passengers_dir", "/nonexistent/path")
        passengers = load_passengers()
        assert passengers == []

    def test_passenger_required_fields(self):
        with pytest.raises(ValidationError):
            PassengerInfo(first_name="길동")  # Missing required fields
