===== requirements-fast.txt =====
yfinance==0.2.40
pandas==2.2.2
numpy==1.26.4
requests==2.32.3
supabase==2.5.1
===== requirements-slow.txt =====
yfinance==0.2.40
pandas==2.2.2
numpy==1.26.4
requests==2.32.3
supabase==2.5.1
pandas-ta==0.3.14b
scikit-learn==1.5.0
xgboost==2.0.3
===== src/config.py =====
import os
from supabase import create_client, Client

# Configurazione Supabase
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY')

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Missing Supabase credentials in environment variables")

# Client Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Configurazione API esterne
FINNHUB_KEY = os.environ.get('FINNHUB_KEY', '')
NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY', '')
HUGGINGFACE_API_KEY = os.environ.get('HUGGINGFACE_API_KEY', '')  # (v3.1) sentiment via Inference API

# Ticker da monitorare (personalizza), divisi per mercato (v3.5 — necessario per il run
# dedicato post-chiusura USA, vedi SAPTA_v3.md §1.6bis)
TICKERS_USA = ["AAPL", "MSFT", "GOOGL"]
TICKERS_EU = ["ENI.MI", "ISP.MI", "UCG.MI"]
TICKERS = TICKERS_USA + TICKERS_EU  # lista completa, usata di default (--market=ALL)

# Soglie di riconciliazione multi-fonte
PRICE_DIVERGENCE_THRESHOLD = 0.003  # 0.3%

# Soglie Modulo H (anomalie)
VOLUME_ANOMALY_THRESHOLD = 5.0  # 5x la media
PRICE_ANOMALY_THRESHOLD = 0.03  # 3%

# (v3.1) Cache news: minuti entro cui le news di un ticker vengono riusate
# invece di richiamare NewsAPI, per restare sotto il limite di 100 richieste/giorno free tier
NEWS_CACHE_MINUTES = 60

# (v3.2) Mappa settore per ticker, usata dal Modulo E per il limite di concentrazione.
# Personalizza in base alla tua watchlist reale (TICKERS sopra).
SECTOR_MAP = {
    "AAPL": "Tech",
    "MSFT": "Tech",
    "GOOGL": "Tech",
    "ENI.MI": "Energy",
    "ISP.MI": "Banks",
    "UCG.MI": "Banks",
}

# (v3.2) Limite di concentrazione settoriale nel Modulo E: numero massimo di segnali BUY
# approvati per lo stesso settore entro la finestra sotto, prima di declassare a HOLD
# per "concentrazione" anche se il singolo segnale supererebbe il filtro costo/rendimento.
MAX_POSITIONS_PER_SECTOR = 2
SECTOR_EXPOSURE_LOOKBACK_DAYS = 10  # finestra approssimativa di detenzione swing trading

# (v3.2) Protezione Pattern Day Trader — rilevante solo con broker Alpaca e capitale < $25.000.
# Placeholder di configurazione: la logica vera e propria arriva con il Modulo G (Fase 7),
# quando il sistema traccia le esecuzioni reali e può contare i day-trade effettivi.
PDT_PROTECTION_ENABLED = True
PDT_MAX_DAY_TRADES_5_DAYS = 3
PDT_ACCOUNT_THRESHOLD_USD = 25000

===== src/modulo_a_ingestion.py =====
"""
Modulo A: Data Ingestion Engine (multi-fonte)
Scarica prezzi da yfinance + Finnhub, riconcilia, scrive in Supabase.
"""
import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, timedelta
from config import supabase, TICKERS, FINNHUB_KEY, PRICE_DIVERGENCE_THRESHOLD

def fetch_yfinance(tickers):
    """Fonte primaria: yfinance (Yahoo Finance)"""
    try:
        df = yf.download(tickers, period="2d", interval="15m", group_by='ticker', progress=False)
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
    print(f"🚀 Modulo A - Ingestion: {datetime.utcnow().isoformat()}")

    yf_data = fetch_yfinance(TICKERS)
    fh_data = fetch_finnhub(TICKERS, FINNHUB_KEY)

    records = reconcile_prices(yf_data, fh_data, TICKERS)
    write_to_supabase(records)

===== src/modulo_b_analysis.py =====
"""
Modulo B: Analysis & Prediction Core
Calcola indicatori tecnici, sentiment (via HuggingFace Inference API), genera segnali.
"""

import time
from datetime import datetime, timedelta, timezone

import pandas_ta as ta
import requests
import yfinance as yf

from config import (
    HUGGINGFACE_API_KEY,
    NEWSAPI_KEY,
    NEWS_CACHE_MINUTES,
    TICKERS,
    TICKERS_EU,
    TICKERS_USA,
    supabase,
)

FINBERT_API_URL = "https://api-inference.huggingface.co/models/ProsusAI/finbert"


def get_cached_news(ticker):
    """Legge da Supabase le news già scaricate di recente per il ticker."""
    try:
        threshold = (datetime.now(timezone.utc) - timedelta(minutes=NEWS_CACHE_MINUTES)).isoformat()
        response = (
            supabase.table("news")
            .select("title, sentiment_score, timestamp")
            .contains("related_tickers", [ticker])
            .gte("timestamp", threshold)
            .execute()
        )
        return response.data or []
    except Exception as e:
        print(f"⚠️ Errore lettura cache news per {ticker}: {e}")
        return []


def fetch_news(ticker, api_key):
    """Scarica news recenti per un ticker da NewsAPI."""
    if not api_key:
        return []
    try:
        url = f"https://newsapi.org/v2/everything?q={ticker}&language=en&sortBy=publishedAt&pageSize=5&apiKey={api_key}"
        r = requests.get(url, timeout=5)
        data = r.json()
        return data.get("articles", [])
    except Exception as e:
        print(f"⚠️ Errore NewsAPI per {ticker}: {e}")
        return []


def analyze_sentiment_hf(text, max_retries=2):
    """Chiama la HuggingFace Inference API per il sentiment finanziario."""
    if not HUGGINGFACE_API_KEY or not text:
        return 0.0

    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
    payload = {"inputs": text[:512]}

    for attempt in range(max_retries + 1):
        try:
            r = requests.post(FINBERT_API_URL, headers=headers, json=payload, timeout=15)
            if r.status_code == 503:
                wait = min(r.json().get("estimated_time", 5), 20)
                print(f"   ⏳ Modello FinBERT in caricamento, attendo {wait:.0f}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            result = r.json()[0]
            best = max(result, key=lambda x: x["score"])
            label, score = best["label"].lower(), best["score"]
            if label == "positive":
                return score
            if label == "negative":
                return -score
            return 0.0
        except Exception as e:
            print(f"⚠️ Errore HF Inference API (tentativo {attempt + 1}): {e}")
            time.sleep(1)

    return 0.0


def analyze_sentiment(ticker, articles):
    """Calcola sentiment aggregato."""
    if not articles:
        return 0.0

    scores = []
    news_to_insert = []

    for article in articles:
        title = article.get("title", "")
        if not title:
            continue

        score = analyze_sentiment_hf(title)
        scores.append(score)
        news_to_insert.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "title": title,
                "source": article.get("source", {}).get("name", "NewsAPI"),
                "url": article.get("url"),
                "sentiment_score": score,
                "related_tickers": [ticker],
            }
        )

    if news_to_insert:
        try:
            supabase.table("news").insert(news_to_insert).execute()
        except Exception as e:
            print(f"⚠️ Errore scrittura news {ticker}: {e}")

    return sum(scores) / len(scores) if scores else 0.0


def get_latest_intraday_price(ticker):
    """Legge il prezzo più recente dalla tabella 'prezzi'."""
    try:
        response = (
            supabase.table("prezzi")
            .select("close")
            .eq("ticker", ticker)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        if response.data:
            return float(response.data[0]["close"])
        return None
    except Exception as e:
        print(f"⚠️ Errore lettura prezzo corrente per {ticker}: {e}")
        return None


def calculate_technical_indicators(ticker):
    """Scarica dati storici e calcola indicatori tecnici."""
    try:
        df = yf.download(ticker, period="60d", interval="1d", progress=False)
        if df.empty or len(df) < 31:
            return None

        df["RSI"] = ta.rsi(df["Close"], length=14)
        df["MACD"], df["MACD_signal"], _ = ta.macd(df["Close"])
        df["BB_upper"], df["BB_middle"], df["BB_lower"] = ta.bbands(df["Close"], length=20)
        df["ATR"] = ta.atr(df["High"], df["Low"], df["Close"], length=14)

        last_bar_date = df.index[-1].date()
        today_utc = datetime.now(timezone.utc).date()
        is_provisional = last_bar_date == today_utc
        row_for_indicators = df.iloc[-2] if is_provisional else df.iloc[-1]

        current_price = get_latest_intraday_price(ticker)
        if current_price is None:
            current_price = float(df.iloc[-1]["Close"])

        return {
            "rsi": float(row_for_indicators["RSI"]),
            "macd": float(row_for_indicators["MACD"]),
            "macd_signal": float(row_for_indicators["MACD_signal"]),
            "bb_position": (
                float(row_for_indicators["Close"]) - float(row_for_indicators["BB_lower"])
            ) / (float(row_for_indicators["BB_upper"]) - float(row_for_indicators["BB_lower"])),
            "atr": float(row_for_indicators["ATR"]),
            "close": current_price,
            "is_provisional_bar": is_provisional,
        }
    except Exception as e:
        print(f"❌ Errore indicatori {ticker}: {e}")
        return None


def generate_signal(indicators, sentiment):
    """Genera segnale BUY/SELL/HOLD + confidence + risk score."""
    if not indicators:
        return None

    score = 0

    if indicators["rsi"] < 30:
        score += 2
    elif indicators["rsi"] > 70:
        score -= 2

    if indicators["macd"] > indicators["macd_signal"]:
        score += 1
    else:
        score -= 1

    if indicators["bb_position"] < 0.2:
        score += 1
    elif indicators["bb_position"] > 0.8:
        score -= 1

    score += int(sentiment * 2)

    if score >= 2:
        action = "BUY"
        confidence = min(0.9, 0.5 + score * 0.1)
    elif score <= -2:
        action = "SELL"
        confidence = min(0.9, 0.5 + abs(score) * 0.1)
    else:
        action = "HOLD"
        confidence = 0.5

    risk_score = min(1.0, indicators["atr"] / indicators["close"] * 10) if indicators["close"] else 0.0

    return {
        "action": action,
        "confidence_score": confidence,
        "risk_score": risk_score,
        "atr": indicators["atr"],
        "close_price": indicators["close"],
        "is_provisional_bar": indicators["is_provisional_bar"],
    }


def write_signals_to_supabase(ticker, signal):
    """Scrive segnale grezzo in Supabase."""
    try:
        supabase.table("signals_raw").insert(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "ticker": ticker,
                "action": signal["action"],
                "confidence_score": signal["confidence_score"],
                "risk_score": signal["risk_score"],
                "atr": signal["atr"],
                "close_price": signal["close_price"],
                "is_provisional_bar": signal["is_provisional_bar"],
                "model_version": "v3.1_rule_based",
            }
        ).execute()
        flag = " (barra provvisoria)" if signal["is_provisional_bar"] else ""
        print(f"✅ Segnale {ticker}: {signal['action']} (conf={signal['confidence_score']:.2f}){flag}")
    except Exception as e:
        print(f"❌ Errore scrittura segnale {ticker}: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["ALL", "USA", "EU"], default="ALL")
    args = parser.parse_args()

    tickers_to_process = {"ALL": TICKERS, "USA": TICKERS_USA, "EU": TICKERS_EU}[args.market]

    print(f"🚀 Modulo B - Analysis ({args.market}): {datetime.now(timezone.utc).isoformat()}")
    for ticker in tickers_to_process:
        print(f"\n📊 Analisi {ticker}...")
        indicators = calculate_technical_indicators(ticker)
        if not indicators:
            continue

        cached = get_cached_news(ticker)
        if cached:
            sentiment = sum(n["sentiment_score"] for n in cached) / len(cached)
            print(f"   Sentiment: {sentiment:.2f} (da cache, {len(cached)} news)")
        else:
            articles = fetch_news(ticker, NEWSAPI_KEY)
            sentiment = analyze_sentiment(ticker, articles)
            print(f"   Sentiment: {sentiment:.2f} (da {len(articles)} news nuove)")

        signal = generate_signal(indicators, sentiment)
        if signal:
            write_signals_to_supabase(ticker, signal)

===== src/modulo_e_cost_filter.py =====
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

===== src/modulo_f_backtest.py =====
"""
Modulo F: Backtesting Engine
Esegue backtest on-demand della strategia su dati storici.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from config import supabase, TICKERS

def fetch_historical_data(ticker, days=180):
    try:
        threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        response = (supabase.table('prezzi')
                    .select('timestamp, open, high, low, close, volume')
                    .eq('ticker', ticker)
                    .gte('timestamp', threshold)
                    .order('timestamp', asc=True)
                    .execute())
        if not response.data:
            return None
        df = pd.DataFrame(response.data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"✠ Errore dati storici {ticker}: {e}")
        return None

def simulate_strategy(df, initial_capital=10000):
    if df is None or len(df) < 30:
        return None
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    capital = initial_capital
    position = 0
    trades = []
    for i in range(30, len(df)):
        rsi = df['rsi'].iloc[i]
        price = df['close'].iloc[i]
        if rsi < 30 and position == 0:
            shares_to_buy = int(capital / price)
            if shares_to_buy > 0:
                position = shares_to_buy
                capital -= shares_to_buy * price
                trades.append({'date': df.index[i], 'action': 'BUY', 'price': price, 'shares': shares_to_buy, 'capital': capital})
        elif rsi > 70 and position > 0:
            capital += position * price
            trades.append({'date': df.index[i], 'action': 'SELL', 'price': price, 'shares': position, 'capital': capital})
            position = 0
    final_value = capital + (position * df['close'].iloc[-1] if position > 0 else 0)
    total_return = (final_value - initial_capital) / initial_capital
    return {
        'total_return': total_return,
        'total_operations': len([t for t in trades if t['action'] == 'SELL']),
        'final_value': final_value
    }

def run_backtest(ticker, days=180, initial_capital=10000):
    print(f"\n💪 Backtest {ticker} ({days} giorni)...")
    df = fetch_historical_data(ticker, days)
    if df is None:
        print(f"➘ Nessun dato per {ticker}")
        return None
    results = simulate_strategy(df, initial_capital)
    if results is None:
        return None
    try:
        supabase.table('backtest_results').insert({
            'strategy_name': 'rule_based_rsi',
            'start_date': df.index[0].date().isoformat(),
            'end_date': df.index[-1].date().isoformat(),
            'gross_return': results['total_return'],
            'net_return': results['total_return'],
            'max_drawdown': 0.0,
            'total_operations': results['total_operations'],
            'win_rate': 0.0,
            'sharpe_ratio': 0.0
        }).execute()
        print(f"↔ Backtest {ticker}: return={results['total_return']:.2%}, ops={results['total_operations']}")
        return results
    except Exception as e:
        print(f"❤ Errore salvataggio backtest: {e}")
        return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', type=str, default=None)
    parser.add_argument('--days', type=int, default=180)
    parser.add_argument('--capital', type=float, default=10000)
    args = parser.parse_args()
    print(f"🚠 Modulo F - Backtesting: {datetime.now(timezone.utc).isoformat()}")
    tickers_to_test = [args.ticker] if args.ticker else TICKERS
    for ticker in tickers_to_test:
        run_backtest(ticker, args.days, args.capital)

===== src/modulo_h_anomaly.py =====
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

===== src/keep_alive.py =====
"""
Keep-Alive: mantiene attivo Supabase free tier.
"""
from datetime import datetime, timezone
from config import supabase

if __name__ == "__main__":
    try:
        supabase.table('costi_operazione').select('id').limit(1).execute()
        print(f"Keep-alive OK: {datetime.now(timezone.utc).isoformat()}")
    except Exception as e:
        print(f"Keep-alive fallito: {e}")

===== .github/workflows/keep_alive.yml =====
name: SAPTA Supabase Keep-Alive

on:
  schedule:
    - cron: '0 6 */3 * *'
  workflow_dispatch:

jobs:
  ping:
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Set up Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
      - name: Install minimal dependency
        run: pip install supabase==2.5.1
      - name: Ping Supabase
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: python src/keep_alive.py

===== .github/workflows/sapta_fast.yml =====
name: SAPTA Fast Pipeline (Ingestion + Anomaly Scanner)

on:
  schedule:
    # Ogni 15 minuti, 9-17 UTC, Lun-Ven
    - cron: '*/15 9-17 * * 1-5'
  workflow_dispatch:

concurrency:
  group: sapta-fast
  cancel-in-progress: true

jobs:
  ingestion-and-anomaly:
    runs-on: ubuntu-latest
    timeout-minutes: 8
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Set up Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'
          cache-dependency-path: requirements-fast.txt
      - name: Install dependencies (leggere, nessuna libreria ML)
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-fast.txt
      - name: Run Modulo A - Data Ingestion
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          FINNHUB_KEY: ${{ secrets.FINNHUB_KEY }}
        run: python src/modulo_a_ingestion.py
      - name: Run Modulo H - Anomaly Scanner
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: python src/modulo_h_anomaly.py

===== .github/workflows/sapta_slow.yml =====
name: SAPTA Slow Pipeline (Analysis + Cost Filter)

on:
  schedule:
    - cron: '0,30 9-17 * * 1-5'
  workflow_dispatch:

concurrency:
  group: sapta-slow
  cancel-in-progress: true

jobs:
  analysis-and-cost-filter:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Set up Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'
          cache-dependency-path: requirements-slow.txt
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-slow.txt
      - name: Run Modulo B - Analysis & Signals
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          NEWSAPI_KEY: ${{ secrets.NEWSAPI_KEY }}
          HUGGINGFACE_API_KEY: ${{ secrets.HUGGINGFACE_API_KEY }}
        run: python src/modulo_b_analysis.py
      - name: Run Modulo E - Cost Filter
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: python src/modulo_e_cost_filter.py

===== .github/workflows/sapta_us_close.yml =====
name: SAPTA US Close Pipeline (Segnale USA finalizzato, 1x/day)

on:
  schedule:
    - cron: '30 21 * * 1-5'
  workflow_dispatch:

concurrency:
  group: sapta-us-close
  cancel-in-progress: true

jobs:
  us-close-signal:
    runs-on: ubuntu-latest
    timeout-minutes: 8
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Set up Python 3.10
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'
          cache: 'pip'
          cache-dependency-path: requirements-slow.txt
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements-slow.txt
      - name: Run Modulo B - Analysis & Signals (solo USA, barra ormai finalizzata)
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
          NEWSAPI_KEY: ${{ secrets.NEWSAPI_KEY }}
          HUGGINGFACE_API_KEY: ${{ secrets.HUGGINGFACE_API_KEY }}
        run: python src/modulo_b_analysis.py --market=USA
      - name: Run Modulo E - Cost Filter (solo USA)
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_SERVICE_ROLE_KEY: ${{ secrets.SUPABASE_SERVICE_ROLE_KEY }}
        run: python src/modulo_e_cost_filter.py --market=USA

