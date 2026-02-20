import logging
import random
from datetime import datetime, timedelta

from app.models.schemas import TransitOption, TransportType

logger = logging.getLogger(__name__)

# Realistic Korean train routes: (origin, destination, providers, base_duration_min, base_price_krw)
_TRAIN_ROUTES: dict[tuple[str, str], list[dict]] = {
    ("서울", "부산"): [
        {"provider": "KTX", "duration": 155, "price": 59800},
        {"provider": "SRT", "duration": 150, "price": 52600},
        {"provider": "KTX-산천", "duration": 158, "price": 59800},
        {"provider": "무궁화호", "duration": 320, "price": 28600},
    ],
    ("서울", "대전"): [
        {"provider": "KTX", "duration": 50, "price": 23700},
        {"provider": "SRT", "duration": 48, "price": 20900},
        {"provider": "무궁화호", "duration": 120, "price": 11200},
    ],
    ("서울", "광주"): [
        {"provider": "KTX", "duration": 113, "price": 42300},
        {"provider": "SRT", "duration": 110, "price": 37200},
        {"provider": "무궁화호", "duration": 270, "price": 20100},
    ],
    ("서울", "대구"): [
        {"provider": "KTX", "duration": 100, "price": 43500},
        {"provider": "SRT", "duration": 97, "price": 38300},
    ],
    ("서울", "강릉"): [
        {"provider": "KTX", "duration": 108, "price": 27600},
    ],
    ("서울", "목포"): [
        {"provider": "KTX", "duration": 150, "price": 48100},
        {"provider": "무궁화호", "duration": 330, "price": 24500},
    ],
    ("대전", "부산"): [
        {"provider": "KTX", "duration": 95, "price": 34700},
        {"provider": "SRT", "duration": 92, "price": 30500},
    ],
}

# Generate reverse routes automatically
_reverse: dict[tuple[str, str], list[dict]] = {}
for (o, d), opts in _TRAIN_ROUTES.items():
    _reverse[(d, o)] = opts
_TRAIN_ROUTES.update(_reverse)


def _generate_departure_times(date_str: str, preferred_time: str | None, count: int) -> list[datetime]:
    """Generate realistic departure times spread throughout the day."""
    base_date = datetime.strptime(date_str, "%Y-%m-%d")

    if preferred_time:
        try:
            h, m = map(int, preferred_time.split(":"))
            center_hour = h
        except (ValueError, IndexError):
            center_hour = 12
    else:
        center_hour = 10

    times: list[datetime] = []
    start_hour = max(6, center_hour - 2)
    for i in range(count):
        hour = start_hour + i * 2
        if hour > 22:
            hour = 22 - (count - 1 - i)
        minute = random.choice([0, 10, 15, 20, 30, 40, 45, 50])
        times.append(base_date.replace(hour=min(hour, 23), minute=minute))
    return times


async def search_trains(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search for train options between two Korean cities.

    Returns realistic mock data for known routes, or a minimal
    fallback list for unknown routes.
    """
    try:
        key = (origin, destination)
        templates = _TRAIN_ROUTES.get(key)

        if templates is None:
            # Fallback: generate a single generic KTX option
            templates = [{"provider": "KTX", "duration": 180, "price": 45000}]

        dep_times = _generate_departure_times(date, time, len(templates))

        options: list[TransitOption] = []
        for tmpl, dep in zip(templates, dep_times):
            jitter_min = random.randint(-5, 5)
            jitter_price = random.randint(-2000, 2000)
            duration = max(30, tmpl["duration"] + jitter_min)
            price = max(5000, tmpl["price"] + jitter_price)

            options.append(
                TransitOption(
                    transport_type=TransportType.train,
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
        logger.exception("search_trains failed")
        return []
