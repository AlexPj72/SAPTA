"""
Market Context (NUOVO 19/09 - Punto 4): contesto di mercato e di settore

Risponde all'osservazione dell'utente (via analisi ChatGPT su NFLX/VZ e
sulla giornata mista del 18/09: S&P500 +0.17%, Nasdaq +0.40%, Dow -0.18%):
un movimento va giudicato anche rispetto a COSA STA FACENDO IL MERCATO
GENERALE e IL SETTORE, non solo guardando il singolo titolo isolato.

Due funzioni, entrambe fail-open (nessun dato disponibile = None, mai
un'eccezione che blocca il chiamante):
- get_market_direction(): variazione giornaliera di S&P 500 e FTSE MIB
  (ticker '^GSPC'/'FTSEMIB.MI', scritti da modulo_a_ingestion.py insieme
  al resto dell'universo, ma NON ne fanno parte - vedi INDEX_TICKERS lì).
- get_sector_strength(sector, tickers_by_sector, changes_by_ticker):
  media della variazione odierna di tutti i titoli dello stesso settore
  GIA' presenti nei dati che il chiamante ha sotto mano - non serve una
  fonte dati nuova per questa parte, si ricalcola da quanto già scaricato.
"""
from config import supabase


def get_market_direction():
    """Ultima variazione giornaliera disponibile per S&P 500 e FTSE MIB.
    Ritorna un dict {'usa': pct|None, 'italia': pct|None}."""
    result = {'usa': None, 'italia': None}
    index_map = {'^GSPC': 'usa', 'FTSEMIB.MI': 'italia'}
    for ticker, key in index_map.items():
        try:
            rows = (supabase.table('prezzi')
                    .select('close,timestamp')
                    .eq('ticker', ticker)
                    .eq('interval', '15m')
                    .order('timestamp', desc=True)
                    .limit(40)  # ~1 giorno di barre 15m, sufficiente per il confronto
                    .execute())
            data = rows.data or []
            if len(data) < 2:
                continue
            last_date = data[0]['timestamp'][:10]
            same_day = [d for d in data if d['timestamp'][:10] == last_date]
            if len(same_day) < 2:
                continue
            latest = float(same_day[0]['close'])
            first_of_day = float(same_day[-1]['close'])
            result[key] = round((latest / first_of_day - 1) * 100, 2)
        except Exception as e:
            print(f"⚠️ Errore lettura indice {ticker} (contesto di mercato): {e}")
    return result


def market_direction_label(pct):
    if pct is None:
        return "dato non disponibile"
    if pct > 0.15:
        return f"in rialzo (+{pct}%)"
    if pct < -0.15:
        return f"in ribasso ({pct}%)"
    return f"sostanzialmente piatto ({pct}%)"


def get_sector_strength(sector, ticker, metrics_list):
    """Media della variazione odierna (price_change_pct) degli ALTRI ticker
    dello stesso settore presenti in metrics_list (stessa lista già
    calcolata dal chiamante, es. get_universe_metrics() di
    modulo_ai_watch.py) - nessuna query aggiuntiva, nessuna fonte dati
    nuova. Esclude esplicitamente `ticker` dalla media, per confrontarlo
    con gli altri e non (in parte) con sé stesso."""
    peers = [m for m in metrics_list if m.get('sector') == sector and m.get('ticker') != ticker]
    if len(peers) < 2:
        return None
    avg = sum(m['price_change_pct'] for m in peers) / len(peers)
    return round(avg, 2)
