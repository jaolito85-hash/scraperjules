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

SUPPORTED_VERTICALS = {"business_local", "vehicle", "real_estate", "product", "service_demand"}
LEGACY_CATEGORY_TO_VERTICAL = {
    "b2b_services": "business_local",
    "automotive": "vehicle",
    "real_estate": "real_estate",
}
VERTICAL_TO_PIPELINE = {
    "business_local": "b2b_services",
    "vehicle": "automotive",
    "real_estate": "real_estate",
    "product": "product",
    "service_demand": "service_demand",
}
BUSINESS_KEYWORDS = {
    "clinica",
    "clínica",
    "odontologica",
    "odontológica",
    "dentista",
    "restaurante",
    "academia",
    "hotel",
    "oficina",
    "empresa",
    "loja",
    "mercado",
    "farmacia",
    "farmácia",
    "imobiliaria",
    "imobiliária",
}
REAL_ESTATE_KEYWORDS = {"apartamento", "casa", "imovel", "imóvel", "terreno", "quartos", "kitnet", "sobrado"}
VEHICLE_KEYWORDS = {"carro", "moto", "veiculo", "veículo", "caminhonete", "sedan", "hatch", "suv"}
PRODUCT_KEYWORDS = {"iphone", "geladeira", "tv", "televisao", "televisão", "notebook", "sofa", "sofá"}
SERVICE_PROFESSIONS = {
    "encanador",
    "pedreiro",
    "eletricista",
    "advogado",
    "pintor",
    "diarista",
    "mecanico",
    "mecânico",
    "freteiro",
    "marceneiro",
}
VEHICLE_BRANDS = {
    "toyota",
    "honda",
    "chevrolet",
    "fiat",
    "volkswagen",
    "vw",
    "hyundai",
    "renault",
    "ford",
    "nissan",
    "jeep",
    "yamaha",
    "suzuki",
    "bmw",
    "mercedes",
    "audi",
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
    "pr",
    "sp",
    "rj",
    "sc",
    "rs",
    "mg",
}
STOPWORDS = {
    "procure",
    "buscar",
    "busque",
    "mais",
    "barato",
    "barata",
    "clientes",
    "cliente",
    "para",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "em",
    "no",
    "na",
    "o",
    "a",
    "os",
    "as",
}


@dataclass(frozen=True)
class SearchIntent:
    original_search_term: str
    requested_category: str
    vertical: str
    goal: str
    entity: str
    brand: str
    model: str
    year: str
    location: str
    attributes: dict[str, str]
    sort: str
    primary_terms: tuple[str, ...]
    expanded_terms: tuple[str, ...]
    primary_query: str
    alternate_queries: tuple[str, ...]
    pipeline_category: str


def is_openai_enabled() -> bool:
    flag = os.getenv("OPENAI_ENABLED", "").strip().lower()
    return flag in {"1", "true", "yes", "on"} and bool(os.getenv("OPENAI_API_KEY", "").strip())


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL


def resolve_pipeline_category(intent: SearchIntent) -> str:
    return intent.pipeline_category


def analyze_search_intent(search_term: str, category: str) -> SearchIntent:
    fallback_intent = _build_fallback_intent(search_term, category)
    if not is_openai_enabled():
        return fallback_intent

    try:
        payload = _chat_json(
            system_prompt=(
                "Voce interpreta buscas livres para um motor de arbitragem. "
                "Responda JSON valido com: vertical, goal, entity, brand, model, year, location, attributes, sort, "
                "primary_terms, expanded_terms, primary_query, alternate_queries. "
                "Use apenas estas verticais: business_local, vehicle, real_estate, product, service_demand. "
                "alternate_queries deve ter no maximo 2 itens. attributes deve ser um objeto simples."
            ),
            user_prompt=json.dumps(
                {
                    "search_term": search_term,
                    "requested_category": category,
                    "supported_verticals": sorted(SUPPORTED_VERTICALS),
                    "legacy_mapping": LEGACY_CATEGORY_TO_VERTICAL,
                },
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
            (_score_lead(lead, intent=intent), _build_reason_fallback(lead, intent=intent), lead)
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
    vertical = _infer_vertical(normalized, category)
    goal = _infer_goal(normalized, vertical)
    location = _extract_location(normalized)
    brand = _extract_brand(normalized)
    year = _extract_year(normalized)
    attributes = _extract_attributes(normalized, vertical)
    entity = _extract_entity(normalized, vertical, location, brand, year)
    model = _extract_model(normalized, brand, location, year)
    sort = "price_asc" if any(term in normalized.lower() for term in ("mais barato", "mais barata", "menor preco", "menor preço")) else "relevance"
    primary_terms = _build_primary_terms(vertical, entity, brand, model, year, location, attributes)
    expanded_terms = _expand_terms(primary_terms, vertical, goal)
    primary_query = _build_primary_query(vertical, normalized, entity, brand, model, year, location, attributes, goal)
    alternate_queries = tuple(query for query in _build_alternate_queries(vertical, normalized, entity, brand, model, year, location, goal) if query != primary_query)[:2]

    return SearchIntent(
        original_search_term=search_term,
        requested_category=category,
        vertical=vertical,
        goal=goal,
        entity=entity,
        brand=brand,
        model=model,
        year=year,
        location=location,
        attributes=attributes,
        sort=sort,
        primary_terms=tuple(primary_terms[:6]),
        expanded_terms=tuple(expanded_terms[:8]),
        primary_query=primary_query,
        alternate_queries=alternate_queries,
        pipeline_category=VERTICAL_TO_PIPELINE[vertical],
    )


def _infer_vertical(search_term: str, category: str) -> str:
    category_key = category.strip().lower()
    if category_key in LEGACY_CATEGORY_TO_VERTICAL:
        return LEGACY_CATEGORY_TO_VERTICAL[category_key]

    lowered = search_term.lower()
    if "clientes para" in lowered or "cliente para" in lowered:
        return "service_demand"
    if any(keyword in lowered for keyword in REAL_ESTATE_KEYWORDS):
        return "real_estate"
    if any(keyword in lowered for keyword in VEHICLE_KEYWORDS) or any(keyword in lowered for keyword in VEHICLE_BRANDS):
        return "vehicle"
    if any(keyword in lowered for keyword in BUSINESS_KEYWORDS):
        return "business_local"
    if any(keyword in lowered for keyword in SERVICE_PROFESSIONS):
        return "service_demand"
    if any(keyword in lowered for keyword in PRODUCT_KEYWORDS):
        return "product"
    return "product"


def _infer_goal(search_term: str, vertical: str) -> str:
    lowered = search_term.lower()
    if "clientes para" in lowered or "cliente para" in lowered:
        return "generate_demand"
    if any(term in lowered for term in ("mais barato", "mais barata", "menor preco", "menor preço")):
        return "find_cheapest"
    if vertical == "business_local":
        return "find_local_business"
    return "search_supply"


def _extract_location(search_term: str) -> str:
    lowered = search_term.lower()
    segments = [segment.strip() for segment in re.split(r"[,/\-\n]+", lowered) if segment.strip()]
    for segment in reversed(segments):
        words = segment.split()
        if segment in BRAZILIAN_STATES or len(words) in {1, 2}:
            return segment.title()

    words = [word for word in lowered.split() if word]
    for size in (2, 1):
        if len(words) >= size:
            candidate = " ".join(words[-size:])
            if candidate in BRAZILIAN_STATES or size == 2:
                return candidate.title()
    return ""


def _extract_brand(search_term: str) -> str:
    lowered = search_term.lower()
    for brand in sorted(VEHICLE_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand)}\b", lowered):
            return brand.title()
    return ""


def _extract_year(search_term: str) -> str:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", search_term)
    return match.group(1) if match else ""


def _extract_attributes(search_term: str, vertical: str) -> dict[str, str]:
    attributes: dict[str, str] = {}
    lowered = search_term.lower()
    quartos = re.search(r"(\d+)\s+quartos?", lowered)
    if quartos:
        attributes["rooms"] = quartos.group(1)
    if vertical == "service_demand":
        for profession in SERVICE_PROFESSIONS:
            if profession in lowered:
                attributes["service"] = profession
                break
    if "brasil" in lowered:
        attributes["scope"] = "Brasil"
    return attributes


def _extract_entity(search_term: str, vertical: str, location: str, brand: str, year: str) -> str:
    normalized = search_term
    for value in (location, brand, year):
        if value:
            normalized = re.sub(re.escape(value), "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\b(procure|buscar|busque|mais barato|mais barata|do brasil|de brasil)\b", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,-")
    if normalized:
        return normalized
    defaults = {
        "business_local": "negocio local",
        "vehicle": "veiculo",
        "real_estate": "imovel",
        "product": "produto",
        "service_demand": "demanda de servico",
    }
    return defaults[vertical]


def _extract_model(search_term: str, brand: str, location: str, year: str) -> str:
    normalized = search_term
    for value in (brand, location, year):
        if value:
            normalized = re.sub(re.escape(value), "", normalized, flags=re.IGNORECASE)
    tokens = [token for token in re.split(r"[^a-zA-Z0-9à-ÿÀ-ß]+", normalized) if token]
    cleaned = [token for token in tokens if token.lower() not in STOPWORDS and len(token) > 1]
    if brand and cleaned:
        try:
            brand_index = [token.lower() for token in cleaned].index(brand.lower())
        except ValueError:
            brand_index = -1
        if brand_index >= 0:
            cleaned = cleaned[brand_index + 1 :]
    return " ".join(cleaned[:3]).strip()


def _build_primary_terms(
    vertical: str,
    entity: str,
    brand: str,
    model: str,
    year: str,
    location: str,
    attributes: dict[str, str],
) -> list[str]:
    candidates = [entity, brand, model, year, location, attributes.get("service", ""), attributes.get("rooms", "")]
    terms: list[str] = []
    for candidate in candidates:
        for token in re.split(r"[^a-zA-Z0-9à-ÿÀ-ß]+", str(candidate).lower()):
            if len(token) < 2 or token in STOPWORDS or token in terms:
                continue
            terms.append(token)
    if vertical == "vehicle" and "carro" not in terms and "moto" not in terms:
        terms.append("veiculo")
    return terms


def _expand_terms(primary_terms: Iterable[str], vertical: str, goal: str) -> list[str]:
    expansions = list(primary_terms)
    by_vertical = {
        "business_local": ["google maps", "telefone", "contato"],
        "vehicle": ["webmotors", "olx", "seminovo"],
        "real_estate": ["imovel", "zap", "olx"],
        "product": ["marketplace", "preco", "oferta"],
        "service_demand": ["orcamento", "precisa", "contratar"],
    }
    for term in by_vertical.get(vertical, []):
        if term not in expansions:
            expansions.append(term)
    if goal == "find_cheapest" and "mais barato" not in expansions:
        expansions.append("mais barato")
    return expansions


def _build_primary_query(
    vertical: str,
    original_search_term: str,
    entity: str,
    brand: str,
    model: str,
    year: str,
    location: str,
    attributes: dict[str, str],
    goal: str,
) -> str:
    if vertical == "service_demand":
        service = attributes.get("service") or entity
        base = f"{service} clientes {location}".strip()
        return re.sub(r"\s+", " ", base).strip()
    if vertical == "real_estate":
        rooms = f"{attributes['rooms']} quartos " if attributes.get("rooms") else ""
        sort = " mais barato" if goal == "find_cheapest" else ""
        base = f"{entity} {rooms}{location}{sort}"
        return re.sub(r"\s+", " ", base).strip()
    if vertical == "vehicle":
        sort = " mais barato" if goal == "find_cheapest" else ""
        base = f"{brand} {model} {year} {location}{sort}"
        return re.sub(r"\s+", " ", base).strip()
    if vertical == "business_local":
        return re.sub(r"\s+", " ", f"{entity} {location}".strip()).strip()
    if vertical == "product":
        sort = " mais barato" if goal == "find_cheapest" else ""
        return re.sub(r"\s+", " ", f"{entity} {brand} {model} {location}{sort}".strip()).strip()
    return original_search_term


def _build_alternate_queries(
    vertical: str,
    original_search_term: str,
    entity: str,
    brand: str,
    model: str,
    year: str,
    location: str,
    goal: str,
) -> list[str]:
    queries: list[str] = []
    if vertical == "service_demand":
        queries.append(f"{entity} precisa {location}".strip())
        queries.append(f"contratar {entity} {location}".strip())
    elif vertical == "vehicle":
        queries.append(f"{brand} {model} {year} olx {location}".strip())
        queries.append(f"{brand} {model} {year} webmotors".strip())
    elif vertical == "real_estate":
        queries.append(f"{entity} olx {location}".strip())
        queries.append(f"{entity} zap imoveis {location}".strip())
    elif vertical == "business_local":
        queries.append(f"{entity} {location} telefone".strip())
        queries.append(f"{entity} {location} google maps".strip())
    else:
        queries.append(f"{entity} marketplace {location}".strip())
        if goal == "find_cheapest":
            queries.append(f"{entity} menor preco {location}".strip())
    queries.append(original_search_term.strip())
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
    vertical = str(payload.get("vertical") or fallback_intent.vertical).strip()
    if vertical not in SUPPORTED_VERTICALS:
        vertical = fallback_intent.vertical

    attributes = payload.get("attributes")
    if not isinstance(attributes, dict):
        attributes = fallback_intent.attributes

    primary_query = str(payload.get("primary_query") or fallback_intent.primary_query).strip()
    alternate_queries = tuple(
        query
        for query in _sanitize_list(payload.get("alternate_queries"), fallback_intent.alternate_queries)
        if query and query != primary_query
    )[:2]

    return SearchIntent(
        original_search_term=fallback_intent.original_search_term,
        requested_category=fallback_intent.requested_category,
        vertical=vertical,
        goal=str(payload.get("goal") or fallback_intent.goal).strip(),
        entity=str(payload.get("entity") or fallback_intent.entity).strip(),
        brand=str(payload.get("brand") or fallback_intent.brand).strip(),
        model=str(payload.get("model") or fallback_intent.model).strip(),
        year=str(payload.get("year") or fallback_intent.year).strip(),
        location=str(payload.get("location") or fallback_intent.location).strip(),
        attributes={str(key): str(value) for key, value in attributes.items()},
        sort=str(payload.get("sort") or fallback_intent.sort).strip(),
        primary_terms=_sanitize_list(payload.get("primary_terms"), fallback_intent.primary_terms),
        expanded_terms=_sanitize_list(payload.get("expanded_terms"), fallback_intent.expanded_terms),
        primary_query=primary_query,
        alternate_queries=alternate_queries,
        pipeline_category=VERTICAL_TO_PIPELINE.get(vertical, fallback_intent.pipeline_category),
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


def _score_lead(lead: dict[str, Any], *, intent: SearchIntent) -> int:
    haystack = " ".join([str(lead.get("title") or ""), str(lead.get("seller_name") or ""), str(lead.get("link") or "")]).lower()
    score = 0
    primary_matches = sum(1 for term in intent.primary_terms if term.lower() in haystack)
    score += min(primary_matches, 3) * 2
    expanded_matches = sum(1 for term in intent.expanded_terms if term.lower() in haystack)
    score += min(expanded_matches, 2)
    if intent.location and intent.location.lower() in haystack:
        score += 2
    if intent.year and intent.year in haystack:
        score += 2
    if intent.brand and intent.brand.lower() in haystack:
        score += 2
    if intent.model and intent.model.lower() in haystack:
        score += 2
    if lead.get("phone"):
        score += 3
    if lead.get("email"):
        score += 2
    if str(lead.get("price") or "").strip() and str(lead.get("price")).lower() != "sob consulta":
        score += 1
    score += _source_weight(_infer_source_label(str(lead.get("link") or "")), intent.vertical)
    if intent.sort == "price_asc" and str(lead.get("price") or "").lower() != "sob consulta":
        score += 1
    return score


def _source_weight(source: str, vertical: str) -> int:
    weights = {
        "business_local": {"Google Maps": 2, "Google Search": 1},
        "vehicle": {"Webmotors": 2, "OLX": 1, "Facebook Marketplace": 1},
        "real_estate": {"Zap Imoveis": 2, "OLX": 1, "Facebook Marketplace": 1},
        "product": {"Facebook Marketplace": 2, "Google Search": 1},
        "service_demand": {"Google Search": 2},
    }
    return weights.get(vertical, {}).get(source, 0)


def _build_reason_fallback(lead: dict[str, Any], *, intent: SearchIntent) -> str:
    haystack = " ".join([str(lead.get("title") or ""), str(lead.get("link") or "")]).lower()
    source = _infer_source_label(str(lead.get("link") or ""))
    reasons: list[str] = []

    if intent.sort == "price_asc" and str(lead.get("price") or "").lower() != "sob consulta":
        reasons.append("preco visivel")
    if intent.location and intent.location.lower() in haystack:
        reasons.append(f"localizacao em {intent.location}")
    if intent.year and intent.year in haystack:
        reasons.append(f"ano {intent.year} correspondente")
    if intent.model and intent.model.lower() in haystack:
        reasons.append("modelo correspondente")
    if lead.get("phone") and lead.get("email"):
        reasons.append("contato completo")
    elif lead.get("phone"):
        reasons.append("telefone disponivel")
    elif lead.get("email"):
        reasons.append("email disponivel")
    if source:
        reasons.append(f"fonte {source}")

    if not reasons:
        reasons.append("aderencia ao termo buscado")

    text = ", ".join(reasons[:3])
    return text[0].upper() + text[1:] + "."


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
            "Voce escreve reasons curtos para leads de um motor universal de busca. "
            "Responda JSON valido com chave items, lista de objetos {id, reason}. "
            "Cada reason deve ser curto, factual, em pt-BR, maximo 90 caracteres."
        ),
        user_prompt=json.dumps(
            {
                "original_search_term": original_search_term,
                "category": category,
                "vertical": intent.vertical,
                "goal": intent.goal,
                "intent": {
                    "entity": intent.entity,
                    "brand": intent.brand,
                    "model": intent.model,
                    "year": intent.year,
                    "location": intent.location,
                    "attributes": intent.attributes,
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
