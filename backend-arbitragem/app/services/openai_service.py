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
LEGACY_CATEGORY_TO_VERTICAL = {"b2b_services": "business_local", "automotive": "vehicle", "real_estate": "real_estate"}
VERTICAL_TO_PIPELINE = {"business_local": "b2b_services", "vehicle": "automotive", "real_estate": "real_estate", "product": "product", "service_demand": "service_demand"}
REAL_ESTATE_KEYWORDS = {"apartamento", "casa", "imovel", "terreno", "quartos", "kitnet", "sobrado"}
VEHICLE_KEYWORDS = {"carro", "moto", "veiculo", "caminhonete", "sedan", "hatch", "suv"}
KNOWN_VEHICLE_BRANDS = {"toyota", "honda", "chevrolet", "fiat", "volkswagen", "vw", "hyundai", "renault", "ford", "nissan", "jeep", "yamaha", "suzuki", "bmw", "mercedes", "audi", "kawasaki"}
BUSINESS_KEYWORDS = {"clinica", "odontologica", "dentista", "restaurante", "academia", "hotel", "oficina", "loja", "empresa", "imobiliaria", "mercado", "farmacia"}
PRODUCT_KEYWORDS = {"iphone", "geladeira", "televisao", "tv", "notebook", "sofa", "fogao"}
SERVICE_PROFESSIONS = {"encanador", "pedreiro", "eletricista", "advogado", "pintor", "diarista", "mecanico", "freteiro", "marceneiro"}
BRAZILIAN_STATES = {"acre", "alagoas", "amapa", "amazonas", "bahia", "ceara", "distrito federal", "espirito santo", "goias", "maranhao", "mato grosso", "mato grosso do sul", "minas gerais", "para", "paraiba", "parana", "pernambuco", "piaui", "rio de janeiro", "rio grande do norte", "rio grande do sul", "rondonia", "roraima", "santa catarina", "sao paulo", "sergipe", "tocantins", "pr", "sp", "rj", "sc", "rs", "mg"}
STOPWORDS = {"procure", "buscar", "busque", "mais", "barato", "barata", "clientes", "cliente", "para", "de", "do", "da", "dos", "das", "em", "no", "na", "o", "a", "os", "as"}


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


@dataclass(frozen=True)
class MatchEvaluation:
    score: int
    keep: bool
    reason: str
    match_label: str
    source: str
    temperature: str


def is_openai_enabled() -> bool:
    return os.getenv("OPENAI_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"} and bool(os.getenv("OPENAI_API_KEY", "").strip())


def get_openai_model() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL).strip() or DEFAULT_OPENAI_MODEL


def resolve_pipeline_category(intent: SearchIntent) -> str:
    return intent.pipeline_category


def analyze_search_intent(search_term: str, category: str) -> SearchIntent:
    fallback = _build_fallback_intent(search_term, category)
    if not is_openai_enabled():
        return fallback
    try:
        payload = _chat_json(
            "Responda JSON com vertical, goal, entity, brand, model, year, location, attributes, sort, primary_terms, expanded_terms, primary_query, alternate_queries. Use apenas business_local, vehicle, real_estate, product, service_demand.",
            json.dumps({"search_term": search_term, "requested_category": category}, ensure_ascii=False),
        )
        return _parse_intent_payload(payload, fallback)
    except Exception as exc:
        logger.warning("Falha ao interpretar busca com OpenAI; usando heuristica local", extra={"error": str(exc)})
        return fallback


def enrich_and_rank_leads(leads: list[dict[str, Any]], intent: SearchIntent, *, original_search_term: str, category: str) -> list[dict[str, Any]]:
    if not leads:
        return leads
    evaluated = [(_evaluate_lead(lead, intent), lead) for lead in leads]
    kept = [(ev, lead) for ev, lead in evaluated if ev.keep] or [(_evaluate_lead(lead, intent, allow_relaxed=True), lead) for lead in leads]
    kept.sort(key=lambda item: item[0].score, reverse=True)
    enriched = [{**lead, "reason": ev.reason, "source": ev.source or None, "match_label": ev.match_label, "temperature": ev.temperature} for ev, lead in kept]
    if not is_openai_enabled():
        return enriched
    try:
        reason_map = _generate_reason_map_with_openai(enriched, intent=intent, original_search_term=original_search_term, category=category)
    except Exception as exc:
        logger.warning("Falha ao enriquecer reasons com OpenAI; mantendo reasons deterministicas", extra={"error": str(exc)})
        return enriched
    return [{**lead, "reason": reason_map.get(str(lead.get("id")), str(lead.get("reason") or ""))} for lead in enriched]


def _build_fallback_intent(search_term: str, category: str) -> SearchIntent:
    normalized = _collapse(search_term)
    vertical = _infer_vertical(normalized, category)
    location = _extract_location(normalized)
    brand = _extract_brand(normalized)
    year = _extract_year(normalized)
    attributes = _extract_attributes(normalized, vertical)
    entity = _extract_entity(normalized, vertical, location, brand, year)
    model = _extract_model(normalized, brand, location, year)
    goal = _infer_goal(normalized, vertical)
    sort = "price_asc" if "mais barato" in normalized.lower() or "mais barata" in normalized.lower() else "relevance"
    primary_terms = _terms(entity, brand, model, year, location, attributes)
    expanded_terms = _expand_terms(primary_terms, vertical, goal)
    primary_query = _build_primary_query(vertical, entity, brand, model, year, location, attributes, goal, normalized)
    alternate_queries = tuple(q for q in _alternate_queries(vertical, entity, brand, model, year, location, goal, normalized) if q != primary_query)[:2]
    return SearchIntent(normalized, category, vertical, goal, entity, brand, model, year, location, attributes, sort, tuple(primary_terms[:6]), tuple(expanded_terms[:8]), primary_query, alternate_queries, VERTICAL_TO_PIPELINE[vertical])


def _infer_vertical(search_term: str, category: str) -> str:
    if category.strip().lower() in LEGACY_CATEGORY_TO_VERTICAL:
        return LEGACY_CATEGORY_TO_VERTICAL[category.strip().lower()]
    lowered = search_term.lower()
    if "clientes para" in lowered or "cliente para" in lowered or any(p in lowered for p in SERVICE_PROFESSIONS):
        return "service_demand"
    if any(k in lowered for k in REAL_ESTATE_KEYWORDS):
        return "real_estate"
    if any(k in lowered for k in VEHICLE_KEYWORDS) or any(k in lowered for k in KNOWN_VEHICLE_BRANDS):
        return "vehicle"
    if any(k in lowered for k in BUSINESS_KEYWORDS):
        return "business_local"
    if any(k in lowered for k in PRODUCT_KEYWORDS):
        return "product"
    return "product"


def _infer_goal(search_term: str, vertical: str) -> str:
    lowered = search_term.lower()
    if "clientes para" in lowered or "cliente para" in lowered:
        return "generate_demand"
    if "mais barato" in lowered or "mais barata" in lowered:
        return "find_cheapest"
    if any(t in lowered for t in ("aluguel", "alugar", "locacao")):
        return "rent"
    if vertical == "business_local":
        return "find_local_business"
    return "search_supply"


def _extract_location(search_term: str) -> str:
    lowered = search_term.lower()
    parts = [part.strip() for part in re.split(r"[,/\-\n]+", lowered) if part.strip()]
    for part in reversed(parts):
        words = part.split()
        if part in BRAZILIAN_STATES or len(words) in {1, 2}:
            return part.title()
    words = [word for word in lowered.split() if word]
    if len(words) >= 2:
        return " ".join(words[-2:]).title()
    return ""


def _extract_brand(search_term: str) -> str:
    lowered = search_term.lower()
    for brand in sorted(KNOWN_VEHICLE_BRANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(brand)}\b", lowered):
            return brand.title()
    return ""


def _extract_year(search_term: str) -> str:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", search_term)
    return match.group(1) if match else ""


def _extract_attributes(search_term: str, vertical: str) -> dict[str, str]:
    lowered = search_term.lower()
    attrs: dict[str, str] = {}
    rooms = re.search(r"(\d+)\s+quartos?", lowered)
    if rooms:
        attrs["rooms"] = rooms.group(1)
    if "moto" in lowered:
        attrs["vehicle_type"] = "moto"
    elif "carro" in lowered or "sedan" in lowered or "hatch" in lowered or "suv" in lowered:
        attrs["vehicle_type"] = "carro"
    if "apartamento" in lowered:
        attrs["property_type"] = "apartamento"
    elif "casa" in lowered:
        attrs["property_type"] = "casa"
    if any(t in lowered for t in ("aluguel", "alugar", "locacao")):
        attrs["transaction_type"] = "rent"
    elif any(t in lowered for t in ("venda", "comprar", "compra")):
        attrs["transaction_type"] = "sale"
    if vertical == "service_demand":
        for profession in SERVICE_PROFESSIONS:
            if profession in lowered:
                attrs["service"] = profession
                break
    return attrs


def _extract_entity(search_term: str, vertical: str, location: str, brand: str, year: str) -> str:
    value = search_term
    for item in (location, brand, year):
        if item:
            value = re.sub(re.escape(item), "", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(procure|buscar|busque|mais barato|mais barata|do brasil|de brasil|o|a|os|as)\b", "", value, flags=re.IGNORECASE)
    value = _collapse(value).strip(" ,-")
    return value or {"business_local": "negocio local", "vehicle": "veiculo", "real_estate": "imovel", "product": "produto", "service_demand": "demanda de servico"}[vertical]


def _extract_model(search_term: str, brand: str, location: str, year: str) -> str:
    value = search_term
    for item in (brand, location, year):
        if item:
            value = re.sub(re.escape(item), "", value, flags=re.IGNORECASE)
    tokens = [token for token in re.split(r"[^a-zA-Z0-9à-ÿÀ-ß]+", value) if token]
    clean = [token for token in tokens if token.lower() not in STOPWORDS and len(token) > 1]
    return " ".join(clean[:3]).strip()


def _terms(entity: str, brand: str, model: str, year: str, location: str, attrs: dict[str, str]) -> list[str]:
    terms: list[str] = []
    for candidate in (entity, brand, model, year, location, attrs.get("service", ""), attrs.get("rooms", ""), attrs.get("property_type", "")):
        for token in re.split(r"[^a-zA-Z0-9à-ÿÀ-ß]+", str(candidate).lower()):
            if len(token) < 2 or token in STOPWORDS or token in terms:
                continue
            terms.append(token)
    if attrs.get("vehicle_type") and attrs["vehicle_type"] not in terms:
        terms.append(attrs["vehicle_type"])
    return terms


def _expand_terms(primary_terms: Iterable[str], vertical: str, goal: str) -> list[str]:
    extras = {
        "business_local": ["google maps", "telefone", "contato"],
        "vehicle": ["webmotors", "olx", "seminovo"],
        "real_estate": ["imovel", "zap", "olx"],
        "product": ["marketplace", "preco", "oferta"],
        "service_demand": ["orcamento", "contratar", "servico"],
    }
    expanded = list(primary_terms)
    for term in extras.get(vertical, []):
        if term not in expanded:
            expanded.append(term)
    if goal == "find_cheapest" and "mais barato" not in expanded:
        expanded.append("mais barato")
    return expanded


def _build_primary_query(vertical: str, entity: str, brand: str, model: str, year: str, location: str, attrs: dict[str, str], goal: str, original: str) -> str:
    if vertical == "service_demand":
        return _collapse(f"{attrs.get('service') or entity} clientes {location}")
    if vertical == "real_estate":
        return _collapse(f"{entity} {attrs.get('rooms', '')} quartos {location} {'mais barato' if goal == 'find_cheapest' else ''}")
    if vertical == "vehicle":
        return _collapse(f"{brand} {model} {year} {location} {'mais barato' if goal == 'find_cheapest' else ''}")
    if vertical in {"business_local", "product"}:
        return _collapse(f"{entity} {location}")
    return original


def _alternate_queries(vertical: str, entity: str, brand: str, model: str, year: str, location: str, goal: str, original: str) -> list[str]:
    queries: list[str] = []
    if vertical == "service_demand":
        queries.extend([_collapse(f"contratar {entity} {location}"), _collapse(f"{entity} orcamento {location}")])
    elif vertical == "vehicle":
        queries.extend([_collapse(f"{brand} {model} {year} olx {location}"), _collapse(f"{brand} {model} {year} webmotors")])
    elif vertical == "real_estate":
        queries.extend([_collapse(f"{entity} olx {location}"), _collapse(f"{entity} zap imoveis {location}")])
    elif vertical == "business_local":
        queries.extend([_collapse(f"{entity} {location} telefone"), _collapse(f"{entity} {location} google maps")])
    else:
        queries.append(_collapse(f"{entity} marketplace {location}"))
        if goal == "find_cheapest":
            queries.append(_collapse(f"{entity} menor preco {location}"))
    queries.append(_collapse(original))
    return [query for i, query in enumerate(queries) if query and query not in queries[:i]]


def _openai_headers() -> dict[str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY nao configurada.")
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def _chat_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    response = httpx.post(
        f"{os.getenv('OPENAI_BASE_URL', DEFAULT_OPENAI_BASE_URL).rstrip('/')}/chat/completions",
        headers=_openai_headers(),
        json={"model": get_openai_model(), "temperature": 0.2, "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]},
        timeout=25.0,
    )
    response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


def _parse_intent_payload(payload: dict[str, Any], fallback: SearchIntent) -> SearchIntent:
    vertical = str(payload.get("vertical") or fallback.vertical).strip()
    if vertical not in SUPPORTED_VERTICALS:
        vertical = fallback.vertical
    attrs = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else fallback.attributes
    primary_query = str(payload.get("primary_query") or fallback.primary_query).strip()
    alternate = tuple(q for q in _sanitize_list(payload.get("alternate_queries"), fallback.alternate_queries) if q and q != primary_query)[:2]
    return SearchIntent(
        fallback.original_search_term,
        fallback.requested_category,
        vertical,
        str(payload.get("goal") or fallback.goal).strip(),
        str(payload.get("entity") or fallback.entity).strip(),
        str(payload.get("brand") or fallback.brand).strip(),
        str(payload.get("model") or fallback.model).strip(),
        str(payload.get("year") or fallback.year).strip(),
        str(payload.get("location") or fallback.location).strip(),
        {str(k): str(v) for k, v in attrs.items()},
        str(payload.get("sort") or fallback.sort).strip(),
        _sanitize_list(payload.get("primary_terms"), fallback.primary_terms),
        _sanitize_list(payload.get("expanded_terms"), fallback.expanded_terms),
        primary_query,
        alternate,
        VERTICAL_TO_PIPELINE.get(vertical, fallback.pipeline_category),
    )


def _sanitize_list(value: Any, fallback: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        return tuple(str(item).strip() for item in fallback if str(item).strip())
    out: list[str] = []
    for item in value:
        item = str(item).strip()
        if item and item not in out:
            out.append(item)
    return tuple(out)


def _evaluate_lead(lead: dict[str, Any], intent: SearchIntent, allow_relaxed: bool = False) -> MatchEvaluation:
    source = _infer_source_label(str(lead.get("link") or ""))
    haystack = _haystack(lead)
    if intent.vertical == "vehicle":
        score = 0
        reasons: list[str] = []
        keep = True
        if intent.attributes.get("vehicle_type") == "moto":
            if any(t in haystack for t in ("moto", "cg", "titan")):
                score += 3
                reasons.append("tipo moto correspondente")
            elif not allow_relaxed:
                keep = False
        if intent.brand:
            if intent.brand.lower() in haystack:
                score += 4
                reasons.append(f"marca {intent.brand} correspondente")
            elif any(b in haystack for b in KNOWN_VEHICLE_BRANDS if b != intent.brand.lower()) and not allow_relaxed:
                keep = False
                reasons.append("marca divergente")
        if intent.model:
            if intent.model.lower() in haystack:
                score += 4
                reasons.append("modelo correspondente")
            elif not allow_relaxed:
                score -= 3
        if intent.year and intent.year in haystack:
            score += 3
            reasons.append(f"ano {intent.year} correspondente")
        if intent.location and intent.location.lower() in haystack:
            score += 2
            reasons.append(f"localizacao em {intent.location}")
        if str(lead.get("price") or "").lower() != "sob consulta":
            score += 1
            if intent.sort == "price_asc":
                reasons.append("preco visivel")
        return _build_eval(score, keep and score >= (3 if not allow_relaxed else 0), reasons or ["aderencia parcial ao veiculo pedido"], source, hot=8, warm=3)

    if intent.vertical == "real_estate":
        score = 0
        reasons = []
        keep = True
        ptype = intent.attributes.get("property_type")
        if ptype:
            if ptype in haystack:
                score += 3
                reasons.append(f"tipo {ptype} correspondente")
            elif not allow_relaxed:
                keep = False
        rooms = intent.attributes.get("rooms")
        if rooms and (re.search(rf"\b{re.escape(rooms)}\s+quartos?\b", haystack) or re.search(rf"\b{re.escape(rooms)}\s+dormitorios?\b", haystack)):
            score += 3
            reasons.append(f"{rooms} quartos correspondentes")
        elif rooms and not allow_relaxed:
            score -= 2
        if intent.location and intent.location.lower() in haystack:
            score += 3
            reasons.append(f"localizacao em {intent.location}")
        if str(lead.get("price") or "").lower() != "sob consulta":
            score += 1
            if intent.sort == "price_asc":
                reasons.append("preco visivel")
        if intent.attributes.get("transaction_type") == "rent" and any(t in haystack for t in ("aluguel", "alugar", "locacao")):
            score += 2
            reasons.append("objetivo de aluguel compativel")
        if intent.attributes.get("transaction_type") == "sale" and any(t in haystack for t in ("venda", "comprar", "financiamento")):
            score += 2
            reasons.append("objetivo de compra compativel")
        return _build_eval(score, keep and score >= (2 if not allow_relaxed else 0), reasons or ["aderencia parcial ao imovel pedido"], source, hot=7, warm=2)

    if intent.vertical == "service_demand":
        score = 0
        reasons = []
        service = intent.attributes.get("service") or intent.entity
        if service and service.lower() in haystack:
            score += 3
            reasons.append(f"servico {service} relacionado")
        if intent.location and intent.location.lower() in haystack:
            score += 2
            reasons.append(f"atende ou menciona {intent.location}")
        demand = any(t in haystack for t in ("precisa", "procura", "orcamento", "contratar"))
        partner = any(t in haystack for t in ("24h", "empresa", "servico", "atendemos", "assistencia", "solucao"))
        label = "HOT" if demand else "PARTNER" if partner else "WARM"
        if demand:
            score += 4
            reasons.append("sinal de demanda explicita")
        elif partner:
            score += 2
            reasons.append("sinal de parceiro potencial")
        if lead.get("phone") or lead.get("email"):
            score += 2
            reasons.append("contato disponivel")
        temp = "HOT" if label == "HOT" else "WARM" if score >= 2 else "COLD"
        return MatchEvaluation(score, score >= (2 if not allow_relaxed else 0), _render(reasons or ["resultado generico para a demanda"]), label, source, temp)

    if intent.vertical == "business_local":
        score = sum(2 for term in intent.primary_terms if term in haystack[:300])
        reasons = []
        if intent.location and intent.location.lower() in haystack:
            score += 2
            reasons.append(f"localizacao em {intent.location}")
        if lead.get("phone"):
            score += 3
            reasons.append("telefone disponivel")
        if source:
            reasons.append(f"fonte {source}")
        return _build_eval(score, score >= (2 if not allow_relaxed else 0), reasons or ["negocio local com sinais basicos de aderencia"], source, hot=6, warm=2)

    score = min(sum(2 for term in intent.primary_terms if term in haystack), 6)
    reasons = ["nome do item aderente"] if score else ["aderencia basica ao produto"]
    if intent.location and intent.location.lower() in haystack:
        score += 2
        reasons.append(f"localizacao em {intent.location}")
    if str(lead.get("price") or "").lower() != "sob consulta":
        score += 1
        reasons.append("preco visivel")
    return _build_eval(score, score >= (2 if not allow_relaxed else 0), reasons, source, hot=6, warm=2)


def _build_eval(score: int, keep: bool, reasons: list[str], source: str, hot: int, warm: int) -> MatchEvaluation:
    temperature = "HOT" if score >= hot else "WARM" if score >= warm else "COLD"
    label = "HOT" if temperature == "HOT" else "WARM"
    return MatchEvaluation(score, keep, _render(reasons), label, source, temperature)


def _haystack(lead: dict[str, Any]) -> str:
    return " ".join([str(lead.get("title") or ""), str(lead.get("seller_name") or ""), str(lead.get("link") or ""), str(lead.get("reason") or "")]).lower()


def _infer_source_label(link: str) -> str:
    host = urlparse(link).netloc.lower()
    if "google.com" in host and "maps" in link:
        return "Google Maps"
    if "google.com" in host:
        return "Google Search"
    if "webmotors" in host:
        return "Webmotors"
    if "olx" in host:
        return "OLX"
    if "zapimoveis" in host:
        return "Zap Imoveis"
    if "facebook" in host:
        return "Facebook Marketplace"
    return ""


def _render(reasons: list[str]) -> str:
    unique = [reason.strip() for reason in reasons if reason.strip()]
    deduped = [reason for i, reason in enumerate(unique) if reason not in unique[:i]]
    text = ", ".join(deduped[:3]) or "aderencia basica ao pedido"
    return text[0].upper() + text[1:] + "."


def _collapse(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _generate_reason_map_with_openai(leads: list[dict[str, Any]], *, intent: SearchIntent, original_search_term: str, category: str) -> dict[str, str]:
    compact = [{"id": str(lead.get("id")), "title": str(lead.get("title") or ""), "price": str(lead.get("price") or ""), "temperature": str(lead.get("temperature") or ""), "match_label": str(lead.get("match_label") or ""), "source": str(lead.get("source") or ""), "has_phone": bool(lead.get("phone")), "has_email": bool(lead.get("email")), "current_reason": str(lead.get("reason") or "")} for lead in leads[:12]]
    payload = _chat_json(
        "Escreva reasons curtos para leads. Responda JSON com items: [{id, reason}] e no maximo 90 caracteres por reason.",
        json.dumps({"original_search_term": original_search_term, "category": category, "vertical": intent.vertical, "goal": intent.goal, "intent": {"entity": intent.entity, "brand": intent.brand, "model": intent.model, "year": intent.year, "location": intent.location, "attributes": intent.attributes}, "leads": compact}, ensure_ascii=False),
    )
    items = payload.get("items")
    if not isinstance(items, list):
        return {}
    return {str(item.get("id")).strip(): str(item.get("reason")).strip()[:90] for item in items if isinstance(item, dict) and str(item.get("id") or "").strip() and str(item.get("reason") or "").strip()}
