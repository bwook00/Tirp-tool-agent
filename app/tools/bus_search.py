import logging
import random
from datetime import datetime, timedelta

from app.models.schemas import TransitOption, TransportType

logger = logging.getLogger(__name__)

# Realistic Korean bus routes
_BUS_ROUTES: dict[tuple[str, str], list[dict]] = {
    ("서울", "부산"): [
        {"provider": "고속버스 우등", "duration": 260, "price": 34200},
        {"provider": "고속버스 프리미엄", "duration": 260, "price": 39500},
        {"provider": "고속버스 일반", "duration": 270, "price": 23000},
        {"provider": "시외버스", "duration": 300, "price": 21000},
    ],
    ("서울", "대전"): [
        {"provider": "고속버스 우등", "duration": 120, "price": 18200},
        {"provider": "고속버스 일반", "duration": 130, "price": 12000},
        {"provider": "시외버스", "duration": 140, "price": 10500},
    ],
    ("서울", "광주"): [
        {"provider": "고속버스 우등", "duration": 210, "price": 28600},
        {"provider": "고속버스 일반", "duration": 220, "price": 19200},
        {"provider": "시외버스", "duration": 240, "price": 17500},
    ],
    ("서울", "대구"): [
        {"provider": "고속버스 우등", "duration": 210, "price": 25800},
        {"provider": "고속버스 프리미엄", "duration": 210, "price": 30200},
        {"provider": "고속버스 일반", "duration": 225, "price": 17600},
    ],
    ("서울", "전주"): [
        {"provider": "고속버스 우등", "duration": 170, "price": 19800},
        {"provider": "고속버스 일반", "duration": 180, "price": 13200},
        {"provider": "시외버스", "duration": 190, "price": 11800},
    ],
    ("서울", "강릉"): [
        {"provider": "고속버스 우등", "duration": 155, "price": 21300},
        {"provider": "고속버스 일반", "duration": 165, "price": 14400},
        {"provider": "시외버스", "duration": 180, "price": 13000},
    ],
    ("서울", "목포"): [
        {"provider": "고속버스 우등", "duration": 240, "price": 30500},
        {"provider": "고속버스 일반", "duration": 255, "price": 21000},
    ],
    ("대전", "부산"): [
        {"provider": "고속버스 우등", "duration": 150, "price": 20100},
        {"provider": "고속버스 일반", "duration": 165, "price": 13500},
    ],
}

_reverse: dict[tuple[str, str], list[dict]] = {}
for (o, d), opts in _BUS_ROUTES.items():
    _reverse[(d, o)] = opts
_BUS_ROUTES.update(_reverse)


def _generate_departure_times(date_str: str, preferred_time: str | None, count: int) -> list[datetime]:
    base_date = datetime.strptime(date_str, "%Y-%m-%d")

    if preferred_time:
        try:
            h, _ = map(int, preferred_time.split(":"))
            center_hour = h
        except (ValueError, IndexError):
            center_hour = 10
    else:
        center_hour = 9

    times: list[datetime] = []
    start_hour = max(6, center_hour - 2)
    for i in range(count):
        hour = start_hour + i * 2
        if hour > 22:
            hour = 22 - (count - 1 - i)
        minute = random.choice([0, 10, 20, 30, 40, 50])
        times.append(base_date.replace(hour=min(hour, 23), minute=minute))
    return times


async def search_buses(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search for bus options between two Korean cities.

    Returns realistic mock data for known routes, or a minimal
    fallback list for unknown routes.
    """
    try:
        key = (origin, destination)
        templates = _BUS_ROUTES.get(key)

        if templates is None:
            templates = [
                {"provider": "고속버스 우등", "duration": 200, "price": 25000},
                {"provider": "고속버스 일반", "duration": 220, "price": 17000},
            ]

        dep_times = _generate_departure_times(date, time, len(templates))

        options: list[TransitOption] = []
        for tmpl, dep in zip(templates, dep_times):
            jitter_min = random.randint(-10, 10)
            jitter_price = random.randint(-1000, 1000)
            duration = max(30, tmpl["duration"] + jitter_min)
            price = max(5000, tmpl["price"] + jitter_price)

            options.append(
                TransitOption(
                    transport_type=TransportType.bus,
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
        logger.exception("search_buses failed")
        return []
