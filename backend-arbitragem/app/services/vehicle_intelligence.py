from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

VEHICLE_CONFIDENCE_MIN = 7

VEHICLE_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "car": ("carro", "carros", "veiculo", "veiculo", "automovel", "automoveis", "sedan", "hatch", "suv", "pickup", "caminhonete", "cupe"),
    "motorcycle": ("moto", "motos", "motocicleta", "motocicletas"),
}

VEHICLE_BRAND_ALIASES: dict[str, tuple[str, ...]] = {
    "Honda": ("honda",),
    "Toyota": ("toyota",),
    "Chevrolet": ("chevrolet", "gm"),
    "Citroen": ("citroen",),
    "Fiat": ("fiat",),
    "Volkswagen": ("volkswagen", "vw"),
    "Hyundai": ("hyundai",),
    "Kia": ("kia",),
    "Renault": ("renault",),
    "Ford": ("ford",),
    "Nissan": ("nissan",),
    "Jeep": ("jeep",),
    "Peugeot": ("peugeot",),
    "Yamaha": ("yamaha",),
    "Suzuki": ("suzuki",),
    "BMW": ("bmw",),
    "Mercedes-Benz": ("mercedes", "mercedes benz"),
    "Audi": ("audi",),
    "BYD": ("byd",),
    "Caoa Chery": ("caoa chery", "chery"),
    "Kawasaki": ("kawasaki",),
    "Lexus": ("lexus",),
    "Mitsubishi": ("mitsubishi",),
    "Volvo": ("volvo",),
    "Porsche": ("porsche",),
    "Ram": ("ram",),
    "Subaru": ("subaru",),
}

MODEL_ALIASES: dict[str, dict[str, Any]] = {
    "civic": {"brand": "Honda", "vehicle_type": "car", "aliases": ("civic", "new civic", "novo civic")},
    "city": {"brand": "Honda", "vehicle_type": "car", "aliases": ("city",)},
    "fit": {"brand": "Honda", "vehicle_type": "car", "aliases": ("fit",)},
    "corolla": {"brand": "Toyota", "vehicle_type": "car", "aliases": ("corolla",)},
    "hilux": {"brand": "Toyota", "vehicle_type": "car", "aliases": ("hilux",)},
    "onix": {"brand": "Chevrolet", "vehicle_type": "car", "aliases": ("onix", "onix plus")},
    "tracker": {"brand": "Chevrolet", "vehicle_type": "car", "aliases": ("tracker",)},
    "gol": {"brand": "Volkswagen", "vehicle_type": "car", "aliases": ("gol",)},
    "polo": {"brand": "Volkswagen", "vehicle_type": "car", "aliases": ("polo", "virtus")},
    "hb20": {"brand": "Hyundai", "vehicle_type": "car", "aliases": ("hb20",)},
    "compass": {"brand": "Jeep", "vehicle_type": "car", "aliases": ("compass",)},
    "taycan": {"brand": "Porsche", "vehicle_type": "car", "aliases": ("taycan",)},
    "ex30": {"brand": "Volvo", "vehicle_type": "car", "aliases": ("ex30",)},
    "titan": {"brand": "Honda", "vehicle_type": "motorcycle", "aliases": ("titan", "cg titan", "titan 160", "cg 160 titan")},
    "fan": {"brand": "Honda", "vehicle_type": "motorcycle", "aliases": ("fan", "cg fan")},
    "bros": {"brand": "Honda", "vehicle_type": "motorcycle", "aliases": ("bros", "nxr", "nxr bros")},
    "biz": {"brand": "Honda", "vehicle_type": "motorcycle", "aliases": ("biz",)},
    "lander": {"brand": "Yamaha", "vehicle_type": "motorcycle", "aliases": ("lander",)},
    "factor": {"brand": "Yamaha", "vehicle_type": "motorcycle", "aliases": ("factor",)},
    "fazer": {"brand": "Yamaha", "vehicle_type": "motorcycle", "aliases": ("fazer",)},
}

LOCATION_STOPWORDS = {
    "brasil",
    "br",
    "mais",
    "barato",
    "barata",
    "baratos",
    "baratas",
    "procure",
    "buscar",
    "busque",
    "ache",
    "quero",
    "comprar",
    "de",
    "do",
    "da",
    "dos",
    "das",
    "no",
    "na",
    "nos",
    "nas",
    "em",
    "o",
    "a",
    "os",
    "as",
}

BRAZIL_LOCATION_ALIASES: dict[str, tuple[str, ...]] = {
    "Brasil": ("brasil", "br"),
    "Parana": ("parana", "pr"),
    "Sao Paulo": ("sao paulo", "sp"),
    "Rio de Janeiro": ("rio de janeiro", "rj"),
    "Santa Catarina": ("santa catarina", "sc"),
    "Rio Grande do Sul": ("rio grande do sul", "rs"),
    "Minas Gerais": ("minas gerais", "mg"),
}

GENERIC_VEHICLE_STOPWORDS = LOCATION_STOPWORDS | {
    "carro",
    "carros",
    "moto",
    "motos",
    "veiculo",
    "veiculos",
    "seminovo",
    "seminovos",
    "usado",
    "usados",
}


@dataclass(frozen=True)
class VehicleQuery:
    original: str
    normalized: str
    vehicle_type: str
    brand: str
    model: str
    year: str
    location: str
    goal: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class VehicleCandidate:
    normalized_title: str
    vehicle_type: str
    brand: str
    model: str
    brand_hits: tuple[str, ...]
    model_hits: tuple[str, ...]
    years: tuple[str, ...]
    location: str


@dataclass(frozen=True)
class VehicleMatch:
    keep: bool
    score: int
    reason: str
    confidence: str
    matched_brand: str
    matched_model: str


def normalize_vehicle_text(value: str) -> str:
    ascii_value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9]+", " ", ascii_value).lower()).strip()


def parse_vehicle_query(search_term: str) -> VehicleQuery:
    normalized = normalize_vehicle_text(search_term)
    goal = "find_cheapest" if any(term in normalized for term in ("mais barato", "mais barata", "menor preco")) else "search_supply"
    brand = _extract_brand(normalized)
    model = _extract_model(normalized, brand)
    vehicle_type = _extract_vehicle_type(normalized, model)
    year = _extract_year(normalized)
    location = _extract_location(normalized)
    aliases = _build_aliases(brand, model)
    return VehicleQuery(
        original=search_term,
        normalized=normalized,
        vehicle_type=vehicle_type,
        brand=brand,
        model=model,
        year=year,
        location=location,
        goal=goal,
        aliases=aliases,
    )


def is_vehicle_search(search_term: str) -> bool:
    parsed = parse_vehicle_query(search_term)
    signal = vehicle_signal_score(search_term)
    return signal >= 3 or bool(parsed.brand or parsed.model or (parsed.vehicle_type and parsed.year))


def vehicle_signal_score(search_term: str) -> int:
    normalized = normalize_vehicle_text(search_term)
    score = 0
    if _extract_brand(normalized):
        score += 2
    if _extract_model(normalized, _extract_brand(normalized)):
        score += 2
    if _extract_vehicle_type(normalized):
        score += 1
    if _extract_year(normalized):
        score += 1
    return score


def build_vehicle_queries(query: VehicleQuery) -> dict[str, str]:
    base_tokens = [query.brand, query.model, query.year, query.location]
    inventory_term = "moto" if query.vehicle_type == "motorcycle" else "carro"
    source_term = "motos" if query.vehicle_type == "motorcycle" else "carros"
    if query.vehicle_type:
        base_tokens.append(inventory_term)
    base = _collapse_join(base_tokens)
    cheapest = "mais barato" if query.goal == "find_cheapest" else ""
    return {
        "webmotors": _collapse_join([query.brand, query.model, query.year, query.location, cheapest, source_term]),
        "olx_cars": _collapse_join([query.brand, query.model, query.year, query.location, cheapest]),
        "marketplace": _collapse_join([base, cheapest]),
        "fallback": _collapse_join([base, cheapest, "brasil"]),
    }


def parse_vehicle_candidate(item: dict[str, Any]) -> VehicleCandidate:
    identity_parts = [
        item.get("title"),
        item.get("name"),
        item.get("headline"),
        item.get("listingTitle"),
        item.get("brand"),
        item.get("model"),
        item.get("version"),
        item.get("year"),
        item.get("city"),
        item.get("state"),
        item.get("location"),
    ]
    normalized_title = normalize_vehicle_text(" ".join(str(part or "") for part in identity_parts if part))
    explicit_brand = _extract_brand(normalize_vehicle_text(str(item.get("brand") or "")))
    explicit_model = _extract_model(normalize_vehicle_text(str(item.get("model") or "")), explicit_brand)
    brand_hits = _extract_brand_hits(normalized_title)
    model_hits = _extract_model_hits(normalized_title)
    brand = explicit_brand or _resolve_brand_from_hits(brand_hits, model_hits)
    model = explicit_model or _resolve_model_from_hits(model_hits, brand)
    vehicle_type = _extract_vehicle_type(normalized_title, model)
    location = _extract_location(normalized_title)
    years = tuple(dict.fromkeys(re.findall(r"\b(19\d{2}|20\d{2})\b", normalized_title)))
    return VehicleCandidate(
        normalized_title=normalized_title,
        vehicle_type=vehicle_type,
        brand=brand,
        model=model,
        brand_hits=brand_hits,
        model_hits=model_hits,
        years=years,
        location=location,
    )


def evaluate_vehicle_match(candidate: VehicleCandidate, query: VehicleQuery, *, source: str = "") -> VehicleMatch:
    reasons: list[str] = []
    score = 0
    brand_hits = set(candidate.brand_hits)
    model_hits = set(candidate.model_hits)

    if source == "Google Search":
        polluted_tail = _strip_query_prefix(candidate.normalized_title, query)
        if polluted_tail and not _tail_mentions_requested_vehicle(polluted_tail, query):
            return VehicleMatch(False, 0, "", "LOW", candidate.brand, candidate.model)

    if query.vehicle_type:
        if candidate.vehicle_type != query.vehicle_type:
            return VehicleMatch(False, 0, "", "LOW", candidate.brand, candidate.model)
        score += 2
        reasons.append("tipo correspondente")

    if query.brand:
        if query.brand not in brand_hits and candidate.brand != query.brand:
            return VehicleMatch(False, 0, "", "LOW", candidate.brand, candidate.model)
        conflicting_brands = {brand for brand in brand_hits if brand != query.brand}
        if conflicting_brands:
            return VehicleMatch(False, 0, "", "LOW", candidate.brand, candidate.model)
        score += 4
        reasons.append(f"marca {query.brand}")

    if query.model:
        if query.model not in model_hits and candidate.model != query.model:
            return VehicleMatch(False, 0, "", "LOW", candidate.brand, candidate.model)
        conflicting_models = {model for model in model_hits if model != query.model}
        if conflicting_models:
            return VehicleMatch(False, 0, "", "LOW", candidate.brand, candidate.model)
        score += 4
        reasons.append(f"modelo {query.model}")

    if query.year:
        if query.year not in candidate.years:
            return VehicleMatch(False, 0, "", "LOW", candidate.brand, candidate.model)
        score += 3
        reasons.append(f"ano {query.year}")

    if query.location:
        if candidate.location and candidate.location != query.location:
            return VehicleMatch(False, 0, "", "LOW", candidate.brand, candidate.model)
        if candidate.location == query.location:
            score += 2
            reasons.append(f"local {query.location}")

    if score < _min_vehicle_score(query):
        return VehicleMatch(False, score, "", "LOW", candidate.brand, candidate.model)

    confidence = "HIGH" if score >= 10 else "MEDIUM"
    return VehicleMatch(True, score, ", ".join(reasons[:3]), confidence, candidate.brand, candidate.model)


def is_vehicle_listing_result(link: str, query: VehicleQuery, *, source: str = "", price: str = "") -> bool:
    normalized_price = str(price or "").strip().lower()
    if query.goal == "find_cheapest" and normalized_price in {"", "sob consulta"}:
        return False

    parsed = urlparse(str(link or "").strip())
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    last_segment = path.rstrip("/").split("/")[-1] if path else ""
    blocked_path_markers = (
        "/busca",
        "/search",
        "tabela-fipe",
        "/fipe",
        "/tabela",
        "/catalogo",
        "/blog",
        "/noticia",
        "/noticias",
        "/artigo",
        "/review",
        "/comparativo",
        "/guia",
        "/precos",
    )

    if not host:
        return False

    blocked_hosts = (
        "youtube.com",
        "youtu.be",
        "instagram.com",
        "tiktok.com",
        "linkedin.com",
        "wikipedia.org",
        "globo.com",
        "uol.com.br",
        "napista.com.br",
    )
    if any(domain in host for domain in blocked_hosts):
        return False
    if any(marker in path for marker in blocked_path_markers):
        return False

    if "facebook.com" in host:
        return "marketplace/item" in path

    if "webmotors" in host:
        detail_markers = ("/comprar/", "/detalhe/", "/anuncio/", "/veiculo/")
        return any(marker in path for marker in detail_markers) and bool(re.search(r"\d{4,}", path))

    if "olx.com.br" in host:
        return "/item/" in path or "/d/" in path or bool(re.search(r"-\d{6,}$", last_segment))

    if "mercadolivre" in host:
        return "mlb-" in path and "/lista" not in path

    if "icarros.com.br" in host:
        return bool(re.search(r"\d{5,}", last_segment))

    if "mobiauto.com.br" in host:
        return any(marker in path for marker in ("/veiculo/", "/anuncio/", "/oferta/")) or bool(re.search(r"\d{5,}", last_segment))

    if "kavak.com" in host:
        return any(marker in path for marker in ("/veiculo/", "/carro/", "/compra/")) and bool(re.search(r"\d{4,}", path))

    if source == "Google Search":
        return False

    return bool(re.search(r"\d{5,}", last_segment)) and not any(marker in path for marker in blocked_path_markers)


def canonical_vehicle_type(value: str) -> str:
    normalized = normalize_vehicle_text(value)
    for canonical, aliases in VEHICLE_TYPE_ALIASES.items():
        if any(alias in normalized.split() or f" {alias} " in f" {normalized} " for alias in aliases):
            return canonical
    return ""


def canonical_location(value: str) -> str:
    normalized = normalize_vehicle_text(value)
    for canonical, aliases in BRAZIL_LOCATION_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            return canonical
    return value.strip().title() if value.strip() else ""


def _extract_brand(normalized: str) -> str:
    hits = _extract_brand_hits(normalized)
    if hits:
        return hits[0]
    return ""


def _extract_brand_hits(normalized: str) -> tuple[str, ...]:
    hits: list[str] = []
    for canonical, aliases in VEHICLE_BRAND_ALIASES.items():
        for alias in aliases:
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                hits.append(canonical)
                break
    for model_name, config in MODEL_ALIASES.items():
        for alias in config["aliases"]:
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                hits.append(str(config["brand"]))
                break
    return tuple(dict.fromkeys(hits))


def _extract_model(normalized: str, brand: str) -> str:
    hits = _extract_model_hits(normalized, brand)
    if hits:
        return hits[0]
    return ""


def _extract_model_hits(normalized: str, brand: str = "") -> tuple[str, ...]:
    hits: list[str] = []
    for canonical, config in MODEL_ALIASES.items():
        if brand and config["brand"] != brand:
            continue
        for alias in config["aliases"]:
            if re.search(rf"\b{re.escape(alias)}\b", normalized):
                hits.append(canonical)
                break

    stripped = normalized
    if brand:
        for alias in VEHICLE_BRAND_ALIASES.get(brand, (brand.lower(),)):
            stripped = re.sub(rf"\b{re.escape(alias)}\b", " ", stripped)
    stripped = re.sub(r"\b(19\d{2}|20\d{2})\b", " ", stripped)
    stripped = re.sub(r"\b(mais barato|mais barata|menor preco)\b", " ", stripped)
    stripped = re.sub(r"\b(brasil|parana|sao paulo|rio de janeiro|santa catarina|minas gerais|rio grande do sul|pr|sp|rj|sc|mg|rs)\b", " ", stripped)
    tokens = [token for token in stripped.split() if token not in GENERIC_VEHICLE_STOPWORDS and len(token) > 1]
    if not tokens:
        return tuple(dict.fromkeys(hits))
    if not hits:
        hits.append(" ".join(tokens[:2]))
    return tuple(dict.fromkeys(hits))


def _extract_vehicle_type(normalized: str, model: str = "") -> str:
    for canonical, aliases in VEHICLE_TYPE_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            return canonical
    if model and model in MODEL_ALIASES:
        return str(MODEL_ALIASES[model]["vehicle_type"])
    return ""


def _extract_year(normalized: str) -> str:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", normalized)
    return match.group(1) if match else ""


def _extract_location(normalized: str) -> str:
    for canonical, aliases in BRAZIL_LOCATION_ALIASES.items():
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized) for alias in aliases):
            return canonical
    tokens = normalized.split()
    for size in (3, 2, 1):
        for start in range(len(tokens) - size + 1):
            chunk = " ".join(tokens[start : start + size])
            if chunk in LOCATION_STOPWORDS:
                continue
            if start > 0 and tokens[start - 1] in {"em", "no", "na", "do", "da"}:
                return chunk.title()
    return ""


def _build_aliases(brand: str, model: str) -> tuple[str, ...]:
    aliases: list[str] = []
    if model and model in MODEL_ALIASES:
        for alias in MODEL_ALIASES[model]["aliases"]:
            aliases.append(alias)
    if brand and model:
        aliases.append(f"{brand.lower()} {model}")
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def _min_vehicle_score(query: VehicleQuery) -> int:
    score = 0
    if query.vehicle_type:
        score += 2
    if query.brand:
        score += 4
    if query.model:
        score += 4
    if query.year:
        score += 3
    if query.location:
        score += 1
    return max(VEHICLE_CONFIDENCE_MIN, min(score, 11))


def _collapse_join(values: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(str(value or "").strip() for value in values if str(value or "").strip())).strip()


def _resolve_brand_from_hits(brand_hits: tuple[str, ...], model_hits: tuple[str, ...]) -> str:
    if len(brand_hits) == 1:
        return brand_hits[0]
    for model in model_hits:
        config = MODEL_ALIASES.get(model)
        if config and str(config["brand"]) in brand_hits:
            return str(config["brand"])
    return brand_hits[0] if brand_hits else ""


def _resolve_model_from_hits(model_hits: tuple[str, ...], brand: str) -> str:
    if not brand:
        return model_hits[0] if model_hits else ""
    for model in model_hits:
        config = MODEL_ALIASES.get(model)
        if config and str(config["brand"]) == brand:
            return model
    return model_hits[0] if model_hits else ""


def _strip_query_prefix(normalized_title: str, query: VehicleQuery) -> str:
    prefixes = [
        query.normalized,
        _collapse_join([query.brand, query.model, query.year, query.location]),
        _collapse_join([query.model, query.year, query.location]),
        _collapse_join([query.brand, query.model, query.year]),
        _collapse_join([query.brand, query.model]),
    ]
    for prefix in dict.fromkeys(prefix for prefix in prefixes if prefix):
        if normalized_title.startswith(prefix):
            tail = normalized_title[len(prefix) :].strip()
            if tail:
                return tail
    return ""


def _tail_mentions_requested_vehicle(normalized_tail: str, query: VehicleQuery) -> bool:
    if query.model:
        aliases = MODEL_ALIASES.get(query.model, {}).get("aliases", (query.model,))
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized_tail) for alias in aliases):
            return True
    if query.brand:
        aliases = VEHICLE_BRAND_ALIASES.get(query.brand, (query.brand.lower(),))
        if any(re.search(rf"\b{re.escape(alias)}\b", normalized_tail) for alias in aliases):
            return True
    return False
