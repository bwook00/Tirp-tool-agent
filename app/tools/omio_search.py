"""Omio search scraper via Playwright.

Searches Omio for train/bus options and returns TransitOption list.
Results are cached in-memory to avoid duplicate browser launches when
the agent calls search_trains then search_buses for the same route.
"""

import logging
import re
from datetime import datetime, timedelta

from playwright.async_api import Page, async_playwright

from app.core.config import settings
from app.models.schemas import TransitOption, TransportType

logger = logging.getLogger(__name__)

_OMIO_BASE_URL = "https://www.omio.com"
_SELECTOR_TIMEOUT_MS = 15_000

# In-memory cache: key -> (cached_at, results)
_search_cache: dict[str, tuple[datetime, list[TransitOption]]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


async def search_omio(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search Omio for transit options and return a list of TransitOption.

    Uses an in-memory cache (5 min TTL) so that consecutive calls for the
    same origin/destination/date reuse results from a single browser session.
    """
    cache_key = f"{origin}:{destination}:{date}"
    if cache_key in _search_cache:
        cached_at, cached_results = _search_cache[cache_key]
        if (datetime.now() - cached_at).total_seconds() < _CACHE_TTL_SECONDS:
            logger.info("Cache hit for %s", cache_key)
            return cached_results

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.omio_search_headless)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        page.set_default_timeout(_SELECTOR_TIMEOUT_MS)

        try:
            logger.info("Searching Omio: %s -> %s on %s", origin, destination, date)
            await page.goto(
                _OMIO_BASE_URL,
                wait_until="networkidle",
                timeout=settings.omio_search_timeout_ms,
            )

            await _dismiss_cookie_banner(page)
            await _fill_search(page, origin, destination, date)
            await _click_search(page)
            results = await _parse_search_results(page, date)

            _search_cache[cache_key] = (datetime.now(), results)
            logger.info("Omio returned %d results for %s", len(results), cache_key)
            return results

        except Exception:
            logger.exception("Omio search failed for %s", cache_key)
            return []
        finally:
            await browser.close()


async def _dismiss_cookie_banner(page: Page) -> None:
    """Dismiss the cookie consent banner if present."""
    try:
        accept_btn = page.locator(
            '[data-element="gdpr-banner-button-accept"], '
            "#didomi-notice-agree-button, "
            "button:has-text('Accept')"
        )
        if await accept_btn.first.is_visible(timeout=3000):
            await accept_btn.first.click()
            logger.debug("Cookie banner dismissed")
    except Exception:
        logger.debug("No cookie banner found or already dismissed")


async def _fill_search(
    page: Page,
    origin: str,
    destination: str,
    date: str,
) -> None:
    """Fill in the Omio search form: origin, destination, date."""
    # Origin
    origin_input = page.locator('[data-e2e="departurePositionInput"]').first
    await origin_input.click()
    await origin_input.fill(origin)
    await page.wait_for_timeout(1000)
    suggestion = page.locator('[data-e2e="positionSuggestion"]')
    await suggestion.first.wait_for(timeout=_SELECTOR_TIMEOUT_MS)
    await suggestion.first.click()

    # Destination
    dest_input = page.locator('[data-e2e="arrivalPositionInput"]').first
    await dest_input.click()
    await dest_input.fill(destination)
    await page.wait_for_timeout(1000)
    suggestion = page.locator('[data-e2e="positionSuggestion"]')
    await suggestion.first.wait_for(timeout=_SELECTOR_TIMEOUT_MS)
    await suggestion.first.click()

    # Date — open calendar and click the target day
    date_btn = page.locator('[data-e2e="buttonDepartureDate"]').first
    await date_btn.click()
    await page.wait_for_timeout(500)

    # Parse target date parts for matching
    target = datetime.strptime(date, "%Y-%m-%d")
    target_month = target.strftime("%b")  # e.g. "Mar"
    target_day = str(target.day)          # e.g. "15"

    # Scroll through calendar months until we find the target
    for _ in range(12):
        day_cells = page.locator('[data-e2e="calendarDay"]')
        count = await day_cells.count()
        for i in range(count):
            cell = day_cells.nth(i)
            date_attr = await cell.get_attribute("date")
            if date_attr and date_attr.startswith(target.strftime("%a %b %d %Y")):
                await cell.click()
                return
        # Try clicking a forward/next button to advance the calendar
        try:
            next_btn = page.locator(
                '[data-e2e="calendarButtonNext"], '
                'button[aria-label="Next month"], '
                'button[aria-label="next"]'
            ).first
            if await next_btn.is_visible(timeout=2000):
                await next_btn.click()
                await page.wait_for_timeout(500)
            else:
                break
        except Exception:
            break

    logger.warning("Could not find target date %s in calendar", date)


async def _click_search(page: Page) -> None:
    """Click the search button and wait for results to load."""
    search_btn = page.locator('[data-e2e="buttonSearch"]').first
    await search_btn.click()
    await page.wait_for_load_state(
        "networkidle",
        timeout=settings.omio_search_timeout_ms,
    )


async def _parse_search_results(
    page: Page,
    date: str,
) -> list[TransitOption]:
    """Parse search result cards from the Omio results page."""
    await page.wait_for_timeout(3000)  # Allow results to render

    result_cards = page.locator(
        "[data-testid='result-card'], "
        "[data-testid='search-result'], "
        ".search-result-card"
    )
    count = await result_cards.count()
    logger.debug("Found %d result cards on page", count)

    options: list[TransitOption] = []
    for i in range(min(count, 15)):
        card = result_cards.nth(i)
        try:
            text_content = await card.inner_text()
            option = _parse_result_card(text_content, date)
            if option:
                options.append(option)
        except Exception:
            logger.debug("Failed to parse result card %d", i)
            continue

    return options


def _parse_result_card(text: str, date: str) -> TransitOption | None:
    """Parse a single result card's text content into a TransitOption.

    Omio result cards typically contain lines like:
        14:30  →  18:45       (departure/arrival times)
        4h 15min              (duration)
        €29                   (price)
        Deutsche Bahn         (provider)
        Direct / 1 change     (transfers)
    """
    if not text.strip():
        return None

    # Extract times (HH:MM patterns)
    time_pattern = re.compile(r"(\d{1,2}:\d{2})")
    times = time_pattern.findall(text)

    # Extract price (€XX or EUR XX)
    price_pattern = re.compile(r"€\s*(\d+(?:[.,]\d+)?)")
    price_match = price_pattern.search(text)

    # Extract duration (Xh Ymin or X:YY)
    duration_pattern = re.compile(
        r"(\d+)\s*h\s*(\d+)\s*min|(\d+)\s*h(?!\s*\d)|(\d+)\s*min"
    )
    duration_match = duration_pattern.search(text)

    # Need at minimum times and price
    if len(times) < 2 or not price_match:
        return None

    dep_time_str = times[0]
    arr_time_str = times[1]

    try:
        departure_time = datetime.strptime(f"{date} {dep_time_str}", "%Y-%m-%d %H:%M")
        arrival_time = datetime.strptime(f"{date} {arr_time_str}", "%Y-%m-%d %H:%M")
        # Handle overnight journeys
        if arrival_time <= departure_time:
            arrival_time += timedelta(days=1)
    except ValueError:
        return None

    # Parse price
    price_str = price_match.group(1).replace(",", ".")
    try:
        price = float(price_str)
    except ValueError:
        return None

    # Parse duration
    duration_minutes = int((arrival_time - departure_time).total_seconds() / 60)
    if duration_match:
        groups = duration_match.groups()
        if groups[0] is not None and groups[1] is not None:
            duration_minutes = int(groups[0]) * 60 + int(groups[1])
        elif groups[2] is not None:
            duration_minutes = int(groups[2]) * 60
        elif groups[3] is not None:
            duration_minutes = int(groups[3])

    # Detect transport type from keywords
    text_lower = text.lower()
    transport_type = _detect_transport_type(text_lower)

    # Detect provider
    provider = _detect_provider(text)

    # Detect transfers
    transfers = _detect_transfers(text_lower)

    return TransitOption(
        transport_type=transport_type,
        provider=provider,
        departure_time=departure_time,
        arrival_time=arrival_time,
        duration_minutes=duration_minutes,
        price=price,
        currency="EUR",
        transfers=transfers,
        details=f"{provider} {dep_time_str}-{arr_time_str}",
    )


def _detect_transport_type(text_lower: str) -> TransportType:
    """Detect transport type from result card text."""
    bus_keywords = ["bus", "flixbus", "eurolines", "blablabus", "regiojet bus"]
    train_keywords = [
        "train", "ice", "tgv", "eurostar", "railjet", "frecciarossa",
        "intercity", "regional", "db", "sncf", "trenitalia", "renfe",
        "thalys", "deutsche bahn",
    ]

    for kw in bus_keywords:
        if kw in text_lower:
            return TransportType.bus
    for kw in train_keywords:
        if kw in text_lower:
            return TransportType.train

    # Default to train (Omio is train-heavy)
    return TransportType.train


_KNOWN_PROVIDERS = [
    "Deutsche Bahn", "DB", "SNCF", "Trenitalia", "Renfe", "Eurostar",
    "Thalys", "FlixBus", "FlixTrain", "RegioJet", "BlaBlaBus",
    "Italo", "SBB", "OBB", "PKP", "Czech Railways", "NS",
    "OUIGO", "Frecciarossa", "ICE", "TGV", "RailJet",
]


def _detect_provider(text: str) -> str:
    """Detect provider name from result card text."""
    for provider in _KNOWN_PROVIDERS:
        if provider.lower() in text.lower():
            return provider
    return "Omio"


def _detect_transfers(text_lower: str) -> int:
    """Detect number of transfers from result card text."""
    if "direct" in text_lower or "nonstop" in text_lower:
        return 0
    transfer_match = re.search(r"(\d+)\s*(?:change|transfer|stop)", text_lower)
    if transfer_match:
        return int(transfer_match.group(1))
    return 0
