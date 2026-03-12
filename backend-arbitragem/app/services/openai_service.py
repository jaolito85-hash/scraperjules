from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

CATEGORY_LABELS = {"b2b_services", "automotive", "real_estate"}
LOCATION_STOPWORDS = {
    "de",
    "da",
    "do",
    "dos",
    "das",
    "para",
    "em",
    "com",
    "na",
    "no",
    "e",
}
BRAZILIAN_STATES = {
    "acre",
    "alagoas",
    "amapa",
    "amazonas",
    "bahia",
    "ceara",
    "distrito federal",
    "espirito santo",
    "goias",
    "maranhao",
    "mato grosso",
    "mato grosso do sul",
    "minas gerais",
    "para",
    "paraiba",
    "parana",
    "pernambuco",
    "piaui",
    "rio de janeiro",
    "rio grande do norte",
    "rio grande do sul",
    "rondonia",
    "roraima",
    "santa catarina",
    "sao paulo",
    "sergipe",
    "tocantins",
}


@dataclass(frozen=True)
class SearchIntent:
    original_search_term: str
    requested_category: str
    inferred_category: str
    location: str
    product_or_service: str
    primary_terms: tuple[str, ...]
    expanded_terms: tuple[str, ...]
    primary_query: str
    alternate_queries: tuple[str, ...]


def is_openai_enabled() -> bool:
    flag = os.getenv("OPENAI_ENABLED", "").strip().lower()
    return flag in {"1", "true", "yes", "on"} and bool(os.getenv("OPENAI_API_KEY", "").strip())


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL


def analyze_search_intent(search_term: str, category: str) -> SearchIntent:
    fallback_intent = _build_fallback_intent(search_term, category)
    if not is_openai_enabled():
        return fallback_intent

    try:
        payload = _chat_json(
            system_prompt=(
                "Voce estrutura buscas para um SaaS brasileiro de arbitragem via scraping. "
                "Responda JSON valido com chaves: inferred_category, location, product_or_service, "
                "primary_terms, expanded_terms, primary_query, alternate_queries. "
                "Se estiver em duvida, preserve a categoria solicitada. "
                "alternate_queries deve ter no maximo 2 itens curtos e uteis."
            ),
            user_prompt=json.dumps(
                {"search_term": search_term, "requested_category": category, "supported_categories": sorted(CATEGORY_LABELS)},
                ensure_ascii=False,
            ),
        )
        return _parse_intent_payload(payload, fallback_intent)
    except Exception as exc:
        logger.warning("Falha ao interpretar busca com OpenAI; usando heuristica local", extra={"error": str(exc)})
        return fallback_intent


def enrich_and_rank_leads(
    leads: list[dict[str, Any]],
    intent: SearchIntent,
    *,
    original_search_term: str,
    category: str,
) -> list[dict[str, Any]]:
    if not leads:
        return leads

    ranked = sorted(
        (
            (_score_lead(lead, intent=intent, category=category), _build_reason_fallback(lead, intent=intent, category=category), lead)
            for lead in leads
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    enriched = [{**lead, "reason": reason} for _, reason, lead in ranked]
    if not is_openai_enabled():
        return enriched

    try:
        ai_reason_map = _generate_reason_map_with_openai(enriched, intent=intent, original_search_term=original_search_term, category=category)
    except Exception as exc:
        logger.warning("Falha ao enriquecer reasons com OpenAI; mantendo reasons deterministicas", extra={"error": str(exc)})
        return enriched

    return [{**lead, "reason": ai_reason_map.get(str(lead.get("id")), lead["reason"])} for lead in enriched]


def _build_fallback_intent(search_term: str, category: str) -> SearchIntent:
    normalized = re.sub(r"\s+", " ", search_term).strip()
    location = _extract_location(normalized)
    product_or_service = _extract_product_or_service(normalized, location)
    primary_terms = _split_terms(product_or_service or normalized)
    expanded_terms = _expand_terms(primary_terms, category)
    primary_query = _build_primary_query(product_or_service or normalized, location)
    alternate_queries = tuple(
        query for query in _build_alternate_queries(product_or_service or normalized, location, expanded_terms) if query != primary_query
    )[:2]
    return SearchIntent(
        original_search_term=search_term,
        requested_category=category,
        inferred_category=category,
        location=location,
        product_or_service=product_or_service or normalized,
        primary_terms=tuple(primary_terms[:5]),
        expanded_terms=tuple(expanded_terms[:6]),
        primary_query=primary_query,
        alternate_queries=alternate_queries,
    )


def _extract_location(search_term: str) -> str:
    lowered = search_term.lower()
    segments = [segment.strip() for segment in re.split(r"[,/\-\n]+", lowered) if segment.strip()]
    for segment in reversed(segments):
        if segment in BRAZILIAN_STATES or len(segment.split()) >= 2:
            return segment.title()

    words = lowered.split()
    tail = []
    for token in reversed(words):
        if token.isdigit():
            continue
        tail.append(token)
        phrase = " ".join(reversed(tail))
        if phrase in BRAZILIAN_STATES:
            return phrase.title()
        if len(tail) == 2:
            return phrase.title()
    return ""


def _extract_product_or_service(search_term: str, location: str) -> str:
    normalized = search_term
    if location:
        normalized = re.sub(re.escape(location), "", normalized, flags=re.IGNORECASE).strip(" ,-/")
    normalized = re.sub(r"\b(19\d{2}|20\d{2})\b", "", normalized).strip()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _split_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in re.split(r"[^a-zA-Z0-9à-ÿÀ-ß]+", text.lower()):
        token = token.strip()
        if len(token) < 3 or token in LOCATION_STOPWORDS:
            continue
        if token not in terms:
            terms.append(token)
    return terms


def _expand_terms(primary_terms: Iterable[str], category: str) -> list[str]:
    expansions = list(primary_terms)
    category_expansions = {
        "b2b_services": ["empresa", "contato", "telefone", "orcamento"],
        "automotive": ["seminovo", "loja", "webmotors", "olx"],
        "real_estate": ["imovel", "apartamento", "casa", "corretor"],
    }
    for term in category_expansions.get(category, []):
        if term not in expansions:
            expansions.append(term)
    return expansions


def _build_primary_query(product_or_service: str, location: str) -> str:
    if location and location.lower() not in product_or_service.lower():
        return f"{product_or_service} {location}".strip()
    return product_or_service.strip()


def _build_alternate_queries(product_or_service: str, location: str, expanded_terms: list[str]) -> list[str]:
    queries: list[str] = []
    if location:
        queries.append(f"{product_or_service} {location} contato".strip())
    if expanded_terms:
        queries.append(f"{product_or_service} {' '.join(expanded_terms[:2])}".strip())
    queries.append(product_or_service.strip())
    deduped: list[str] = []
    for query in queries:
        normalized = re.sub(r"\s+", " ", query).strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _openai_headers() -> dict[str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY nao configurada.")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _chat_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    base_url = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/")
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers=_openai_headers(),
        json={
            "model": get_openai_model(),
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=25.0,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    return json.loads(content)


def _parse_intent_payload(payload: dict[str, Any], fallback_intent: SearchIntent) -> SearchIntent:
    inferred_category = str(payload.get("inferred_category") or fallback_intent.requested_category).strip()
    if inferred_category not in CATEGORY_LABELS:
        inferred_category = fallback_intent.requested_category

    primary_terms = _sanitize_list(payload.get("primary_terms"), fallback_intent.primary_terms)
    expanded_terms = _sanitize_list(payload.get("expanded_terms"), fallback_intent.expanded_terms)
    primary_query = str(payload.get("primary_query") or fallback_intent.primary_query).strip()
    alternate_queries = tuple(
        query
        for query in _sanitize_list(payload.get("alternate_queries"), fallback_intent.alternate_queries)
        if query and query != primary_query
    )[:2]

    return SearchIntent(
        original_search_term=fallback_intent.original_search_term,
        requested_category=fallback_intent.requested_category,
        inferred_category=inferred_category,
        location=str(payload.get("location") or fallback_intent.location).strip(),
        product_or_service=str(payload.get("product_or_service") or fallback_intent.product_or_service).strip(),
        primary_terms=primary_terms,
        expanded_terms=expanded_terms,
        primary_query=primary_query,
        alternate_queries=alternate_queries,
    )


def _sanitize_list(value: Any, fallback: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return tuple(str(item).strip() for item in fallback if str(item).strip())
    cleaned = []
    for item in value:
        normalized = str(item).strip()
        if normalized and normalized not in cleaned:
            cleaned.append(normalized)
    return tuple(cleaned)


def _score_lead(lead: dict[str, Any], *, intent: SearchIntent, category: str) -> int:
    haystack = " ".join(
        [
            str(lead.get("title") or ""),
            str(lead.get("seller_name") or ""),
            str(lead.get("link") or ""),
        ]
    ).lower()
    score = 0
    matches = sum(1 for term in intent.primary_terms if term.lower() in haystack)
    score += min(matches, 3) * 2
    expanded_matches = sum(1 for term in intent.expanded_terms if term.lower() in haystack)
    score += min(expanded_matches, 2)
    if lead.get("phone"):
        score += 3
    if lead.get("email"):
        score += 2
    if str(lead.get("price") or "").strip() and str(lead.get("price")).lower() != "sob consulta":
        score += 1
    if intent.location and intent.location.lower() in haystack:
        score += 2
    score += _source_weight(_infer_source_label(str(lead.get("link") or "")), category)
    temperature = str(lead.get("temperature") or "").upper()
    if temperature == "HOT":
        score += 2
    elif temperature == "WARM":
        score += 1
    return score


def _source_weight(source: str, category: str) -> int:
    weights = {
        "b2b_services": {"Google Maps": 2, "Google Search": 1},
        "automotive": {"Webmotors": 2, "OLX": 1, "Facebook Marketplace": 1},
        "real_estate": {"Zap Imoveis": 2, "OLX": 1, "Facebook Marketplace": 1},
    }
    return weights.get(category, {}).get(source, 0)


def _build_reason_fallback(lead: dict[str, Any], *, intent: SearchIntent, category: str) -> str:
    title = str(lead.get("title") or "").lower()
    source = _infer_source_label(str(lead.get("link") or ""))
    match_level = "boa aderencia"
    if sum(1 for term in intent.primary_terms if term.lower() in title) >= 2:
        match_level = "alta aderencia"

    details: list[str] = [match_level]
    if intent.location and intent.location.lower() in title:
        details.append(f"em {intent.location}")
    if lead.get("phone") and lead.get("email"):
        details.append("com telefone e email")
    elif lead.get("phone"):
        details.append("com telefone")
    elif lead.get("email"):
        details.append("com email")
    elif str(lead.get("price") or "").lower() != "sob consulta":
        details.append("com preco visivel")
    if source:
        details.append(f"via {source}")

    reason = ", ".join(details[:3]).strip()
    if not reason:
        reason = f"Lead {category} com sinais basicos de aderencia."
    return reason[0].upper() + reason[1:] + "."


def _infer_source_label(link: str) -> str:
    hostname = urlparse(link).netloc.lower()
    if "google.com" in hostname and "maps" in link:
        return "Google Maps"
    if "google.com" in hostname:
        return "Google Search"
    if "webmotors" in hostname:
        return "Webmotors"
    if "olx" in hostname:
        return "OLX"
    if "zapimoveis" in hostname:
        return "Zap Imoveis"
    if "facebook" in hostname:
        return "Facebook Marketplace"
    return ""


def _generate_reason_map_with_openai(
    leads: list[dict[str, Any]],
    *,
    intent: SearchIntent,
    original_search_term: str,
    category: str,
) -> dict[str, str]:
    compact_leads = [
        {
            "id": str(lead.get("id")),
            "title": str(lead.get("title") or ""),
            "price": str(lead.get("price") or ""),
            "has_phone": bool(lead.get("phone")),
            "has_email": bool(lead.get("email")),
            "source": _infer_source_label(str(lead.get("link") or "")),
            "current_reason": str(lead.get("reason") or ""),
        }
        for lead in leads[: min(len(leads), 12)]
    ]
    payload = _chat_json(
        system_prompt=(
            "Voce escreve reasons curtos para leads de um SaaS de arbitragem. "
            "Responda JSON valido com chave items, uma lista de objetos {id, reason}. "
            "Cada reason deve ser curto, factual, em pt-BR, maximo 90 caracteres, sem promessas."
        ),
        user_prompt=json.dumps(
            {
                "original_search_term": original_search_term,
                "category": category,
                "intent": {
                    "location": intent.location,
                    "product_or_service": intent.product_or_service,
                    "primary_terms": list(intent.primary_terms),
                },
                "leads": compact_leads,
            },
            ensure_ascii=False,
        ),
    )
    items = payload.get("items")
    if not isinstance(items, list):
        return {}

    reason_map: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        lead_id = str(item.get("id") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if lead_id and reason:
            reason_map[lead_id] = reason[:90]
    return reason_map
