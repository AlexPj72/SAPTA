"""
Modulo A: Data Ingestion Engine (multi-fonte)
Scarica prezzi da yfinance + Finnhub, riconcilia, scrive in Supabase.
"""
import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from config import supabase, TICKERS, FINNHUB_KEY, PRICE_DIVERGENCE_THRESHOLD

def fetch_yfinance(tickers):
    """Fonte primaria: yfinance (Yahoo Finance)"""
    try:
        df = yf.download(tickers, period="2d", interval="15m", group_by='ticker', auto_adjust=True, progress=False)
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
            
            records.append({
                'ticker': ticker,
                'timestamp': yf_timestamp.isoformat(),
                'open': float(last_row['Open']),
                'high': float(last_row['High']),
                'low': float(last_row['Low']),
                'close': yf_close,
                'volume': int(last_row['Volume']),
                'source': 'yfinance',
                'reliability_score': reliability
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
        # Supabase upsert: inserisce o aggiorna in base alla unique constraint
        response = supabase.table('prezzi').upsert(
            records,
            on_conflict='ticker,timestamp,source'
        ).execute()
        
        print(f"✅ Scritti {len(records)} record in Supabase")
    except Exception as e:
        print(f"❌ Errore scrittura Supabase: {e}")

if __name__ == "__main__":
    print(f"🚀 Modulo A - Ingestion: {datetime.now(timezone.utc).isoformat()}")
    
    yf_data = fetch_yfinance(TICKERS)
    fh_data = fetch_finnhub(TICKERS, FINNHUB_KEY)
    
    records = reconcile_prices(yf_data, fh_data, TICKERS)
    write_to_supabase(records)
