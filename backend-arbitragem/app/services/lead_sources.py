from __future__ import annotations

from typing import Any

from app.services.apify_service import (
    ApifyConfigurationError,
    ApifyRunFailedError,
    ApifyTimeoutError,
    is_mock_scraper_enabled,
    run_apify_layer,
)
from app.services.mock_leads import build_mock_leads
from app.services.openai_service import analyze_search_intent, enrich_and_rank_leads, resolve_pipeline_category
from app.services.search_strategy import RoutingLayer, build_search_strategy


def search_leads(search_term: str, category: str, limit: int) -> list[dict]:
    if is_mock_scraper_enabled():
        return build_mock_leads(search_term)[:limit]

    intent = analyze_search_intent(search_term, category)
    pipeline_category = resolve_pipeline_category(intent)
    strategy = build_search_strategy(intent, limit)
    collected: list[dict[str, Any]] = []
    last_error: Exception | None = None

    for layer in strategy.layers:
        query = _query_for_layer(intent, search_term, layer)
        try:
            collected = run_apify_layer(
                query,
                pipeline_category,
                layer.actor_name,
                limit,
                intent=intent,
                existing_leads=collected,
            )
        except (ApifyConfigurationError, ApifyRunFailedError, ApifyTimeoutError) as exc:
            last_error = exc
            continue

        ranked = enrich_and_rank_leads(
            collected[:limit],
            intent,
            original_search_term=search_term,
            category=pipeline_category,
            apply_reason_enrichment=False,
        )
        if not _should_continue(layer, ranked, limit):
            collected = ranked
            break
        collected = ranked

    if not collected:
        if isinstance(last_error, ApifyTimeoutError):
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


def _query_for_layer(intent, search_term: str, layer: RoutingLayer) -> str:
    if layer.actor_name == "service_demand_intent":
        return next((query for query in intent.alternate_queries if query), intent.primary_query or search_term)
    if layer.use_broad_query:
        return search_term
    return intent.primary_query or search_term


def _should_continue(layer: RoutingLayer, ranked: list[dict[str, Any]], limit: int) -> bool:
    if not ranked:
        return True
    if len(ranked) >= limit:
        return False
    if len(ranked) < layer.min_results:
        return True
    contact_ratio = _ratio(ranked, lambda lead: bool(lead.get("phone") or lead.get("email")))
    priced_ratio = _ratio(ranked, lambda lead: str(lead.get("price") or "").lower() != "sob consulta")
    if contact_ratio < layer.min_contact_ratio:
        return True
    if priced_ratio < layer.min_priced_ratio:
        return True
    return False


def _ratio(leads: list[dict[str, Any]], predicate) -> float:
    if not leads:
        return 0.0
    hits = sum(1 for lead in leads if predicate(lead))
    return hits / len(leads)


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
