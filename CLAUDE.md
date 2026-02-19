# Emergency Transit Rescue Agent — MVP Context (CLAUDE.md)

## What we are building
A web-based emergency booking assistant for EU travel disruptions.
User fills a short survey (from/to/date/time/pax + preferences). The system selects the single best next option
(train/bus/flight) and returns a Results URL that shows the top recommendation and a checkout link button.

Key idea: **Output is a Results URL**, not email by default.

## Core constraints (MVP)
- Modes supported: Train / Bus / Flight only.
- Strike detection is user-triggered: user clicks "위급 상황 발생" to open the survey.
- Recommend **Top 1** option only.
- Checkout link should be "card-number-only" style (external checkout URL). For MVP we mock the provider.
- Traveler profile is assumed to exist locally (json/md). Only required field for MVP: email (optional in output).
- Delivery channel: Results URL page. Email/SMS/Slack are NOT required for MVP.

## Primary UX
1) `/emergency` survey page
2) submit -> server runs agent -> creates `result_id`
3) redirect user to `/r/{result_id}`
4) `/r/{result_id}` shows:
   - itinerary summary card
   - "Open checkout" button
   - "Copy link" button
   - error/empty state

## Architecture overview
- Web app: Next.js (UI + API routes)
- Results storage: file-based JSON in `./data/results/{id}.json` (MVP)
- Agent core:
  - `BookingProvider` interface:
    - `search(request) -> itineraries[]`
    - `createCheckout(itinerary, travelerProfile) -> { checkout_url, expires_at }`
  - MVP uses `MockBookingProvider`
  - `scoreAndPickTop1(itineraries, preferences) -> top1`

## Data model (MVP)
### EmergencyRequest
- from: string
- to: string
- earliest_departure_datetime: ISO string
- pax_count: number
- preferences: object (survey outputs)

### Result payload (stored by result_id)
- result_id: string
- created_at: ISO string
- request: EmergencyRequest (no sensitive personal data)
- recommendation:
  - itinerary: normalized itinerary (mode, depart/arrive, duration, price, transfers, provider)
  - score_explain: optional
- checkout:
  - checkout_url: string
  - expires_at: ISO string | null

## Preferences (survey fields)
Minimum set:
- primary_goal: fastest | cheapest | fewest_transfers | flexible_change
- max_transfers: 0 | 1 | 2 | any
- mode_preference: any | train | bus | flight
- avoid_night: boolean
- avoid_long_layover: boolean (optional)

## Non-goals (explicitly out of scope for MVP)
- Real provider integrations (Omio, rail APIs, airline booking)
- Authentication / user accounts
- SMS / Kakao / Slack / Discord delivery
- Complex traveler profile requirements (passport/DoB/etc)
- Multiple recommendations or comparison UI (Top 1 only)

## Repository structure (suggested)
- /app
  - /emergency (survey page)
  - /r/[result_id] (results page)
- /pages/api or /app/api
  - /results (POST)
  - /results/[id] (GET)
  - /emergency/run (POST)
- /src
  - /agent (core logic)
  - /providers (BookingProvider + Mock)
  - /models (types)
- /data/results (file storage, gitignored)

## Local run
- `cp .env.example .env`
- `npm install`
- `npm run dev`
- Visit `/emergency`

## Coding principles
- Keep the MVP minimal and composable:
  - UI should not know provider details.
  - Agent core should be testable without UI.
- Prefer deterministic behavior for tests (seeded mock itineraries).
- Never store sensitive PII in results payload.

## How to extend after MVP
- Add real BookingProvider integration
- Add delivery channels (email/Slack/Discord) as optional adapters
- Add retry behavior (if checkout URL fails, try top2/top3)
- Add caching + expiration handling
