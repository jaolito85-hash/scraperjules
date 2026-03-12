# Deploy do SaaS Arbitragem

## Arquitetura
- Frontend Next.js em um servico separado no Coolify.
- Backend FastAPI em outro servico no Coolify.
- Banco e persistencia no Supabase.

## Supabase
1. Crie um projeto no Supabase.
2. Abra o SQL Editor e rode `supabase/schema.sql`.
3. Copie `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`.
4. O backend cria perfis automaticamente usando o header `X-User-Id` enviado pelo frontend.

## Backend no Coolify
- Tipo: Dockerfile.
- Diretorio raiz: `backend-arbitragem`.
- Porta: `8000`.
- Health check path: `/health`.
- Variaveis obrigatorias:
  - `PORT=8000`
  - `FRONTEND_URL=https://seu-frontend.com`
  - `ALLOWED_ORIGINS=https://seu-frontend.com,http://localhost:3000`
  - `SUPABASE_URL=...`
  - `SUPABASE_SERVICE_ROLE_KEY=...`
  - `DEFAULT_USER_CREDITS=100`
  - `REVEAL_COST=30`
  - `OPENAI_API_KEY=...`

## Frontend no Coolify
- Tipo: Dockerfile ou Node.
- Diretorio raiz: `front-end-scraper-jules`.
- Variavel obrigatoria: `NEXT_PUBLIC_API_URL=https://sua-api.com`
- Build: `npm run build`
- Start: `npm run start`

## Ordem recomendada de deploy
1. Suba o backend no Coolify.
2. Configure as variaveis do backend.
3. Teste `GET /health` e `POST /leads/search`.
4. Suba o frontend apontando `NEXT_PUBLIC_API_URL` para a URL publica do backend.
5. Rode uma busca e revele um lead para confirmar gravacao nas tabelas `profiles`, `search_history` e `revealed_leads`.
