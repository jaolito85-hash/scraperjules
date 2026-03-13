from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutingLayer:
    actor_name: str
    min_results: int
    min_contact_ratio: float = 0.0
    min_priced_ratio: float = 0.0
    use_broad_query: bool = False


@dataclass(frozen=True)
class SearchStrategy:
    vertical: str
    goal: str
    layers: tuple[RoutingLayer, ...]


def build_search_strategy(intent, limit: int) -> SearchStrategy:
    target = max(1, min(limit, 5))

    if intent.vertical == "vehicle":
        return SearchStrategy(
            vertical=intent.vertical,
            goal=intent.goal,
            layers=(
                RoutingLayer("automotive_primary", min_results=min(target, 3), min_priced_ratio=0.6),
                RoutingLayer("automotive_secondary", min_results=min(target, 4), min_priced_ratio=0.6),
                RoutingLayer("marketplace", min_results=min(target, 4), min_priced_ratio=0.5),
                RoutingLayer("fallback", min_results=limit, min_priced_ratio=0.4, use_broad_query=True),
            ),
        )

    if intent.vertical == "real_estate":
        return SearchStrategy(
            vertical=intent.vertical,
            goal=intent.goal,
            layers=(
                RoutingLayer("real_estate_primary", min_results=min(target, 3), min_priced_ratio=0.6),
                RoutingLayer("real_estate_secondary", min_results=min(target, 4), min_priced_ratio=0.6),
                RoutingLayer("marketplace", min_results=min(target, 4), min_priced_ratio=0.5),
                RoutingLayer("fallback", min_results=limit, min_priced_ratio=0.4, use_broad_query=True),
            ),
        )

    if intent.vertical == "business_local":
        return SearchStrategy(
            vertical=intent.vertical,
            goal=intent.goal,
            layers=(
                RoutingLayer("b2b_primary", min_results=min(target, 4), min_contact_ratio=0.35),
                RoutingLayer("b2b_enrich", min_results=min(target, 4), min_contact_ratio=0.6),
                RoutingLayer("fallback", min_results=limit, min_contact_ratio=0.3, use_broad_query=True),
            ),
        )

    if intent.vertical == "service_demand":
        return SearchStrategy(
            vertical=intent.vertical,
            goal=intent.goal,
            layers=(
                RoutingLayer("service_demand_search", min_results=min(target, 3)),
                RoutingLayer("service_demand_intent", min_results=min(target, 4)),
                RoutingLayer("fallback", min_results=limit, use_broad_query=True),
            ),
        )

    return SearchStrategy(
        vertical=intent.vertical,
        goal=intent.goal,
        layers=(
            RoutingLayer("product_marketplace", min_results=min(target, 4), min_priced_ratio=0.6),
            RoutingLayer("fallback", min_results=limit, min_priced_ratio=0.4, use_broad_query=True),
        ),
    )

