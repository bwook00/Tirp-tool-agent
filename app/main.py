from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import api, webhook, pages

app = FastAPI(title="Tirp-tool-agent", version="0.1.0")

# Static files & templates
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=BASE_DIR.parent / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Routers
app.include_router(api.router)
app.include_router(webhook.router)
app.include_router(pages.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
