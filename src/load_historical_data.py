"""
Caricamento storico daily per backtest (Sezione 21 spec v5.1.1).

Due modalità, selezionate con --scope:
  --scope=base     -> 2 anni di barre giornaliere su TUTTO l'universo (~136 ticker)
  --scope=extended -> storico esteso su un sottoinsieme di 18 ticker rappresentativi,
                       con data di inizio fissa (non un "periodo relativo") per
                       garantire la copertura reale di marzo 2020 e del bear market 2022 -
                       "5-6 anni" nella spec è indicativo, l'obiettivo vero è la copertura
                       di quegli eventi specifici, non un numero di anni esatto.

Non fa parte del ciclo schedulato (fast/slow/us_close): è un caricamento one-off,
lanciato manualmente via workflow_dispatch quando serve (prima esecuzione, o per
ricaricare dopo una pulizia).

Nota importante: questo script NON esegue i controlli di qualità dato completi del
Modulo A (Sezione 4.2 - split/dividendo/halt). Scrive con data_quality_flag='ok' di
default per tutte le barre storiche: è una scelta esplicita per non bloccare il
caricamento iniziale, ma va tenuto presente nel backtest - un'anomalia di prezzo in
questo storico potrebbe essere un artefatto (split non rettificato) non ancora
filtrato. Da rivedere se il backtest mostra risultati sospetti concentrati su
date specifiche.
"""
import sys
import time
import argparse
from datetime import datetime, timezone
import yfinance as yf
from config import supabase
from universe import UNIVERSE_FULL

# Sottoinsieme per lo stress test (Sezione 21/22): 18 ticker, mix di fasce di
# liquidità e settori diversi, scelto verificando ticker_sectors in questa sessione.
# Include l'unico ticker LIQ_LOW disponibile nell'universo (AVIO.MI).
STRESS_TEST_SUBSET = [
    # LIQ_HIGH - USA, settori diversi
    "AAPL",     # Technology
    "JPM",      # Financial Services
    "XOM",      # Energy
    "JNJ",      # Healthcare
    "CAT",      # Industrials
    "KO",       # Consumer Defensive
    "AMZN",     # Consumer Cyclical
    "NEE",      # Utilities
    "META",     # Communication Services
    # LIQ_HIGH - IT
    "ENI.MI",   # Energy
    "ISP.MI",   # Financial Services
    "ENEL.MI",  # Utilities
    # LIQ_MEDIUM - IT, settori diversi
    "SRG.MI",   # Utilities
    "CPR.MI",   # Consumer Defensive
    "IP.MI",    # Industrials
    "AMP.MI",   # Healthcare
    "SOL.MI",   # Basic Materials
    # LIQ_LOW - unico disponibile nell'universo
    "AVIO.MI",  # Industrials
]

# Data di inizio fissa per lo storico esteso: garantisce la copertura di marzo 2020
# (crash COVID) con margine, e del bear market 2022. Non un "period=6y" relativo,
# che con la data odierna mancherebe marzo 2020 per alcuni mesi.
EXTENDED_START_DATE = "2019-06-01"

BATCH_SIZE = 20  # ticker per chiamata yf.download, per non fare un'unica richiesta enorme


def fetch_and_write(tickers, period=None, start=None, label=""):
    written_total = 0
    failed = []

    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        print(f"[{label}] Batch {i // BATCH_SIZE + 1}: {batch}")
        try:
            if period:
                df = yf.download(batch, period=period, interval="1d",
                                  group_by='ticker', progress=False, auto_adjust=True)
            else:
                df = yf.download(batch, start=start, interval="1d",
                                  group_by='ticker', progress=False, auto_adjust=True)
        except Exception as e:
            print(f"❌ Errore download batch {batch}: {e}")
            failed.extend(batch)
            time.sleep(2)
            continue

        for ticker in batch:
            try:
                if len(batch) == 1:
                    ticker_df = df.dropna()
                else:
                    ticker_df = df[ticker].dropna() if ticker in df.columns.get_level_values(0) else None

                if ticker_df is None or ticker_df.empty:
                    print(f"⚠️ {ticker}: nessun dato restituito")
                    failed.append(ticker)
                    continue

                records = []
                for idx, row in ticker_df.iterrows():
                    records.append({
                        'ticker': ticker,
                        'timestamp': idx.tz_localize('UTC').isoformat() if idx.tzinfo is None else idx.isoformat(),
                        'interval': '1d',
                        'open': float(row['Open']),
                        'high': float(row['High']),
                        'low': float(row['Low']),
                        'close': float(row['Close']),
                        'volume': int(row['Volume']) if not (row['Volume'] != row['Volume']) else 0,
                        'source': 'yfinance',
                        'reliability_score': 1.0,
                        'data_quality_flag': 'ok'
                    })

                # Upsert a chunk per volta per non superare limiti di payload
                for j in range(0, len(records), 500):
                    chunk = records[j:j + 500]
                    supabase.table('prezzi').upsert(
                        chunk, on_conflict='ticker,interval,timestamp,source'
                    ).execute()

                written_total += len(records)
                print(f"✅ {ticker}: {len(records)} barre scritte")

            except Exception as e:
                print(f"❌ Errore processing {ticker}: {e}")
                failed.append(ticker)

        time.sleep(1)  # piccola pausa tra batch, cortesia verso yfinance

    return written_total, failed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', choices=['base', 'extended'], required=True)
    args = parser.parse_args()

    print(f"🚀 Caricamento storico ({args.scope}): {datetime.now(timezone.utc).isoformat()}")

    if args.scope == 'base':
        total, failed = fetch_and_write(UNIVERSE_FULL, period="2y", label="base-2y")
    else:
        total, failed = fetch_and_write(STRESS_TEST_SUBSET, start=EXTENDED_START_DATE, label="extended")

    print(f"\n📊 Totale barre scritte: {total}")
    if failed:
        print(f"⚠️ Ticker falliti ({len(failed)}): {failed}")
        sys.exit(1)  # fa fallire il workflow visibilmente se qualcosa non è andato
