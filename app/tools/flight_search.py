import logging
import random
from datetime import datetime, timedelta

from app.models.schemas import TransitOption, TransportType

logger = logging.getLogger(__name__)

# Realistic Korean domestic flight routes
_FLIGHT_ROUTES: dict[tuple[str, str], list[dict]] = {
    ("서울", "부산"): [
        {"provider": "대한항공", "duration": 60, "price": 77000},
        {"provider": "아시아나항공", "duration": 60, "price": 74000},
        {"provider": "진에어", "duration": 65, "price": 49000},
        {"provider": "제주항공", "duration": 65, "price": 47000},
    ],
    ("서울", "제주"): [
        {"provider": "대한항공", "duration": 70, "price": 82000},
        {"provider": "아시아나항공", "duration": 70, "price": 79000},
        {"provider": "진에어", "duration": 75, "price": 52000},
        {"provider": "티웨이항공", "duration": 75, "price": 50000},
    ],
    ("서울", "광주"): [
        {"provider": "대한항공", "duration": 55, "price": 68000},
        {"provider": "아시아나항공", "duration": 55, "price": 65000},
    ],
    ("서울", "대구"): [
        {"provider": "대한항공", "duration": 55, "price": 71000},
        {"provider": "진에어", "duration": 60, "price": 45000},
    ],
    ("부산", "제주"): [
        {"provider": "대한항공", "duration": 55, "price": 65000},
        {"provider": "아시아나항공", "duration": 55, "price": 62000},
        {"provider": "에어부산", "duration": 60, "price": 42000},
    ],
}

_reverse: dict[tuple[str, str], list[dict]] = {}
for (o, d), opts in _FLIGHT_ROUTES.items():
    _reverse[(d, o)] = opts
_FLIGHT_ROUTES.update(_reverse)


def _generate_departure_times(date_str: str, preferred_time: str | None, count: int) -> list[datetime]:
    base_date = datetime.strptime(date_str, "%Y-%m-%d")

    if preferred_time:
        try:
            h, _ = map(int, preferred_time.split(":"))
            center_hour = h
        except (ValueError, IndexError):
            center_hour = 12
    else:
        center_hour = 11

    times: list[datetime] = []
    start_hour = max(7, center_hour - 2)
    for i in range(count):
        hour = start_hour + i * 3
        if hour > 21:
            hour = 21 - (count - 1 - i)
        minute = random.choice([0, 10, 20, 30, 40, 50])
        times.append(base_date.replace(hour=min(hour, 22), minute=minute))
    return times


async def search_flights(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search for flight options between two Korean cities.

    Returns realistic mock data for known routes, or a minimal
    fallback list for unknown routes.
    """
    try:
        key = (origin, destination)
        templates = _FLIGHT_ROUTES.get(key)

        if templates is None:
            templates = [{"provider": "대한항공", "duration": 70, "price": 80000}]

        dep_times = _generate_departure_times(date, time, len(templates))

        options: list[TransitOption] = []
        for tmpl, dep in zip(templates, dep_times):
            jitter_min = random.randint(-5, 5)
            jitter_price = random.randint(-3000, 3000)
            duration = max(40, tmpl["duration"] + jitter_min)
            price = max(30000, tmpl["price"] + jitter_price)

            options.append(
                TransitOption(
                    transport_type=TransportType.flight,
                    provider=tmpl["provider"],
                    departure_time=dep,
                    arrival_time=dep + timedelta(minutes=duration),
                    duration_minutes=duration,
                    price=float(price),
                    currency="KRW",
                    transfers=0,
                    details=f"{tmpl['provider']} {origin}→{destination}",
                )
            )

        return options

    except Exception:
        logger.exception("search_flights failed")
        return []
