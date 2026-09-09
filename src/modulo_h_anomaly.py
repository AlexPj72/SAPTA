"""
Modulo H: Anomaly Detection
Releve anomalie di volume e prezzo.
"""
import yfinance as yf
from datetime import datetime, timedelta, timezone
from config import supabase, TICKERS, VOLUME_ANOMALY_THRESHOLD, PRICE_ANOMALY_THRESHOLD

def detect_anomalies(tickers):
    for ticker in tickers:
        try:
            df = yf.download(ticker, period="25d", interval="1d", progress=False)
            if df.empty or len(df) < 21:
                continue
            today = df.iloc[-1]
            historical = df.iloc[:-1]
            avg_volume = historical['Volume'].mean()
            current_volume = today['Volume']
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            prev_close = df.iloc[-2]['Close']
            current_close = today['Close']
            price_change_pct = (current_close - prev_close) / prev_close
            is_volume_anomaly = volume_ratio > VOLUME_ANOMALY_THRESHOLD
            is_price_anomaly = abs(price_change_pct) > PRICE_ANOMALY_THRESHOLD
            if not is_volume_anomaly and not is_price_anomaly:
                continue
            has_news = False
            try:
                threshold_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
                news_check = (supabase.table('news')
                              .select('id')
                              .contains('related_tickers', [ticker])
                              .gte('timestamp', threshold_time)
                              .limit(1)
                              .execute())
                has_news = len(news_check.data) > 0 if news_check.data else False
            except Exception:
                pass
            if is_volume_anomaly and is_price_anomaly:
                confidence = 0.9
            elif is_volume_anomaly:
                confidence = 0.7
            else:
                confidence = 0.6
            if has_news:
                confidence = min(1.0, confidence + 0.1)
            supabase.table('anomalies').insert({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'ticker': ticker,
                'volume_ratio': round(volume_ratio, 2),
                'price_change_percent': round(price_change_pct * 100,  2),
                'has_related_news': has_news,
                'confidence_score': confidence
            }).execute()
            flags = []
            if is_volume_anomaly:
                flags.append(f"Volume {volume_ratio:.1f}x")
            if is_price_anomaly:
                flags.append(f"Prezzo {price_change_pct:.1%}")
            news_flag = " 🐬" if has_news else ""
            print(f"➡ ANOMALIA {ticker}: {', '.join(flags)}{news_flag} (conf={confidence:.2f})")
        except Exception as e:
            print(f"✠ Errore anomaly scan {ticker}: {e}")

if __name__ == "__main__":
    print(f"🚠 Modulo H - Anomaly Detection: {datetime.now(timezone.utc).isoformat()}")
    detect_anomalies(TICKERS)
