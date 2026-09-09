"""
Modulo H: Momentum & Volume Anomaly Scanner (v3.3 — intraday reale)
Legge i dati a 15 minuti già raccolti dal Modulo A nella tabella 'prezzi',
invece di riscaricare dati giornalieri in modo indipendente: solo così
il ciclo a 15 minuti ha un vantaggio reale di tempestività.
"""
from datetime import datetime, timedelta, timezone
from config import supabase, TICKERS, VOLUME_ANOMALY_THRESHOLD, PRICE_ANOMALY_THRESHOLD

BARS_LOOKBACK = 20          # ~5 ore di storico intraday a 15 min (20 x 15min)
MIN_BARS_FOR_BASELINE = 8   # almeno ~2 ore di dati raccolti oggi prima di valutare un'anomalia


def get_recent_bars(ticker, limit=BARS_LOOKBACK):
    """Legge le ultime N barre a 15 minuti dalla tabella 'prezzi' (scritte dal Modulo A)."""
    try:
        response = (supabase.table('prezzi')
                    .select('timestamp, close, volume')
                    .eq('ticker', ticker)
                    .order('timestamp', desc=True)
                    .limit(limit)
                    .execute())
        # Supabase le restituisce dalla più recente: le rimetto in ordine cronologico
        return list(reversed(response.data)) if response.data else []
    except Exception as e:
        print(f"⚠️ Errore lettura prezzi intraday per {ticker}: {e}")
        return []


def check_related_news(ticker):
    """Controlla se ci sono news recenti per il ticker (ultime 24h)."""
    try:
        threshold = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        response = (supabase.table('news')
                    .select('id')
                    .contains('related_tickers', [ticker])
                    .gte('timestamp', threshold)
                    .execute())
        return len(response.data) > 0
    except Exception as e:
        print(f"⚠️ Errore check news per {ticker}: {e}")
        return False


def scan_anomalies():
    """Scansiona ticker per anomalie volume/prezzo usando i dati intraday già raccolti oggi."""
    for ticker in TICKERS:
        bars = get_recent_bars(ticker)
        if len(bars) < MIN_BARS_FOR_BASELINE:
            # Non abbastanza storico intraday raccolto oggi (es. mercato appena aperto,
            # oppure ticker con dati mancanti) — si salta, non si stima "a occhio"
            continue

        *baseline_bars, current_bar = bars
        try:
            current_volume = float(current_bar['volume'] or 0)
            current_close = float(current_bar['close'])
            baseline_volumes = [float(b['volume'] or 0) for b in baseline_bars]
            avg_volume = sum(baseline_volumes) / len(baseline_volumes) if baseline_volumes else 0
            if avg_volume == 0:
                continue

            volume_ratio = current_volume / avg_volume

            # Variazione prezzo rispetto all'inizio della finestra di riferimento (non al giorno prima)
            reference_close = float(baseline_bars[0]['close'])
            price_change = (current_close - reference_close) / reference_close

            if volume_ratio >= VOLUME_ANOMALY_THRESHOLD and abs(price_change) >= PRICE_ANOMALY_THRESHOLD:
                print(f"🚨 ANOMALIA INTRADAY {ticker}: volume {volume_ratio:.1f}x, prezzo {price_change:.2%}")

                has_news = check_related_news(ticker)
                confidence = 0.8 if has_news else 0.5

                supabase.table('anomalies').insert({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'ticker': ticker,
                    'volume_ratio': volume_ratio,
                    'price_change_percent': price_change * 100,
                    'has_related_news': has_news,
                    'confidence_score': confidence
                }).execute()
        except Exception as e:
            print(f"❌ Errore scan {ticker}: {e}")


if __name__ == "__main__":
    print(f"🚀 Modulo H - Anomaly Scanner: {datetime.now(timezone.utc).isoformat()}")
    scan_anomalies()
