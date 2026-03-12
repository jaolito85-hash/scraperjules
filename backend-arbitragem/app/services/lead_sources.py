from __future__ import annotations

from app.services.apify_service import (
    ApifyConfigurationError,
    ApifyRunFailedError,
    ApifyTimeoutError,
    is_mock_scraper_enabled,
    run_apify_search,
)
from app.services.mock_leads import build_mock_leads


def search_leads(search_term: str, category: str, limit: int) -> list[dict]:
    if is_mock_scraper_enabled():
        return build_mock_leads(search_term)[:limit]

    return run_apify_search(search_term, category, limit)


__all__ = [
    "ApifyConfigurationError",
    "ApifyRunFailedError",
    "ApifyTimeoutError",
    "search_leads",
]
