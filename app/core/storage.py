import json
import os

from app.core.config import settings
from app.core.security import generate_result_id, safe_result_path
from app.models.schemas import ProcessingStatus, RecommendationResult, StatusEnum

# In-memory mapping: response_id -> ProcessingStatus
_status_store: dict[str, ProcessingStatus] = {}
_STATUS_DIR = os.path.join(settings.data_dir, "statuses")


def _ensure_data_dir() -> None:
    os.makedirs(settings.data_dir, exist_ok=True)


async def save_result(result: RecommendationResult) -> str:
    _ensure_data_dir()
    result_id = generate_result_id()
    result.result_id = result_id
    path = safe_result_path(settings.data_dir, result_id)
    if path is None:
        raise ValueError(f"Generated result_id failed validation: {result_id}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))
    return result_id


async def load_result(result_id: str) -> RecommendationResult | None:
    path = safe_result_path(settings.data_dir, result_id)
    if path is None:
        return None
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return RecommendationResult(**data)


async def set_status(response_id: str, status: StatusEnum, result_id: str | None = None, error_message: str | None = None) -> ProcessingStatus:
    ps = ProcessingStatus(
        response_id=response_id,
        status=status,
        result_id=result_id,
        error_message=error_message,
    )
    _status_store[response_id] = ps
    os.makedirs(_STATUS_DIR, exist_ok=True)
    path = os.path.join(_STATUS_DIR, f"{response_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ps.model_dump_json(indent=2))
    return ps


async def get_status(response_id: str) -> ProcessingStatus | None:
    if response_id in _status_store:
        return _status_store[response_id]
    path = os.path.join(_STATUS_DIR, f"{response_id}.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ps = ProcessingStatus(**data)
        _status_store[response_id] = ps
        return ps
    return None


def clear_all_statuses() -> None:
    """Clear in-memory status cache and status files (for testing)."""
    import shutil

    _status_store.clear()
    if os.path.isdir(_STATUS_DIR):
        shutil.rmtree(_STATUS_DIR)
