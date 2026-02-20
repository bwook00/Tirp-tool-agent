import re
import uuid
from pathlib import Path

_UUID4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def generate_result_id() -> str:
    """Generate a cryptographically random UUID4 result_id."""
    return str(uuid.uuid4())


def validate_result_id(result_id: str) -> bool:
    """Validate that a result_id is a proper UUID4 format. Prevents directory traversal."""
    return bool(_UUID4_PATTERN.match(result_id))


def safe_result_path(data_dir: str, result_id: str) -> str | None:
    """Build a safe file path for result_id, preventing directory traversal.

    Returns None if the ID is invalid.
    """
    if not validate_result_id(result_id):
        return None
    base = Path(data_dir).resolve()
    target = (base / f"{result_id}.json").resolve()
    if not str(target).startswith(str(base)):
        return None
    return str(target)
