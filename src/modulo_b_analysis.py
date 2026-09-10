"""
Modulo B: Analysis & Prediction Core
Calcola indicatori tecnici, sentiment (via HuggingFace Inference API), genera segnali.
"""
import time
import yfinance as yf
import requests
import pandas as pd
import pandas_ta_classic as ta  # v3.6 — pandas-ta originale rimosso da PyPI, sostituito con il fork mantenuto
from datetime import datetime, timedelta, timezone
from config import supabase, TICKERS, NEWSAPI_KEY, HUGGINGFACE_API_KEY, NEWS_CACHE_MINUTES

FINBERT_API_URL = "https://api-inference.huggingface.co/models/ProsusAI/finbert"


def get_cached_news(ticker):
    """Legge da Supabase le news già scaricate di recente per il ticker (evita di richiamare NewsAPI ogni ciclo)."""
    try:
        threshold = (datetime.now(timezone.utc) - timedelta(minutes=NEWS_CACHE_MINUTES)).isoformat()
        response = (supabase.table('news')
                    .select('title, sentiment_score, timestamp')
                    .contains('related_tickers', [ticker])
                    .gte('timestamp', threshold)
                    .execute())
        return response.data or []
    except Exception as e:
        print(f"⚠️ Errore lettura cache news per {ticker}: {e}")
        return []


def fetch_news(ticker, api_key):
    """Scarica news recenti per un ticker da NewsAPI (solo se non presenti in cache)."""
    if not api_key:
        return []
    try:
        url = f"https://newsapi.org/v2/everything?q={ticker}&language=en&sortBy=publishedAt&pageSize=5&apiKey={api_key}"
        r = requests.get(url, timeout=5)
        data = r.json()
        return data.get('articles', [])
    except Exception as e:
        print(f"⚠️ Errore NewsAPI per {ticker}: {e}")
        return []


def analyze_sentiment_hf(text, max_retries=2):
    """Chiama la HuggingFace Inference API per il sentiment finanziario (FinBERT).
    Ritorna un punteggio da -1 (negativo) a +1 (positivo)."""
    if not HUGGINGFACE_API_KEY or not text:
        return 0.0

    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
    payload = {"inputs": text[:512]}

    for attempt in range(max_retries + 1):
        try:
            r = requests.post(FINBERT_API_URL, headers=headers, json=payload, timeout=15)
            if r.status_code == 503:
                # Modello "freddo": HF indica un tempo stimato di caricamento
                wait = min(r.json().get('estimated_time', 5), 20)
                print(f"   ⏳ Modello FinBERT in caricamento, attendo {wait:.0f}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            result = r.json()[0]  # lista di {label, score} per ogni classe
            best = max(result, key=lambda x: x['score'])
            label, score = best['label'].lower(), best['score']
            if label == 'positive':
                return score
            elif label == 'negative':
                return -score
            return 0.0
        except Exception as e:
            print(f"⚠️ Errore HF Inference API (tentativo {attempt+1}): {e}")
            time.sleep(1)
    return 0.0


def analyze_sentiment(ticker, articles):
    """Calcola sentiment aggregato: riusa gli score già in cache, chiama l'API solo per le news nuove."""
    if not articles:
        return 0.0

    scores = []
    news_to_insert = []
    for article in articles:
        title = article.get('title', '')
        if not title:
            continue
        score = analyze_sentiment_hf(title)
        scores.append(score)
        news_to_insert.append({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'title': title,
            'source': article.get('source', {}).get('name', 'NewsAPI'),
            'url': article.get('url'),
            'sentiment_score': score,
            'related_tickers': [ticker]
        })

    if news_to_insert:
        try:
            supabase.table('news').insert(news_to_insert).execute()
        except Exception as e:
            print(f"⚠️ Errore scrittura news {ticker}: {e}")

    return sum(scores) / len(scores) if scores else 0.0


def calculate_technical_indicators(ticker):
    """Scarica dati storici e calcola indicatori tecnici.

    Gestisce esplicitamente il MultiIndex restituito da yfinance per il download
    di un singolo ticker. Calcola gli indicatori sulla barra giornaliera chiusa
    più recente quando la barra di oggi è ancora provvisoria; il prezzo corrente
    viene invece letto dalla tabella Supabase 'prezzi'.
    """
    try:
        df = yf.download(
            ticker,
            period="60d",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        if df is None or df.empty or len(df) < 31:
            print(f"⚠️ Dati storici insufficienti per {ticker}")
            return None

        # yfinance può restituire un MultiIndex anche per un singolo ticker.
        # In quel caso riduciamo il DataFrame alle sole colonne OHLCV del ticker.
        if isinstance(df.columns, pd.MultiIndex):
            if ticker in df.columns.get_level_values(0):
                df = df.xs(ticker, axis=1, level=0)
            elif ticker in df.columns.get_level_values(1):
                df = df.xs(ticker, axis=1, level=1)

        required = ["Open", "High", "Low", "Close", "Volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            print(f"⚠️ Colonne mancanti per {ticker}: {missing}")
            return None

        close = pd.to_numeric(df["Close"], errors="coerce")
        high = pd.to_numeric(df["High"], errors="coerce")
        low = pd.to_numeric(df["Low"], errors="coerce")

        # RSI
        df["RSI"] = ta.rsi(close, length=14)

        # MACD: pandas-ta-classic restituisce un DataFrame.
        # Prima colonna = MACD, terza = signal; verifichiamo comunque la risposta.
        macd_df = ta.macd(close)
        if macd_df is None or macd_df.empty or macd_df.shape[1] < 3:
            print(f"⚠️ MACD non disponibile per {ticker}")
            return None

        df["MACD"] = macd_df.iloc[:, 0]
        df["MACD_signal"] = macd_df.iloc[:, 2]

        # Bollinger Bands: [lower, middle, upper, ...]
        bb_df = ta.bbands(close, length=20)
        if bb_df is None or bb_df.empty or bb_df.shape[1] < 3:
            print(f"⚠️ Bollinger Bands non disponibili per {ticker}")
            return None

        df["BB_lower"] = bb_df.iloc[:, 0]
        df["BB_middle"] = bb_df.iloc[:, 1]
        df["BB_upper"] = bb_df.iloc[:, 2]

        # ATR
        df["ATR"] = ta.atr(high, low, close, length=14)

        # Servono indicatori completi sulla barra utilizzata.
        df = df.dropna(
            subset=[
                "RSI",
                "MACD",
                "MACD_signal",
                "BB_lower",
                "BB_middle",
                "BB_upper",
                "ATR"
            ]
        )

        if len(df) < 2:
            print(f"⚠️ Indicatori insufficienti per {ticker}")
            return None

        last_bar_date = df.index[-1].date()
        today_utc = datetime.now(timezone.utc).date()
        is_provisional = (last_bar_date == today_utc)

        # Se oggi è ancora in formazione, indicatori sulla penultima barra chiusa.
        row_for_indicators = df.iloc[-2] if is_provisional else df.iloc[-1]

        # Prezzo corrente: dato intraday prodotto dal Modulo A.
        current_price = get_latest_intraday_price(ticker)
        if current_price is None:
            current_price = float(close.iloc[-1])

        bb_range = (
            float(row_for_indicators["BB_upper"])
            - float(row_for_indicators["BB_lower"])
        )

        if bb_range == 0:
            bb_position = 0.5
        else:
            bb_position = (
                float(row_for_indicators["Close"])
                - float(row_for_indicators["BB_lower"])
            ) / bb_range

        return {
            "rsi": float(row_for_indicators["RSI"]),
            "macd": float(row_for_indicators["MACD"]),
            "macd_signal": float(row_for_indicators["MACD_signal"]),
            "bb_position": float(bb_position),
            "atr": float(row_for_indicators["ATR"]),
            "close": float(current_price),
            "is_provisional_bar": is_provisional
        }

    except Exception as e:
        print(f"❌ Errore indicatori {ticker}: {e}")
        return None


def get_latest_intraday_price(ticker):
    """(v3.5) Legge il prezzo più recente dalla tabella 'prezzi' (scritta dal Modulo A
    ogni 15 minuti nel workflow 'fast'). Più fresco e affidabile del Close di una barra
    giornaliera ancora provvisoria."""
    try:
        response = (supabase.table('prezzi')
                    .select('close')
                    .eq('ticker', ticker)
                    .order('timestamp', desc=True)
                    .limit(1)
                    .execute())
        if response.data:
            return float(response.data[0]['close'])
        return None
    except Exception as e:
        print(f"⚠️ Errore lettura prezzo corrente per {ticker}: {e}")
        return None


def generate_signal(indicators, sentiment):
    """Genera segnale BUY/SELL/HOLD + confidence + risk score."""
    if not indicators:
        return None

    # Logica semplificata (da sostituire con modello XGBoost addestrato in Fase 4)
    score = 0
    if indicators['rsi'] < 30:
        score += 2
    elif indicators['rsi'] > 70:
        score -= 2

    if indicators['macd'] > indicators['macd_signal']:
        score += 1
    else:
        score -= 1

    if indicators['bb_position'] < 0.2:
        score += 1
    elif indicators['bb_position'] > 0.8:
        score -= 1

    score += int(sentiment * 2)

    if score >= 2:
        action = 'BUY'
        confidence = min(0.9, 0.5 + score * 0.1)
    elif score <= -2:
        action = 'SELL'
        confidence = min(0.9, 0.5 + abs(score) * 0.1)
    else:
        action = 'HOLD'
        confidence = 0.5

    risk_score = min(1.0, indicators['atr'] / indicators['close'] * 10)

    return {
        'action': action,
        'confidence_score': confidence,
        'risk_score': risk_score,
        'atr': indicators['atr'],
        'close_price': indicators['close'],
        'is_provisional_bar': indicators['is_provisional_bar']
    }


def write_signals_to_supabase(ticker, signal):
    """Scrive segnale grezzo in Supabase, incluso ATR, prezzo e flag di provvisorietà (v3.5)."""
    try:
        supabase.table('signals_raw').insert({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'ticker': ticker,
            'action': signal['action'],
            'confidence_score': signal['confidence_score'],
            'risk_score': signal['risk_score'],
            'atr': signal['atr'],
            'close_price': signal['close_price'],
            'is_provisional_bar': signal['is_provisional_bar'],  # v3.5 — vedi calculate_technical_indicators
            'model_version': 'v3.1_rule_based'  # Da aggiornare quando usi XGBoost (Fase 4)
        }).execute()
        flag = " (barra provvisoria)" if signal['is_provisional_bar'] else ""
        print(f"✅ Segnale {ticker}: {signal['action']} (conf={signal['confidence_score']:.2f}){flag}")
    except Exception as e:
        print(f"❌ Errore scrittura segnale {ticker}: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', choices=['ALL', 'USA', 'EU'], default='ALL',
                         help='(v3.5) Filtra i ticker processati. ALL=default (workflow slow), '
                              'USA=solo ticker USA (usato dal run dedicato post-chiusura, §1.6bis)')
    args = parser.parse_args()

    from config import TICKERS_USA, TICKERS_EU
    tickers_to_process = {'ALL': TICKERS, 'USA': TICKERS_USA, 'EU': TICKERS_EU}[args.market]

    print(f"🚀 Modulo B - Analysis ({args.market}): {datetime.now(timezone.utc).isoformat()}")

    for ticker in tickers_to_process:
        print(f"\n📊 Analisi {ticker}...")

        indicators = calculate_technical_indicators(ticker)
        if not indicators:
            continue

        # News: prima la cache Supabase, solo se vuota si richiama NewsAPI
        cached = get_cached_news(ticker)
        if cached:
            sentiment = sum(n['sentiment_score'] for n in cached) / len(cached)
            print(f"   Sentiment: {sentiment:.2f} (da cache, {len(cached)} news)")
        else:
            articles = fetch_news(ticker, NEWSAPI_KEY)
            sentiment = analyze_sentiment(ticker, articles)
            print(f"   Sentiment: {sentiment:.2f} (da {len(articles)} news nuove)")

        signal = generate_signal(indicators, sentiment)
        if signal:
            write_signals_to_supabase(ticker, signal)