"""
Modulo Experimental Rule (NUOVO 20/09)

Regola sperimentale proposta dall'utente (via ChatGPT) il 20/09, dopo aver
visto 4 alert AI Watch con variazioni di prezzo vistose ma volumi molto
bassi (STM +4.76% vol 0.1x, STLAM -4.47% vol 0.1x, ENEL -2.24% vol 0.12x,
PRY +2.99% vol 0.11x) - tutti e 4 sarebbero stati scartati da questa regola.

ESPLICITAMENTE NON OPERATIVA: non genera segnali reali, non scrive su
signals_filtered, non tocca H1/H2/Modulo B/E, non tocca AI Watch. Serve
SOLO a rispondere con dati reali, accumulati nel tempo: "questa regola
avrebbe filtrato meglio i falsi segnali?" - non "questa regola dice di
entrare". Confronto quantitativo previsto tra qualche settimana, quando
c'è abbastanza storico in experimental_rule_candidates.

Gerarchia INVARIATA (deciso esplicitamente con l'utente il 20/09):
  AI Watch (WATCH, soglie sue) -> QUESTO MODULO (candidato sperimentale,
  soglie sue, PURAMENTE OSSERVATIVO) -> H1 (soglie rigide 3.0x/1.5%,
  INVARIATE, unica fonte di segnali operativi insieme a H2/B/E)

Regola (esattamente come proposta, incluse le soglie):
- volume_ratio < 0.7x  -> no_signal_low_volume (filtro duro, qualunque
  sia il prezzo - è il punto centrale della proposta dell'utente)
- volume_ratio 0.7-1.5x -> watch_low_volume (nessuna direzione assegnata)
- volume_ratio >= 1.5x:
    prezzo>=+2% AND sovraperforma il settore AND sopra MA20 -> candidate_long
    prezzo<=-2% AND sottoperforma il settore AND sotto MA20 -> candidate_short
    altrimenti -> watch_high_volume_no_direction
- Conferma (solo per i candidate_*): il giorno dopo, chiusura non
  inferiore (long) / non superiore (short) alla chiusura del giorno della
  candidatura ("non tradisce il livello di breakout").

MA20 e forza di settore sono feature SPERIMENTALI dichiarate come tali fin
dall'inizio (come l'utente ha chiesto): si registrano, non si sa ancora se
aggiungono informazione reale rispetto a guardare solo prezzo+volume.

Girano una volta al giorno, agganciate allo stesso workflow di EOD Verify
(sapta_us_close, 21:30 UTC) - stesso principio di riuso di schedule già
usato per gli altri moduli EOD.
"""
from datetime import datetime, timezone
from config import supabase
from universe import get_universe
from market_context import get_sector_strength

VOLUME_NO_SIGNAL = 0.7
VOLUME_CANDIDATE = 1.5
PRICE_THRESHOLD_PCT = 2.0
MA_PERIOD = 20


def resolve_pending_candidates(today):
    """[Step 1] Risolve i candidati di ieri ancora senza conferma, PRIMA di
    generarne di nuovi oggi - stesso pattern del ciclo di conferma di
    AI Watch, ma su base giornaliera (seduta successiva) invece che ogni
    15 minuti."""
    try:
        rows = (supabase.table('experimental_rule_candidates')
                .select('id,ticker,direction,close_price')
                .is_('confirmed_next_session', 'null')
                .lt('eval_date', today)
                .execute())
        pending = rows.data or []
    except Exception as e:
        print(f"⚠️ Errore lettura candidati sperimentali in sospeso: {e}")
        return

    if not pending:
        print("   Nessun candidato sperimentale in sospeso da confermare.")
        return

    for p in pending:
        try:
            close_rows = (supabase.table('prezzi')
                          .select('close')
                          .eq('ticker', p['ticker']).eq('interval', '1d')
                          .order('timestamp', desc=True).limit(1).execute())
            if not close_rows.data:
                continue  # nessun dato ancora oggi per questo ticker, riprova al prossimo giro
            confirm_close = float(close_rows.data[0]['close'])
            confirmed = (confirm_close >= p['close_price']) if p['direction'] == 'long' else (confirm_close <= p['close_price'])
            supabase.table('experimental_rule_candidates').update({
                'confirmed_next_session': confirmed,
                'confirm_close_price': confirm_close,
                'confirm_checked_at': datetime.now(timezone.utc).isoformat(),
            }).eq('id', p['id']).execute()
        except Exception as e:
            print(f"⚠️ Errore conferma candidato sperimentale {p['ticker']}: {e}")

    n_confirmed = sum(1 for p in pending if p.get('id'))  # conteggio tentativi, non esito
    print(f"   {len(pending)} candidati sperimentali di ieri ricontrollati")


def get_daily_metrics():
    """Per ogni ticker dell'universo: variazione oggi, volume relativo (vs
    media 20gg), MA20, settore. Una query sola per tutto l'universo."""
    try:
        response = (supabase.table('prezzi')
                    .select('ticker,timestamp,close,volume')
                    .eq('interval', '1d')
                    .order('timestamp', desc=True)
                    .limit(MA_PERIOD * 150)  # margine per ~128 ticker x 21+ barre
                    .execute())
    except Exception as e:
        print(f"⚠️ Errore lettura prezzi giornalieri: {e}")
        return []

    by_ticker = {}
    for row in response.data or []:
        t = row.get('ticker')
        if not t or row.get('close') is None:
            continue
        by_ticker.setdefault(t, [])
        if len(by_ticker[t]) < MA_PERIOD + 1:
            by_ticker[t].append(row)

    sectors_resp = supabase.table('ticker_sectors').select('ticker,sector').execute()
    sector_map = {r['ticker']: r.get('sector') or '—' for r in (sectors_resp.data or [])}

    metrics = []
    for t, bars in by_ticker.items():
        if len(bars) < MA_PERIOD + 1:
            continue  # serve MA_PERIOD di baseline + oggi
        today_bar = bars[0]
        baseline = bars[1:MA_PERIOD + 1]
        avg_vol = sum((b.get('volume') or 0) for b in baseline) / len(baseline)
        ma20 = sum(float(b['close']) for b in baseline) / len(baseline)
        if not avg_vol or today_bar.get('close') is None:
            continue
        price_change_pct = (float(today_bar['close']) / float(baseline[0]['close']) - 1) * 100
        volume_ratio = (today_bar.get('volume') or 0) / avg_vol
        metrics.append({
            'ticker': t, 'sector': sector_map.get(t, '—'),
            'volume_ratio': round(volume_ratio, 2), 'price_change_pct': round(price_change_pct, 2),
            'close_price': float(today_bar['close']), 'ma20': round(ma20, 4),
            'above_ma20': float(today_bar['close']) > ma20,
        })
    return metrics


def classify(m, sector_avg):
    """Applica la regola esattamente come proposta dall'utente il 20/09."""
    if m['volume_ratio'] < VOLUME_NO_SIGNAL:
        return 'no_signal_low_volume', None
    if m['volume_ratio'] < VOLUME_CANDIDATE:
        return 'watch_low_volume', None
    # volume_ratio >= 1.5x da qui in poi
    outperforms = sector_avg is None or m['price_change_pct'] > sector_avg
    underperforms = sector_avg is None or m['price_change_pct'] < sector_avg
    if m['price_change_pct'] >= PRICE_THRESHOLD_PCT and outperforms and m['above_ma20']:
        return 'candidate_long', 'long'
    if m['price_change_pct'] <= -PRICE_THRESHOLD_PCT and underperforms and not m['above_ma20']:
        return 'candidate_short', 'short'
    return 'watch_high_volume_no_direction', None


def run_experimental_rule():
    print("🧪 Modulo Experimental Rule (sperimentale, non operativo): avvio...")
    today = datetime.now(timezone.utc).date().isoformat()

    resolve_pending_candidates(today)

    metrics = get_daily_metrics()
    if not metrics:
        print("   Nessun ticker con dati sufficienti (serve almeno MA20+1 barre), uscita.")
        return

    counts = {'no_signal_low_volume': 0, 'watch_low_volume': 0,
              'watch_high_volume_no_direction': 0, 'candidate_long': 0, 'candidate_short': 0}
    candidates_to_save = []

    for m in metrics:
        sector_avg = get_sector_strength(m['sector'], m['ticker'], metrics)
        label, direction = classify(m, sector_avg)
        counts[label] += 1
        if direction:
            candidates_to_save.append({
                'eval_date': today, 'ticker': m['ticker'], 'direction': direction,
                'volume_ratio': m['volume_ratio'], 'price_change_pct': m['price_change_pct'],
                'sector_avg_pct': sector_avg, 'ma20': m['ma20'], 'above_ma20': m['above_ma20'],
                'close_price': m['close_price'],
            })

    print(f"   Classificazione su {len(metrics)} ticker: {counts}")

    for c in candidates_to_save:
        try:
            supabase.table('experimental_rule_candidates').insert(c).execute()
        except Exception as e:
            # probabile duplicato (unique ticker+data) se il job viene rilanciato
            print(f"⚠️ {c['ticker']} non salvato (probabile duplicato): {e}")

    try:
        supabase.table('experimental_rule_daily_stats').insert({
            'stat_date': today, 'n_totale': len(metrics),
            'n_no_signal_low_volume': counts['no_signal_low_volume'],
            'n_watch_low_volume': counts['watch_low_volume'],
            'n_watch_high_volume_no_direction': counts['watch_high_volume_no_direction'],
            'n_candidate_long': counts['candidate_long'], 'n_candidate_short': counts['candidate_short'],
        }).execute()
    except Exception as e:
        print(f"⚠️ Statistiche giornaliere non salvate (probabile duplicato): {e}")

    print("✅ Experimental Rule completato (nessuna azione operativa generata)")


if __name__ == "__main__":
    run_experimental_rule()
