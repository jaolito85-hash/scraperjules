import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FILES = {
    "requirements.txt": """fastapi==0.110.0
uvicorn[standard]==0.27.1
supabase==2.3.6
openai==1.13.3
beautifulsoup4==4.12.3
playwright==1.42.0
pydantic==2.6.3
python-dotenv==1.0.1
""",
    ".env.example": """OPENAI_API_KEY=sk-SuaChaveAqui
SUPABASE_URL=https://seu-projeto.supabase.co
SUPABASE_SERVICE_ROLE_KEY=sua-service-role-key-aqui
FRONTEND_URL=http://localhost:3000
ALLOWED_ORIGINS=http://localhost:3000
PORT=8000
""",
    ".dockerignore": """__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/
.env
.git/
""",
    "Dockerfile": """FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY .env.example ./

ENV PORT=8000
EXPOSE 8000

CMD [\"sh\", \"-c\", \"uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}\"]
""",
    "app/__init__.py": "",
    "app/routers/__init__.py": "",
    "app/main.py": """from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.routers import leads, export

load_dotenv()


def get_allowed_origins() -> list[str]:
    raw_origins = os.getenv(\"ALLOWED_ORIGINS\")
    if raw_origins:
        return [origin.strip() for origin in raw_origins.split(\",\") if origin.strip()]

    frontend_url = os.getenv(\"FRONTEND_URL\", \"http://localhost:3000\")
    return [frontend_url]


app = FastAPI(title=\"SaaS Arbitragem API\")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=[\"*\"],
    allow_headers=[\"*\"],
)

app.include_router(leads.router)
app.include_router(export.router)


@app.get(\"/\")
def read_root():
    return {
        \"message\": \"API de Arbitragem rodando\",
        \"openai_configurada\": bool(os.getenv(\"OPENAI_API_KEY\")),
        \"supabase_configurado\": bool(os.getenv(\"SUPABASE_URL\")),
    }


@app.get(\"/health\")
def health_check():
    return {\"status\": \"ok\"}
""",
    "app/routers/leads.py": """from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix=\"/leads\", tags=[\"leads\"])


class SearchRequest(BaseModel):
    search_term: str = Field(..., min_length=2)
    category: str = Field(..., min_length=2)
    limit: int = Field(default=10, ge=1, le=50)


class LeadResponse(BaseModel):
    id: str
    title: str
    price: str
    temperature: Literal[\"HOT\", \"WARM\", \"COLD\"]
    reason: str
    is_revealed: bool
    phone: str
    email: str
    seller_name: str
    link: str | None = None


class SearchResponse(BaseModel):
    message: str
    leads: list[LeadResponse]


class RevealResponse(BaseModel):
    message: str
    phone: str
    email: str
    seller_name: str
    link: str


@router.post(\"/search\", response_model=SearchResponse)
async def execute_search(payload: SearchRequest):
    search_term = payload.search_term.strip()

    mock_leads = [
        {
            \"id\": \"1\",
            \"title\": f\"{search_term} - Urgente, mudanca de pais\",
            \"price\": \"R$ 85.000\",
            \"temperature\": \"HOT\",
            \"reason\": \"Preco muito abaixo da FIPE, vendedor demonstrando urgencia.\",
            \"is_revealed\": False,
            \"phone\": \"11999991111\",
            \"email\": \"urgente.real@email.com\",
            \"seller_name\": \"Vendedor Desesperado\",
            \"link\": \"https://www.exemplo.com/anuncio-urgente\",
        },
        {
            \"id\": \"2\",
            \"title\": f\"{search_term} - Aceita troca menor valor\",
            \"price\": \"R$ 98.000\",
            \"temperature\": \"WARM\",
            \"reason\": \"Preco na media, mas aberto a negociacoes e trocas.\",
            \"is_revealed\": True,
            \"phone\": \"11988882222\",
            \"email\": \"contato.morno@email.com\",
            \"seller_name\": \"Vendedor Morno\",
            \"link\": \"https://www.exemplo.com/anuncio-morno\",
        },
        {
            \"id\": \"3\",
            \"title\": f\"{search_term} - Estado de zero, unico dono\",
            \"price\": \"R$ 115.000\",
            \"temperature\": \"COLD\",
            \"reason\": \"Preco alto, inflexivel e sem urgencia.\",
            \"is_revealed\": True,
            \"phone\": \"11977773333\",
            \"email\": \"contato.frio@email.com\",
            \"seller_name\": \"Vendedor Frio\",
            \"link\": \"https://www.exemplo.com/anuncio-frio\",
        },
    ]

    return {
        \"message\": f\"Busca concluida para {payload.category}.\",
        \"leads\": mock_leads[: payload.limit],
    }


@router.post(\"/{lead_id}/reveal\", response_model=RevealResponse)
async def reveal_hot_lead(lead_id: str):
    return {
        \"message\": \"Lead revelado e 30 creditos debitados.\",
        \"phone\": \"11999991111\",
        \"email\": \"urgente.real@email.com\",
        \"seller_name\": \"Vendedor Desesperado\",
        \"link\": \"https://www.exemplo.com/anuncio-urgente\",
    }
""",
    "app/routers/export.py": """from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import io
import csv
from typing import List

router = APIRouter(prefix=\"/export\", tags=[\"export\"])


@router.post(\"/facebook-csv\")
async def export_to_facebook(leads: List[dict]):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([\"email\", \"phone\", \"fn\", \"ln\", \"country\"])

    for lead in leads:
        if lead.get(\"is_revealed\") and (lead.get(\"email\") or lead.get(\"phone\")):
            phone = lead.get(\"phone\", \"\").replace(\"-\", \"\").replace(\" \", \"\").replace(\"(\", \"\").replace(\")\", \"\")
            if len(phone) >= 10 and not phone.startswith(\"55\"):
                phone = f\"55{phone}\"

            email = lead.get(\"email\", \"\").lower()
            full_name = lead.get(\"seller_name\", \"Cliente\")
            name_parts = full_name.split()
            fn = name_parts[0] if name_parts else \"\"
            ln = name_parts[-1] if len(name_parts) > 1 else \"\"

            writer.writerow([email, phone, fn, ln, \"BR\"])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type=\"text/csv\",
        headers={\"Content-Disposition\": \"attachment; filename=facebook_audiences_leads.csv\"},
    )
""",
    "DEPLOY.md": """# Deploy do SaaS Arbitragem

## Arquitetura recomendada
- Frontend Next.js em um servico separado no Coolify.
- Backend FastAPI em outro servico no Coolify.
- Banco, auth e storage no Supabase.

## Supabase
1. Crie um projeto no Supabase.
2. Guarde `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.
3. Use o Supabase para usuarios, creditos, historico de buscas e leads revelados.

## Backend no Coolify
- Tipo: Dockerfile.
- Diretorio raiz: `backend-arbitragem`.
- Porta exposta: `8000`.
- Health check: `/health`.
- Variaveis obrigatorias:
  - `PORT=8000`
  - `FRONTEND_URL=https://seu-frontend.com`
  - `ALLOWED_ORIGINS=https://seu-frontend.com,http://localhost:3000`
  - `SUPABASE_URL=...`
  - `SUPABASE_SERVICE_ROLE_KEY=...`
  - `OPENAI_API_KEY=...`

## Frontend no Coolify
- Tipo: Dockerfile ou Node.
- Diretorio raiz: `front-end-scraper-jules`.
- Variavel obrigatoria: `NEXT_PUBLIC_API_URL=https://sua-api.com`
- Build: `npm run build`
- Start: `npm run start`

## Fluxo local
- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- Busca: `POST /leads/search`
""",
}

for relative_path, content in FILES.items():
    file_path = ROOT / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")

print("Backend do SaaS Arbitragem preparado com sucesso.")
print("1. python gerar_projeto.py")
print("2. pip install -r requirements.txt")
print("3. uvicorn app.main:app --reload")
