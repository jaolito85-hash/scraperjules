create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key default gen_random_uuid(),
  external_id text not null unique,
  credits integer not null default 100 check (credits >= 0),
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.search_history (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  search_term text not null,
  category text not null,
  result_count integer not null default 0,
  raw_response jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.revealed_leads (
  id uuid primary key default gen_random_uuid(),
  profile_id uuid not null references public.profiles(id) on delete cascade,
  lead_external_id text not null,
  title text not null,
  phone text not null,
  email text not null,
  seller_name text not null,
  cost integer not null default 30,
  link text,
  revealed_at timestamptz not null default timezone('utc', now()),
  unique (profile_id, lead_external_id)
);

create index if not exists idx_search_history_profile_id_created_at on public.search_history(profile_id, created_at desc);
create index if not exists idx_revealed_leads_profile_id on public.revealed_leads(profile_id);
