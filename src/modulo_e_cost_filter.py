"""
Modulo E: Cost & Position Sizing Engine
Filtra segnali in base al costo reale dell'operazione, incluso un controllo
di concentrazione settoriale (v3.2).
"""
from datetime import datetime, timedelta, timezone
from config import supabase, SECTOR_MAP, MAX_POSITIONS_PER_SECTOR, SECTOR_EXPOSURE_LOOKBACK_DAYS


def get_broker_costs(broker='Alpaca', mercato='USA'):
    """Recupera costi del broker da Supabase"""
    try:
        response = supabase.table('costi_operazione').select('*').eq('broker', broker).eq('mercato', mercato).eq('attivo', True).execute()
        if response.data:
            return response.data[0]
    except Exception as e:
        print(f"❌ Errore recupero costi: {e}")
    return None


def calculate_operation_cost(price, quantity, costs):
    """Calcola costo totale di un'operazione"""
    commission_fixed = costs['commissione_fissa']
    commission_variable = price * quantity * costs['commissione_percentuale']
    spread_cost = price * quantity * costs['spread_medio_percentuale']
    bollo = price * quantity * costs['bollo_percentuale']

    total_cost = commission_fixed + commission_variable + spread_cost + bollo
    return total_cost


def calculate_expected_return(price, confidence, atr, costs, quantity):
    """Calcola rendimento atteso netto"""
    # Stima rendimento lordo basato su ATR (volatilità) e confidence
    expected_move = atr * 2  # Movimento atteso = 2x ATR
    expected_gross_return = (expected_move / price) * confidence

    # Costo totale
    total_cost = calculate_operation_cost(price, quantity, costs)
    cost_percent = total_cost / (price * quantity)

    # Rendimento netto
    expected_net_return = expected_gross_return - cost_percent

    # Accantonamento tasse su plusvalenza
    # (v3.5 fix: era 'tassazione_plusvalenja_percentuale', refuso che causava
    # KeyError su ogni segnale con rendimento netto positivo, interrompendo
    # il ciclo di filter_signals() a metà batch)
    tax_reserve = expected_net_return * costs['tassazione_plusvalenza_percentuale'] if expected_net_return > 0 else 0

    return {
        'expected_gross_return': expected_gross_return,
        'estimated_cost': cost_percent,
        'expected_net_return': expected_net_return - tax_reserve,
        'total_cost_eur': total_cost
    }


def check_sector_concentration(ticker, sector, lookback_days, max_per_sector):
    """(v3.2) Verifica quanti segnali BUY dello stesso settore sono già stati approvati
    nella finestra di lookback. Approssimazione basata su signals_filtered (non sul
    portafoglio reale, che arriverà con il Modulo G in Fase 7 — vedi SAPTA_v3.md §3).
    Ritorna (ok: bool, conteggio_attuale: int)."""
    if not sector:
        return True, 0  # ticker senza settore mappato: nessun controllo possibile, non blocca

    sector_tickers = [t for t, s in SECTOR_MAP.items() if s == sector]
    if not sector_tickers:
        return True, 0

    try:
        threshold = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
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
        return True, 0  # in caso di errore, non blocchiamo il segnale (fail-open sul solo controllo extra)


def filter_signals(tickers_filter=None):
    """Recupera segnali grezzi recenti e li filtra per costo.

    v3.5: `tickers_filter` (opzionale) limita l'elaborazione a una lista di ticker —
    usato dal run dedicato post-chiusura USA (`--market=USA`) per rielaborare solo
    i segnali appena rigenerati da Modulo B con la barra ormai finalizzata.
    """
    try:
        # Recupera segnali degli ultimi 35 minuti
        threshold = (datetime.now(timezone.utc) - timedelta(minutes=35)).isoformat()
        response = supabase.table('signals_raw').select('*').gte('timestamp', threshold).execute()

        if not response.data:
            print("⚠️ Nessun segnale grezzo recente")
            return

        signals_to_process = response.data
        if tickers_filter is not None:
            signals_to_process = [s for s in signals_to_process if s['ticker'] in tickers_filter]
            if not signals_to_process:
                print(f"⚠️ Nessun segnale grezzo recente per i ticker richiesti ({tickers_filter})")
                return

        costs = get_broker_costs()
        if not costs:
            print("❌ Costi broker non configurati")
            return

        for signal in signals_to_process:
            ticker = signal['ticker']

            price = signal.get('close_price')
            atr = signal.get('atr')
            if not price or not atr:
                print(f"⚠️ {ticker}: segnale senza price/ATR, salto")
                continue

            # Calcola rendimento atteso con quantity fissa (da ottimizzare con position sizing)
            quantity = 10  # Esempio
            returns = calculate_expected_return(price, signal['confidence_score'], atr, costs, quantity)

            # Filtro: approva solo se rendimento netto > 0.5%
            threshold_net = 0.005
            filter_passed = returns['expected_net_return'] > threshold_net

            filtered_action = signal['action'] if filter_passed else 'HOLD'
            filter_reason = None if filter_passed else f"Rendimento netto {returns['expected_net_return']:.2%} < soglia {threshold_net:.2%}"

            # (v3.2) Controllo di concentrazione settoriale
            if filter_passed and filtered_action == 'BUY':
                sector = SECTOR_MAP.get(ticker)
                sector_ok, sector_count = check_sector_concentration(
                    ticker, sector, SECTOR_EXPOSURE_LOOKBACK_DAYS, MAX_POSITIONS_PER_SECTOR
                )
                if not sector_ok:
                    filter_passed = False
                    filtered_action = 'HOLD'
                    # (v3.5 fix: mancava l'interpolazione di sector_count nell'f-string)
                    filter_reason = f"Concentrazione settoriale: già {sector_count} posizioni approvate in '{sector}' negli ultimi {SECTOR_EXPOSURE_LOOKBACK_DAYS} giorni (max {MAX_POSITIONS_PER_SECTOR})"

            # Position sizing suggerito (max 2% del capitale a rischio)
            capital = 10000  # Da configurare
            max_risk_per_trade = capital * 0.02
            position_size = max_risk_per_trade / (atr * 2) if atr > 0 else 0

            # Scrivi in signals_filtered
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
                'position_size_suggested': position_size
            }).execute()

            status = "✅ APPROVATO" if filter_passed else f"❌ DECLASSATO ({filter_reason})"
            print(f"{ticker}: {signal['action']} → {filtered_action} {status}")

    except Exception as e:
        print(f"❌ Errore filtro costi: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', choices=['ALL', 'USA', 'EU'], default='ALL')
    args = parser.parse_args()

    from config import TICKERS_USA, TICKERS_EU
    tickers_filter = {'ALL': None, 'USA': TICKERS_USA, 'EU': TICKERS_EU}[args.market]

    print(f"🚀 Modulo E - Cost Filter ({args.market}): {datetime.now(timezone.utc).isoformat()}")
    filter_signals(tickers_filter=tickers_filter)
