from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from supabase import Client, create_client

DEFAULT_USER_ID = "local-demo-user"
DEFAULT_USER_CREDITS = int(os.getenv("DEFAULT_USER_CREDITS", "100"))
REVEAL_COST = int(os.getenv("REVEAL_COST", "30"))


class CreditsExhaustedError(Exception):
    pass


@lru_cache
def get_supabase_client() -> Client | None:
    url = os.getenv("SUPABASE_URL")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not service_role_key:
        return None

    return create_client(url, service_role_key)


def get_user_external_id(x_user_id: str | None) -> str:
    return (x_user_id or DEFAULT_USER_ID).strip() or DEFAULT_USER_ID


def is_supabase_enabled() -> bool:
    return get_supabase_client() is not None


def get_or_create_profile(external_id: str) -> dict[str, Any]:
    client = get_supabase_client()
    fallback_profile = {
        "id": external_id,
        "external_id": external_id,
        "credits": DEFAULT_USER_CREDITS,
    }

    if client is None:
        return fallback_profile

    existing = (
        client.table("profiles")
        .select("id, external_id, credits")
        .eq("external_id", external_id)
        .limit(1)
        .execute()
    )

    if existing.data:
        return existing.data[0]

    created = (
        client.table("profiles")
        .insert({"external_id": external_id, "credits": DEFAULT_USER_CREDITS})
        .execute()
    )
    return created.data[0]


def record_search(external_id: str, search_term: str, category: str, leads: list[dict]) -> dict[str, Any]:
    profile = get_or_create_profile(external_id)
    client = get_supabase_client()

    if client is None:
        return profile

    client.table("search_history").insert(
        {
            "profile_id": profile["id"],
            "search_term": search_term,
            "category": category,
            "result_count": len(leads),
            "raw_response": leads,
        }
    ).execute()

    return profile


def reveal_lead(external_id: str, lead: dict[str, Any]) -> dict[str, Any]:
    profile = get_or_create_profile(external_id)
    client = get_supabase_client()

    if client is None:
        remaining_credits = max(int(profile["credits"]) - REVEAL_COST, 0)
        return {
            "credits_remaining": remaining_credits,
            "already_revealed": False,
        }

    existing_reveal = (
        client.table("revealed_leads")
        .select("id")
        .eq("profile_id", profile["id"])
        .eq("lead_external_id", lead["id"])
        .limit(1)
        .execute()
    )

    if existing_reveal.data:
        return {
            "credits_remaining": int(profile["credits"]),
            "already_revealed": True,
        }

    current_credits = int(profile["credits"])
    if current_credits < REVEAL_COST:
        raise CreditsExhaustedError("Creditos insuficientes para revelar o lead.")

    remaining_credits = current_credits - REVEAL_COST

    client.table("profiles").update({"credits": remaining_credits}).eq("id", profile["id"]).execute()
    client.table("revealed_leads").insert(
        {
            "profile_id": profile["id"],
            "lead_external_id": lead["id"],
            "title": lead["title"],
            "phone": lead["phone"],
            "email": lead["email"],
            "seller_name": lead["seller_name"],
            "cost": REVEAL_COST,
            "link": lead.get("link"),
        }
    ).execute()

    return {
        "credits_remaining": remaining_credits,
        "already_revealed": False,
    }
