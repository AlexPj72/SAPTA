"""
Modulo B: Analysis & Verdict Engine (v5.1.1)

Non processa più tutto l'universo: legge SOLO i candidati promossi da H2
(screening_candidates.status='promosso_a_B'), non ancora analizzati
(b_processed_at IS NULL). Per ciascuno produce:
- verdetto (BUY/SELL/HOLD) con confidenza esplicita (alto/medio/basso,
  Sezione 11), mappata a moltiplicatore via scoring_weights_v1.json
- classificazione tipologia opportunità (Sezione 8): mean_reversion,
  momentum_breakout, event_driven, o deterioramento_strutturale (esce dal
  funnel senza arrivare al ranking, Sezione 8.4)
- condizione di invalidazione esplicita (Sezione 14): prezzo/evento che
  dimostra che la tesi è sbagliata
- calendario eventi (earnings entro 3-5gg, Sezione 10)

News livello 2 (sentiment HuggingFace/FinBERT) invariato dalla v3.1 - nessuna
modifica necessaria a quella parte, era già corretta.
"""
import os
import json
import time
import argparse
import yfinance as yf
import requests
import pandas as pd
import pandas_ta_classic as ta
from datetime import datetime, timedelta, timezone
from config import supabase, NEWSAPI_KEY, HUGGINGFACE_API_KEY, NEWS_CACHE_MINUTES, GEMINI_API_KEY
from universe import get_universe_metadata

# Hugging Face Inference Providers (endpoint attuale).
# Il vecchio api-inference.huggingface.co non è più l'endpoint da usare.
FINBERT_API_URL = "https://router.huggingface.co/hf-inference/models/ProsusAI/finbert"

WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scoring_weights_v1.json')
with open(WEIGHTS_PATH) as f:
    WEIGHTS = json.load(f)
CONFIDENCE_MULTIPLIER = WEIGHTS['confidence_multiplier']

EARNINGS_HORIZON_DAYS = 5


# ============================================================
# News livello 2 - INVARIATO dalla v3.1, nessuna modifica
# ============================================================

def get_cached_news(ticker):
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
    if not api_key:
        return []
    try:
        url = f"https://newsapi.org/v2/everything?q={ticker}&language=en&sortBy=publishedAt&pageSize=5&apiKey={api_key}"
        r = requests.get(url, timeout=5)
        return r.json().get('articles', [])
    except Exception as e:
        print(f"⚠️ Errore NewsAPI per {ticker}: {e}")
        return []


def analyze_sentiment_hf(text, max_retries=2):
    if not HUGGINGFACE_API_KEY or not text:
        return 0.0
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
    payload = {"inputs": text[:512]}
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(FINBERT_API_URL, headers=headers, json=payload, timeout=15)
            if r.status_code == 503:
                wait = min(r.json().get('estimated_time', 5), 20)
                time.sleep(wait)
                continue
            r.raise_for_status()
            result = r.json()[0]
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
    if not articles:
        return 0.0
    scores, news_to_insert = [], []
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


# ============================================================
# Indicatori tecnici - INVARIATO dalla v3.5 (fix barra provvisoria)
# ============================================================

def get_latest_intraday_price(ticker):
    try:
        response = (supabase.table('prezzi')
                    .select('close')
                    .eq('ticker', ticker)
                    .eq('interval', '15m')
                    .order('timestamp', desc=True)
                    .limit(1)
                    .execute())
        return float(response.data[0]['close']) if response.data else None
    except Exception as e:
        print(f"⚠️ Errore lettura prezzo corrente per {ticker}: {e}")
        return None


DAILY_BATCH_SIZE = 20  # ticker per chiamata yf.download, stesso principio di load_historical_data.py
DAILY_BATCH_SLEEP_SECONDS = 2
GEMINI_CALL_SLEEP_SECONDS = 3  # pausa dopo ogni chiamata a run_ai_agent (Modulo I)


def fetch_daily_batch(tickers):
    """[NUOVO 24/09 - causa radice 2] La versione precedente chiamava
    yf.download() UNA VOLTA PER TICKER dentro il loop di Modulo B (fino a
    ~90 chiamate singole consecutive per run, senza pausa). Confermato su
    Supabase: 154 candidati promossi a B negli ultimi 7gg, 78 processati
    (b_processed_at valorizzato) nelle ultime 48h, ZERO righe in
    signals_raw e ZERO in scartato_deterioramento - cioè tutti fallivano
    dentro calculate_technical_indicators() con DataFrame vuoto. Causa:
    Yahoo Finance applica rate-limit aggressivo agli IP datacenter (i
    runner GitHub Actions sono IP noti), e le chiamate seriali ravvicinate
    lo attivano quasi subito. Modulo A e load_historical_data.py non hanno
    mai avuto questo problema perché scaricano già a batch (rispettivamente
    un'unica chiamata multi-ticker e blocchi da 20 con sleep(2) tra un
    blocco e l'altro) - stesso pattern replicato qui.
    Ritorna {ticker: DataFrame} solo per i ticker con dati validi.

    [FIX 26/09] Il ramo 'elif len(batch) == 1' era un bug: yf.download()
    con group_by='ticker' ritorna colonne MultiIndex (ticker, campo)
    quando l'argomento è una LISTA, indipendentemente dalla sua lunghezza
    - anche per una lista di un solo elemento. Il codice assumeva invece
    che una lista di lunghezza 1 desse colonne piatte come per un ticker
    singolo passato come stringa, il che è falso. Risultato osservato:
    quando un run di Modulo B aveva esattamente un candidato nuovo da
    processare (frequente: i run sono ogni 15-30 min, spesso con 0-1
    candidati), fetch_daily_batch riceveva una lista di un ticker,
    imboccava il ramo sbagliato, e calculate_technical_indicators falliva
    con KeyError su df['Close'] (colonna reale: (ticker, 'Close')) -
    fallimento silenzioso identico a quello risolto il 24/09, stessa
    conseguenza (zero righe in signals_raw), causa diversa. Confermato
    su Supabase: 79 candidati promossi a B dal 24/09, 79 processati,
    ancora zero segnali - il fix del 24/09 non bastava. Corretto usando
    lo stesso controllo già collaudato in modulo_a_ingestion.py
    (reconcile_prices): isinstance(df.columns, pd.MultiIndex), non la
    lunghezza della lista."""
    result = {}
    tickers = list(dict.fromkeys(tickers))  # dedup preservando l'ordine
    for i in range(0, len(tickers), DAILY_BATCH_SIZE):
        batch = tickers[i:i + DAILY_BATCH_SIZE]
        try:
            df = yf.download(batch, period="60d", interval="1d", group_by='ticker',
                              auto_adjust=True, progress=False)
            if df.empty:
                print(f"⚠️ Batch giornaliero vuoto per {batch}")
            elif not isinstance(df.columns, pd.MultiIndex):
                # Difesa in profondità: se yfinance dovesse mai restituire
                # colonne piatte (comportamento osservato solo passando UNA
                # STRINGA, non una lista, ma mai fare affidamento su questo).
                result[batch[0]] = df
            else:
                for t in batch:
                    try:
                        sub = df[t].dropna(how='all')
                        if not sub.empty:
                            result[t] = sub
                    except (KeyError, Exception):
                        pass
        except Exception as e:
            print(f"❌ Errore yf.download batch giornaliero {batch}: {e}")
        if i + DAILY_BATCH_SIZE < len(tickers):
            time.sleep(DAILY_BATCH_SLEEP_SECONDS)
    return result


def calculate_technical_indicators(ticker, daily_df=None):
    try:
        df = daily_df if daily_df is not None else fetch_daily_batch([ticker]).get(ticker)
        if df is None or df.empty:
            # [NUOVO 22/09 - audit, causa confermata 24/09] Prima ritornava
            # None senza log: causa del blocco silenzioso "b_processed_at
            # settato ma nessun signals_raw scritto" osservato in audit
            # (21-22/09/2026). Causa radice reale trovata il 24/09: vedi
            # fetch_daily_batch() - non era il ticker, erano le chiamate
            # yf.download seriali senza pausa che finivano rate-limitate.
            print(f"⚠️ {ticker}: nessun dato giornaliero disponibile (60d/1d) - "
                  f"nessun indicatore calcolabile, candidato scartato senza segnale")
            return None
        if len(df) < 35:
            print(f"⚠️ {ticker}: solo {len(df)} barre giornaliere ricevute da yfinance "
                  f"(soglia minima 35 per RSI/MACD 12-26-9/BBands sulla penultima barra) - candidato scartato senza segnale")
            return None

        df['RSI'] = ta.rsi(df['Close'], length=14)
        # [FIX 30/09 - handoff Codex] ta.macd/ta.bbands ritornano DataFrame
        # (bbands: 5 colonne BBL/BBM/BBU/BBB/BBP; macd: MACD/MACDh/MACDs),
        # non tuple da spacchettare. Estrazione per nome, mai per posizione.
        macd = ta.macd(df['Close'])
        bb = ta.bbands(df['Close'], length=20)
        if macd is None or bb is None:
            print(f"⚠️ {ticker}: indicatori MACD/BB non calcolabili (None)")
            return None
        df['MACD'] = macd.filter(regex=r'^MACD_').iloc[:, 0]
        df['MACD_signal'] = macd.filter(regex=r'^MACDs_').iloc[:, 0]
        df['BB_lower'] = bb.filter(regex=r'^BBL_').iloc[:, 0]
        df['BB_middle'] = bb.filter(regex=r'^BBM_').iloc[:, 0]
        df['BB_upper'] = bb.filter(regex=r'^BBU_').iloc[:, 0]
        df['ATR'] = ta.atr(df['High'], df['Low'], df['Close'], length=14)

        last_bar_date = df.index[-1].date()
        today_utc = datetime.now(timezone.utc).date()
        is_provisional = (last_bar_date == today_utc)
        row = df.iloc[-2] if is_provisional else df.iloc[-1]

        # [FIX 30/09 - handoff Codex] Indicatori NaN/inf o degeneri = errore
        # tecnico (candidato da ritentare), mai un segnale con valori sporchi.
        import math
        needed = ['RSI', 'MACD', 'MACD_signal', 'BB_lower', 'BB_upper', 'ATR', 'Close']
        vals = {k: float(row[k]) for k in needed}
        if any(not math.isfinite(v) for v in vals.values()):
            print(f"⚠️ {ticker}: indicatori non finiti (NaN/inf) - errore tecnico, verra ritentato")
            return None
        if vals['BB_upper'] <= vals['BB_lower'] or vals['ATR'] <= 0:
            print(f"⚠️ {ticker}: indicatori degeneri (BB piatte o ATR<=0) - errore tecnico, verra ritentato")
            return None

        current_price = get_latest_intraday_price(ticker) or float(df.iloc[-1]['Close'])

        return {
            'rsi': float(row['RSI']),
            'macd': float(row['MACD']),
            'macd_signal': float(row['MACD_signal']),
            'bb_position': (float(row['Close']) - float(row['BB_lower'])) / (float(row['BB_upper']) - float(row['BB_lower'])),
            'atr': float(row['ATR']),
            'close': current_price,
            'is_provisional_bar': is_provisional,
            # [NUOVO 01/10 - persistenza indicatori] Solo per tracciabilita':
            # non entrano in nessuna regola di decisione.
            'bb_lower': float(row['BB_lower']),
            'bb_upper': float(row['BB_upper']),
            'daily_close': float(row['Close']),
            'daily_bar_date': (df.index[-2] if is_provisional else df.index[-1]).date().isoformat(),
            'daily_bars_used': int(len(df)),
        }
    except Exception as e:
        print(f"❌ Errore indicatori {ticker}: {type(e).__name__}: {e}")
        return None


# ============================================================
# NUOVO v5.1.1 — Calendario eventi (Sezione 10)
# ============================================================

def has_upcoming_earnings(ticker, horizon_days=EARNINGS_HORIZON_DAYS):
    """Verifica earnings entro horizon_days. Fail-open: errore -> False,
    non blocca il resto dell'analisi (coerente con l'approccio fail-open
    già usato nel controllo di concentrazione settoriale, v3.2)."""
    try:
        cal = yf.Ticker(ticker).get_earnings_dates(limit=4)
        if cal is None or cal.empty:
            return False
        now = datetime.now(timezone.utc)
        horizon = now + timedelta(days=horizon_days)
        for dt in cal.index:
            dt_utc = dt.to_pydatetime()
            if dt_utc.tzinfo is None:
                dt_utc = dt_utc.replace(tzinfo=timezone.utc)
            if now <= dt_utc <= horizon:
                return True
        return False
    except Exception as e:
        print(f"⚠️ Errore calendario earnings per {ticker}: {e}")
        return False


# ============================================================
# NUOVO v5.1.1 — Confidenza esplicita (Sezione 11)
# ============================================================

def compute_confidence_detail(indicators, sentiment, context_score):
    """Conta quanti segnali di contesto convergono nella stessa direzione.
    Placeholder ragionevole, NON calibrato - vedi v5.1.1 §28 alert 4:
    va validato con backtest walk-forward, non lasciato fisso per assunzione.

    [01/10] Stessa identica logica di prima, ma ritorna anche i segnali e
    l'accordo, cosi' da poterli salvare in signals_raw.decision_detail.
    compute_confidence() qui sotto resta con la firma e il risultato di sempre."""
    signals = []
    if context_score is not None and abs(context_score) > 0.05:
        signals.append(1 if context_score > 0 else -1)
    if abs(sentiment) > 0.1:
        signals.append(1 if sentiment > 0 else -1)
    signals.append(1 if indicators['macd'] > indicators['macd_signal'] else -1)
    if indicators['rsi'] < 30:
        signals.append(1)
    elif indicators['rsi'] > 70:
        signals.append(-1)

    if not signals:
        return {'level': 'basso', 'net': 0, 'agreement': None, 'signals': []}

    net = sum(signals)
    agreement = max(signals.count(1), signals.count(-1)) / len(signals)

    if agreement >= 0.75 and abs(net) >= 2:
        level = 'alto'
    elif agreement >= 0.5:
        level = 'medio'
    else:
        level = 'basso'
    return {'level': level, 'net': net, 'agreement': agreement, 'signals': signals}


def compute_confidence(indicators, sentiment, context_score):
    d = compute_confidence_detail(indicators, sentiment, context_score)
    return d['level'], d['net']


# ============================================================
# NUOVO v5.1.1 — Tipologia opportunità (Sezione 8) + invalidazione (Sezione 14)
# ============================================================

def classify_opportunity(indicators, context_score, news_light_count, has_earnings, net_signal):
    """Euristica esplicitamente dichiarata come punto di partenza, non
    verità consolidata - va rivista con l'analisi dei falsi positivi
    scartati come deterioramento (Sezione 22, backtest)."""
    strong_negative_context = context_score is not None and context_score < -0.5
    weak_sentiment_signals = net_signal <= -2

    if strong_negative_context and weak_sentiment_signals:
        return 'deterioramento_strutturale'

    if has_earnings or (news_light_count or 0) >= 5:
        return 'event_driven'

    if indicators['bb_position'] < 0.15 or indicators['bb_position'] > 0.85:
        return 'mean_reversion'

    return 'momentum_breakout'


def compute_invalidation(action, close_price, atr):
    """[Sezione 14] Livello di prezzo che invalida la tesi. Distanza 1.5x ATR,
    valore di partenza da calibrare col backtest, non definitivo."""
    if action == 'BUY':
        price = close_price - 1.5 * atr
        reason = f"Rottura supporto: prezzo sotto {price:.2f} (1.5x ATR dall'ingresso)"
    elif action == 'SELL':
        price = close_price + 1.5 * atr
        reason = f"Rottura resistenza: prezzo sopra {price:.2f} (1.5x ATR dall'ingresso)"
    else:
        price, reason = None, None
    return price, reason


def compute_target(action, close_price, atr, risk_reward_ratio=2.0):
    """[NUOVO - recupero pezzi persi] Livello di target/take-profit, simmetrico
    a compute_invalidation. Distanza = rischio (1.5x ATR) x risk_reward_ratio,
    quindi 3x ATR di default (rapporto 1:2). Placeholder da calibrare col
    backtest walk-forward, stesso principio dello stop - non è un valore
    definitivo, è un punto di partenza operativo."""
    risk_distance = 1.5 * atr
    if action == 'BUY':
        price = close_price + risk_distance * risk_reward_ratio
        reason = f"Target 1:{risk_reward_ratio:.0f} rischio/rendimento (3x ATR dall'ingresso)"
    elif action == 'SELL':
        price = close_price - risk_distance * risk_reward_ratio
        reason = f"Target 1:{risk_reward_ratio:.0f} rischio/rendimento (3x ATR dall'ingresso)"
    else:
        price, reason = None, None
    return price, reason


# Modello: Flash Lite invece di Flash pieno — RPD 500 vs RPD 20 sul tier
# gratuito (verificato dall'utente su aistudio.google.com/rate-limit, 14/09).
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"


def run_ai_agent(ticker, indicators, sentiment, context_score, news_light_count, has_earnings):
    """[Modulo I - SAPTA_v4.md §3] Terzo canale indipendente: riceve gli stessi
    dati grezzi di Modulo B ma NON il verdetto/score di B, e ragiona in autonomia
    via LLM gratuito (Gemini 3.1 Flash Lite, Google AI Studio - free tier,
    nessuna carta richiesta; il modello è stato aggiornato il 14/09, questo
    docstring era rimasto disallineato). Scrive in ai_agent_decisions, tabella
    parallela a signals_raw - non influenza in alcun modo il filtro di Modulo E.
    Anticipato dalla Fase 7 (dove nasce nella spec) su richiesta esplicita utente."""
    if not GEMINI_API_KEY:
        return  # secret non configurato, salta silenziosamente senza bloccare Modulo B

    prompt = f"""Sei un analista tecnico indipendente. Dati grezzi per {ticker}:
- Prezzo attuale: {indicators['close']:.2f}
- RSI(14): {indicators['rsi']:.1f}
- MACD: {indicators['macd']:.4f} (signal: {indicators['macd_signal']:.4f})
- Posizione nelle Bollinger Bands (0=banda bassa, 1=banda alta): {indicators['bb_position']:.2f}
- ATR(14): {indicators['atr']:.2f}
- Sentiment news (-1 negativo, +1 positivo): {sentiment:.2f}
- Punteggio di contesto (trend/settore, -1/+1): {context_score if context_score is not None else 'N/D'}
- Notizie recenti rilevate: {news_light_count if news_light_count is not None else 'N/D'}
- Earnings imminenti (3-5gg): {'Sì' if has_earnings else 'No'}

Ragiona in autonomia, senza applicare soglie fisse standard (es. RSI 30/70). Rispondi
SOLO con un oggetto JSON, nessun altro testo, in questo formato esatto:
{{"decision": "BUY" o "SELL" o "HOLD", "confidence": numero da 0 a 1, "reasoning": "motivazione in 1-2 frasi in italiano"}}"""

    try:
        # Autenticazione via header, non query param: le chiavi Gemini
        # generate da settembre 2026 sono in formato "AQ." (Auth key) e
        # vengono rifiutate (401) se passate come ?key=... nell'URL, che
        # resta valido solo per le vecchie chiavi "AIza..." ormai dismesse
        # da Google. Vedi forum ufficiale Google AI Developers, thread
        # multipli su ACCESS_TOKEN_TYPE_UNSUPPORTED.
        r = requests.post(
            GEMINI_API_URL,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=20
        )
        if r.status_code == 429:
            print(f"⚠️ Modulo I: rate limit Gemini raggiunto per {ticker}, salto (non blocca Modulo B)")
            return
        r.raise_for_status()
        content = r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        content = content.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(content)

        supabase.table('ai_agent_decisions').insert({
            'ticker': ticker,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'model_used': 'gemini-3.1-flash-lite',
            'ai_decision': parsed.get('decision', 'HOLD'),
            'ai_confidence': float(parsed.get('confidence', 0.5)),
            'ai_reasoning': parsed.get('reasoning', ''),
        }).execute()
        print(f"   🤖 Modulo I: {parsed.get('decision')} (conf={parsed.get('confidence')})")
    except Exception as e:
        print(f"⚠️ Modulo I (Gemini) errore per {ticker}: {e} — non blocca Modulo B")


def generate_signal(indicators, sentiment, context_score, news_light_count, has_earnings):
    # [01/10] Stessa aritmetica di prima: le componenti sono solo registrate
    # a parte per poterle salvare (score_total = somma delle componenti).
    score_rsi = 0
    if indicators['rsi'] < 30:
        score_rsi = 2
    elif indicators['rsi'] > 70:
        score_rsi = -2
    score_macd = 1 if indicators['macd'] > indicators['macd_signal'] else -1
    score_bb = 0
    if indicators['bb_position'] < 0.2:
        score_bb = 1
    elif indicators['bb_position'] > 0.8:
        score_bb = -1
    score_sentiment = int(sentiment * 2)
    score_context = int(context_score * 2) if context_score is not None else 0
    score = score_rsi + score_macd + score_bb + score_sentiment + score_context

    if score >= 2:
        action = 'BUY'
    elif score <= -2:
        action = 'SELL'
    else:
        action = 'HOLD'

    conf = compute_confidence_detail(indicators, sentiment, context_score)
    confidence_level, net_signal = conf['level'], conf['net']
    confidence_multiplier = CONFIDENCE_MULTIPLIER.get(confidence_level, 0.4)
    opportunity_type = classify_opportunity(indicators, context_score, news_light_count, has_earnings, net_signal)
    invalidation_price, invalidation_reason = compute_invalidation(action, indicators['close'], indicators['atr'])
    target_price, target_reason = compute_target(action, indicators['close'], indicators['atr'])
    risk_score = min(1.0, indicators['atr'] / indicators['close'] * 10)
    final_action = action if opportunity_type != 'deterioramento_strutturale' else 'HOLD'

    decision_detail = {
        'rules_version': 'v5.1.1_rule_based',
        'score': {'rsi': score_rsi, 'macd': score_macd, 'bb': score_bb,
                  'sentiment': score_sentiment, 'context': score_context, 'total': score},
        'thresholds': {'buy_if_score_gte': 2, 'sell_if_score_lte': -2,
                       'rsi_oversold': 30, 'rsi_overbought': 70, 'bb_low': 0.2, 'bb_high': 0.8},
        'inputs': {
            'rsi': indicators['rsi'], 'macd': indicators['macd'], 'macd_signal': indicators['macd_signal'],
            'bb_position': indicators['bb_position'],
            'bb_lower': indicators.get('bb_lower'), 'bb_upper': indicators.get('bb_upper'),
            'atr': indicators['atr'], 'price_used': indicators['close'],
            'daily_close': indicators.get('daily_close'), 'daily_bar_date': indicators.get('daily_bar_date'),
            'daily_bars_used': indicators.get('daily_bars_used'),
            'is_provisional_bar': indicators['is_provisional_bar'],
            'sentiment': sentiment, 'context_score': context_score,
            'news_light_count': news_light_count, 'has_earnings': has_earnings,
        },
        'confidence': {'level': confidence_level, 'net': net_signal,
                       'agreement': conf['agreement'], 'signals': conf['signals']},
        'opportunity_type': opportunity_type,
        'action_from_score': action,
        'action_final': final_action,
    }

    return {
        'action': final_action,
        'confidence_score': min(0.9, 0.5 + abs(score) * 0.1),
        'confidence_level': confidence_level,
        'confidence_multiplier': confidence_multiplier,
        'opportunity_type': opportunity_type,
        'risk_score': risk_score,
        'atr': indicators['atr'],
        'close_price': indicators['close'],
        'is_provisional_bar': indicators['is_provisional_bar'],
        'has_upcoming_earnings': has_earnings,
        'invalidation_price': invalidation_price,
        'invalidation_reason': invalidation_reason,
        'target_price': target_price,
        'target_reason': target_reason,
        # [NUOVO 01/10 - persistenza indicatori]
        'score_total': score,
        'score_rsi': score_rsi,
        'score_macd': score_macd,
        'score_bb': score_bb,
        'score_sentiment': score_sentiment,
        'score_context': score_context,
        'sentiment_value': sentiment,
        'context_score': context_score,
        'news_light_count': news_light_count,
        'indicators': indicators,
        'decision_detail': decision_detail,
    }


# ============================================================
# Lettura candidati da H2 (sostituisce il loop su TICKERS)
# ============================================================

def get_candidates(market_filter='ALL', force_reprocess=False):
    """Legge screening_candidates promossi da H2 e non ancora analizzati da B.

    market_filter: 'ALL'/'USA'/'EU' - filtra per mercato via universe.py
    (necessario perché sapta_us_close.yml chiama con --market=USA).
    force_reprocess: usato da sapta_us_close.yml per rianalizzare alla
    chiusura reale anche candidati già processati durante il ciclo slow
    (barra ormai definitiva invece che provvisoria, v3.5 §1.6bis).
    """
    try:
        query = supabase.table('screening_candidates').select('*').eq('status', 'promosso_a_B')
        if not force_reprocess:
            query = query.is_('b_processed_at', 'null')
        else:   # rianalisi di chiusura: solo i candidati delle ultime 24h (prima ~300+ => timeout del workflow)
            query = query.gte('created_at', (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat())
        response = query.execute()
        rows = response.data or []
    except Exception as e:
        print(f"❌ Errore lettura screening_candidates: {e}")
        return []

    if market_filter == 'ALL':
        return rows

    metadata = get_universe_metadata()
    return [r for r in rows if metadata.get(r['ticker'], {}).get('market') == market_filter]


def mark_processed(candidate_id):
    try:
        supabase.table('screening_candidates').update({
            'b_processed_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', candidate_id).execute()
    except Exception as e:
        print(f"⚠️ Errore aggiornamento b_processed_at per candidato {candidate_id}: {e}")


def _fit_numeric(value, precision, scale):
    """Arrotonda a `scale` decimali; se il valore non entra nella colonna
    numeric(precision, scale) ritorna None invece di far fallire l'insert
    (il valore esatto resta comunque in decision_detail)."""
    if value is None:
        return None
    try:
        v = round(float(value), scale)
    except (TypeError, ValueError):
        return None
    return v if abs(v) < 10 ** (precision - scale) else None


def build_raw_row(ticker, candidate_id, signal):
    """Riga di signals_raw (separata da write_signal per poterla testare)."""
    ind = signal.get('indicators') or {}
    return {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'ticker': ticker,
        'screening_candidate_id': candidate_id,
        'action': signal['action'],
        'confidence_score': signal['confidence_score'],
        'confidence_level': signal['confidence_level'],
        'confidence_multiplier': signal['confidence_multiplier'],
        'opportunity_type': signal['opportunity_type'],
        'risk_score': signal['risk_score'],
        'atr': signal['atr'],
        'close_price': signal['close_price'],
        'is_provisional_bar': signal['is_provisional_bar'],
        'has_upcoming_earnings': signal['has_upcoming_earnings'],
        'invalidation_price': signal['invalidation_price'],
        'invalidation_reason': signal['invalidation_reason'],
        'target_price': signal['target_price'],
        'target_reason': signal['target_reason'],
        'model_version': 'v5.1.1_rule_based',
        # [NUOVO 01/10 - persistenza indicatori] colonne gia' esistenti ma mai scritte
        'rsi': _fit_numeric(ind.get('rsi'), 6, 3),
        'macd': _fit_numeric(ind.get('macd'), 10, 5),
        'macd_signal': _fit_numeric(ind.get('macd_signal'), 10, 5),
        'bb_position': _fit_numeric(ind.get('bb_position'), 6, 4),
        # colonne nuove
        'score_total': signal.get('score_total'),
        'score_rsi': signal.get('score_rsi'),
        'score_macd': signal.get('score_macd'),
        'score_bb': signal.get('score_bb'),
        'score_sentiment': signal.get('score_sentiment'),
        'score_context': signal.get('score_context'),
        'sentiment_value': signal.get('sentiment_value'),
        'context_score': signal.get('context_score'),
        'news_light_count': signal.get('news_light_count'),
        'bb_lower': ind.get('bb_lower'),
        'bb_upper': ind.get('bb_upper'),
        'daily_close': ind.get('daily_close'),
        'daily_bar_date': ind.get('daily_bar_date'),
        'daily_bars_used': ind.get('daily_bars_used'),
        'decision_detail': signal.get('decision_detail'),
    }


def write_signal(ticker, candidate_id, signal):
    try:
        res = supabase.table('signals_raw').insert(build_raw_row(ticker, candidate_id, signal)).execute()
        # [FIX 30/09 - handoff Codex] Scritto = il DB ha restituito un id.
        if not getattr(res, 'data', None) or not res.data[0].get('id'):
            print(f"❌ Scrittura signals_raw {ticker} non confermata dal DB (nessun id restituito)")
            return False
        flag = " (barra provvisoria)" if signal['is_provisional_bar'] else ""
        print(f"✅ {ticker}: {signal['action']} [{signal['opportunity_type']}] "
              f"conf={signal['confidence_level']}{flag}")
        return True
    except Exception as e:
        print(f"❌ Errore scrittura segnale {ticker}: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--market', choices=['ALL', 'USA', 'EU'], default='ALL')
    parser.add_argument('--force-reprocess', action='store_true',
                         help='Rianalizza candidati già processati (usato da sapta_us_close.yml)')
    args = parser.parse_args()

    print(f"🚀 Modulo B - Analysis ({args.market}): {datetime.now(timezone.utc).isoformat()}")

    candidates = get_candidates(args.market, args.force_reprocess)
    if not candidates:
        print("⚠️ Nessun candidato da analizzare (H2 non ha promosso nulla, o già tutto processato)")

    # [NUOVO 24/09 - causa radice 2] Un solo giro di chiamate batch
    # all'inizio del run invece di una yf.download per candidato dentro il
    # loop: vedi fetch_daily_batch() per il motivo (rate-limit Yahoo su IP
    # datacenter). Anche a run vuoto la chiamata è innocua (lista vuota).
    daily_data = fetch_daily_batch([c['ticker'] for c in candidates])

    # [NUOVO 22/09 - audit] Contatori diagnostici: rispondono a "zero
    # segnali perché non c'erano opportunità" vs "zero segnali perché la
    # pipeline è bloccata da qualche parte" (Sezione 13 addendum audit).
    n_totale = len(candidates)
    n_no_indicators = 0
    n_deterioramento = 0
    n_signal_written = 0
    n_write_failed = 0

    for candidate in candidates:
        ticker = candidate['ticker']
        print(f"\n📊 Analisi {ticker} (context_score={candidate.get('context_score')}, "
              f"news_light_count={candidate.get('news_light_count')})...")

        indicators = calculate_technical_indicators(ticker, daily_data.get(ticker))
        if not indicators:
            # [FIX 30/09 - handoff Codex] Errore tecnico: NON marcare processato,
            # il candidato viene ritentato al run successivo.
            n_no_indicators += 1
            continue

        cached = get_cached_news(ticker)
        if cached:
            sentiment = sum(n['sentiment_score'] for n in cached) / len(cached)
        else:
            articles = fetch_news(ticker, NEWSAPI_KEY)
            sentiment = analyze_sentiment(ticker, articles)

        earnings_soon = has_upcoming_earnings(ticker)

        signal = generate_signal(
            indicators, sentiment,
            candidate.get('context_score'),
            candidate.get('news_light_count'),
            earnings_soon
        )

        if signal['opportunity_type'] == 'deterioramento_strutturale':
            # Scarto STRATEGICO: decisione prevista dalla strategia, si marca processato.
            n_deterioramento += 1
            try:
                supabase.table('screening_candidates').update({
                    'status': 'scartato_deterioramento'
                }).eq('id', candidate['id']).execute()
                print(f"🗑️ {ticker}: scartato come deterioramento strutturale (Sezione 8.4)")
            except Exception as e:
                print(f"⚠️ Errore aggiornamento status per {ticker}: {e}")
        else:
            if not write_signal(ticker, candidate['id'], signal):
                # Scrittura fallita: NON marcare processato, retry al prossimo run.
                n_write_failed += 1
                continue
            n_signal_written += 1
            run_ai_agent(ticker, indicators, sentiment, candidate.get('context_score'),
                         candidate.get('news_light_count'), earnings_soon)
            # [FIX 26/09] Pausa dopo ogni chiamata Gemini: la stessa chiave è
            # condivisa con AI Watch, Briefing e la Chat AI interattiva della
            # dashboard (dashboard/chat.php) - segnalato dall'utente come
            # "la chat finisce subito i token/quota". Senza pausa, più segnali
            # scritti nello stesso run chiamano Gemini a raffica (stesso
            # difetto già corretto per yf.download in fetch_daily_batch),
            # consumando la quota al minuto prima che l'utente apra la chat.
            time.sleep(GEMINI_CALL_SLEEP_SECONDS)

        if not args.force_reprocess:
            mark_processed(candidate['id'])

    print(f"\n📋 Riepilogo run: {n_totale} candidati letti · "
          f"{n_no_indicators} scartati per indicatori tecnici non disponibili (yfinance) · "
          f"{n_deterioramento} scartati per deterioramento strutturale · "
          f"{n_signal_written} segnali scritti su signals_raw · "
          f"{n_write_failed} scritture fallite (da ritentare)")
    if n_totale > 0 and n_signal_written == 0:
        print("⚠️ ATTENZIONE: nessun segnale scritto in questo run nonostante candidati presenti - "
              "controllare la riga 'scartati per indicatori tecnici' qui sopra. Se tutti i candidati "
              "sono finiti lì, probabile rate-limit Yahoo Finance (vedi fetch_daily_batch), non assenza di opportunità")
