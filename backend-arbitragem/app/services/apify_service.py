from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

DEFAULT_APIFY_BASE_URL = "https://api.apify.com/v2"
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("APIFY_TIMEOUT_SECONDS", "120"))
DEFAULT_POLL_INTERVAL = float(os.getenv("APIFY_POLL_INTERVAL", "3"))
DEFAULT_LIMIT = 10
MAX_LIMIT = 50
TERMS_COLD = ("consultar", "sob consulta", "nao informado", "indisponivel")
BRAZILIAN_STATES = {
    "ac": "acre",
    "al": "alagoas",
    "ap": "amapa",
    "am": "amazonas",
    "ba": "bahia",
    "ce": "ceara",
    "df": "distrito federal",
    "es": "espirito santo",
    "go": "goias",
    "ma": "maranhao",
    "mt": "mato grosso",
    "ms": "mato grosso do sul",
    "mg": "minas gerais",
    "pa": "para",
    "pb": "paraiba",
    "pr": "parana",
    "pe": "pernambuco",
    "pi": "piaui",
    "rj": "rio de janeiro",
    "rn": "rio grande do norte",
    "rs": "rio grande do sul",
    "ro": "rondonia",
    "rr": "roraima",
    "sc": "santa catarina",
    "sp": "sao paulo",
    "se": "sergipe",
    "to": "tocantins",
}


class ApifyConfigurationError(Exception):
    pass


class ApifyRunFailedError(Exception):
    pass


class ApifyTimeoutError(Exception):
    pass


@dataclass(frozen=True)
class ActorCandidate:
    name: str
    env_key: str
    default_actor_id: str | None
    mode: str
    optional: bool = False
    enrich: bool = False


@dataclass(frozen=True)
class SearchContext:
    search_term: str
    category: str
    limit: int
    existing_leads: tuple[dict[str, Any], ...] = ()


CATEGORY_PIPELINES: dict[str, list[ActorCandidate]] = {
    "b2b_services": [
        ActorCandidate("b2b_primary", "APIFY_ACTOR_ID_B2B_SERVICES", "compass/crawler-google-places", "google_places"),
        ActorCandidate("b2b_enrich", "APIFY_ACTOR_ID_B2B_ENRICH", "vdrmota/contact-info-scraper", "contact_enrich", optional=True, enrich=True),
        ActorCandidate("fallback", "APIFY_ACTOR_ID_FALLBACK", "apify/google-search-scraper", "generic_query"),
    ],
    "automotive": [
        ActorCandidate("automotive_primary", "APIFY_ACTOR_ID_AUTOMOTIVE_PRIMARY", "ribtools/webmotors-scraper", "webmotors", optional=True),
        ActorCandidate("automotive_secondary", "APIFY_ACTOR_ID_AUTOMOTIVE_SECONDARY", "israeloriente/olx-cars-scraper", "olx_cars", optional=True),
        ActorCandidate("marketplace", "APIFY_ACTOR_ID_MARKETPLACE", "apify/facebook-marketplace-scraper", "marketplace", optional=True),
        ActorCandidate("fallback", "APIFY_ACTOR_ID_FALLBACK", "apify/google-search-scraper", "generic_query"),
    ],
    "real_estate": [
        ActorCandidate("real_estate_primary", "APIFY_ACTOR_ID_REAL_ESTATE_PRIMARY", "viralanalyzer/brazil-real-estate-scraper", "brazil_real_estate", optional=True),
        ActorCandidate("real_estate_secondary", "APIFY_ACTOR_ID_REAL_ESTATE_SECONDARY", "fatihtahta/zap-imoveis-scraper", "zap_imoveis", optional=True),
        ActorCandidate("marketplace", "APIFY_ACTOR_ID_MARKETPLACE", "apify/facebook-marketplace-scraper", "marketplace", optional=True),
        ActorCandidate("fallback", "APIFY_ACTOR_ID_FALLBACK", "apify/google-search-scraper", "generic_query"),
    ],
}

LEGACY_CATEGORY_ENV_KEYS = {
    "automotive": "APIFY_ACTOR_ID_AUTOMOTIVE",
    "real_estate": "APIFY_ACTOR_ID_REAL_ESTATE",
    "b2b_services": "APIFY_ACTOR_ID_B2B_SERVICES",
}


def is_mock_scraper_enabled() -> bool:
    return os.getenv("USE_MOCK_SCRAPER", "").strip().lower() in {"1", "true", "yes", "on"}


def get_actor_id_for_category(category: str) -> str | None:
    pipeline = CATEGORY_PIPELINES.get(category, [])
    if pipeline:
        first = pipeline[0]
        resolved = _resolve_actor_id(first, category)
        if resolved:
            return resolved
    return os.getenv(f"APIFY_ACTOR_ID_{category.upper()}") or os.getenv("APIFY_ACTOR_ID")


def _resolve_actor_id(candidate: ActorCandidate, category: str) -> str | None:
    if candidate.env_key:
        value = os.getenv(candidate.env_key, "").strip()
        if value:
            return value

    if candidate.name == "fallback":
        fallback_value = os.getenv("APIFY_ACTOR_ID", "").strip()
        if fallback_value:
            return fallback_value

    legacy_env = LEGACY_CATEGORY_ENV_KEYS.get(category)
    if legacy_env and not candidate.enrich and "FALLBACK" not in candidate.env_key and "MARKETPLACE" not in candidate.env_key:
        legacy_value = os.getenv(legacy_env, "").strip()
        if legacy_value:
            return legacy_value

    if candidate.default_actor_id:
        return candidate.default_actor_id

    return None


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


def _sanitize_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


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
        params={"clean": "true", "limit": _sanitize_limit(limit)},
    )
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _run_actor(actor_id: str, actor_input: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    run_id = _start_actor_run(actor_id, actor_input)
    run = _wait_for_run(run_id)
    dataset_id = run.get("defaultDatasetId")
    if not dataset_id:
        raise ApifyRunFailedError("O actor do Apify concluiu sem dataset de saida.")
    logger.info("Actor do Apify concluido", extra={"actor_id": actor_id, "run_id": run_id, "dataset_id": dataset_id})
    return _read_dataset_items(str(dataset_id), limit)


def _first_non_empty(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _nested_first(item: Any, *paths: str) -> Any:
    for path in paths:
        current = item
        valid = True
        for segment in path.split("."):
            if not isinstance(current, dict):
                valid = False
                break
            current = current.get(segment)
            if current in (None, "", [], {}):
                valid = False
                break
        if valid:
            return current
    return None


def _join_search_term(search_term: str, value: str | None) -> str:
    if not value:
        return search_term
    if search_term.lower() in value.lower():
        return value
    return f"{search_term} - {value}"


def _pick_phone(item: dict[str, Any]) -> str:
    value = (
        _first_non_empty(item, "phone", "phoneNumber", "telephone", "formattedPhone", "contactPhone")
        or _nested_first(item, "seller.phone", "seller.phoneNumber", "contact.phone")
    )
    if isinstance(value, list):
        value = next((entry for entry in value if entry), "")
    return str(value or "")


def _pick_email(item: dict[str, Any]) -> str:
    value = (
        _first_non_empty(item, "email", "contactEmail", "publicEmail")
        or _nested_first(item, "seller.email", "contact.email")
    )
    if isinstance(value, list):
        value = next((entry for entry in value if entry), "")
    return str(value or "")


def _pick_link(item: dict[str, Any]) -> str | None:
    value = _first_non_empty(item, "url", "link", "website", "organicUrl", "placeUrl", "listingUrl")
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
        match = re.search(r"R\$\s?[\d\.]+(?:,\d{2})?", str(value))
        if match:
            return match.group(0)
    return "Sob consulta"


def _normalize_temperature(value: Any, price: str, phone: str, email: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in {"HOT", "WARM", "COLD"}:
        return normalized
    if normalized == "QUENTE":
        return "HOT"
    if normalized == "MORNO":
        return "WARM"
    if normalized == "FRIO":
        return "COLD"
    if phone or email:
        return "HOT"
    if price and not any(term in price.lower() for term in TERMS_COLD):
        return "WARM"
    return "COLD"


def _build_reason(category: str, temperature: str, phone: str, email: str, link: str | None) -> str:
    if temperature == "HOT":
        return f"Lead {category} com contato mais completo."
    if temperature == "WARM":
        return f"Lead {category} com dados parciais, precisa validacao."
    if not link:
        return f"Lead {category} sem pagina de origem confiavel."
    if not phone and not email:
        return f"Lead {category} sem contato direto retornado pelo actor."
    return f"Lead {category} com baixa confianca de arbitragem."


def _stable_lead_id(item: dict[str, Any], link: str | None, title: str) -> str:
    raw_id = _first_non_empty(item, "id", "placeId", "listingId", "itemId", "adId", "offerId", "propertyId")
    if raw_id:
        return str(raw_id)
    seed = link or title or repr(item)
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]


def _normalize_common(
    item: dict[str, Any],
    *,
    search_term: str,
    category: str,
    title: Any = None,
    price_value: Any = None,
    phone: str | None = None,
    email: str | None = None,
    seller_name: Any = None,
    link: str | None = None,
    reason: Any = None,
    temperature: Any = None,
) -> dict[str, Any]:
    raw_title = title or _first_non_empty(
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
    normalized_title = _join_search_term(search_term, str(raw_title) if raw_title else None)
    normalized_phone = phone if phone is not None else _pick_phone(item)
    normalized_email = email if email is not None else _pick_email(item)
    normalized_link = link if link is not None else _pick_link(item)
    normalized_price = _format_price(price_value if price_value is not None else _first_non_empty(item, "price", "priceValue", "amount", "offerPrice"))
    if normalized_price == "Sob consulta":
        normalized_price = _extract_price_from_text(item.get("description"), raw_title)
    normalized_temperature = _normalize_temperature(
        temperature if temperature is not None else _first_non_empty(item, "temperature", "score", "leadTemperature"),
        normalized_price,
        normalized_phone,
        normalized_email,
    )
    normalized_seller = str(
        seller_name
        or _first_non_empty(item, "seller_name", "sellerName", "companyName", "ownerName", "contactName", "name")
        or _nested_first(item, "seller.name", "contact.name", "agency.name")
        or "Oculto"
    )
    normalized_reason = str(reason or item.get("reason") or _build_reason(category, normalized_temperature, normalized_phone, normalized_email, normalized_link))
    return {
        "id": _stable_lead_id(item, normalized_link, normalized_title),
        "title": normalized_title,
        "price": normalized_price,
        "temperature": normalized_temperature,
        "reason": normalized_reason,
        "is_revealed": False,
        "phone": normalized_phone,
        "email": normalized_email,
        "seller_name": normalized_seller,
        "link": normalized_link,
    }


def _normalize_generic_item(item: dict[str, Any], search_term: str, category: str) -> dict[str, Any]:
    return _normalize_common(item, search_term=search_term, category=category)


def _normalize_webmotors_item(item: dict[str, Any], search_term: str, category: str) -> dict[str, Any]:
    seller = item.get("seller") if isinstance(item.get("seller"), dict) else {}
    title_parts = [
        _first_non_empty(item, "title", "name"),
        _first_non_empty(item, "brand"),
        _first_non_empty(item, "model"),
        _first_non_empty(item, "version"),
        _first_non_empty(item, "year"),
    ]
    title = " ".join(str(part).strip() for part in title_parts if part)
    return _normalize_common(
        item,
        search_term=search_term,
        category=category,
        title=title or _first_non_empty(item, "title", "name"),
        price_value=_first_non_empty(item, "price", "fipe_price"),
        phone=str(seller.get("phone") or ""),
        email=str(seller.get("email") or ""),
        seller_name=seller.get("name") or seller.get("dealerName"),
        link=str(item.get("url") or item.get("link") or ""),
        reason="Lead automotivo vindo de inventario estruturado.",
    )


def _normalize_olx_item(item: dict[str, Any], search_term: str, category: str) -> dict[str, Any]:
    seller_name = _first_non_empty(item, "sellerName", "ownerName", "owner", "userName")
    location = _first_non_empty(item, "location", "city", "state")
    reason = "Lead automotivo vindo de classificados."
    if location:
        reason = f"Lead automotivo vindo de classificados em {location}."
    return _normalize_common(
        item,
        search_term=search_term,
        category=category,
        price_value=_first_non_empty(item, "price", "priceValue"),
        seller_name=seller_name,
        link=str(_pick_link(item) or ""),
        reason=reason,
    )


def _normalize_real_estate_item(item: dict[str, Any], search_term: str, category: str) -> dict[str, Any]:
    price_value = _first_non_empty(item, "price", "totalPrice", "salePrice", "rentPrice")
    seller_name = (
        _first_non_empty(item, "agencyName", "brokerName", "sellerName", "companyName")
        or _nested_first(item, "agency.name", "broker.name")
    )
    location = _first_non_empty(item, "city", "region", "neighborhood")
    reason = "Lead imobiliario capturado do portal."
    if location:
        reason = f"Lead imobiliario em {location}."
    return _normalize_common(
        item,
        search_term=search_term,
        category=category,
        title=_first_non_empty(item, "title", "headline", "propertyType"),
        price_value=price_value,
        seller_name=seller_name,
        phone=_pick_phone(item),
        email=_pick_email(item),
        link=str(_pick_link(item) or ""),
        reason=reason,
    )


def _normalize_marketplace_item(item: dict[str, Any], search_term: str, category: str) -> dict[str, Any]:
    return _normalize_common(
        item,
        search_term=search_term,
        category=category,
        price_value=_first_non_empty(item, "price", "listingPrice", "amount"),
        seller_name=_first_non_empty(item, "sellerName", "ownerName", "name"),
        link=str(_pick_link(item) or ""),
        reason=f"Lead {category} vindo de marketplace.",
    )


NORMALIZERS: dict[str, Callable[[dict[str, Any], str, str], dict[str, Any]]] = {
    "google_places": _normalize_generic_item,
    "generic_query": _normalize_generic_item,
    "contact_enrich": _normalize_generic_item,
    "webmotors": _normalize_webmotors_item,
    "olx_cars": _normalize_olx_item,
    "brazil_real_estate": _normalize_real_estate_item,
    "zap_imoveis": _normalize_real_estate_item,
    "marketplace": _normalize_marketplace_item,
}


def _expand_actor_items(actor_mode: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if actor_mode != "generic_query":
        return items

    expanded: list[dict[str, Any]] = []
    for item in items:
        organic_results = item.get("organicResults")
        if isinstance(organic_results, list) and organic_results:
            for organic in organic_results:
                if isinstance(organic, dict):
                    expanded.append({**organic, "searchQuery": item.get("searchQuery"), "resultsTotal": item.get("resultsTotal")})
            continue
        expanded.append(item)
    return expanded


def _dedupe_leads(leads: Iterable[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
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


def _infer_state(search_term: str) -> str | None:
    normalized = re.sub(r"[^a-zA-Z\s]", " ", search_term).lower()
    tokens = [token for token in normalized.split() if token]
    for token in tokens:
        if token in BRAZILIAN_STATES:
            return token.upper()
    for code, name in BRAZILIAN_STATES.items():
        if name in normalized:
            return code.upper()
    return None


def _infer_city(search_term: str) -> str | None:
    parts = [part.strip() for part in re.split(r"[,/\-\n]+", search_term) if part.strip()]
    if len(parts) >= 2:
        return parts[-1]
    return None


def _infer_year(search_term: str) -> int | None:
    match = re.search(r"(19\d{2}|20\d{2})", search_term)
    return int(match.group(1)) if match else None


def _detect_transaction_type(search_term: str) -> str:
    normalized = search_term.lower()
    if any(term in normalized for term in ("aluguel", "locacao", "locar", "alugar")):
        return "rent"
    return "sale"


def _build_google_places_input(context: SearchContext) -> dict[str, Any]:
    return {
        "searchStringsArray": [context.search_term],
        "maxCrawledPlaces": _sanitize_limit(context.limit),
        "language": "pt-BR",
        "region": "BR",
        "scrapeContacts": True,
        "scrapeReviewsPersonalData": False,
    }


def _build_generic_query_input(context: SearchContext) -> dict[str, Any]:
    return {
        "queries": context.search_term,
        "maxPagesPerQuery": 1,
        "resultsPerPage": max(_sanitize_limit(context.limit), DEFAULT_LIMIT),
        "mobileResults": False,
        "languageCode": "pt-BR",
        "countryCode": "br",
        "includeUnfilteredResults": False,
        "saveHtml": False,
    }


def _build_webmotors_input(context: SearchContext) -> dict[str, Any]:
    query = quote(context.search_term)
    return {
        "query": context.search_term,
        "searchTerm": context.search_term,
        "maxItems": _sanitize_limit(context.limit),
        "startUrls": [{"url": f"https://www.webmotors.com.br/carros/estoque?search={query}"}],
    }


def _build_olx_cars_input(context: SearchContext) -> dict[str, Any]:
    state = _infer_state(context.search_term) or os.getenv("APIFY_OLX_DEFAULT_STATE", "SP")
    city = _infer_city(context.search_term)
    payload: dict[str, Any] = {
        "query": context.search_term,
        "searchTerm": context.search_term,
        "state": state,
        "maxItems": _sanitize_limit(context.limit),
    }
    if city:
        payload["city"] = city
    year = _infer_year(context.search_term)
    if year:
        payload["yearFrom"] = year
        payload["yearTo"] = year
    return payload


def _build_brazil_real_estate_input(context: SearchContext) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": context.search_term,
        "searchTerm": context.search_term,
        "transactionType": _detect_transaction_type(context.search_term),
        "maxListings": _sanitize_limit(context.limit),
    }
    state = _infer_state(context.search_term)
    city = _infer_city(context.search_term)
    if state:
        payload["state"] = state
    if city:
        payload["city"] = city
    return payload


def _build_zap_imoveis_input(context: SearchContext) -> dict[str, Any]:
    query = quote(context.search_term)
    return {
        "query": context.search_term,
        "searchTerm": context.search_term,
        "limit": _sanitize_limit(context.limit),
        "startUrls": [{"url": f"https://www.zapimoveis.com.br/busca?query={query}"}],
    }


def _build_marketplace_input(context: SearchContext) -> dict[str, Any]:
    return {
        "searchTerm": context.search_term,
        "query": context.search_term,
        "maxItems": _sanitize_limit(context.limit),
        "locale": "pt_BR",
    }


def _build_contact_enrich_input(context: SearchContext) -> dict[str, Any]:
    urls: list[str] = []
    for lead in context.existing_leads:
        link = str(lead.get("link") or "")
        if link and link not in urls:
            urls.append(link)
    return {
        "startUrls": [{"url": url} for url in urls[: _sanitize_limit(context.limit)]],
        "maxItems": _sanitize_limit(context.limit),
    }


INPUT_BUILDERS: dict[str, Callable[[SearchContext], dict[str, Any]]] = {
    "google_places": _build_google_places_input,
    "generic_query": _build_generic_query_input,
    "webmotors": _build_webmotors_input,
    "olx_cars": _build_olx_cars_input,
    "brazil_real_estate": _build_brazil_real_estate_input,
    "zap_imoveis": _build_zap_imoveis_input,
    "marketplace": _build_marketplace_input,
    "contact_enrich": _build_contact_enrich_input,
}


def _normalize_items(items: list[dict[str, Any]], actor_mode: str, search_term: str, category: str) -> list[dict[str, Any]]:
    normalizer = NORMALIZERS.get(actor_mode, _normalize_generic_item)
    expanded = _expand_actor_items(actor_mode, items)
    return [normalizer(item, search_term, category) for item in expanded]


def _merge_enrichment(leads: list[dict[str, Any]], enrichment_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not leads or not enrichment_items:
        return leads

    enrichment_map: dict[str, dict[str, Any]] = {}
    for item in enrichment_items:
        key = str(_pick_link(item) or item.get("url") or "").strip()
        if key:
            enrichment_map[key] = item

    merged: list[dict[str, Any]] = []
    for lead in leads:
        enrichment = enrichment_map.get(str(lead.get("link") or "").strip())
        if not enrichment:
            merged.append(lead)
            continue

        phone = _pick_phone(enrichment) or lead.get("phone", "")
        email = _pick_email(enrichment) or lead.get("email", "")
        temperature = _normalize_temperature(lead.get("temperature"), lead.get("price", ""), phone, email)
        merged.append(
            {
                **lead,
                "phone": phone,
                "email": email,
                "temperature": temperature,
                "reason": "Lead enriquecido com dados de contato da pagina de origem.",
            }
        )
    return merged


def _execute_candidate(candidate: ActorCandidate, context: SearchContext, actor_id: str) -> list[dict[str, Any]]:
    builder = INPUT_BUILDERS.get(candidate.mode)
    if builder is None:
        raise ApifyConfigurationError(f"Modo de actor nao suportado: {candidate.mode}")

    actor_input = builder(context)
    if candidate.enrich and not actor_input.get("startUrls"):
        return []

    logger.info("Executando estrategia Apify", extra={"candidate": candidate.name, "actor_id": actor_id, "category": context.category})
    raw_items = _run_actor(actor_id, actor_input, context.limit)
    return _normalize_items(raw_items, candidate.mode, context.search_term, context.category)


def _pipeline_for_category(category: str) -> list[ActorCandidate]:
    if category in CATEGORY_PIPELINES:
        return CATEGORY_PIPELINES[category]
    return [ActorCandidate("fallback", "APIFY_ACTOR_ID_FALLBACK", os.getenv("APIFY_ACTOR_ID", "").strip() or "apify/google-search-scraper", "generic_query")]


def run_apify_search(search_term: str, category: str, limit: int) -> list[dict[str, Any]]:
    sanitized_limit = _sanitize_limit(limit)
    pipeline = _pipeline_for_category(category)
    collected: list[dict[str, Any]] = []
    last_error: Exception | None = None

    for candidate in pipeline:
        actor_id = _resolve_actor_id(candidate, category)
        if not actor_id:
            logger.info("Actor nao configurado para estrategia", extra={"candidate": candidate.name, "category": category})
            continue

        context = SearchContext(
            search_term=search_term,
            category=category,
            limit=max(sanitized_limit - len(collected), 1),
            existing_leads=tuple(collected),
        )

        try:
            candidate_results = _execute_candidate(candidate, context, actor_id)
        except (httpx.HTTPError, ApifyRunFailedError, ApifyTimeoutError) as exc:
            last_error = exc
            logger.warning(
                "Falha na estrategia do Apify; seguindo para a proxima",
                extra={"candidate": candidate.name, "actor_id": actor_id, "category": category, "error": str(exc)},
            )
            continue

        if candidate.enrich:
            collected = _dedupe_leads(_merge_enrichment(collected, candidate_results), sanitized_limit)
        else:
            collected = _dedupe_leads([*collected, *candidate_results], sanitized_limit)

        if len(collected) >= sanitized_limit:
            break

    if collected:
        return collected[:sanitized_limit]

    if last_error is not None:
        if isinstance(last_error, ApifyTimeoutError):
            raise last_error
        if isinstance(last_error, ApifyRunFailedError):
            raise last_error
        raise ApifyRunFailedError(f"Nenhuma estrategia do Apify retornou resultados: {last_error}") from last_error

    raise ApifyConfigurationError(
        "Nenhum actor do Apify configurado. Defina os APIFY_ACTOR_ID_* por categoria ou APIFY_ACTOR_ID_FALLBACK."
    )
