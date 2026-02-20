# CLAUDE.md

## Project

Tirp-tool-agent — **Emergency Transit Rescue** service.
Users fill out a Typeform survey about their disrupted travel, and an LLM agent finds the best alternative transit option.
Single Python FastAPI service. No frontend framework.

## Repository

- Remote: https://github.com/bwook00/Tirp-tool-agent.git
- Branch: main
- Python 3.11+

## Tech Stack

- **Web**: FastAPI + Uvicorn, Jinja2 templates
- **LLM**: Claude API (tool-use), Pydantic v2
- **MCP Tools**: `search_trains`, `search_flights`, `search_buses`, `get_checkout_link`
- **Survey**: Typeform (webhook only — no custom survey UI)
- **Storage**: file-based JSON (no database)

## Architecture — User Flow

1. User clicks Typeform link → fills out disrupted-travel survey
2. Survey completion triggers two things simultaneously: webhook `POST /webhook/typeform` + user redirect to `/wait`
3. Agent processes the request → calls MCP tools (trains/flights/buses) → scores options → picks Top 1
4. Waiting page polls `/api/status/{response_id}` → redirects to `/r/{result_id}` when ready
5. Result page shows recommendation; user clicks "Open Checkout" → external booking site

## Project Structure

```
app/
  main.py              # FastAPI app entry point
  routers/             # Route handlers (webhook, api, pages)
  core/                # Agent logic, scoring, config
  tools/               # MCP tool definitions
  models/              # Pydantic models
  templates/           # Jinja2 HTML templates
data/results/          # Stored results (gitignored)
static/                # Static assets (CSS, JS)
tests/                 # Test suite
requirements.txt
.env.example
.gitignore
CLAUDE.md
```

## Endpoints

| Method | Path                       | Purpose                  |
|--------|----------------------------|--------------------------|
| POST   | `/webhook/typeform`        | Typeform webhook 수신     |
| GET    | `/api/status/{response_id}`| 처리 상태 폴링             |
| GET    | `/api/results/{result_id}` | 결과 JSON                |
| GET    | `/wait`                    | 대기 페이지 (polling UI)   |
| GET    | `/r/{result_id}`           | 결과 페이지 (HTML)         |
| GET    | `/health`                  | Health check             |

## Domain Models (Pydantic)

- **TypeformWebhookPayload** — Typeform webhook 요청 파싱
- **TravelRequest** — 사용자 여행 정보 (출발지, 도착지, 일시 등)
- **TransitOption** — 단일 교통 옵션 (열차/항공/버스)
- **ScoredOption** — 스코어링된 교통 옵션
- **RecommendationResult** — 최종 추천 결과 (Top 1 + 메타데이터)
- **ProcessingStatus** — 처리 상태 (pending / processing / done / error)

## Development

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API keys

# Run
uvicorn app.main:app --reload --port 8000

# Test
pytest tests/ -v

# Local webhook testing (ngrok HTTPS URL → Typeform webhook endpoint)
ngrok http 8000
```

## Environment Variables

| Variable           | Purpose                              |
|--------------------|--------------------------------------|
| `ANTHROPIC_API_KEY`| Claude API 인증                       |
| `TYPEFORM_SECRET`  | Webhook 서명 검증                      |
| `DATA_DIR`         | 결과 저장 경로 (기본: `./data/results`) |

## Non-Goals

- No 사용자 인증/계정 시스템
- No DB (file-based JSON only)
- No 프론트엔드 프레임워크 (React, Next.js, Vue 등)
- No 설문 UI (Typeform 전적 사용)
- No 랜딩 페이지
- No 결제 처리
- No Docker/배포 설정 (당분간)

## Conventions

- `async def` 사용 (모든 라우트 핸들러 & I/O 함수)
- Python 3.11+ 타입 힌트 필수
- Absolute imports (`from app.models.travel import TravelRequest`)
- `snake_case` — 파일명, 함수명, 변수명
- `PascalCase` — Pydantic 모델, 클래스
- API 라우트 에러 → `HTTPException` raise
- HTML 라우트 에러 → template error page 렌더

## Issue Tracking

- **M0 Foundation**: #16 Bootstrap FastAPI, #17 CLAUDE.md update
- **M1 Storage & Display**: #18 Results Storage API, #19 Result Page, #20 Waiting Page
- **M2 Survey Flow**: #21 Typeform webhook, #22 Connect webhook to pipeline
- **M3 Agent Core**: #14 MCP tools, #15 LLM Agent
- **M4 Integration**: #23 Replace stub with real agent
- **M5 Expiration**: #11 Checkout expiration handling
- **M6 Security**: #12 Secure result_id generation
