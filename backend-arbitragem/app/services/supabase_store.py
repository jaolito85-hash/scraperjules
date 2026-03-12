from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import httpx

DEFAULT_USER_ID = "local-demo-user"
DEFAULT_USER_CREDITS = int(os.getenv("DEFAULT_USER_CREDITS", "100"))
REVEAL_COST = int(os.getenv("REVEAL_COST", "30"))


class CreditsExhaustedError(Exception):
    pass


@lru_cache
def get_supabase_settings() -> tuple[str, str] | None:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not service_role_key:
        return None
    return url, service_role_key


def get_user_external_id(x_user_id: str | None) -> str:
    return (x_user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID


def is_supabase_enabled() -> bool:
    return get_supabase_settings() is not None


def _fallback_profile(external_id: str) -> dict[str, Any]:
    return {
        "id": external_id,
        "external_id": external_id,
        "credits": DEFAULT_USER_CREDITS,
    }


def _headers(*prefer: str) -> dict[str, str] | None:
    settings = get_supabase_settings()
    if settings is None:
        return None

    _, service_role_key = settings
    headers = {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = ",".join(prefer)
    return headers


def _table_url(table_name: str) -> str | None:
    settings = get_supabase_settings()
    if settings is None:
        return None
    base_url, _ = settings
    return f"{base_url}/rest/v1/{table_name}"


def _request(
    method: str,
    table_name: str,
    *,
    params: dict[str, str] | None = None,
    json: Any = None,
    prefer: tuple[str, ...] = (),
) -> Any:
    table_url = _table_url(table_name)
    headers = _headers(*prefer)

    if table_url is None or headers is None:
        return None

    response = httpx.request(
        method,
        table_url,
        params=params,
        json=json,
        headers=headers,
        timeout=20.0,
    )
    response.raise_for_status()
    if not response.content:
        return None
    return response.json()


def get_or_create_profile(external_id: str) -> dict[str, Any]:
    if not is_supabase_enabled():
        return _fallback_profile(external_id)

    created = _request(
        "POST",
        "profiles",
        params={"on_conflict": "external_id", "select": "id,external_id,credits"},
        json={"external_id": external_id, "credits": DEFAULT_USER_CREDITS},
        prefer=("resolution=merge-duplicates", "return=representation"),
    )
    if created:
        return created[0]

    existing = _request(
        "GET",
        "profiles",
        params={
            "external_id": f"eq.{external_id}",
            "select": "id,external_id,credits",
            "limit": "1",
        },
    )
    if existing:
        return existing[0]

    return _fallback_profile(external_id)


def record_search(
    external_id: str,
    search_term: str,
    category: str,
    leads: list[dict],
) -> dict[str, Any]:
    profile = get_or_create_profile(external_id)

    if not is_supabase_enabled():
        return profile

    _request(
        "POST",
        "search_history",
        json={
            "profile_id": profile["id"],
            "search_term": search_term,
            "category": category,
            "result_count": len(leads),
            "raw_response": leads,
        },
    )
    return profile


def hydrate_revealed_leads(external_id: str, leads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not leads or not is_supabase_enabled():
        return leads

    profile = get_or_create_profile(external_id)
    lead_ids = ",".join(f'"{lead["id"]}"' for lead in leads if lead.get("id"))
    if not lead_ids:
        return leads

    revealed_items = _request(
        "GET",
        "revealed_leads",
        params={
            "profile_id": f"eq.{profile['id']}",
            "lead_external_id": f"in.({lead_ids})",
            "select": "lead_external_id,phone,email,seller_name,link",
        },
    ) or []

    revealed_map = {item["lead_external_id"]: item for item in revealed_items}
    hydrated: list[dict[str, Any]] = []

    for lead in leads:
        revealed = revealed_map.get(lead["id"])
        if not revealed:
            hydrated.append(lead)
            continue

        hydrated.append(
            {
                **lead,
                "is_revealed": True,
                "phone": revealed.get("phone", lead.get("phone", "")),
                "email": revealed.get("email", lead.get("email", "")),
                "seller_name": revealed.get("seller_name", lead.get("seller_name", "Oculto")),
                "link": revealed.get("link", lead.get("link")),
            }
        )

    return hydrated


def get_lead_from_history(external_id: str, lead_id: str) -> dict[str, Any] | None:
    if not is_supabase_enabled():
        return None

    profile = get_or_create_profile(external_id)
    search_history = _request(
        "GET",
        "search_history",
        params={
            "profile_id": f"eq.{profile['id']}",
            "select": "raw_response,created_at",
            "order": "created_at.desc",
            "limit": "10",
        },
    ) or []

    for row in search_history:
        raw_response = row.get("raw_response") or []
        if not isinstance(raw_response, list):
            continue

        for lead in raw_response:
            if isinstance(lead, dict) and str(lead.get("id")) == lead_id:
                return lead

    revealed_items = _request(
        "GET",
        "revealed_leads",
        params={
            "profile_id": f"eq.{profile['id']}",
            "lead_external_id": f"eq.{lead_id}",
            "select": "lead_external_id,title,phone,email,seller_name,link",
            "limit": "1",
        },
    ) or []

    if not revealed_items:
        return None

    item = revealed_items[0]
    return {
        "id": item["lead_external_id"],
        "title": item.get("title", "Lead revelado"),
        "phone": item.get("phone", ""),
        "email": item.get("email", ""),
        "seller_name": item.get("seller_name", "Oculto"),
        "link": item.get("link"),
        "is_revealed": True,
        "price": "Sob consulta",
        "temperature": "WARM",
        "reason": "Lead recuperado do historico de reveals.",
    }


def reveal_lead(external_id: str, lead: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_profile(external_id)

    if not is_supabase_enabled():
        remaining_credits = max(int(profile["credits"]) - REVEAL_COST, 0)
        return {
            "credits_remaining": remaining_credits,
            "already_revealed": False,
        }

    existing_reveal = _request(
        "GET",
        "revealed_leads",
        params={
            "profile_id": f"eq.{profile['id']}",
            "lead_external_id": f"eq.{lead['id']}",
            "select": "id",
            "limit": "1",
        },
    )
    if existing_reveal:
        return {
            "credits_remaining": int(profile["credits"]),
            "already_revealed": True,
        }

    current_credits = int(profile["credits"])
    if current_credits < REVEAL_COST:
        raise CreditsExhaustedError("Creditos insuficientes para revelar o lead.")

    remaining_credits = current_credits - REVEAL_COST

    _request(
        "PATCH",
        "profiles",
        params={"id": f"eq.{profile['id']}"},
        json={"credits": remaining_credits},
    )
    _request(
        "POST",
        "revealed_leads",
        json={
            "profile_id": profile["id"],
            "lead_external_id": lead["id"],
            "title": lead["title"],
            "phone": lead["phone"],
            "email": lead["email"],
            "seller_name": lead["seller_name"],
            "cost": REVEAL_COST,
            "link": lead.get("link"),
        },
    )

    return {
        "credits_remaining": remaining_credits,
        "already_revealed": False,
    }
