-- SAPTA — Backtest indicatori tecnici aggiuntivi (protocollo utente 24/09/2026)
-- Da eseguire su Supabase (progetto wpgozxddhlmzgymvpacq), read-only.
--
-- COSA FA: per ogni evento in screening_candidates (= "anomalia SAPTA" nella
-- definizione attuale H1/H2), calcola gli indicatori tecnici AS OF la data
-- dell'evento (nessun lookahead: usa solo barre <= event_date) e i rendimenti
-- successivi a 1/3/5/10/20 giorni di BORSA (non calendario, tramite LEAD()
-- sulla serie ordinata per data - salta weekend automaticamente).
--
-- LIMITE NOTO (rivedere quando si ri-esegue): screening_candidates esiste
-- solo dal 18/09/2026 (rewrite v5.1.1). +5d/+10d/+20d restano DATA_UNAVAILABLE
-- (N=0) finché non passano abbastanza giorni di borsa dagli eventi più vecchi.
-- +10d richiede eventi di almeno ~2 settimane fa, +20d di almeno ~4-5 settimane
-- fa. Anche a orizzonti disponibili, se gli eventi coprono solo pochi giorni
-- di calendario le osservazioni NON sono indipendenti (un giorno di mercato
-- forte/debole si riflette su tutti i sottogruppi insieme) - prima di trarre
-- conclusioni, controllare che gli eventi coprano più settimane/regimi di
-- mercato diversi, non solo più N.
--
-- METODOLOGIA (semplificazioni dichiarate, non parametri "standard" esatti):
-- - RSI14 e ATR14: media mobile semplice di gain/loss/true-range, non
--   smoothing di Wilder (differenza tipica di pochi punti, non richiede una
--   CTE ricorsiva per uno screening di questo tipo).
-- - MACD, ADX, Relative Strength, Gap, Supporti/Resistenze: NON ancora
--   implementati in questa versione (richiedono EMA ricorsiva o dati indice
--   aggiuntivi - vedi chatgpt_implementazione.md sessione 24/09 per il piano).
--
-- Copiare/incollare in Supabase SQL editor o tramite mcp Supabase execute_sql.

with base as (
  select ticker, timestamp::date as d, open, high, low, close, volume
  from prezzi where interval = '1d' and ticker in (select distinct ticker from screening_candidates)
),
ret as (
  select *,
    lag(close,1)  over wt as prev_close,
    lag(close,5)  over wt as close_5ago,
    lead(close,1)  over wt as close_p1,
    lead(close,3)  over wt as close_p3,
    lead(close,5)  over wt as close_p5,
    lead(close,10) over wt as close_p10,
    lead(close,20) over wt as close_p20
  from base window wt as (partition by ticker order by d)
),
ret2 as (
  select *, ln(close / nullif(prev_close,0)) as logret,
    greatest(high - low, abs(high - coalesce(prev_close,high)), abs(low - coalesce(prev_close,low))) as tr,
    greatest(close - coalesce(prev_close,close), 0) as gain,
    greatest(coalesce(prev_close,close) - close, 0) as loss
  from ret
),
ind as (
  select ticker, d, close, close_p1, close_p3, close_p5, close_p10, close_p20,
    avg(close) over w20  as sma20, avg(close) over w50 as sma50, avg(close) over w200 as sma200,
    max(high) over w20  as hi20,  min(low) over w20  as lo20,
    close / nullif(close_5ago,0) - 1 as roc5,
    stddev(logret) over w20 * sqrt(252) as vol20,
    avg(tr) over w14 as atr14, avg(gain) over w14 as avg_gain14, avg(loss) over w14 as avg_loss14
  from ret2
  window w14 as (partition by ticker order by d rows between 13 preceding and current row),
         w20 as (partition by ticker order by d rows between 19 preceding and current row),
         w50 as (partition by ticker order by d rows between 49 preceding and current row),
         w200 as (partition by ticker order by d rows between 199 preceding and current row)
),
ind2 as (
  select *,
    round((100 - 100/(1+ avg_gain14/nullif(avg_loss14,0)))::numeric,1) as rsi14,
    round(((close-lo20)/nullif(hi20-lo20,0))::numeric,3) as bb_pos20,
    round((atr14/close*100)::numeric,2) as atr_pct,
    (close > sma20) as sopra_sma20, (close > sma50) as sopra_sma50, (close > sma200) as sopra_sma200
  from ind
),
events as (
  select sc.id as event_id, sc.ticker as ev_ticker, (sc.timestamp at time zone 'utc')::date as event_date
  from screening_candidates sc
),
matched as (
  select e.event_id, i.*, row_number() over (partition by e.event_id order by i.d desc) as rn
  from events e join ind2 i on i.ticker = e.ev_ticker and i.d <= e.event_date
),
final as (select * from matched where rn = 1),
dir as (
  select *,
    case when close_p1  is not null then close_p1/close  - 1 end as ret1,
    case when close_p3  is not null then close_p3/close  - 1 end as ret3,
    case when close_p5  is not null then close_p5/close  - 1 end as ret5,
    case when close_p10 is not null then close_p10/close - 1 end as ret10,
    case when close_p20 is not null then close_p20/close - 1 end as ret20
  from final
),
grp as (
  select 'BASELINE' as gruppo, 'tutte le anomalie' as cond, * from dir
  union all select 'RSI14', case when rsi14<30 then 'RSI<30' when rsi14<50 then 'RSI 30-50' when rsi14<70 then 'RSI 50-70' else 'RSI>70' end, dir.* from dir
  union all select 'Trend SMA20', case when sopra_sma20 then 'sopra SMA20' else 'sotto SMA20' end, dir.* from dir
  union all select 'Trend SMA50', case when sopra_sma50 then 'sopra SMA50' else 'sotto SMA50' end, dir.* from dir
  union all select 'Trend SMA200', case when sopra_sma200 then 'sopra SMA200' else 'sotto SMA200' end, dir.* from dir
  union all select 'Bollinger pos', case when bb_pos20<0.15 then 'vicino banda bassa' when bb_pos20>0.85 then 'vicino banda alta' else 'centrale' end, dir.* from dir
  union all select 'ROC5 segno', case when roc5>=0 then 'ROC5 positivo' else 'ROC5 negativo' end, dir.* from dir
)
select gruppo, cond,
  count(*) as n,
  count(ret1) as n1, round((avg(ret1)*100)::numeric,2) as avg1_pct, round((percentile_cont(0.5) within group (order by ret1)*100)::numeric,2) as med1_pct, round((100.0*count(*) filter (where ret1>0)/nullif(count(ret1),0))::numeric,1) as pos1_pct,
  count(ret3) as n3, round((avg(ret3)*100)::numeric,2) as avg3_pct, round((percentile_cont(0.5) within group (order by ret3)*100)::numeric,2) as med3_pct, round((100.0*count(*) filter (where ret3>0)/nullif(count(ret3),0))::numeric,1) as pos3_pct,
  count(ret5) as n5, round((avg(ret5)*100)::numeric,2) as avg5_pct, round((100.0*count(*) filter (where ret5>0)/nullif(count(ret5),0))::numeric,1) as pos5_pct,
  count(ret10) as n10, round((avg(ret10)*100)::numeric,2) as avg10_pct, round((100.0*count(*) filter (where ret10>0)/nullif(count(ret10),0))::numeric,1) as pos10_pct,
  count(ret20) as n20, round((avg(ret20)*100)::numeric,2) as avg20_pct, round((100.0*count(*) filter (where ret20>0)/nullif(count(ret20),0))::numeric,1) as pos20_pct
from grp
group by gruppo, cond
order by case gruppo when 'BASELINE' then 0 else 1 end, gruppo, cond;
