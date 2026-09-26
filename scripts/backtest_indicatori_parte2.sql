-- SAPTA — Backtest indicatori tecnici, parte 2 (24/09/2026)
-- Completa scripts/backtest_indicatori.sql con: MACD, ADX, Relative Strength
-- (proxy), Gap, Supporti/Resistenze, combinazioni a 2 condizioni.
--
-- NOTA TECNICA IMPORTANTE: MACD e ADX richiedono EMA/Wilder-smoothing, che in
-- SQL puro serve una CTE RICORSIVA (WITH RECURSIVE) valutata riga per riga.
-- Su 88 ticker con la finestra a 1 anno usata in backtest_indicatori.sql, la
-- ricorsione va in timeout (anche con statement_timeout alto: il collo di
-- bottiglia è il gateway del connettore, non Postgres). Soluzioni applicate:
-- 1) materializzare i dati in una TEMP TABLE indicizzata (ticker,rn) PRIMA
--    della ricorsione (senza indice, ogni passo ricorsivo fa una scansione
--    completa della CTE precedente: O(n^2) per ticker);
-- 2) ridurre la finestra storica a 125 giorni di borsa invece di 1 anno —
--    sufficiente per la convergenza di EMA12/26 e Wilder-14 (convergono in
--    ~3-5x il periodo, cioè ~50-100 barre), ma NON sufficiente per SMA200
--    (per questo MACD/ADX usano una query separata da RSI/SMA/Bollinger).
-- Ogni CREATE TEMP TABLE + la ricorsione che la usa devono stare nella STESSA
-- chiamata SQL: le temp table non sopravvivono a chiamate/connessioni diverse.
--
-- Metodologia dichiarata: RSI/ATR/ADX usano Wilder "in forma EMA" (alpha=1/14
-- dalla prima riga), non la stagionatura esatta di Wilder (SMA dei primi 14
-- valori come seed) — differenza tipicamente di pochi decimi di punto, non
-- rilevante per uno screening di questo tipo.

-- ============================================================
-- QUERY 1: MACD + ADX (finestra 125gg, con ricorsione)
-- ============================================================
SET statement_timeout = '170000';
CREATE TEMP TABLE ranked_tmp AS
  SELECT ticker, timestamp::date as d, open, high, low, close, volume,
         row_number() over (partition by ticker order by timestamp::date) as rn,
         lead(close,1)  over (partition by ticker order by timestamp::date) as close_p1,
         lead(close,3)  over (partition by ticker order by timestamp::date) as close_p3,
         lead(close,5)  over (partition by ticker order by timestamp::date) as close_p5,
         lead(close,10) over (partition by ticker order by timestamp::date) as close_p10,
         lead(close,20) over (partition by ticker order by timestamp::date) as close_p20
  FROM prezzi
  WHERE interval = '1d' AND ticker in (select distinct ticker from screening_candidates)
    AND timestamp::date >= '2026-01-01';  -- ~125 giorni di borsa da oggi (24/09/2026); avanzare con la data di esecuzione
CREATE UNIQUE INDEX ON ranked_tmp(ticker, rn);

CREATE TEMP TABLE events_asof AS
  select sc.id as event_id, sc.ticker as ev_ticker, (sc.timestamp at time zone 'utc')::date as event_date,
    (select max(rt.rn) from ranked_tmp rt where rt.ticker = sc.ticker and rt.d <= (sc.timestamp at time zone 'utc')::date) as asof_rn
  from screening_candidates sc;

with recursive ema_calc as (
  select ticker, d, rn, close::numeric as ema12, close::numeric as ema26
  from ranked_tmp where rn = 1
  union all
  select r.ticker, r.d, r.rn,
    (r.close * (2.0/13) + e.ema12 * (1 - 2.0/13))::numeric,
    (r.close * (2.0/27) + e.ema26 * (1 - 2.0/27))::numeric
  from ranked_tmp r join ema_calc e on r.ticker = e.ticker and r.rn = e.rn + 1
),
macd_raw as (select ticker, d, rn, (ema12-ema26)::numeric as macd from ema_calc),
signal_calc as (
  select ticker, d, rn, macd, macd as signal9 from macd_raw where rn = 1
  union all
  select m.ticker, m.d, m.rn, m.macd,
    (m.macd * (2.0/10) + s.signal9 * (1 - 2.0/10))::numeric
  from macd_raw m join signal_calc s on m.ticker = s.ticker and m.rn = s.rn + 1
),
rk as (
  select *, lag(high) over (partition by ticker order by d) as prev_high,
            lag(low) over (partition by ticker order by d) as prev_low,
            lag(close) over (partition by ticker order by d) as prev_close
  from ranked_tmp
),
raw_dm as (
  select ticker, d, rn,
    greatest(high-low, abs(high-coalesce(prev_close,high)), abs(low-coalesce(prev_close,low))) as tr,
    case when (high-coalesce(prev_high,high)) > (coalesce(prev_low,low)-low) and (high-coalesce(prev_high,high))>0
         then (high-coalesce(prev_high,high)) else 0 end as dm_plus,
    case when (coalesce(prev_low,low)-low) > (high-coalesce(prev_high,high)) and (coalesce(prev_low,low)-low)>0
         then (coalesce(prev_low,low)-low) else 0 end as dm_minus
  from rk
),
smooth as (
  select ticker, d, rn, tr::numeric as tr14, dm_plus::numeric as dmp14, dm_minus::numeric as dmm14
  from raw_dm where rn = 1
  union all
  select r.ticker, r.d, r.rn,
    (s.tr14*(13.0/14) + r.tr)::numeric,
    (s.dmp14*(13.0/14) + r.dm_plus)::numeric,
    (s.dmm14*(13.0/14) + r.dm_minus)::numeric
  from raw_dm r join smooth s on r.ticker=s.ticker and r.rn=s.rn+1
),
dx_calc as (
  select ticker, d, rn,
    coalesce(100*abs(dmp14-dmm14)/nullif(dmp14+dmm14,0), 0) as dx
  from smooth
),
adx_calc as (
  select ticker, d, rn, dx, dx::numeric as adx
  from dx_calc where rn = 1
  union all
  select x.ticker, x.d, x.rn, x.dx,
    (a.adx*(13.0/14) + x.dx*(1.0/14))::numeric
  from dx_calc x join adx_calc a on x.ticker=a.ticker and x.rn=a.rn+1
),
joined as (
  select ea.event_id, r.close, r.close_p1, r.close_p3, r.close_p5, r.close_p10, r.close_p20,
    sc.macd, sc.signal9, (sc.macd-sc.signal9) as macd_hist, ac.adx
  from events_asof ea
  join ranked_tmp r on r.ticker=ea.ev_ticker and r.rn=ea.asof_rn
  join signal_calc sc on sc.ticker=ea.ev_ticker and sc.rn=ea.asof_rn
  join adx_calc ac on ac.ticker=ea.ev_ticker and ac.rn=ea.asof_rn
),
dir as (
  select *,
    case when close_p1 is not null then close_p1/close-1 end as ret1,
    case when close_p3 is not null then close_p3/close-1 end as ret3
  from joined
),
grp as (
  select 'MACD segno' as gruppo, case when macd_hist>=0 then 'histogram positivo (sopra signal)' else 'histogram negativo (sotto signal)' end as cond, * from dir
  union all select 'ADX livello', case when adx<20 then 'ADX<20 (trend debole)' when adx<40 then 'ADX 20-40' else 'ADX>40 (trend forte)' end, dir.* from dir
)
select gruppo, cond, count(*) n,
  count(ret1) n1, round((avg(ret1)*100)::numeric,2) avg1_pct, round((100.0*count(*) filter (where ret1>0)/nullif(count(ret1),0))::numeric,1) pos1_pct,
  count(ret3) n3, round((avg(ret3)*100)::numeric,2) avg3_pct, round((100.0*count(*) filter (where ret3>0)/nullif(count(ret3),0))::numeric,1) pos3_pct
from grp group by gruppo, cond order by gruppo, cond;

-- ============================================================
-- QUERY 2: Relative Strength (proxy cross-sezionale US/IT), Gap,
-- Supporti/Resistenze 50gg (finestra piena, nessuna ricorsione)
-- ============================================================
with base as (
  select ticker, timestamp::date as d, open, high, low, close, volume,
    (case when ticker like '%.MI' then 'IT' else 'US' end) as market
  from prezzi where interval = '1d' and ticker in (select distinct ticker from screening_candidates)
),
ret as (
  select *,
    lag(close,1)  over wt as prev_close,
    lag(close,5)  over wt as close_5ago, lag(close,20) over wt as close_20ago,
    lead(close,1)  over wt as close_p1, lead(close,3)  over wt as close_p3
  from base window wt as (partition by ticker order by d)
),
ret2 as (
  select *, ln(close / nullif(prev_close,0)) as logret,
    (open - prev_close)/nullif(prev_close,0) as gap_pct
  from ret
),
ret3 as (select *, avg(logret) over (partition by market, d) as mkt_logret from ret2),
ind as (
  select ticker, d, close, gap_pct, close_p1, close_p3,
    close / nullif(close_5ago,0) - 1 as roc5,
    sum(mkt_logret) over w5  as mkt_cumlog5,
    close / nullif(close_20ago,0) - 1 as roc20,
    sum(mkt_logret) over w20 as mkt_cumlog20,
    max(high) over w50  as hi50,  min(low) over w50  as lo50
  from ret3
  window w5 as (partition by ticker order by d rows between 4 preceding and current row),
         w20 as (partition by ticker order by d rows between 19 preceding and current row),
         w50 as (partition by ticker order by d rows between 49 preceding and current row)
),
ind2 as (
  select *,
    round((roc5 - (exp(mkt_cumlog5)-1))::numeric*100,2) as rs5_pp,
    round(((close-hi50)/nullif(hi50,0))::numeric*100,2) as dist_hi50_pct,
    round(((close-lo50)/nullif(lo50,0))::numeric*100,2) as dist_lo50_pct
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
  select 'Relative Strength 5d' as gruppo, case when rs5_pp>=0 then 'RS5 positiva (batte il mercato)' else 'RS5 negativa (sotto il mercato)' end as cond, * from dir
  union all select 'Gap apertura', case when gap_pct>0.005 then 'gap up (>0.5%)' when gap_pct<-0.005 then 'gap down (<-0.5%)' else 'nessun gap rilevante' end, dir.* from dir
  union all select 'Vicinanza max 50gg', case when dist_hi50_pct>-1 then 'vicino massimo 50gg (entro 1%)' else 'lontano dal massimo 50gg' end, dir.* from dir
  union all select 'Vicinanza min 50gg', case when dist_lo50_pct<1 then 'vicino minimo 50gg (entro 1%)' else 'lontano dal minimo 50gg' end, dir.* from dir
)
select gruppo, cond, count(*) n,
  count(ret1) n1, round((avg(ret1)*100)::numeric,2) avg1_pct, round((100.0*count(*) filter (where ret1>0)/nullif(count(ret1),0))::numeric,1) pos1_pct,
  count(ret3) n3, round((avg(ret3)*100)::numeric,2) avg3_pct
from grp group by gruppo, cond order by gruppo, cond;

-- ============================================================
-- QUERY 3: combinazioni a 2 condizioni (SMA20 x RSI, Bollinger x ROC5)
-- ============================================================
with base as (
  select ticker, timestamp::date as d, open, high, low, close, volume
  from prezzi where interval = '1d' and ticker in (select distinct ticker from screening_candidates)
),
ret as (
  select *, lag(close,1) over wt as prev_close, lag(close,5) over wt as close_5ago,
    lead(close,1) over wt as close_p1, lead(close,3) over wt as close_p3
  from base window wt as (partition by ticker order by d)
),
ret2 as (
  select *, ln(close/nullif(prev_close,0)) as logret,
    greatest(high-low, abs(high-coalesce(prev_close,high)), abs(low-coalesce(prev_close,low))) as tr,
    greatest(close-coalesce(prev_close,close),0) as gain, greatest(coalesce(prev_close,close)-close,0) as loss
  from ret
),
ind as (
  select ticker, d, close, close_p1, close_p3,
    avg(close) over w20 as sma20, max(high) over w20 as hi20, min(low) over w20 as lo20,
    close/nullif(close_5ago,0)-1 as roc5,
    avg(gain) over w14 as avg_gain14, avg(loss) over w14 as avg_loss14
  from ret2
  window w14 as (partition by ticker order by d rows between 13 preceding and current row),
         w20 as (partition by ticker order by d rows between 19 preceding and current row)
),
ind2 as (
  select *, round((100-100/(1+avg_gain14/nullif(avg_loss14,0)))::numeric,1) as rsi14,
    round(((close-lo20)/nullif(hi20-lo20,0))::numeric,3) as bb_pos20,
    (close>sma20) as sopra_sma20
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
  select 'Combo: SMA20 x RSI' as gruppo,
    (case when sopra_sma20 then 'sopra SMA20' else 'sotto SMA20' end) || ' + ' ||
    (case when rsi14<30 then 'RSI<30' when rsi14<50 then 'RSI 30-50' when rsi14<70 then 'RSI 50-70' else 'RSI>70' end) as cond,
    * from dir
  union all
  select 'Combo: Bollinger x ROC5',
    (case when bb_pos20<0.15 then 'banda bassa' when bb_pos20>0.85 then 'banda alta' else 'centrale' end) || ' + ' ||
    (case when roc5>=0 then 'ROC5 pos' else 'ROC5 neg' end),
    dir.* from dir
)
select gruppo, cond, count(*) n,
  count(ret1) n1, round((avg(ret1)*100)::numeric,2) avg1_pct, round((100.0*count(*) filter (where ret1>0)/nullif(count(ret1),0))::numeric,1) pos1_pct,
  count(ret3) n3, round((avg(ret3)*100)::numeric,2) avg3_pct
from grp group by gruppo, cond having count(*) >= 5 order by gruppo, n desc;
