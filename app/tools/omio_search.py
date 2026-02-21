"""Omio search via HTTP API + Playwright fallback.

Primary: Calls Omio's B2B ChatGPT plugin API (fast, no browser).
Fallback: Playwright browser automation if the API is blocked.
Results are cached in-memory (5 min TTL) to avoid duplicate requests.
"""

import logging
import re
from datetime import datetime, timedelta

import httpx

from app.core.config import settings
from app.models.schemas import TransitOption, TransportType

logger = logging.getLogger(__name__)

# In-memory cache: key -> (cached_at, results)
_search_cache: dict[str, tuple[datetime, list[TransitOption]]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes

# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def search_omio(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search Omio for transit options.

    Tries the HTTP API first (fast, reliable).  Falls back to
    Playwright browser automation if the API is unavailable.
    """
    cache_key = f"{origin}:{destination}:{date}"
    if cache_key in _search_cache:
        cached_at, cached_results = _search_cache[cache_key]
        if (datetime.now() - cached_at).total_seconds() < _CACHE_TTL_SECONDS:
            logger.info("Cache hit for %s", cache_key)
            return cached_results

    # 1) Try HTTP API (no browser needed)
    try:
        results = await _search_via_api(origin, destination, date)
        if results:
            logger.info("API returned %d results for %s", len(results), cache_key)
            _search_cache[cache_key] = (datetime.now(), results)
            return results
        logger.info("API returned 0 results for %s, trying Playwright", cache_key)
    except Exception:
        logger.info("API unavailable for %s, trying Playwright", cache_key)

    # 2) Fallback: Playwright browser automation
    try:
        results = await _search_via_playwright(origin, destination, date, time)
        _search_cache[cache_key] = (datetime.now(), results)
        logger.info("Playwright returned %d results for %s", len(results), cache_key)
        return results
    except Exception:
        logger.exception("Playwright also failed for %s", cache_key)

    return []


# ---------------------------------------------------------------------------
# HTTP API approach (primary)
# ---------------------------------------------------------------------------

_API_URL = "https://www.omio.com/b2b-chatgpt-plugin/schedules"


async def _search_via_api(
    origin: str,
    destination: str,
    date: str,
    transport_mode: str | None = None,
) -> list[TransitOption]:
    """Search Omio via their B2B ChatGPT plugin API."""
    params: dict[str, str] = {
        "departureLocation": origin,
        "arrivalLocation": destination,
        "departureDate": date,
    }
    if transport_mode:
        params["transportMode"] = transport_mode

    headers = {
        "Accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (compatible; ChatGPT-User/1.0; "
            "+https://openai.com/bot)"
        ),
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(_API_URL, params=params, headers=headers)
        resp.raise_for_status()

        # Reject non-JSON responses (e.g. Cloudflare challenge HTML)
        content_type = resp.headers.get("content-type", "")
        if "json" not in content_type:
            raise ValueError(f"Non-JSON response: {content_type}")

        data = resp.json()

    return _parse_api_response(data, date)


def _parse_api_response(data: dict, date: str) -> list[TransitOption]:
    """Parse API response into TransitOption list."""
    options: list[TransitOption] = []
    schedules = data.get("schedules", [])
    currency = data.get("currency", "EUR")

    for s in schedules:
        try:
            dep_str = s.get("departureDateAndTime", "")
            arr_str = s.get("arrivalDateAndTime", "")
            if not dep_str or not arr_str:
                continue

            dep_time = datetime.fromisoformat(dep_str.replace("Z", "+00:00"))
            arr_time = datetime.fromisoformat(arr_str.replace("Z", "+00:00"))
            # Strip timezone for consistency with the rest of the codebase
            dep_time = dep_time.replace(tzinfo=None)
            arr_time = arr_time.replace(tzinfo=None)

            duration = s.get("durationInMinutes")
            if duration is None:
                duration = int((arr_time - dep_time).total_seconds() / 60)

            price = s.get("price", s.get("priceFrom", 0))
            if not price:
                continue

            provider = s.get(
                "provider",
                s.get("companyName", s.get("carrier", "Omio")),
            )

            mode = s.get("transportMode", s.get("mode", "train"))
            mode_lower = str(mode).lower()
            if mode_lower == "bus":
                tt = TransportType.bus
            else:
                tt = TransportType.train

            transfers = s.get(
                "changes",
                s.get("transfers", s.get("numberOfChanges", 0)),
            )
            deep_link = s.get("deepLink", s.get("link", ""))

            options.append(
                TransitOption(
                    transport_type=tt,
                    provider=str(provider),
                    departure_time=dep_time,
                    arrival_time=arr_time,
                    duration_minutes=int(duration),
                    price=float(price),
                    currency=currency,
                    transfers=int(transfers) if transfers else 0,
                    details=deep_link,
                )
            )
        except Exception:
            logger.debug("Failed to parse schedule item: %s", s)
            continue

    return options


# ---------------------------------------------------------------------------
# Playwright browser approach (fallback)
# ---------------------------------------------------------------------------

_SELECTOR_TIMEOUT_MS = 15_000


async def _search_via_playwright(
    origin: str,
    destination: str,
    date: str,
    time: str | None = None,
) -> list[TransitOption]:
    """Search Omio via Playwright browser automation (fallback)."""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=settings.omio_search_headless,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--single-process",
            ],
        )
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
            logger.info("Playwright: Omio %s -> %s on %s", origin, destination, date)
            await page.goto(
                "https://www.omio.com",
                wait_until="domcontentloaded",
                timeout=60_000,
            )

            await _dismiss_cookie_banner(page)
            await _fill_search(page, origin, destination, date)
            await _click_search(page)
            return await _parse_search_results(page, date)

        except Exception:
            logger.exception("Playwright search failed for %s->%s", origin, destination)
            return []
        finally:
            await browser.close()


async def _dismiss_cookie_banner(page) -> None:
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


async def _fill_search(page, origin: str, destination: str, date: str) -> None:
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

    target = datetime.strptime(date, "%Y-%m-%d")

    for _ in range(12):
        day_cells = page.locator('[data-e2e="calendarDay"]')
        count = await day_cells.count()
        for i in range(count):
            cell = day_cells.nth(i)
            date_attr = await cell.get_attribute("date")
            if date_attr and date_attr.startswith(target.strftime("%a %b %d %Y")):
                await cell.click()
                return
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


async def _click_search(page) -> None:
    """Click the search button and wait for results to load."""
    search_btn = page.locator('[data-e2e="buttonSearch"]').first
    await search_btn.click()
    await page.wait_for_load_state("domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(5000)  # Allow results to render


async def _parse_search_results(page, date: str) -> list[TransitOption]:
    """Parse search result cards from the Omio results page."""
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


# ---------------------------------------------------------------------------
# Result card text parsing (shared by Playwright path)
# ---------------------------------------------------------------------------


def _parse_result_card(text: str, date: str) -> TransitOption | None:
    """Parse a single result card's text content into a TransitOption."""
    if not text.strip():
        return None

    time_pattern = re.compile(r"(\d{1,2}:\d{2})")
    times = time_pattern.findall(text)

    price_pattern = re.compile(r"€\s*(\d+(?:[.,]\d+)?)")
    price_match = price_pattern.search(text)

    duration_pattern = re.compile(
        r"(\d+)\s*h\s*(\d+)\s*min|(\d+)\s*h(?!\s*\d)|(\d+)\s*min"
    )
    duration_match = duration_pattern.search(text)

    if len(times) < 2 or not price_match:
        return None

    dep_time_str = times[0]
    arr_time_str = times[1]

    try:
        departure_time = datetime.strptime(f"{date} {dep_time_str}", "%Y-%m-%d %H:%M")
        arrival_time = datetime.strptime(f"{date} {arr_time_str}", "%Y-%m-%d %H:%M")
        if arrival_time <= departure_time:
            arrival_time += timedelta(days=1)
    except ValueError:
        return None

    price_str = price_match.group(1).replace(",", ".")
    try:
        price = float(price_str)
    except ValueError:
        return None

    duration_minutes = int((arrival_time - departure_time).total_seconds() / 60)
    if duration_match:
        groups = duration_match.groups()
        if groups[0] is not None and groups[1] is not None:
            duration_minutes = int(groups[0]) * 60 + int(groups[1])
        elif groups[2] is not None:
            duration_minutes = int(groups[2]) * 60
        elif groups[3] is not None:
            duration_minutes = int(groups[3])

    text_lower = text.lower()
    transport_type = _detect_transport_type(text_lower)
    provider = _detect_provider(text)
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
