"""
Modulo A: Data Ingestion Engine (multi-fonte)
Scarica prezzi da yfinance + Finnhub, riconcilia, scrive in Supabase.

[MODIFICA v5.1 - STEP 3]
- FIX URGENTE: 'interval' è ora NOT NULL su Supabase (migrazione STEP 2).
  Ogni record scritto DEVE includere 'interval', altrimenti l'upsert fallisce.
- L'universo dei ticker non arriva più da config.TICKERS ma da
  src/universe.py (UNIVERSE_FULL), come previsto dalla Sezione 6 della spec.
- Aggiunto un controllo leggero di qualità dato (Sezione 4.2): non sostituisce
  un vero controllo su split/dividendi/halt (da implementare più avanti),
  ma intercetta i due casi più semplici ed economici da rilevare qui:
  dato "stale" (più vecchio di quanto atteso per un ciclo a 15 minuti) e
  volume a zero (possibile halt o dato mancante).
"""
import os
import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from config import supabase, FINNHUB_KEY, PRICE_DIVERGENCE_THRESHOLD
from universe import get_universe

# [MODIFICA v5.1] L'universo non è più config.TICKERS ma quello curato e
# versionato in universe.py (stessa cartella di questo file ed eseguito
# con lo stesso working directory di config.py).
TICKERS = get_universe()

# [NUOVO 19/09 - Punto 4 filtro mercato] Indici di riferimento per il
# contesto di mercato generale (usati da modulo_ai_watch.py per capire se
# un titolo si muove CON o CONTRO il mercato/piazza di appartenenza).
# Scritti in 'prezzi' come ticker normali, ma NON fanno parte di TICKERS
# quindi non entrano mai nello screening H1/H2 (get_universe() non li
# include). Simboli standard Yahoo Finance - da verificare al primo run
# reale nei log (se uno dei due risulta vuoto, il simbolo va corretto).
INDEX_TICKERS = ['^GSPC', 'FTSEMIB.MI']  # S&P 500 (USA), FTSE MIB (Italia)

# [NUOVO v5.1] Soglia oltre la quale un dato viene marcato 'stale'.
# Il ciclo di ingestion gira ogni 15 minuti: un dato con timestamp più
# vecchio di questa soglia indica probabilmente un problema a monte
# (mercato chiuso, feed in ritardo, ticker illiquido senza scambi recenti).
STALE_THRESHOLD_MINUTES = 30


def fetch_yfinance(tickers):
    """Fonte primaria: yfinance (Yahoo Finance)"""
    try:
        df = yf.download(tickers, period=os.getenv("A_PERIOD", "2d"), interval="15m", group_by='ticker', auto_adjust=True, progress=False)
        return df
    except Exception as e:
        print(f"❌ Errore yfinance: {e}")
        return None


def fetch_finnhub(tickers, api_key):
    """Fonte secondaria: Finnhub (solo USA, cross-check)"""
    if not api_key:
        return {}

    prices = {}
    for ticker in tickers:
        if not ticker.endswith('.MI'):  # Finnhub copre solo USA
            try:
                url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={api_key}"
                r = requests.get(url, timeout=5)
                data = r.json()
                if 'c' in data and data['c'] > 0:
                    prices[ticker] = {
                        'close': data['c'],
                        'high': data['h'],
                        'low': data['l'],
                        'open': data['o'],
                        'timestamp': datetime.fromtimestamp(data['t'])
                    }
            except Exception as e:
                print(f"⚠️ Errore Finnhub per {ticker}: {e}")
    return prices


def assess_data_quality(yf_timestamp, volume):
    """
    [NUOVO v5.1] Controllo leggero di qualità dato, eseguito in A prima
    della scrittura, come richiesto dalla Sezione 4.2 della spec.

    Ritorna una stringa: 'ok', 'stale' o 'zero_volume'.
    Non è un sostituto del controllo completo su split/dividendi/halt
    (quello resta da progettare separatamente), ma evita che H/B lavorino
    su dati palesemente inaffidabili senza che nessuno l'abbia segnalato.
    """
    now_utc = datetime.now(timezone.utc)
    ts = yf_timestamp
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    age_minutes = (now_utc - ts).total_seconds() / 60
    if age_minutes > STALE_THRESHOLD_MINUTES:
        return 'stale'

    if volume == 0:
        return 'zero_volume'

    return 'ok'


def reconcile_prices(yf_data, fh_data, tickers):
    """Riconcilia prezzi tra fonti. Se divergono troppo, marca come incerto."""
    records = []

    for ticker in tickers:
        try:
            # Dati yfinance
            if isinstance(yf_data.columns, pd.MultiIndex):
                ticker_df = yf_data[ticker].dropna()
            else:
                ticker_df = yf_data.dropna()

            if ticker_df.empty:
                continue

            last_row = ticker_df.iloc[-1]
            yf_close = float(last_row['Close'])
            yf_timestamp = last_row.name.to_pydatetime()
            yf_volume = int(last_row['Volume'])

            # Cross-check con Finnhub (solo se disponibile)
            reliability = 1.0
            if ticker in fh_data:
                fh_close = fh_data[ticker]['close']
                divergence = abs(yf_close - fh_close) / yf_close

                if divergence > PRICE_DIVERGENCE_THRESHOLD:
                    print(f"⚠️ Divergenza {ticker}: yf={yf_close:.2f} vs fh={fh_close:.2f} ({divergence:.2%})")
                    reliability = 0.5  # Dato incerto
                else:
                    reliability = 1.0  # Fonti concordano

            # [NUOVO v5.1] Flag di qualità dato, calcolato qui e propagato
            # nel record, non lasciato implicito per i moduli a valle.
            quality_flag = assess_data_quality(yf_timestamp, yf_volume)
            if quality_flag != 'ok':
                print(f"⚠️ Qualità dato {ticker}: flag='{quality_flag}'")

            records.append({
                'ticker': ticker,
                'timestamp': yf_timestamp.isoformat(),
                'interval': '15m',  # [FIX v5.1] obbligatorio: colonna NOT NULL
                'open': float(last_row['Open']),
                'high': float(last_row['High']),
                'low': float(last_row['Low']),
                'close': yf_close,
                'volume': yf_volume,
                'source': 'yfinance',
                'reliability_score': reliability,
                'data_quality_flag': quality_flag,
            })
        except Exception as e:
            print(f"❌ Errore processing {ticker}: {e}")

    return records


def write_to_supabase(records):
    """Scrive i prezzi in Supabase (upsert)"""
    if not records:
        print("⚠️ Nessun dato da scrivere")
        return

    try:
        # [MODIFICA v5.1] on_conflict include ora anche 'interval': la
        # tabella ospiterà in futuro anche lo storico giornaliero
        # (interval='1d', STEP 10) sugli stessi ticker/source, quindi la
        # combinazione univoca deve distinguere i due intervalli.
        # NB: verificare che esista davvero un unique constraint Supabase
        # su (ticker, interval, timestamp, source) prima di questo deploy:
        # se il constraint attuale è ancora (ticker, timestamp, source),
        # questa chiamata fallisce. In tal caso va aggiornato il constraint
        # su Supabase, non solo questa riga di codice.
        response = supabase.table('prezzi').upsert(
            records,
            on_conflict='ticker,interval,timestamp,source'
        ).execute()

        print(f"✅ Scritti {len(records)} record in Supabase")
    except Exception as e:
        print(f"❌ Errore scrittura Supabase: {e}")


if __name__ == "__main__":
    print(f"🚀 Modulo A - Ingestion: {datetime.now(timezone.utc).isoformat()}")
    print(f"📋 Universo: {len(TICKERS)} titoli (src/universe.py)")

    yf_data = fetch_yfinance(TICKERS)
    fh_data = fetch_finnhub(TICKERS, FINNHUB_KEY)

    records = reconcile_prices(yf_data, fh_data, TICKERS)
    write_to_supabase(records)

    # [NUOVO 19/09] Indici di mercato - stessa pipeline, nessun cross-check
    # Finnhub (non li copre), fail-open: se un simbolo non risponde, gli
    # altri ticker dell'universo non ne risentono (già scritti sopra).
    print(f"📈 Indici di contesto: {INDEX_TICKERS}")
    try:
        index_yf_data = fetch_yfinance(INDEX_TICKERS)
        index_records = reconcile_prices(index_yf_data, {}, INDEX_TICKERS)
        write_to_supabase(index_records)
    except Exception as e:
        print(f"⚠️ Errore ingestion indici di mercato (non bloccante): {e}")
