from __future__ import annotations

from copy import deepcopy

_BASE_LEADS = [
    {
        "id": "1",
        "title_suffix": "Urgente, mudanca de pais",
        "price": "R$ 85.000",
        "temperature": "HOT",
        "reason": "Preco muito abaixo da FIPE, vendedor demonstrando urgencia.",
        "is_revealed": False,
        "phone": "11999991111",
        "email": "urgente.real@email.com",
        "seller_name": "Vendedor Desesperado",
        "link": "https://www.exemplo.com/anuncio-urgente",
    },
    {
        "id": "2",
        "title_suffix": "Aceita troca menor valor",
        "price": "R$ 98.000",
        "temperature": "WARM",
        "reason": "Preco na media, mas aberto a negociacoes e trocas.",
        "is_revealed": True,
        "phone": "11988882222",
        "email": "contato.morno@email.com",
        "seller_name": "Vendedor Morno",
        "link": "https://www.exemplo.com/anuncio-morno",
    },
    {
        "id": "3",
        "title_suffix": "Estado de zero, unico dono",
        "price": "R$ 115.000",
        "temperature": "COLD",
        "reason": "Preco alto, inflexivel e sem urgencia.",
        "is_revealed": True,
        "phone": "11977773333",
        "email": "contato.frio@email.com",
        "seller_name": "Vendedor Frio",
        "link": "https://www.exemplo.com/anuncio-frio",
    },
]


def build_mock_leads(search_term: str) -> list[dict]:
    normalized_term = search_term.strip()
    leads: list[dict] = []

    for base_lead in _BASE_LEADS:
        lead = deepcopy(base_lead)
        lead["title"] = f"{normalized_term} - {lead.pop('title_suffix')}"
        leads.append(lead)

    return leads


def get_mock_lead_by_id(lead_id: str) -> dict | None:
    for lead in _BASE_LEADS:
        if lead["id"] == lead_id:
            revealed_lead = deepcopy(lead)
            revealed_lead["title"] = f"Lead {lead_id} - {revealed_lead.pop('title_suffix')}"
            return revealed_lead
    return None
