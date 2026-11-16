"""
Modulo E: Cost, Risk & Position Sizing Engine (v5.1.1)

Cambiamenti rispetto a v3.2:
- Settore letto da ticker_sectors (128 ticker) invece di SECTOR_MAP
  hardcoded in config.py (6 ticker) - il controllo di concentrazione
  settoriale ora copre davvero tutto l'universo.
- Slippage differenziato per fascia di liquidità (Sezione 12), aggiunto
  al costo prima del calcolo del rendimento netto.
- Formula di position sizing SOSTITUITA (Sezione 13): non più
  capitale*2% / (ATR*2), ma capitale*rischio% / (entry - invalidation_price).
  Richiede invalidation_price da Modulo B - se manca, il segnale viene
  saltato invece di stimare un valore arbitrario.

[NUOVO 16/09] Sezione 15 (Rischio di portafoglio) + Sezione 16 (Ranking):
- check_sector_concentration() esisteva già (v5.1.1) e copre sia la
  concentrazione settoriale sia, come approssimazione esplicitamente
  permessa dalla spec ("una stima semplice basata su settore/mercato e'
  sufficiente in questa fase"), la correlazione approssimata.
- NUOVO: check_portfolio_exposure() - esposizione totale stimata se tutte
  le opportunita' BUY approvate nella finestra venissero eseguite insieme,
  confrontata col capitale corrente. Se supera la soglia, declassa a HOLD
  come gia' avviene per la concentrazione settoriale (stesso pattern).
- NUOVO: compute_final_rank_score() - score combinato Sezione 16 (anomaly,
  contesto, confidenza, rendimento netto, qualita' dato, penalita' di
  rischio). Pesi in scoring_weights_v1.json (ranking_weights, v3) -
  PLACEHOLDER NON CALIBRATI, stesso principio di context_weights: da
  validare con backtest walk-forward prima di dare peso operativo al
  ranking, non solo ordinale/informativo.
"""
import re
import argparse
import sys
import json
import os
from datetime import datetime, timedelta, timezone
from config import supabase
from sizing import (DEFAULT_SLIPPAGE, REFERENCE_CAPITAL_EUR, RISK_PER_TRADE_PERCENT, SLIPPAGE_BY_LIQUIDITY,  # noqa: F401
                    calculate_operation_cost, entry_reference_price, round_trip_cost, size_position)


def _fromiso(s):
    """fromisoformat tollerante: Python <3.11 accetta solo 3 o 6 cifre di frazione."""
    s = str(s).replace('Z', '+00:00')
    s = re.sub(r'\.(\d{1,6})\d*', lambda m: '.' + m.group(1).ljust(6, '0'), s, count=1)
    return datetime.fromisoformat(s)


# [v5.1.1] Sostituisce SECTOR_MAP hardcoded - non più importato da config.py
MAX_POSITIONS_PER_SECTOR = 2
SECTOR_EXPOSURE_LOOKBACK_DAYS = 10

# [Sezione 15 - NUOVO 16/09] Esposizione totale massima stimata, come
# frazione del capitale corrente, se tutte le posizioni BUY approvate nella
# finestra di lookback (stessa di MAX_POSITIONS_PER_SECTOR) venissero
# eseguite insieme. Placeholder non calibrato - vedi nota in testa al file.
MAX_PORTFOLIO_EXPOSURE_PERCENT = 0.60

WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scoring_weights_v1.json')
with open(WEIGHTS_PATH) as f:
    _WEIGHTS = json.load(f)
RANKING_WEIGHTS = _WEIGHTS.get('ranking_weights', {})
SCORING_WEIGHTS_VERSION = _WEIGHTS['version']

# [Sezione 13] Rischio massimo per singola operazione, % del capitale

# Fallback estremo se capital_state è vuota o irraggiungibile - non è più il
# valore "vero" del capitale, solo una rete di sicurezza per non bloccare il
# job. Il capitale reale si legge da capital_state (tabella Supabase),
# impostabile a runtime dalla dashboard: consente di testare capitali diversi,
# aumentarlo/diminuirlo nel tempo, e in futuro (Fase 7, Modulo G) aggiornarlo
# automaticamente in base ai P&L realizzati (change_type='realized_pnl').
FALLBACK_CAPITAL_EUR = REFERENCE_CAPITAL_EUR   # solo se capital_state e' VUOTA; un errore di lettura NON usa il ripiego


class CapitalUnavailable(RuntimeError):
    pass


def get_current_capital():
    """Legge il capitale corrente da capital_state (riga piu' recente). [Passo 3] Tabella vuota = capitale di riferimento
    (1.000 EUR, avviso nel log). Errore di lettura = CapitalUnavailable: E si ferma con errore, nessun segnale viene valutato
    su un capitale presunto."""
    try:
        response = (supabase.table('capital_state')
                    .select('capital_eur, created_at')
                    .order('created_at', desc=True)
                    .limit(1)
                    .execute())
    except Exception as e:
        raise CapitalUnavailable(f"lettura capital_state fallita: {e}")
    if response.data:
        return float(response.data[0]['capital_eur'])
    print(f"⚠️ capital_state vuota, uso il capitale di riferimento €{FALLBACK_CAPITAL_EUR}")
    return FALLBACK_CAPITAL_EUR


def get_broker_costs(broker='Alpaca', mercato='USA'):
    try:
        response = (supabase.table('costi_operazione')
                    .select('*')
                    .eq('broker', broker).eq('mercato', mercato).eq('attivo', True)
                    .execute())
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"❌ Errore recupero costi: {e}")
        return None


# [NUOVO 03/10] Costi per mercato: titoli USA -> riga Alpaca/USA, titoli italiani (.MI) ->
# riga Interactive Brokers/EU. Prima TUTTI i ticker usavano la riga USA (zero commissioni).
# Formula, soglie e filtro restano identici: cambia solo QUALE riga di costi_operazione si usa.
COST_ROW_BY_MARKET = {
    'USA': ('Alpaca', 'USA'),
    'EU': ('Interactive Brokers', 'EU'),
}


def market_for_ticker(ticker):
    """'USA' se il ticker e' nell'universo USA, altrimenti 'EU' (tutti gli altri sono titoli italiani .MI)."""
    from universe import UNIVERSE_USA
    return 'USA' if ticker in UNIVERSE_USA else 'EU'


def get_costs_by_market():
    """Una riga di costi per mercato (None se mancante o non attiva)."""
    return {m: get_broker_costs(broker=b, mercato=mk) for m, (b, mk) in COST_ROW_BY_MARKET.items()}


def get_ticker_sector_and_liquidity(ticker):
    """[v5.1.1] Legge da ticker_sectors (128 ticker) invece di SECTOR_MAP."""
    try:
        response = (supabase.table('ticker_sectors')
                    .select('sector, liquidity_bucket')
                    .eq('ticker', ticker)
                    .execute())
        if response.data:
            return response.data[0].get('sector'), response.data[0].get('liquidity_bucket')
        return None, None
    except Exception as e:
        print(f"⚠️ Errore lettura ticker_sectors per {ticker}: {e}")
        return None, None


def calculate_expected_return(price, confidence_multiplier, atr, costs, quantity, liquidity_bucket, target_price=None):
    """[Passo 3] Rendimento atteso coerente con livelli e costi reali.
    - mossa attesa = distanza dal prezzo di ingresso di dimensionamento (R + 0,5 ATR, con slippage) al TARGET effettivo del
      segnale; se il target manca, ripiego storico 2*ATR;
    - costi = ANDATA E RITORNO (commissione fissa x2, commissione %, spread, bollo e slippage su entrambi i lati);
    - lordo = mossa/ingresso x confidence_multiplier (1.0/0.7/0.4, Sezione 11), netto = lordo - costi - riserva fiscale."""
    entry = entry_reference_price(price, atr, liquidity_bucket)
    expected_move = (float(target_price) - entry) if target_price is not None and float(target_price) > entry else atr * 2
    expected_gross_return = (expected_move / entry) * confidence_multiplier

    total_cost, slippage_pct = round_trip_cost(entry, quantity, costs, liquidity_bucket)
    cost_percent = total_cost / (entry * quantity)

    expected_net_return = expected_gross_return - cost_percent
    tax_reserve = expected_net_return * costs['tassazione_plusvalenza_percentuale'] if expected_net_return > 0 else 0

    return {
        'expected_gross_return': expected_gross_return,
        'estimated_cost': cost_percent,
        'expected_net_return': expected_net_return - tax_reserve,
        'slippage_applied_percent': slippage_pct,
    }


def get_usd_per_eur():
    """[FIX 30/09 - handoff Codex] Dollari per 1 EUR (Yahoo EURUSD=X, ultima
    chiusura disponibile). NON e' un feed FX tick-by-tick: cambio indicativo,
    non operativo real-time. None se non disponibile/non plausibile."""
    try:
        import yfinance as yf
        hist = yf.Ticker('EURUSD=X').history(period='5d')['Close'].dropna()
        fx = float(hist.iloc[-1])
        if 0.5 < fx < 2.0:
            return fx
        print(f"⚠️ Cambio EURUSD non plausibile: {fx}")
    except Exception as e:
        print(f"⚠️ Cambio EURUSD non disponibile: {e}")
    return None


# Quando il portafoglio paper sara' collegato (FASE 5) bastera' cambiare QUESTA funzione: una sola fonte autorevole.
ACTIVE_CYCLE_STATES = ('ENTRY_PENDING', 'ACTIVE', 'EXIT_PENDING')   # capitale impegnato (un WATCH non ha comprato nulla)
RACE_WINDOW_MINUTES = 30      # BUY approvati da E da meno di 30 min che T non ha ancora trasformato in ciclo


def get_active_exposure_items():
    """Elenco [{'ticker', 'eur', 'source'}] di cio' che impegna capitale ADESSO:
    1) cicli di T con ingresso deciso e non ancora usciti (controvalore reale del ciclo);
    2) finestra di corsa: BUY approvati da E negli ultimi 30 minuti senza ancora un ciclo (cosi' piu' segnali approvati
       nello stesso run si vedono tra loro, come prima) - non contano se il titolo ha gia' un ciclo attivo.
    Scaduti, invalidati, chiusi e storici non contano."""
    items = []
    cyc = (supabase.table('trade_lifecycle').select('ticker,countervalue_eur,state')
           .in_('state', list(ACTIVE_CYCLE_STATES)).execute().data or [])
    active_tickers = set()
    for c in cyc:
        items.append({'ticker': c['ticker'], 'eur': float(c.get('countervalue_eur') or 0), 'source': 'T'})
        active_tickers.add(c['ticker'])
    since = (datetime.now(timezone.utc) - timedelta(minutes=RACE_WINDOW_MINUTES)).isoformat()
    recent = (supabase.table('signals_filtered').select('raw_signal_id,ticker,position_size_suggested')
              .eq('filtered_action', 'BUY').eq('filter_passed', True).gte('timestamp', since).execute().data or [])
    if recent:
        raw_ids = [r['raw_signal_id'] for r in recent if r.get('raw_signal_id') is not None]
        with_cycle = set()
        if raw_ids:
            with_cycle = {r['raw_signal_id'] for r in (supabase.table('trade_lifecycle').select('raw_signal_id')
                                                       .in_('raw_signal_id', raw_ids).execute().data or [])}
        for r in recent:
            if r.get('raw_signal_id') in with_cycle or r['ticker'] in active_tickers:
                continue
            items.append({'ticker': r['ticker'], 'eur': float(r.get('position_size_suggested') or 0), 'source': 'signal'})
    return items


def check_sector_concentration(ticker, sector, lookback_days, max_per_sector):
    """[Passo 3 - P1-6] FAIL-CLOSED. Ritorna (ok, conteggio, motivo_di_blocco).
    Settore sconosciuto o controllo non eseguibile = NON ok (il BUY viene bloccato) con il motivo esplicito.
    Si contano le posizioni ATTIVE del settore (get_active_exposure_items); lookback_days non e' piu' usato."""
    if not sector:
        return False, 0, f"Settore non riconosciuto per {ticker}: concentrazione non verificabile"
    try:
        same_sector = (supabase.table('ticker_sectors').select('ticker').eq('sector', sector).execute())
        sector_tickers = {r['ticker'] for r in (same_sector.data or [])}
        if not sector_tickers:
            return False, 0, f"Settore '{sector}' senza ticker in ticker_sectors: concentrazione non verificabile"
        held = {i['ticker'] for i in get_active_exposure_items() if i['ticker'] in sector_tickers}
        count = len(held)
        if count >= max_per_sector:
            return False, count, f"Concentrazione settoriale: già {count} posizioni in '{sector}' (max {max_per_sector})"
        return True, count, None
    except Exception as e:
        print(f"❌ Errore controllo concentrazione settore {sector}: {e}")
        return False, 0, f"Controllo concentrazione settoriale NON eseguibile ({e}): BUY bloccato"


def check_portfolio_exposure(new_position_eur, capital, lookback_days, max_exposure_percent):
    """[Passo 3 - P1-6] FAIL-CLOSED. Ritorna (ok, esposizione_pct, motivo_di_blocco). Esposizione = capitale impegnato dalle
    posizioni attive piu' la nuova candidata, rispetto al capitale. Errore di lettura = NON ok, motivo esplicito."""
    try:
        existing_exposure = sum(i['eur'] for i in get_active_exposure_items())
        total_exposure = existing_exposure + (new_position_eur or 0)
        exposure_pct = total_exposure / capital if capital else 1.0
        if exposure_pct > max_exposure_percent:
            return False, exposure_pct, f"Esposizione di portafoglio stimata {exposure_pct:.0%} > soglia {max_exposure_percent:.0%}"
        return True, exposure_pct, None
    except Exception as e:
        print(f"❌ Errore controllo esposizione di portafoglio: {e}")
        return False, 0.0, f"Controllo esposizione NON eseguibile ({e}): BUY bloccato"


def get_screening_candidates_map(candidate_ids):
    """Una sola query per tutti i candidati del batch corrente, invece di
    una query per segnale - stesso pattern di get_ticker_meta_map in H."""
    if not candidate_ids:
        return {}
    try:
        response = (supabase.table('screening_candidates')
                    .select('id, anomaly_score, context_score, data_quality_flag')
                    .in_('id', list(candidate_ids))
                    .execute())
        return {row['id']: row for row in (response.data or [])}
    except Exception as e:
        print(f"⚠️ Errore lettura screening_candidates per ranking: {e}")
        return {}


def compute_final_rank_score(anomaly_score, context_score, confidence_multiplier,
                              expected_net_return, data_quality_flag, risk_penalty):
    """[Sezione 16 - NUOVO 16/09] Score combinato 0-100, solo per opportunita'
    BUY/SELL approvate (le HOLD non vengono ranked). PLACEHOLDER NON
    CALIBRATO: normalizzazioni (soft cap anomaly a 20, rendimento netto a
    5%) e pesi (ranking_weights in scoring_weights_v1.json) sono punti di
    partenza ragionevoli, da validare col backtest walk-forward (Sezione 22)
    prima di dare peso operativo al ranking - vedi nota in testa al file."""
    if not RANKING_WEIGHTS:
        return None

    anomaly_norm = min((anomaly_score or 0) / 20.0, 1.0)
    context_norm = ((context_score or 0.0) + 1) / 2  # -1..+1 -> 0..1, neutro (0.5) se mancante
    return_norm = min(max((expected_net_return or 0) / 0.05, 0.0), 1.0)
    data_quality_score = 1.0 if data_quality_flag == 'ok' else 0.5

    w = RANKING_WEIGHTS
    score = (
        w.get('anomaly', 0) * anomaly_norm
        + w.get('context', 0) * context_norm
        + w.get('confidence', 0) * (confidence_multiplier or 0)
        + w.get('net_return', 0) * return_norm
        + w.get('data_quality', 0) * data_quality_score
        - w.get('risk_penalty', 0) * min(risk_penalty or 0, 1.0)
    )
    return round(score * 100, 2)


def _norm_ts(value):
    """Timestamp ISO -> datetime UTC confrontabile (i formati di Supabase
    possono differire per separatore/offset ma indicano lo stesso istante)."""
    try:
        return _fromiso(value).astimezone(timezone.utc)
    except Exception:
        return None


def get_already_evaluated(threshold):
    """[NUOVO 01/10 - idempotenza] Ritorna (ids, coppie) dei segnali grezzi che
    hanno gia' una riga in signals_filtered: per raw_signal_id, e - per le righe
    storiche senza id - per (ticker, timestamp). Se la query fallisce solleva
    l'eccezione: meglio saltare il run che scrivere duplicati."""
    resp = supabase.table('signals_filtered').select('raw_signal_id,ticker,timestamp') \
        .gte('timestamp', threshold).execute()
    ids = {r['raw_signal_id'] for r in (resp.data or []) if r.get('raw_signal_id') is not None}
    pairs = {(r['ticker'], _norm_ts(r['timestamp'])) for r in (resp.data or [])
             if r.get('raw_signal_id') is None}
    return ids, pairs


def _is_unique_violation(exc):
    msg = str(exc).lower()
    return '23505' in msg or 'duplicate key' in msg or 'unique constraint' in msg


def filter_signals(tickers_filter=None):
    try:
        threshold = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
        response = supabase.table('signals_raw').select('*').gte('timestamp', threshold).execute()
        if not response.data:
            print("⚠️ Nessun segnale grezzo recente")
            return

        signals_to_process = response.data
        if tickers_filter is not None:
            signals_to_process = [s for s in signals_to_process if s['ticker'] in tickers_filter]
            if not signals_to_process:
                print(f"⚠️ Nessun segnale grezzo recente per i ticker richiesti")
                return

        # [NUOVO 01/10 - idempotenza] Un solo risultato E per segnale grezzo.
        # sapta_slow gira ogni 15 minuti e la finestra e' di 35: senza questo
        # controllo ogni segnale veniva rivalutato 2-4 volte (e il controllo di
        # esposizione contava anche i propri duplicati). La logica decisionale
        # non cambia: si evita solo di rivalutare cio' che e' gia' stato valutato.
        done_ids, done_pairs = get_already_evaluated(threshold)
        n_before = len(signals_to_process)
        signals_to_process = [
            s_ for s_ in signals_to_process
            if s_['id'] not in done_ids and (s_['ticker'], _norm_ts(s_['timestamp'])) not in done_pairs
        ]
        n_skipped = n_before - len(signals_to_process)
        if n_skipped:
            print(f"ℹ️ {n_skipped} segnali grezzi già valutati in precedenza: saltati (idempotenza)")
        if not signals_to_process:
            print("✅ Nessun segnale nuovo da valutare")
            return

        control_failures, write_failures = [], 0
        costs_by_market = get_costs_by_market()
        if not any(costs_by_market.values()):
            print("❌ Costi broker non configurati")
            return

        # Letto una sola volta per run (non per singolo segnale): il capitale
        # non cambia nel corso di un'esecuzione di 2-3 minuti, e così si evita
        # una query Supabase per ogni ticker.
        try:
            current_capital = get_current_capital()
        except CapitalUnavailable as e:
            print(f"❌ {e}: nessun segnale valutato (fail-closed)")
            return 1
        print(f"💰 Capitale corrente: €{current_capital:,.2f}")

        # [Sezione 16 - NUOVO 16/09] Batch fetch di anomaly_score/context_score
        # dai candidati H2 collegati, una sola query per l'intero run.
        candidate_ids = {s['screening_candidate_id'] for s in signals_to_process
                          if s.get('screening_candidate_id')}
        candidates_map = get_screening_candidates_map(candidate_ids)

        # [FIX 30/09] Cambio USD/EUR letto una sola volta, solo se serve.
        from universe import UNIVERSE_USA
        usd_per_eur = get_usd_per_eur() if any(
            s_['ticker'] in UNIVERSE_USA for s_ in signals_to_process) else None

        for signal in signals_to_process:
            ticker = signal['ticker']
            price = signal.get('close_price')
            atr = signal.get('atr')
            confidence_multiplier = signal.get('confidence_multiplier', 0.4)
            invalidation_price = signal.get('invalidation_price')
            target_price = signal.get('target_price')

            if not price or not atr:
                print(f"⚠️ {ticker}: segnale senza price/ATR, salto")
                continue

            sector, liquidity_bucket = get_ticker_sector_and_liquidity(ticker)

            # [Sezione 13] Se manca invalidation_price (es. azione HOLD, o
            # deterioramento già scartato da B), niente size, niente filtro E
            # [FIX 30/09 - handoff Codex] Unita' esplicite:
            #   quantity = numero di azioni; countervalue = quantity * prezzo.
            # Capitale in EUR, prezzo nella valuta del titolo (USD per USA).
            fx_to_eur = 1.0  # EUR per 1 unita' di valuta del prezzo
            if ticker in UNIVERSE_USA:
                if not usd_per_eur:
                    print(f"⚠️ {ticker}: cambio USD/EUR non disponibile, salto (ritentato al prossimo run)")
                    continue
                fx_to_eur = 1.0 / usd_per_eur
            costs = costs_by_market.get(market_for_ticker(ticker))
            if not costs:
                print(f"⚠️ {ticker}: costi di mercato {market_for_ticker(ticker)} non configurati - salto (ritentato al prossimo run)")
                continue
            if invalidation_price is None and signal['action'] != 'HOLD':
                print(f"⚠️ {ticker}: manca invalidation_price, impossibile dimensionare - salto")
                continue
            # [Passo 3 - P1-7] stessa funzione di Modulo T: prezzo R + 0,5 ATR, costi andata/ritorno inclusi nel rischio, quantita' intera
            sizing = size_position(price, atr, invalidation_price, current_capital, fx_to_eur, costs, liquidity_bucket)
            quantity = sizing['quantity'] if sizing else 0
            if sizing is None and signal['action'] != 'HOLD':
                print(f"⚠️ {ticker}: stop non sotto il prezzo di ingresso, impossibile dimensionare - salto")
                continue
            countervalue_eur = sizing['countervalue_eur'] if sizing else 0.0
            position_size = countervalue_eur if quantity else None  # EUR (vedi check_portfolio_exposure)
            returns = calculate_expected_return(price, confidence_multiplier, atr, costs, max(quantity, 1), liquidity_bucket, target_price)

            threshold_net = 0.005
            filter_passed = returns['expected_net_return'] > threshold_net and signal['action'] != 'HOLD'
            filtered_action = signal['action'] if filter_passed else 'HOLD'
            filter_reason = None if filter_passed else (
                f"Rendimento netto {returns['expected_net_return']:.2%} < soglia {threshold_net:.2%}"
                if signal['action'] != 'HOLD' else "Azione originale già HOLD"
            )

            sector_count = 0
            exposure_pct = 0.0
            if filter_passed and filtered_action == 'BUY' and quantity < 1:
                filter_passed, filtered_action = False, 'HOLD'
                filter_reason = "Quantita' < 1 azione con il rischio per operazione (costi inclusi)"
            if filter_passed and filtered_action == 'BUY':
                sector_ok, sector_count, block_reason = check_sector_concentration(
                    ticker, sector, SECTOR_EXPOSURE_LOOKBACK_DAYS, MAX_POSITIONS_PER_SECTOR
                )
                if not sector_ok:
                    filter_passed, filtered_action, filter_reason = False, 'HOLD', block_reason
                    if block_reason and 'NON eseguibile' in block_reason or 'non riconosciuto' in (block_reason or ''):
                        control_failures.append(f"{ticker}: {block_reason}")

            # [Sezione 15] Esposizione totale stimata, solo se il segnale e' ancora BUY dopo il filtro settoriale. FAIL-CLOSED.
            if filter_passed and filtered_action == 'BUY':
                exposure_ok, exposure_pct, block_reason = check_portfolio_exposure(
                    countervalue_eur, current_capital, SECTOR_EXPOSURE_LOOKBACK_DAYS,
                    MAX_PORTFOLIO_EXPOSURE_PERCENT
                )
                if not exposure_ok:
                    filter_passed, filtered_action, filter_reason = False, 'HOLD', block_reason
                    if 'NON eseguibile' in (block_reason or ''):
                        control_failures.append(f"{ticker}: {block_reason}")

            # [Sezione 16 - NUOVO 16/09] Ranking, solo per opportunità
            # ancora BUY/SELL dopo tutti i filtri di Sezione 12+15.
            final_rank_score = None
            if filter_passed and filtered_action != 'HOLD':
                candidate = candidates_map.get(signal.get('screening_candidate_id'), {})
                final_rank_score = compute_final_rank_score(
                    anomaly_score=candidate.get('anomaly_score'),
                    context_score=candidate.get('context_score'),
                    confidence_multiplier=confidence_multiplier,
                    expected_net_return=returns['expected_net_return'],
                    data_quality_flag=candidate.get('data_quality_flag'),
                    risk_penalty=exposure_pct,
                )

            row_filtered = {
                'raw_signal_id': signal['id'],
                'timestamp': signal['timestamp'],
                'ticker': ticker,
                'original_action': signal['action'],
                'filtered_action': filtered_action,
                'expected_gross_return': returns['expected_gross_return'],
                'estimated_cost': returns['estimated_cost'],
                'expected_net_return': returns['expected_net_return'],
                'filter_passed': filter_passed,
                'filter_reason': filter_reason,
                'position_size_suggested': position_size,
                'opportunity_type': signal.get('opportunity_type'),
                'confidence_level': signal.get('confidence_level'),
                'invalidation_price': invalidation_price,
                'target_price': target_price,
                'invalidation_reason': signal.get('invalidation_reason'),
                'liquidity_bucket': liquidity_bucket,
                'slippage_applied_percent': returns['slippage_applied_percent'],
                'sector_concentration_count': sector_count,
                'portfolio_exposure_pct': round(exposure_pct, 4),
                'final_rank_score': final_rank_score,
            }
            try:
                res_f = supabase.table('signals_filtered').insert(row_filtered).execute()
                if not getattr(res_f, 'data', None):
                    raise RuntimeError("scrittura non confermata dal DB (nessuna riga restituita)")
            except Exception as e:
                if _is_unique_violation(e):
                    # valutato nel frattempo da un altro run: non e' un errore
                    print(f"ℹ️ {ticker}: già valutato da un altro run (vincolo di unicità), salto")
                    continue
                print(f"❌ {ticker}: scrittura signals_filtered fallita: {e} - ritentato al prossimo run")
                write_failures += 1
                continue

            status = "✅ APPROVATO" if filter_passed else f"❌ DECLASSATO ({filter_reason})"
            rank_info = f" | rank={final_rank_score}" if final_rank_score is not None else ""
            print(f"{ticker}: {signal['action']} → {filtered_action} {status}{rank_info}")

        for msg in control_failures:
            print(f"❌ CONTROLLO DI RISCHIO FALLITO (BUY bloccato): {msg}")
        print(f"✅ E: controlli di rischio falliti={len(control_failures)}, scritture fallite={write_failures}")
        return 1 if (control_failures or write_failures) else 0

    except Exception as e:
        print(f"❌ Errore filtro costi: {e}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', choices=['ALL', 'USA', 'EU'], default='ALL')
    args = parser.parse_args()

    tickers_filter = None
    if args.market != 'ALL':
        from universe import get_universe_metadata
        metadata = get_universe_metadata()
        tickers_filter = [t for t, m in metadata.items() if m['market'] == args.market]

    print(f"🚀 Modulo E - Cost Filter ({args.market}): {datetime.now(timezone.utc).isoformat()}")
    sys.exit(filter_signals(tickers_filter=tickers_filter) or 0)
