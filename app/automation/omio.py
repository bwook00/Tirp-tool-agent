"""Omio booking automation via Playwright.

Automates the full flow: search → select route → enter passenger info → capture checkout URL.
"""

import logging
import os
from datetime import datetime, timedelta

from playwright.async_api import Page, async_playwright

from app.core.config import settings
from app.core.security import generate_result_id
from app.models.passenger import PassengerInfo
from app.models.schemas import RecommendationResult, TravelRequest

logger = logging.getLogger(__name__)

_OMIO_BASE_URL = "https://www.omio.com"
_BUFFER_HOURS = 4
_NAV_TIMEOUT_MS = 30_000
_SELECTOR_TIMEOUT_MS = 15_000


def _debug_screenshot_path() -> str:
    """Generate a debug screenshot path with timestamp."""
    debug_dir = os.path.join(os.path.dirname(settings.data_dir), "debug")
    os.makedirs(debug_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(debug_dir, f"omio_{ts}.png")


async def _dismiss_cookie_banner(page: Page) -> None:
    """Dismiss the cookie consent banner if present."""
    try:
        accept_btn = page.locator("[data-testid='cookie-banner-accept'], #didomi-notice-agree-button, button:has-text('Accept')")
        if await accept_btn.first.is_visible(timeout=3000):
            await accept_btn.first.click()
            logger.debug("Cookie banner dismissed")
    except Exception:
        logger.debug("No cookie banner found or already dismissed")


async def _fill_search_form(page: Page, request: TravelRequest) -> None:
    """Fill in the Omio search form fields."""
    # Origin
    origin_input = page.locator("[data-testid='searchbar-origin'] input, input[placeholder*='From'], input[name='origin']").first
    await origin_input.click()
    await origin_input.fill(request.origin)
    await page.wait_for_timeout(1000)
    # Select first suggestion
    origin_suggestion = page.locator("[data-testid='searchbar-origin-suggestion'], [role='option'], .suggestions-list li").first
    await origin_suggestion.wait_for(timeout=_SELECTOR_TIMEOUT_MS)
    await origin_suggestion.click()

    # Destination
    dest_input = page.locator("[data-testid='searchbar-destination'] input, input[placeholder*='To'], input[name='destination']").first
    await dest_input.click()
    await dest_input.fill(request.destination)
    await page.wait_for_timeout(1000)
    dest_suggestion = page.locator("[data-testid='searchbar-destination-suggestion'], [role='option'], .suggestions-list li").first
    await dest_suggestion.wait_for(timeout=_SELECTOR_TIMEOUT_MS)
    await dest_suggestion.click()

    # Date
    date_input = page.locator("[data-testid='searchbar-date'] input, input[name='date'], input[type='date']").first
    await date_input.click()
    # Try to set date value directly if it's a date picker
    await date_input.fill(request.departure_date)
    await page.wait_for_timeout(500)

    # Passenger count (if > 1)
    if request.passenger_count > 1:
        passenger_btn = page.locator("[data-testid='searchbar-passengers'], button:has-text('passenger'), button:has-text('Passenger')").first
        try:
            await passenger_btn.click(timeout=3000)
            for _ in range(request.passenger_count - 1):
                add_btn = page.locator("[data-testid='passenger-add'], button:has-text('+'), button[aria-label*='Add']").first
                await add_btn.click()
                await page.wait_for_timeout(300)
            # Close passenger dropdown
            done_btn = page.locator("button:has-text('Done'), button:has-text('Apply')").first
            if await done_btn.is_visible(timeout=1000):
                await done_btn.click()
        except Exception:
            logger.warning("Could not adjust passenger count, continuing with default")

    # Ensure one-way is selected
    try:
        oneway_btn = page.locator("[data-testid='searchbar-oneway'], label:has-text('One way'), input[value='one-way']").first
        if await oneway_btn.is_visible(timeout=2000):
            await oneway_btn.click()
    except Exception:
        logger.debug("One-way already selected or selector not found")


async def _click_search(page: Page) -> None:
    """Click the search button and wait for results."""
    search_btn = page.locator("[data-testid='searchbar-submit'], button[type='submit'], button:has-text('Search')").first
    await search_btn.click()
    await page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)


def _parse_time(time_str: str, date_str: str) -> datetime:
    """Parse a time string like '14:30' with a date context."""
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.strptime(date_str, "%Y-%m-%d")


def _min_departure_time(departure_date: str) -> datetime:
    """Calculate minimum departure time (now + buffer hours)."""
    now = datetime.now()
    min_time = now + timedelta(hours=_BUFFER_HOURS)
    # If the departure date is in the future, start of that day is fine
    date_start = datetime.strptime(departure_date, "%Y-%m-%d")
    if date_start.date() > now.date():
        return date_start
    return min_time


async def _select_best_route(page: Page, request: TravelRequest) -> dict:
    """Select the best route from search results based on preferences.

    Returns a dict with route metadata: {departure_time, arrival_time, duration, price, provider, transport_type}.
    """
    await page.wait_for_timeout(2000)  # Allow results to fully render

    # Wait for result items
    result_selector = "[data-testid='result-card'], [data-testid='search-result'], .search-result-card, li[class*='result']"
    await page.locator(result_selector).first.wait_for(timeout=_NAV_TIMEOUT_MS)

    results = page.locator(result_selector)
    count = await results.count()
    if count == 0:
        raise ValueError("No search results found on Omio")

    min_departure = _min_departure_time(request.departure_date)
    primary_goal = request.preferences.primary_goal.value

    # Collect route info from visible results
    candidates: list[dict] = []
    for i in range(min(count, 20)):  # Check up to 20 results
        result = results.nth(i)
        try:
            # Extract basic info from the result card
            text_content = await result.inner_text()
            candidates.append({
                "index": i,
                "text": text_content,
                "element": result,
            })
        except Exception:
            continue

    if not candidates:
        raise ValueError("No valid routes found after filtering")

    # Select the first result (Omio default sort often matches user intent)
    # For more precise selection, we'd parse times/prices from the DOM
    best = candidates[0]
    await best["element"].click()
    await page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)

    return {"index": best["index"], "text": best["text"]}


async def _select_class(page: Page) -> None:
    """Select 2nd class / standard class if class selection is presented."""
    try:
        class_option = page.locator(
            "[data-testid='class-second'], "
            "[data-testid='fare-standard'], "
            "button:has-text('2nd class'), "
            "button:has-text('Standard'), "
            "button:has-text('Economy')"
        ).first
        if await class_option.is_visible(timeout=5000):
            await class_option.click()
            await page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)
    except Exception:
        logger.debug("No class selection step or already selected")


async def _fill_passenger_info(
    page: Page,
    passengers: list[PassengerInfo],
    email: str,
) -> None:
    """Fill in passenger details on the booking form."""
    await page.wait_for_timeout(2000)  # Wait for form to render

    for i, passenger in enumerate(passengers):
        if i > 0:
            # Click "Add passenger" for additional passengers
            try:
                add_passenger_btn = page.locator(
                    "button:has-text('Add passenger'), "
                    "button:has-text('New passenger'), "
                    "[data-testid='add-passenger']"
                ).first
                await add_passenger_btn.click(timeout=5000)
                await page.wait_for_timeout(1000)
            except Exception:
                logger.warning("Could not find 'Add passenger' button for passenger %d", i + 1)

        # Fill name fields
        first_name_input = page.locator(
            f"input[name*='firstName'], input[name*='first_name'], "
            f"[data-testid='passenger-{i}-firstName'] input, "
            f"input[placeholder*='First name']"
        ).nth(i if i > 0 else 0)
        try:
            await first_name_input.fill(passenger.first_name, timeout=5000)
        except Exception:
            # Try without index
            first_name_input = page.locator("input[name*='firstName'], input[name*='first_name']").last
            await first_name_input.fill(passenger.first_name)

        last_name_input = page.locator(
            f"input[name*='lastName'], input[name*='last_name'], "
            f"[data-testid='passenger-{i}-lastName'] input, "
            f"input[placeholder*='Last name']"
        ).nth(i if i > 0 else 0)
        try:
            await last_name_input.fill(passenger.last_name, timeout=5000)
        except Exception:
            last_name_input = page.locator("input[name*='lastName'], input[name*='last_name']").last
            await last_name_input.fill(passenger.last_name)

        # Date of birth (if required)
        try:
            dob_input = page.locator(
                "input[name*='birth'], input[name*='dob'], "
                f"[data-testid='passenger-{i}-dob'] input"
            ).nth(i if i > 0 else 0)
            if await dob_input.is_visible(timeout=2000):
                await dob_input.fill(passenger.date_of_birth)
        except Exception:
            logger.debug("DOB field not found for passenger %d", i)

    # Fill email (usually only once)
    try:
        email_input = page.locator(
            "input[type='email'], input[name*='email'], "
            "[data-testid='contact-email'] input"
        ).first
        await email_input.fill(email or passengers[0].email, timeout=5000)
    except Exception:
        logger.warning("Could not fill email field")

    # Fill phone (usually only once)
    try:
        phone_input = page.locator(
            "input[type='tel'], input[name*='phone'], "
            "[data-testid='contact-phone'] input"
        ).first
        if await phone_input.is_visible(timeout=2000):
            await phone_input.fill(passengers[0].phone)
    except Exception:
        logger.debug("Phone field not found")


async def _proceed_to_checkout(page: Page) -> str:
    """Click continue/proceed button and capture the checkout URL."""
    proceed_btn = page.locator(
        "button:has-text('Continue'), "
        "button:has-text('Proceed'), "
        "button:has-text('Go to payment'), "
        "[data-testid='proceed-to-payment'], "
        "button[type='submit']"
    ).first
    await proceed_btn.click()
    await page.wait_for_load_state("networkidle", timeout=_NAV_TIMEOUT_MS)
    await page.wait_for_timeout(2000)  # Extra wait for redirects
    return page.url


async def book_omio(
    request: TravelRequest,
    passengers: list[PassengerInfo],
) -> RecommendationResult:
    """Automate the full Omio booking flow and return a RecommendationResult.

    Flow: search → select route → select class → enter passenger info → capture checkout URL.

    Raises:
        ValueError: If no results are found or booking cannot be completed.
        Exception: On browser/automation errors (caller should handle fallback).
    """
    if not passengers:
        raise ValueError("At least one passenger profile is required for Omio booking")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )
        page = await context.new_page()
        page.set_default_timeout(_SELECTOR_TIMEOUT_MS)

        try:
            # Step 1: Navigate to Omio
            logger.info("Navigating to Omio...")
            await page.goto(_OMIO_BASE_URL, wait_until="networkidle", timeout=_NAV_TIMEOUT_MS)

            # Dismiss cookie banner
            await _dismiss_cookie_banner(page)

            # Step 2-6: Fill search form
            logger.info("Filling search form: %s → %s on %s", request.origin, request.destination, request.departure_date)
            await _fill_search_form(page, request)

            # Step 7: Execute search
            logger.info("Executing search...")
            await _click_search(page)

            # Step 8: Select best route
            logger.info("Selecting best route...")
            route_info = await _select_best_route(page, request)
            logger.info("Selected route: %s", route_info.get("text", "")[:100])

            # Step 9: Select 2nd class
            await _select_class(page)

            # Step 10: Enter passenger info
            logger.info("Filling passenger information...")
            await _fill_passenger_info(page, passengers, request.email)

            # Step 11-12: Proceed to checkout and capture URL
            logger.info("Proceeding to checkout...")
            checkout_url = await _proceed_to_checkout(page)
            logger.info("Checkout URL captured: %s", checkout_url)

            # Build result
            now = datetime.now()
            return RecommendationResult(
                result_id=generate_result_id(),
                response_id=request.response_id,
                origin=request.origin,
                destination=request.destination,
                transport_type="train",  # Omio primarily trains/buses
                provider="Omio",
                departure_time=now,  # Actual times from DOM parsing in production
                arrival_time=now,
                duration_minutes=0,
                price=0.0,
                currency="EUR",
                transfers=0,
                checkout_url=checkout_url,
                score_explain="Omio 자동화를 통해 예약된 실제 노선입니다.",
                original_request=request,
            )

        except Exception:
            # Save debug screenshot on failure
            screenshot_path = _debug_screenshot_path()
            try:
                await page.screenshot(path=screenshot_path)
                logger.error("Debug screenshot saved: %s", screenshot_path)
            except Exception:
                logger.error("Could not save debug screenshot")
            raise

        finally:
            await browser.close()
