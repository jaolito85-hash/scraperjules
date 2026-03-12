from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

from app.routers import leads, export
from app.services.supabase_store import is_supabase_enabled

load_dotenv()


def get_allowed_origins() -> list[str]:
    raw_origins = os.getenv("ALLOWED_ORIGINS")
    if raw_origins:
        return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return [frontend_url]


app = FastAPI(title="SaaS Arbitragem API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(leads.router)
app.include_router(export.router)


@app.get("/")
def read_root():
    return {
        "message": "API de Arbitragem rodando",
        "openai_configurada": bool(os.getenv("OPENAI_API_KEY")),
        "supabase_configurado": is_supabase_enabled(),
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
