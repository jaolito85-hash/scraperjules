from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.services.mock_leads import build_mock_leads, get_mock_lead_by_id
from app.services.supabase_store import (
    CreditsExhaustedError,
    get_user_external_id,
    record_search,
    reveal_lead,
)

router = APIRouter(prefix="/leads", tags=["leads"])


class SearchRequest(BaseModel):
    search_term: str = Field(..., min_length=2)
    category: str = Field(..., min_length=2)
    limit: int = Field(default=10, ge=1, le=50)


class LeadResponse(BaseModel):
    id: str
    title: str
    price: str
    temperature: Literal["HOT", "WARM", "COLD"]
    reason: str
    is_revealed: bool
    phone: str
    email: str
    seller_name: str
    link: str | None = None


class SearchResponse(BaseModel):
    message: str
    credits_remaining: int
    leads: list[LeadResponse]


class RevealResponse(BaseModel):
    message: str
    phone: str
    email: str
    seller_name: str
    link: str
    credits_remaining: int
    already_revealed: bool


@router.post("/search", response_model=SearchResponse)
async def execute_search(payload: SearchRequest, x_user_id: str | None = Header(default=None)):
    search_term = payload.search_term.strip()
    leads = build_mock_leads(search_term)[: payload.limit]
    external_user_id = get_user_external_id(x_user_id)
    profile = record_search(external_user_id, search_term, payload.category, leads)

    return {
        "message": f"Busca concluida para {payload.category}.",
        "credits_remaining": int(profile["credits"]),
        "leads": leads,
    }


@router.post("/{lead_id}/reveal", response_model=RevealResponse)
async def reveal_hot_lead(lead_id: str, x_user_id: str | None = Header(default=None)):
    lead = get_mock_lead_by_id(lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead nao encontrado.")

    external_user_id = get_user_external_id(x_user_id)

    try:
        reveal_result = reveal_lead(external_user_id, lead)
    except CreditsExhaustedError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc

    return {
        "message": "Lead revelado com sucesso.",
        "phone": lead["phone"],
        "email": lead["email"],
        "seller_name": lead["seller_name"],
        "link": lead["link"],
        "credits_remaining": reveal_result["credits_remaining"],
        "already_revealed": reveal_result["already_revealed"],
    }
