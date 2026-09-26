-- SAPTA — Backtest indicatori tecnici, parte 3 (26/09/2026)
-- Relative Strength con INDICE REALE (non più il proxy cross-sezionale della
-- parte 2), combinazione a 3 condizioni, supporti/resistenze a 200gg.
--
-- Richiede lo storico giornaliero di ^GSPC e FTSEMIB.MI in prezzi
-- (interval='1d'), caricato il 26/09 con:
--   src/load_historical_data.py --scope=indices
-- (workflow "SAPTA Load Historical Data (one-off)" su GitHub Actions).
-- Senza questo storico, ^GSPC/FTSEMIB.MI esistono solo a 15m dal 18/09,
-- insufficiente per RS a 5/20 giorni di borsa.

-- QUERY 1: RS5 vs indice reale (S&P500 per ticker USA, FTSE MIB per .MI)
with base as (
  select ticker, timestamp::date as d, close,
    (case when ticker like '%.MI' then 'IT' else 'US' end) as market
  from prezzi where interval = '1d'
    and (ticker in (select distinct ticker from screening_candidates) or ticker in ('^GSPC','FTSEMIB.MI'))
),
idx as (select (case when ticker='FTSEMIB.MI' then 'IT' else 'US' end) as market, d, close as idx_close from base where ticker in ('^GSPC','FTSEMIB.MI')),
tk as (select * from base where ticker not in ('^GSPC','FTSEMIB.MI')),
ret as (
  select tk.ticker, tk.d, tk.close, tk.market,
    lag(tk.close,5) over (partition by tk.ticker order by tk.d) as close_5ago,
    lead(tk.close,1) over (partition by tk.ticker order by tk.d) as close_p1,
    lead(tk.close,3) over (partition by tk.ticker order by tk.d) as close_p3,
    i.idx_close, lag(i.idx_close,5) over (partition by tk.ticker order by tk.d) as idx_5ago
  from tk join idx i on i.market = tk.market and i.d = tk.d
),
ind2 as (select *, round(((close/nullif(close_5ago,0)-1) - (idx_close/nullif(idx_5ago,0)-1))::numeric*100,2) as rs5_real_pp from ret),
events as (select sc.id as event_id, sc.ticker as ev_ticker, (sc.timestamp at time zone 'utc')::date as event_date from screening_candidates sc),
matched as (select e.event_id, i.*, row_number() over (partition by e.event_id order by i.d desc) as rn from events e join ind2 i on i.ticker=e.ev_ticker and i.d<=e.event_date),
final as (select * from matched where rn=1),
dir as (select *,
  case when close_p1 is not null then close_p1/close-1 end as ret1,
  case when close_p3 is not null then close_p3/close-1 end as ret3
  from final)
select case when rs5_real_pp>=0 then 'RS5 positiva (batte S&P500/FTSEMIB)' else 'RS5 negativa (sotto S&P500/FTSEMIB)' end as cond,
  count(*) n, count(ret1) n1, round((avg(ret1)*100)::numeric,2) avg1_pct, round((100.0*count(*) filter (where ret1>0)/nullif(count(ret1),0))::numeric,1) pos1_pct,
  count(ret3) n3, round((avg(ret3)*100)::numeric,2) avg3_pct, round((100.0*count(*) filter (where ret3>0)/nullif(count(ret3),0))::numeric,1) pos3_pct
from dir group by cond order by cond;

-- QUERY 2: combinazione a 3 condizioni (SMA20 + RSI + RS5 reale) e
-- supporti/resistenze a 200gg
with base as (
  select ticker, timestamp::date as d, high, low, close,
    (case when ticker like '%.MI' then 'IT' else 'US' end) as market
  from prezzi where interval = '1d'
    and (ticker in (select distinct ticker from screening_candidates) or ticker in ('^GSPC','FTSEMIB.MI'))
),
idx as (select (case when ticker='FTSEMIB.MI' then 'IT' else 'US' end) as market, d, close as idx_close from base where ticker in ('^GSPC','FTSEMIB.MI')),
tk as (select * from base where ticker not in ('^GSPC','FTSEMIB.MI')),
ret as (
  select tk.*, i.idx_close,
    lag(tk.close,1) over wt as prev_close, lag(tk.close,5) over wt as close_5ago,
    lag(i.idx_close,5) over wt as idx_5ago,
    lead(tk.close,1) over wt as close_p1, lead(tk.close,3) over wt as close_p3
  from tk join idx i on i.market=tk.market and i.d=tk.d
  window wt as (partition by tk.ticker order by tk.d)
),
ret2 as (select *, greatest(close-coalesce(prev_close,close),0) as gain, greatest(coalesce(prev_close,close)-close,0) as loss from ret),
ind as (
  select ticker, d, close, close_p1, close_p3,
    avg(close) over w20 as sma20,
    max(high) over w200 as hi200, min(low) over w200 as lo200,
    (close/nullif(close_5ago,0)-1) - (idx_close/nullif(idx_5ago,0)-1) as rs5_real,
    avg(gain) over w14 as avg_gain14, avg(loss) over w14 as avg_loss14
  from ret2
  window w14 as (partition by ticker order by d rows between 13 preceding and current row),
         w20 as (partition by ticker order by d rows between 19 preceding and current row),
         w200 as (partition by ticker order by d rows between 199 preceding and current row)
),
ind2 as (
  select *, round((100-100/(1+avg_gain14/nullif(avg_loss14,0)))::numeric,1) as rsi14,
    (close>sma20) as sopra_sma20,
    round(((close-hi200)/nullif(hi200,0))::numeric*100,2) as dist_hi200_pct,
    round(((close-lo200)/nullif(lo200,0))::numeric*100,2) as dist_lo200_pct
  from ind
),
events as (select sc.id as event_id, sc.ticker as ev_ticker, (sc.timestamp at time zone 'utc')::date as event_date from screening_candidates sc),
matched as (select e.event_id, i.*, row_number() over (partition by e.event_id order by i.d desc) as rn from events e join ind2 i on i.ticker=e.ev_ticker and i.d<=e.event_date),
final as (select * from matched where rn=1),
dir as (select *,
  case when close_p1 is not null then close_p1/close-1 end as ret1,
  case when close_p3 is not null then close_p3/close-1 end as ret3
  from final),
grp as (
  select 'Combo 3: SMA20+RSI+RS5' as gruppo,
    (case when sopra_sma20 then 'sopra SMA20' else 'sotto SMA20' end) || ' + ' ||
    (case when rsi14<50 then 'RSI<50' else 'RSI>=50' end) || ' + ' ||
    (case when rs5_real>=0 then 'RS5+' else 'RS5-' end) as cond, * from dir
  union all
  select 'Vicinanza max/min 200gg',
    case when dist_hi200_pct>-1 then 'vicino massimo 200gg' when dist_lo200_pct<1 then 'vicino minimo 200gg' else 'zona intermedia' end,
    dir.* from dir
)
select gruppo, cond, count(*) n,
  count(ret1) n1, round((avg(ret1)*100)::numeric,2) avg1_pct, round((100.0*count(*) filter (where ret1>0)/nullif(count(ret1),0))::numeric,1) pos1_pct,
  count(ret3) n3, round((avg(ret3)*100)::numeric,2) avg3_pct
from grp group by gruppo, cond having count(*)>=5 order by gruppo, n desc;
