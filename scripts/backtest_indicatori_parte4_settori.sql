-- SAPTA — Backtest indicatori tecnici, parte 4 (26/09/2026)
-- Hit-rate per data_quality_flag, liquidity_bucket, settore (punto 5 delle
-- analisi proposte da Claude il 26/09, non parte del protocollo originale
-- dell'utente ma della stessa famiglia: "cosa nei metadati della pipeline
-- correla con l'esito?").

with base as (
  select ticker, timestamp::date as d, close,
    lead(close,1) over wt as close_p1, lead(close,3) over wt as close_p3
  from prezzi where interval='1d' and ticker in (select distinct ticker from screening_candidates)
  window wt as (partition by ticker order by timestamp::date)
),
events as (
  select sc.id, sc.ticker, (sc.timestamp at time zone 'utc')::date as event_date,
    sc.data_quality_flag, sc.liquidity_bucket
  from screening_candidates sc
),
matched as (
  select e.*, b.close, b.close_p1, b.close_p3, row_number() over (partition by e.id order by b.d desc) rn
  from events e join base b on b.ticker=e.ticker and b.d<=e.event_date
),
final as (select * from matched where rn=1),
dir as (select *,
  case when close_p1 is not null then close_p1/close-1 end ret1,
  case when close_p3 is not null then close_p3/close-1 end ret3
  from final),
grp as (
  select 'data_quality_flag' gruppo, coalesce(data_quality_flag,'(vuoto)') cond, * from dir
  union all select 'liquidity_bucket', coalesce(liquidity_bucket,'(vuoto)'), dir.* from dir
)
select gruppo, cond, count(*) n,
  count(ret1) n1, round((avg(ret1)*100)::numeric,2) avg1_pct, round((100.0*count(*) filter (where ret1>0)/nullif(count(ret1),0))::numeric,1) pos1_pct,
  count(ret3) n3, round((avg(ret3)*100)::numeric,2) avg3_pct
from grp group by gruppo, cond order by gruppo, n desc;

-- Settore (join ticker_sectors)
with base as (
  select ticker, timestamp::date as d, close,
    lead(close,1) over wt as close_p1, lead(close,3) over wt as close_p3
  from prezzi where interval='1d' and ticker in (select distinct ticker from screening_candidates)
  window wt as (partition by ticker order by timestamp::date)
),
events as (
  select sc.id, sc.ticker, (sc.timestamp at time zone 'utc')::date as event_date, ts.sector
  from screening_candidates sc left join ticker_sectors ts on ts.ticker=sc.ticker
),
matched as (
  select e.*, b.close, b.close_p1, b.close_p3, row_number() over (partition by e.id order by b.d desc) rn
  from events e join base b on b.ticker=e.ticker and b.d<=e.event_date
),
final as (select * from matched where rn=1),
dir as (select *,
  case when close_p1 is not null then close_p1/close-1 end ret1,
  case when close_p3 is not null then close_p3/close-1 end ret3
  from final)
select coalesce(sector,'(sconosciuto)') settore, count(*) n,
  count(ret1) n1, round((avg(ret1)*100)::numeric,2) avg1_pct, round((100.0*count(*) filter (where ret1>0)/nullif(count(ret1),0))::numeric,1) pos1_pct,
  count(ret3) n3, round((avg(ret3)*100)::numeric,2) avg3_pct
from dir group by sector having count(*)>=5 order by n desc;
