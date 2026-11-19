-- Migrazione: tabella fx_rates (tassi di riferimento BCE) - SAPTA, 19/11/2026
-- SOLO incrementale: crea UNA tabella nuova. Nessuna modifica o cancellazione di transazioni, segnali, prezzi, cicli o altri dati.
-- Un solo cambio per giornata: la chiave primaria (base, quote, data) impedisce due tassi per lo stesso giorno.
-- Fonte: tassi di riferimento BCE (euro foreign exchange reference rates), gratuiti, pubblicati ogni giorno lavorativo TARGET.
-- Rollback: migrations/20261119_fx_rates_rollback.sql

create table if not exists public.fx_rates (
    base_currency  text          not null default 'EUR',
    quote_currency text          not null,
    rate_date      date          not null,                 -- data di riferimento BCE
    rate           numeric(14,6) not null,                 -- unita' di quote_currency per 1 EUR (es. USD per 1 EUR)
    source         text          not null default 'ECB',
    fetched_at     timestamptz   not null default now(),
    constraint fx_rates_pkey primary key (base_currency, quote_currency, rate_date),
    constraint fx_rates_rate_positive check (rate > 0),
    constraint fx_rates_base_is_eur check (base_currency = 'EUR')
);

comment on table public.fx_rates is
  'Tassi di riferimento BCE (unita'' di valuta per 1 EUR), uno per giornata. E e T leggono lo stesso tasso: l''ultimo con rate_date STRETTAMENTE precedente alla data del segnale. Nessun valore da altre fonti.';

-- Nessuna policy: solo il service role (usato da SAPTA) legge e scrive; anon/authenticated non hanno accesso.
alter table public.fx_rates enable row level security;
