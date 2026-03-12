from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

DEFAULT_APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("APIFY_TIMEOUT_SECONDS", "120"))
DEFAULT_POLL_INTERVAL = float(os.getenv("APIFY_POLL_INTERVAL", "3"))
DEFAULT_LIMIT = 10

CATEGORY_DEFAULT_ACTORS = {
    "automotive": "apify/google-search-scraper",
    "auto": "apify/google-search-scraper",
    "real_estate": "apify/google-search-scraper",
    "services": "compass/crawler-google-places",
    "b2b_services": "compass/crawler-google-places",
}

TERMS_COLD = ("consultar", "sob consulta", "nao informado", "indisponivel")


class ApifyConfigurationError(Exception):
    pass


class ApifyRunFailedError(Exception):
    pass


class ApifyTimeoutError(Exception):
    pass


def is_mock_scraper_enabled() -> bool:
    return os.getenv("USE_MOCK_SCRAPER", "").strip().lower() in {"1", "true", "yes", "on"}


def get_actor_id_for_category(category: str) -> str | None:
    return (
        os.getenv(f"APIFY_ACTOR_ID_{category.upper()}")
        or os.getenv("APIFY_ACTOR_ID")
        or CATEGORY_DEFAULT_ACTORS.get(category)
    )


def _get_apify_settings() -> tuple[str, str]:
    token = os.getenv("APIFY_TOKEN", "").strip()
    if not token:
        raise ApifyConfigurationError("APIFY_TOKEN nao configurado.")

    base_url = os.getenv("APIFY_BASE_URL", DEFAULT_APIFY_BASE_URL).rstrip("/")
    return token, base_url


def _get_timeout_seconds() -> int:
    return int(os.getenv("APIFY_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))


def _get_poll_interval_seconds() -> float:
    return float(os.getenv("APIFY_POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL)))


def _get_actor_mode(actor_id: str, category: str) -> str:
    configured_mode = os.getenv("APIFY_ACTOR_MODE", "").strip().lower()
    if configured_mode:
        return configured_mode

    actor_id_normalized = actor_id.lower()
    if "google-places" in actor_id_normalized or "maps" in actor_id_normalized:
        return "google_places"
    if category in {"b2b_services", "services"}:
        return "google_places"
    return "generic_query"


def _build_actor_input(actor_mode: str, search_term: str, category: str, limit: int) -> dict[str, Any]:
    sanitized_limit = max(1, min(limit, 50))
    if actor_mode == "google_places":
        return {
            "searchStringsArray": [search_term],
            "maxCrawledPlaces": sanitized_limit,
            "language": "pt-BR",
            "region": "BR",
            "scrapeContacts": True,
            "scrapeReviewsPersonalData": False,
        }

    if actor_mode == "generic_query":
        return {
            "queries": search_term,
            "maxPagesPerQuery": 1,
            "resultsPerPage": max(sanitized_limit, DEFAULT_LIMIT),
            "mobileResults": False,
            "languageCode": "pt-BR",
            "countryCode": "br",
            "includeUnfilteredResults": False,
            "saveHtml": False,
        }

    return {
        "query": search_term,
        "search": search_term,
        "category": category,
        "limit": sanitized_limit,
        "maxItems": sanitized_limit,
    }


def _request(method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None) -> dict[str, Any]:
    token, base_url = _get_apify_settings()
    response = httpx.request(
        method,
        f"{base_url}{path}",
        params=params,
        json=json,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {"data": payload}


def _start_actor_run(actor_id: str, actor_input: dict[str, Any]) -> str:
    logger.info("Iniciando actor do Apify", extra={"actor_id": actor_id})
    payload = _request(
        "POST",
        f"/acts/{quote(actor_id, safe='')}/runs",
        params={"memory": 2048, "timeout": _get_timeout_seconds()},
        json=actor_input,
    )
    run = payload.get("data") or {}
    run_id = run.get("id")
    if not run_id:
        raise ApifyRunFailedError("Apify nao retornou o id do run.")
    return str(run_id)


def _wait_for_run(run_id: str) -> dict[str, Any]:
    timeout_seconds = _get_timeout_seconds()
    poll_interval = _get_poll_interval_seconds()
    elapsed = 0.0

    while elapsed <= timeout_seconds:
        payload = _request("GET", f"/actor-runs/{run_id}")
        run = payload.get("data") or {}
        status = str(run.get("status", "")).upper()

        if status == "SUCCEEDED":
            return run
        if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
            raise ApifyRunFailedError(f"Actor do Apify terminou com status {status}.")

        logger.info("Aguardando actor do Apify", extra={"run_id": run_id, "status": status})
        time.sleep(poll_interval)
        elapsed += poll_interval

    raise ApifyTimeoutError(f"Actor do Apify excedeu o timeout de {timeout_seconds}s.")


def _read_dataset_items(dataset_id: str, limit: int) -> list[dict[str, Any]]:
    payload = _request(
        "GET",
        f"/datasets/{dataset_id}/items",
        params={"clean": "true", "limit": max(1, min(limit, 50))},
    )
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _first_non_empty(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _join_search_term(search_term: str, value: str | None) -> str:
    if not value:
        return search_term
    if search_term.lower() in value.lower():
        return value
    return f"{search_term} - {value}"


def _pick_phone(item: dict[str, Any]) -> str:
    value = _first_non_empty(item, "phone", "phoneNumber", "telephone", "formattedPhone", "contactPhone")
    if isinstance(value, list):
        value = next((entry for entry in value if entry), "")
    return str(value or "")


def _pick_email(item: dict[str, Any]) -> str:
    value = _first_non_empty(item, "email", "contactEmail", "publicEmail")
    if isinstance(value, list):
        value = next((entry for entry in value if entry), "")
    return str(value or "")


def _pick_link(item: dict[str, Any]) -> str | None:
    value = _first_non_empty(item, "url", "link", "website", "organicUrl", "placeUrl")
    return str(value) if value else None


def _format_price(value: Any) -> str:
    if value in (None, "", [], {}):
        return "Sob consulta"
    if isinstance(value, (int, float)):
        return f"R$ {value:,.0f}".replace(",", ".")
    return str(value)


def _extract_price_from_text(*values: Any) -> str:
    for value in values:
        if not value:
            continue
        match = re.search(r"R\\$\\s?[\\d\\.]+(?:,\\d{2})?", str(value))
        if match:
            return match.group(0)
    return "Sob consulta"


def _normalize_temperature(value: Any, price: str, phone: str, email: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"HOT", "WARM", "COLD"}:
        return normalized
    if normalized in {"QUENTE"}:
        return "HOT"
    if normalized in {"MORNO"}:
        return "WARM"
    if normalized in {"FRIO"}:
        return "COLD"

    if phone or email:
        return "HOT"
    if price and not any(term in price.lower() for term in TERMS_COLD):
        return "WARM"
    return "COLD"


def _build_reason(category: str, temperature: str, phone: str, email: str, link: str | None) -> str:
    contact_score = sum(bool(value) for value in (phone, email, link))
    if temperature == "HOT":
        return f"Lead {category} com maior completude de contato."
    if temperature == "WARM":
        return f"Lead {category} com dados parciais, precisa validacao."
    if contact_score == 0:
        return f"Lead {category} sem contato direto no retorno do actor."
    return f"Lead {category} com baixa confianca de arbitragem."


def _stable_lead_id(item: dict[str, Any], link: str | None, title: str) -> str:
    raw_id = _first_non_empty(item, "id", "placeId", "listingId", "itemId", "adId", "offerId")
    if raw_id:
        return str(raw_id)

    seed = link or title or repr(item)
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def normalize_actor_item(item: dict[str, Any], search_term: str, category: str) -> dict[str, Any]:
    raw_title = _first_non_empty(
        item,
        "title",
        "name",
        "headline",
        "listingTitle",
        "organicTitle",
        "placeName",
        "businessName",
        "description",
    )
    title = _join_search_term(search_term, str(raw_title) if raw_title else None)
    phone = _pick_phone(item)
    email = _pick_email(item)
    link = _pick_link(item)
    price_value = _first_non_empty(item, "price", "priceValue", "amount", "offerPrice")
    price = _format_price(price_value)
    if price == "Sob consulta":
        price = _extract_price_from_text(item.get("description"), raw_title)
    temperature = _normalize_temperature(_first_non_empty(item, "temperature", "score", "leadTemperature"), price, phone, email)
    seller_name = str(
        _first_non_empty(item, "seller_name", "sellerName", "companyName", "ownerName", "contactName", "name")
        or "Oculto"
    )

    return {
        "id": _stable_lead_id(item, link, title),
        "title": title,
        "price": price,
        "temperature": temperature,
        "reason": str(item.get("reason") or _build_reason(category, temperature, phone, email, link)),
        "is_revealed": False,
        "phone": phone,
        "email": email,
        "seller_name": seller_name,
        "link": link,
    }


def _expand_actor_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expanded: list[dict[str, Any]] = []

    for item in items:
        organic_results = item.get("organicResults")
        if isinstance(organic_results, list) and organic_results:
            for organic in organic_results:
                if not isinstance(organic, dict):
                    continue
                expanded.append(
                    {
                        **organic,
                        "searchQuery": item.get("searchQuery"),
                        "resultsTotal": item.get("resultsTotal"),
                    }
                )
            continue

        expanded.append(item)

    return expanded


def run_apify_search(search_term: str, category: str, limit: int) -> list[dict[str, Any]]:
    actor_id = get_actor_id_for_category(category)
    if not actor_id:
        raise ApifyConfigurationError(
            "Nenhum actor do Apify configurado. Defina APIFY_ACTOR_ID ou APIFY_ACTOR_ID_<CATEGORIA>."
        )

    actor_mode = _get_actor_mode(actor_id, category)
    actor_input = _build_actor_input(actor_mode, search_term, category, limit)
    run_id = _start_actor_run(actor_id, actor_input)
    run = _wait_for_run(run_id)

    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise ApifyRunFailedError("O actor do Apify concluiu sem dataset de saida.")

    logger.info("Actor do Apify concluido", extra={"actor_id": actor_id, "run_id": run_id, "dataset_id": dataset_id})
    items = _expand_actor_items(_read_dataset_items(str(dataset_id), limit))
    return [normalize_actor_item(item, search_term, category) for item in items[:limit]]
