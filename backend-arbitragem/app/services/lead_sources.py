from __future__ import annotations

from typing import Any

from app.services.apify_service import (
    ApifyConfigurationError,
    ApifyRunFailedError,
    ApifyTimeoutError,
    is_mock_scraper_enabled,
    run_apify_search,
)
from app.services.mock_leads import build_mock_leads
from app.services.openai_service import analyze_search_intent, enrich_and_rank_leads, resolve_pipeline_category


def search_leads(search_term: str, category: str, limit: int) -> list[dict]:
    if is_mock_scraper_enabled():
        return build_mock_leads(search_term)[:limit]

    intent = analyze_search_intent(search_term, category)
    pipeline_category = resolve_pipeline_category(intent)
    queries = [intent.primary_query, *intent.alternate_queries]
    collected: list[dict[str, Any]] = []
    last_error: Exception | None = None

    for query in _dedupe_queries(queries, fallback=search_term):
        remaining = max(limit - len(collected), 1)
        try:
            results = run_apify_search(query, pipeline_category, remaining)
        except (ApifyConfigurationError, ApifyRunFailedError, ApifyTimeoutError) as exc:
            last_error = exc
            continue

        collected = _dedupe_leads([*collected, *results], limit)
        if len(collected) >= limit:
            break

    if not collected:
        if last_error is not None:
            raise last_error
        return []

    return enrich_and_rank_leads(
        collected[:limit],
        intent,
        original_search_term=search_term,
        category=pipeline_category,
    )


def _dedupe_queries(queries: list[str], *, fallback: str) -> list[str]:
    deduped: list[str] = []
    for query in [*queries, fallback]:
        normalized = " ".join(str(query or "").split()).strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _dedupe_leads(leads: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lead in leads:
        key = str(lead.get("id") or lead.get("link") or lead.get("title"))
        if not key or key in seen:
            continue
        deduped.append(lead)
        seen.add(key)
        if len(deduped) >= limit:
            break
    return deduped


__all__ = [
    "ApifyConfigurationError",
    "ApifyRunFailedError",
    "ApifyTimeoutError",
    "search_leads",
]
