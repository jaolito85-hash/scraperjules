# SaaS Arbitragem

Monorepo com frontend e backend do SaaS de arbitragem por scraper.
Projeto focado em arbitragem com IA para ramos imobiliarios, automotivos e servicos B2B.

## Estrutura

- `backend-arbitragem`: API FastAPI, integracao com Supabase, schema SQL e Dockerfile.
- `front-end-scraper-jules`: frontend Next.js, integracao com a API e Dockerfile.

## Fluxo local

### Backend

1. Copie `backend-arbitragem/.env.example` para `.env`.
2. Instale dependencias:
   - `pip install -r requirements.txt`
3. Rode:
   - `uvicorn app.main:app --reload`

### Frontend

1. Copie `front-end-scraper-jules/.env.example` para `.env.local`.
2. Instale dependencias:
   - `npm install`
3. Rode:
   - `npm run dev`

## Supabase

O schema base esta em `backend-arbitragem/supabase/schema.sql`.

## Deploy

As instrucoes operacionais de deploy para Coolify estao em `backend-arbitragem/DEPLOY.md`.

## GitHub

Estrutura recomendada do repositorio:

- `/backend-arbitragem`
- `/front-end-scraper-jules`

Depois de inicializar o Git localmente:

1. `git init`
2. `git branch -M main`
3. `git remote add origin https://github.com/jaolito85-hash/scraperjules.git`
4. `git add .`
5. `git commit -m "Initial monorepo setup"`
6. `git push -u origin main`
