from datetime import datetime

from app.models.schemas import RecommendationResult


def is_expired(result: RecommendationResult) -> bool:
    """Check whether a recommendation result's checkout link has expired."""
    if result.expires_at is None:
        return False
    return result.expires_at < datetime.utcnow()
