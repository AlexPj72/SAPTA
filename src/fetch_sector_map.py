"""
src/fetch_sector_map.py (v5.1.1 — corretto su universe.py reale)
Popola la tabella ticker_sectors: settore e industria via yfinance.Ticker.info
per ogni ticker di UNIVERSE_FULL. La fascia di liquidità NON viene calcolata
qui: è già curata a mano in universe.py (get_liquidity_bucket), questo script
si limita a riportarla nella tabella per comodità di query lato H2/E.

Esecuzione: on-demand (workflow_dispatch manuale), non fa parte dei workflow
GitHub Actions schedulati (manutenzione periodica, non ciclo di mercato).
"""
import time
from datetime import datetime, timezone
import yfinance as yf
from config import supabase
from universe import get_universe_metadata

SLEEP_BETWEEN_CALLS = 0.5  # secondi, per non stressare l'endpoint yfinance


def fetch_sector_industry(ticker):
    """Recupera solo settore e industria da yfinance. La liquidità arriva da universe.py."""
    try:
        info = yf.Ticker(ticker).info
        return info.get('sector'), info.get('industry')
    except Exception as e:
        print(f"⚠️ Errore recupero settore per {ticker}: {e}")
        return None, None


def write_to_supabase(record):
    try:
        supabase.table('ticker_sectors').upsert(record, on_conflict='ticker').execute()
        return True
    except Exception as e:
        print(f"❌ Errore scrittura Supabase per {record['ticker']}: {e}")
        return False


def main():
    metadata = get_universe_metadata()  # {ticker: {"market": ..., "liquidity_bucket": ...}}
    tickers = list(metadata.keys())

    print(f"🚀 Popolamento ticker_sectors: {datetime.now(timezone.utc).isoformat()}")
    print(f"   Universo: {len(tickers)} ticker (fonte: universe.py)\n")

    counts = {'LIQ_HIGH': 0, 'LIQ_MEDIUM': 0, 'LIQ_LOW': 0}
    errors = []

    for i, ticker in enumerate(tickers, 1):
        sector, industry = fetch_sector_industry(ticker)
        liquidity_bucket = metadata[ticker]['liquidity_bucket']  # già nota, non calcolata

        record = {
            'ticker': ticker,
            'sector': sector,
            'industry': industry,
            'liquidity_bucket': liquidity_bucket,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }

        ok = write_to_supabase(record)
        counts[liquidity_bucket] = counts.get(liquidity_bucket, 0) + 1

        status = "✅" if ok else "❌"
        print(f"{status} [{i}/{len(tickers)}] {ticker}: settore={sector}, "
              f"liquidità={liquidity_bucket} ({metadata[ticker]['market']})")

        if not ok:
            errors.append(ticker)

        time.sleep(SLEEP_BETWEEN_CALLS)

    print("\n" + "=" * 50)
    print("📊 Riepilogo fasce di liquidità (da universe.py, non ricalcolate):")
    for bucket, count in counts.items():
        print(f"   {bucket}: {count}")

    if errors:
        print(f"\n⚠️ {len(errors)} ticker con errori di scrittura: {', '.join(errors)}")
        print("   Rilancia lo script: l'upsert è idempotente, non duplica righe.")

    print("\n✅ Completato. Verifica su Supabase: SELECT * FROM ticker_sectors ORDER BY sector;")


if __name__ == "__main__":
    main()
