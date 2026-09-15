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
"""
import argparse
from datetime import datetime, timedelta, timezone
from config import supabase

# [v5.1.1] Sostituisce SECTOR_MAP hardcoded - non più importato da config.py
MAX_POSITIONS_PER_SECTOR = 2
SECTOR_EXPOSURE_LOOKBACK_DAYS = 10

# [Sezione 12] Valori di default, non calibrati - vedi v5.1.1 §28 alert 4
SLIPPAGE_BY_LIQUIDITY = {
    'LIQ_HIGH': 0.0005,
    'LIQ_MEDIUM': 0.0015,
    'LIQ_LOW': 0.0040,
}
DEFAULT_SLIPPAGE = 0.0040  # fail-safe: se liquidity_bucket manca, tratta come il caso peggiore

# [Sezione 13] Rischio massimo per singola operazione, % del capitale
RISK_PER_TRADE_PERCENT = 0.01  # 1%, punto medio del range 0.5-1% indicato in spec

# Fallback estremo se capital_state è vuota o irraggiungibile - non è più il
# valore "vero" del capitale, solo una rete di sicurezza per non bloccare il
# job. Il capitale reale si legge da capital_state (tabella Supabase),
# impostabile a runtime dalla dashboard: consente di testare capitali diversi,
# aumentarlo/diminuirlo nel tempo, e in futuro (Fase 7, Modulo G) aggiornarlo
# automaticamente in base ai P&L realizzati (change_type='realized_pnl').
FALLBACK_CAPITAL_EUR = 1000


def get_current_capital():
    """Legge il capitale corrente da capital_state (riga più recente per timestamp).
    Fail-open: se la tabella è vuota o la query fallisce, usa FALLBACK_CAPITAL_EUR
    e stampa un avviso esplicito - non blocca il job, ma il valore usato è
    tracciabile nei log."""
    try:
        response = (supabase.table('capital_state')
                    .select('capital_eur, created_at')
                    .order('created_at', desc=True)
                    .limit(1)
                    .execute())
        if response.data:
            capital = float(response.data[0]['capital_eur'])
            return capital
        print(f"⚠️ capital_state vuota, uso fallback €{FALLBACK_CAPITAL_EUR}")
        return FALLBACK_CAPITAL_EUR
    except Exception as e:
        print(f"⚠️ Errore lettura capital_state: {e} — uso fallback €{FALLBACK_CAPITAL_EUR}")
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


def calculate_operation_cost(price, quantity, costs, liquidity_bucket):
    """[Sezione 12] Aggiunge lo slippage per fascia di liquidità al costo base."""
    commission_fixed = costs['commissione_fissa']
    commission_variable = price * quantity * costs['commissione_percentuale']
    spread_cost = price * quantity * costs['spread_medio_percentuale']
    bollo = price * quantity * costs['bollo_percentuale']

    slippage_pct = SLIPPAGE_BY_LIQUIDITY.get(liquidity_bucket, DEFAULT_SLIPPAGE)
    slippage_cost = price * quantity * slippage_pct

    total_cost = commission_fixed + commission_variable + spread_cost + bollo + slippage_cost
    return total_cost, slippage_pct


def calculate_expected_return(price, confidence_multiplier, atr, costs, quantity, liquidity_bucket):
    """[v5.1.1] confidence_multiplier sostituisce il vecchio uso diretto di
    confidence_score come moltiplicatore grezzo - ora viene dalla mappatura
    esplicita di Sezione 11 (alto/medio/basso -> 1.0/0.7/0.4)."""
    expected_move = atr * 2
    expected_gross_return = (expected_move / price) * confidence_multiplier

    total_cost, slippage_pct = calculate_operation_cost(price, quantity, costs, liquidity_bucket)
    cost_percent = total_cost / (price * quantity)

    expected_net_return = expected_gross_return - cost_percent
    tax_reserve = expected_net_return * costs['tassazione_plusvalenza_percentuale'] if expected_net_return > 0 else 0

    return {
        'expected_gross_return': expected_gross_return,
        'estimated_cost': cost_percent,
        'expected_net_return': expected_net_return - tax_reserve,
        'slippage_applied_percent': slippage_pct,
    }


def calculate_position_size(entry_price, invalidation_price, capital, risk_percent=RISK_PER_TRADE_PERCENT):
    """
    [Sezione 13 - SOSTITUISCE la vecchia formula capitale*2%/(ATR*2)]

    size = (capitale * rischio_max_per_trade%) / (prezzo_entrata - prezzo_stop)

    A differenza della vecchia formula (basata solo su ATR), qui la
    distanza reale dallo stop (invalidation_price di Modulo B, Sezione 14)
    determina la size: due titoli con lo stesso ATR ma stop tecnici a
    distanze diverse ricevono size diverse, riflettendo il rischio vero.
    """
    if invalidation_price is None:
        return None  # niente stima arbitraria: se manca il dato, il segnale va saltato

    stop_distance = abs(entry_price - invalidation_price)
    if stop_distance <= 0:
        return None

    max_risk_eur = capital * risk_percent
    return max_risk_eur / stop_distance


def check_sector_concentration(ticker, sector, lookback_days, max_per_sector):
    """[v5.1.1] Logica invariata dalla v3.2, ma ora sector arriva da
    ticker_sectors (128 ticker) invece che da SECTOR_MAP (6 ticker) -
    il controllo copre finalmente tutto l'universo."""
    if not sector:
        return True, 0  # settore sconosciuto (es. BPSO.MI): fail-open, non blocca

    try:
        threshold = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        # Serve la lista di ticker dello stesso settore: query diretta su ticker_sectors
        same_sector = (supabase.table('ticker_sectors')
                       .select('ticker')
                       .eq('sector', sector)
                       .execute())
        sector_tickers = [r['ticker'] for r in (same_sector.data or [])]
        if not sector_tickers:
            return True, 0

        response = (supabase.table('signals_filtered')
                    .select('ticker')
                    .in_('ticker', sector_tickers)
                    .eq('filtered_action', 'BUY')
                    .eq('filter_passed', True)
                    .gte('timestamp', threshold)
                    .execute())
        count = len(response.data) if response.data else 0
        return count < max_per_sector, count
    except Exception as e:
        print(f"⚠️ Errore controllo concentrazione settore {sector}: {e}")
        return True, 0


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

        costs = get_broker_costs()
        if not costs:
            print("❌ Costi broker non configurati")
            return

        # Letto una sola volta per run (non per singolo segnale): il capitale
        # non cambia nel corso di un'esecuzione di 2-3 minuti, e così si evita
        # una query Supabase per ogni ticker.
        current_capital = get_current_capital()
        print(f"💰 Capitale corrente: €{current_capital:,.2f}")

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
            position_size = calculate_position_size(price, invalidation_price, current_capital)
            if position_size is None and signal['action'] != 'HOLD':
                print(f"⚠️ {ticker}: manca invalidation_price, impossibile dimensionare - salto")
                continue

            quantity = position_size / price if position_size else 0
            returns = calculate_expected_return(price, confidence_multiplier, atr, costs, max(quantity, 1), liquidity_bucket)

            threshold_net = 0.005
            filter_passed = returns['expected_net_return'] > threshold_net and signal['action'] != 'HOLD'
            filtered_action = signal['action'] if filter_passed else 'HOLD'
            filter_reason = None if filter_passed else (
                f"Rendimento netto {returns['expected_net_return']:.2%} < soglia {threshold_net:.2%}"
                if signal['action'] != 'HOLD' else "Azione originale già HOLD"
            )

            if filter_passed and filtered_action == 'BUY':
                sector_ok, sector_count = check_sector_concentration(
                    ticker, sector, SECTOR_EXPOSURE_LOOKBACK_DAYS, MAX_POSITIONS_PER_SECTOR
                )
                if not sector_ok:
                    filter_passed = False
                    filtered_action = 'HOLD'
                    filter_reason = f"Concentrazione settoriale: già {sector_count} posizioni in '{sector}' (max {MAX_POSITIONS_PER_SECTOR})"

            supabase.table('signals_filtered').insert({
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
            }).execute()

            status = "✅ APPROVATO" if filter_passed else f"❌ DECLASSATO ({filter_reason})"
            print(f"{ticker}: {signal['action']} → {filtered_action} {status}")

    except Exception as e:
        print(f"❌ Errore filtro costi: {e}")


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
    filter_signals(tickers_filter=tickers_filter)
