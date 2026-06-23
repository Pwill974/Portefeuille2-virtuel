-- Alpha Zen Pro — portefeuille permanent et valorisation persistante
-- À exécuter UNE FOIS dans Supabase > SQL Editor > New query.

create table if not exists public.az_market_prices (
    profile_id text not null,
    ticker text not null,
    price numeric not null default 0,
    quote_date timestamptz,
    mm50 numeric,
    mm200 numeric,
    distance_mm200 numeric,
    momentum_3m numeric,
    momentum_6m numeric,
    momentum_12m numeric,
    performance_ytd numeric,
    volatility_1y numeric,
    alpha_zen_score numeric,
    signal text,
    updated_at timestamptz not null default now(),
    primary key (profile_id, ticker)
);

create table if not exists public.az_live_portfolio (
    profile_id text primary key,
    capital_reference numeric not null default 0,
    cash numeric not null default 0,
    invested numeric not null default 0,
    positions_value numeric not null default 0,
    total_value numeric not null default 0,
    unrealized_gain numeric not null default 0,
    performance numeric not null default 0,
    active_lines integer not null default 0,
    quote_date timestamptz,
    updated_at timestamptz not null default now()
);

create index if not exists az_market_prices_profile_idx
on public.az_market_prices (profile_id, ticker);

alter table public.az_market_prices enable row level security;
alter table public.az_live_portfolio enable row level security;

revoke all on table public.az_market_prices
from anon, authenticated;

revoke all on table public.az_live_portfolio
from anon, authenticated;

grant all on table public.az_market_prices
to service_role;

grant all on table public.az_live_portfolio
to service_role;
