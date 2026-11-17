"""
Modulo A: Data Ingestion Engine (barre 15m, yfinance)

[PASSO 1 - audit 14/11/2026]
- Scrive TUTTE le barre chiuse del periodo scaricato (A_PERIOD, default 2d), non solo l'ultima: un run saltato
  non lascia piu' buchi, perche' il run successivo ricopre le barre mancanti.
- Solo barre chiuse da almeno 60 s e dentro la negoziazione continua (calendario in market_calendar.py).
- Upsert idempotente (ignore_duplicates): una barra gia' presente non viene toccata, quindi il flag di qualita'
  assegnato all'inserimento non viene mai sovrascritto.
- Flag: ok / zero_volume / feed_error (qualita' intrinseca) e stale (acquisita con ritardo > soglia, solo in modalita'
  live). La freschezza "in lettura" e' in bar_freshness.py.
- Barre a volume zero: conservate e marcate, mai scartate.
- Il confronto con la quotazione corrente Finnhub e' stato RIMOSSO (non omogeneo con una barra chiusa); reliability_score
  non viene piu' scritto (vale il default della colonna).
- Esito di processo: exit code 1 se un download o una scrittura falliscono. Niente falsi successi.

Logica pura in bar_ingestion_core.py (testata in tests/).
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import yfinance as yf

from bar_ingestion_core import (BAR_MINUTES, SETTLE_MINUTES, build_records, coverage, frame_rows, new_counters)
from config import supabase
from universe import get_universe

TICKERS = get_universe()

# Indici di riferimento (contesto di mercato per AI Watch). Fuori da TICKERS: non entrano in H1/H2.
INDEX_TICKERS = ['^GSPC', 'FTSEMIB.MI']  # S&P 500 (USA), FTSE MIB (Italia)

A_PERIOD = os.environ.get('A_PERIOD', '2d')
A_MODE = os.environ.get('A_MODE', '')  # '' = automatico (live se periodo <= 5 giorni), 'live', 'backfill' oppure 'repair'
DOWNLOAD_BATCH = int(os.environ.get('A_DOWNLOAD_BATCH', '25'))
DOWNLOAD_SLEEP = float(os.environ.get('A_DOWNLOAD_SLEEP', '1.0'))
WRITE_CHUNK = int(os.environ.get('A_WRITE_CHUNK', '500'))
ON_CONFLICT = 'ticker,interval,timestamp,source'


def period_days(period):
    p = period.strip().lower()
    if p.endswith('d'):
        return int(p[:-1])
    if p.endswith('wk'):
        return int(p[:-2]) * 7
    if p.endswith('mo'):
        return int(p[:-2]) * 30
    return 999


def is_live_mode(period=A_PERIOD, mode=A_MODE):
    if mode in ('live', 'backfill', 'repair'):
        return mode == 'live'
    return period_days(period) <= 5


def download_batch(batch, period):
    return yf.download(batch, period=period, interval='15m', group_by='ticker', auto_adjust=True,
                       progress=False, threads=False)


def write_records(client, records, counters, chunk=WRITE_CHUNK):
    """Upsert idempotente a blocchi. Con ignore_duplicates Supabase restituisce solo le righe INSERITE."""
    for i in range(0, len(records), chunk):
        part = records[i:i + chunk]
        try:
            resp = (client.table('prezzi')
                    .upsert(part, on_conflict=ON_CONFLICT, ignore_duplicates=True)
                    .execute())
            inserted = len(resp.data or [])
            counters['inserite'] += inserted
            counters['duplicate'] += len(part) - inserted
        except Exception as e:
            counters['errori_scrittura'] += 1
            print(f"❌ Errore scrittura prezzi (blocco {i // chunk + 1}, {len(part)} righe): {e}")


def fetch_provisional_keys(client, since, now):
    """Chiavi (ticker, timestamp) delle barre EU scritte PRIMA che il dato fosse assestato: acquisite meno di SETTLE_MINUTES dopo la
    loro chiusura. Sono provvisorie per definizione e possono essere aggiornate dalla modalita' 'repair' (e solo quelle)."""
    keys, offset = set(), 0
    while True:
        page = (client.table('prezzi').select('ticker,timestamp,created_at').eq('interval', '15m').like('ticker', '%.MI')
                .gte('timestamp', since.isoformat()).order('timestamp').range(offset, offset + 999).execute().data or [])
        for r in page:
            start = datetime.fromisoformat(r['timestamp']).astimezone(timezone.utc)
            created = datetime.fromisoformat(r['created_at']).astimezone(timezone.utc)
            if created - (start + timedelta(minutes=BAR_MINUTES)) < timedelta(minutes=SETTLE_MINUTES['EU']):
                keys.add((r['ticker'], start.isoformat()))
        if len(page) < 1000:
            return keys
        offset += 1000


def write_repairs(client, records, counters, provisional, chunk=WRITE_CHUNK):
    """[Modalita' repair] Aggiorna SOLO le barre provvisorie (vedi fetch_provisional_keys) con i valori ora assestati."""
    todo = [r for r in records if (r['ticker'], r['timestamp']) in provisional]
    for i in range(0, len(todo), chunk):
        part = todo[i:i + chunk]
        try:
            client.table('prezzi').upsert(part, on_conflict=ON_CONFLICT).execute()
            counters['riparate'] += len(part)
        except Exception as e:
            counters['errori_scrittura'] += 1
            print(f"❌ Errore riparazione prezzi (blocco {i // chunk + 1}, {len(part)} righe): {e}")


def run(client=None, downloader=download_batch, now=None, period=A_PERIOD, mode=A_MODE, tickers=None, sleep=DOWNLOAD_SLEEP, provisional=None):
    client = client or supabase
    now = now or datetime.now(timezone.utc)
    live = is_live_mode(period, mode)
    symbols = list(tickers) if tickers is not None else list(TICKERS) + INDEX_TICKERS
    counters = new_counters()
    by_ticker = {}
    repair = mode == 'repair'
    if repair and provisional is None:
        provisional = fetch_provisional_keys(client, now - timedelta(days=period_days(period)), now)
        print(f"🔧 Repair: {len(provisional)} barre EU provvisorie da riallineare")
    print(f"📥 Modulo A — {len(symbols)} simboli, periodo {period}, modalità {'repair' if repair else 'live' if live else 'backfill'}, "
          f"ora {now.isoformat()}")

    for i in range(0, len(symbols), DOWNLOAD_BATCH):
        batch = symbols[i:i + DOWNLOAD_BATCH]
        try:
            df = downloader(batch, period)
        except Exception as e:
            counters['errori_download'] += 1
            print(f"❌ Errore download batch {i // DOWNLOAD_BATCH + 1} ({batch[0]}…{batch[-1]}): {e}")
            continue
        for t in batch:
            rows = frame_rows(df, t)
            if not rows:
                counters['ticker_senza_dati'] += 1
                continue
            recs = build_records(t, rows, now, live, counters)
            by_ticker[t] = recs
            if repair:
                write_repairs(client, recs, counters, provisional)
            else:
                write_records(client, recs, counters)
        if i + DOWNLOAD_BATCH < len(symbols) and sleep:
            time.sleep(sleep)

    cov = coverage(by_ticker, now - timedelta(days=period_days(period)), now) if by_ticker else {}
    summary = dict(counters, modalita='repair' if repair else 'live' if live else 'backfill', periodo=period, **{f'cov_{k}': v for k, v in cov.items()})
    print('A_SUMMARY ' + json.dumps(summary, ensure_ascii=False))
    gh = os.environ.get('GITHUB_STEP_SUMMARY')
    if gh:
        try:
            with open(gh, 'a', encoding='utf-8') as fh:
                fh.write('### Modulo A\n' + '\n'.join(f'- {k}: {v}' for k, v in summary.items()) + '\n')
        except OSError:
            pass
    return summary


def exit_code(summary):
    """0 = tutto ok; 1 = almeno un errore di download o di scrittura."""
    return 1 if (summary['errori_download'] or summary['errori_scrittura']) else 0


if __name__ == '__main__':
    sys.exit(exit_code(run()))
