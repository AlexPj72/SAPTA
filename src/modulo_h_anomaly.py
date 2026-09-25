"""
Modulo H: Anomaly Radar v5.1.1 (H1 + H2)

H1 (workflow "fast", ogni 15 min): screening leggero su tutto l'universo
(128 ticker), zero chiamate esterne, solo query a 'prezzi' già scritto da A.
Scarta i ticker con dato sporco, promuove i migliori ~20-30 a
screening_candidates con status='h1_candidate'.

H2 (workflow "slow", ogni 30 min): rilegge i candidati H1 di oggi, calcola
anomaly_score pieno (soglie più severe), context_score versionato (Sezione 7)
e news_light_count (Google News RSS, Sezione 7 livello 1). Promuove i
migliori ~5-15 a status='promosso_a_B' (letti poi da Modulo B), scarta il
resto con status='scartato_h2'.

NOTA IMPORTANTE - dashboard PHP: questa riscrittura non scrive più sulla
tabella legacy 'anomalies' che la dashboard esistente legge. Finché la
dashboard non viene aggiornata per leggere da 'screening_candidates',
la sezione "Anomalie" della dashboard resterà vuota. Non è un bug di
questo script, è una conseguenza del cambio di modello (Sezione 16: non
più segnale secco, ma opportunità con score) - va pianificato a parte.
"""
import os
import re
import json
import argparse
from datetime import datetime, timezone
from urllib.parse import quote

import requests
import yfinance as yf
from config import supabase
from universe import get_universe

WEIGHTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scoring_weights_v1.json')
with open(WEIGHTS_PATH) as f:
    WEIGHTS = json.load(f)

SCORING_WEIGHTS_VERSION = WEIGHTS['version']
CONTEXT_WEIGHTS = WEIGHTS['context_weights']

# ---- H1: screening ampio, soglie permissive di proposito ----
H1_BARS_LOOKBACK = 20
H1_MIN_BARS_FOR_BASELINE = 8
H1_VOLUME_ANOMALY_THRESHOLD = 3.0
H1_PRICE_ANOMALY_THRESHOLD = 0.015
H1_TOP_N = 30

# ---- H2: soglie piene (stesse della v3.3 originale) ----
H2_VOLUME_ANOMALY_THRESHOLD = 5.0
H2_PRICE_ANOMALY_THRESHOLD = 0.03
H2_TOP_N = 15
H2_MIN_DAILY_BARS_FOR_TREND = 200  # serve SMA200

NEWS_RSS_TIMEOUT_SECONDS = 4
NEWS_RSS_URL = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"


def get_recent_bars(ticker, limit):
    try:
        response = (supabase.table('prezzi')
                    .select('timestamp, close, volume, data_quality_flag')
                    .eq('ticker', ticker)
                    .eq('interval', '15m')
                    .order('timestamp', desc=True)
                    .limit(limit)
                    .execute())
        return list(reversed(response.data)) if response.data else []
    except Exception as e:
        print(f"⚠️ Errore lettura prezzi intraday per {ticker}: {e}")
        return []


def get_ticker_meta_map():
    """Una sola query per tutti i 128 ticker, invece di 128 query separate."""
    try:
        response = supabase.table('ticker_sectors').select('ticker, sector, liquidity_bucket').execute()
        return {row['ticker']: row for row in (response.data or [])}
    except Exception as e:
        print(f"⚠️ Errore lettura ticker_sectors: {e}")
        return {}


def compute_intraday_anomaly(bars, volume_threshold, price_threshold):
    """Logica invariata dalla v3.3: volume ratio + variazione prezzo su barre intraday."""
    *baseline_bars, current_bar = bars
    try:
        current_volume = float(current_bar['volume'] or 0)
        current_close = float(current_bar['close'])
        baseline_volumes = [float(b['volume'] or 0) for b in baseline_bars]
        avg_volume = sum(baseline_volumes) / len(baseline_volumes) if baseline_volumes else 0
        if avg_volume == 0:
            return False, 0.0, 0.0

        volume_ratio = current_volume / avg_volume
        reference_close = float(baseline_bars[0]['close'])
        price_change = (current_close - reference_close) / reference_close

        is_anomaly = volume_ratio >= volume_threshold and abs(price_change) >= price_threshold
        return is_anomaly, volume_ratio, price_change
    except Exception:
        return False, 0.0, 0.0


# ============================================================
# H1
# ============================================================

def get_tickers_already_candidate_today():
    """[NUOVO 24/09 - causa radice 3] H1 girava ogni 15 min e inserzione un
    NUOVO record per lo stesso ticker ogni volta che ricompariva sopra
    soglia nello stesso giorno, invece di aggiornare quello già aperto.
    Risultato osservato in audit: lo stesso ticker (es. ISRG) con più righe
    nella stessa giornata, ciascuna con h1_score diverso (calcolato in
    momenti diversi) ma poi tutte processate da H2 che ricalcola
    anomaly_score sulle barre PIÙ RECENTI per ognuna - da cui righe
    "duplicate" con anomaly_score identico ma h1_score diverso, lette
    dal radar anomalie come se fossero metriche incoerenti tra loro
    (non lo sono: sono la stessa metrica calcolata in istanti diversi).
    Effetto collaterale: lo stesso ticker può finire promosso a B più
    volte nello stesso giorno, gonfiando il conteggio "promosso_a_B" senza
    reale beneficio. Fix: non re-inserire un ticker che ha già un
    candidato aperto oggi (h1_candidate o promosso_a_B, qualunque esito
    H2)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        response = (supabase.table('screening_candidates')
                    .select('ticker')
                    .gte('timestamp', today_start)
                    .in_('status', ['h1_candidate', 'promosso_a_B'])
                    .execute())
        return {row['ticker'] for row in (response.data or [])}
    except Exception as e:
        print(f"⚠️ Errore lettura candidati già aperti oggi: {e}")
        return set()


def run_h1():
    tickers = get_universe()
    meta_map = get_ticker_meta_map()
    already_candidate = get_tickers_already_candidate_today()
    candidates = []

    for ticker in tickers:
        if ticker in already_candidate:
            continue
        bars = get_recent_bars(ticker, H1_BARS_LOOKBACK)
        if len(bars) < H1_MIN_BARS_FOR_BASELINE:
            continue

        # [Sezione 7] scarto a monte se l'ultima barra ha qualità dato negativa
        last_flag = bars[-1].get('data_quality_flag')
        if last_flag not in (None, 'ok'):
            continue

        is_anomaly, volume_ratio, price_change = compute_intraday_anomaly(
            bars, H1_VOLUME_ANOMALY_THRESHOLD, H1_PRICE_ANOMALY_THRESHOLD
        )
        if not is_anomaly:
            continue

        h1_score = volume_ratio * abs(price_change) * 100
        meta = meta_map.get(ticker, {})
        candidates.append({
            'ticker': ticker,
            'h1_score': round(h1_score, 3),
            'data_quality_flag': last_flag or 'ok',
            'liquidity_bucket': meta.get('liquidity_bucket'),
        })

    candidates.sort(key=lambda c: c['h1_score'], reverse=True)
    top_candidates = candidates[:H1_TOP_N]

    now = datetime.now(timezone.utc).isoformat()
    for c in top_candidates:
        try:
            supabase.table('screening_candidates').insert({
                'ticker': c['ticker'],
                'timestamp': now,
                'h1_score': c['h1_score'],
                'data_quality_flag': c['data_quality_flag'],
                'liquidity_bucket': c['liquidity_bucket'],
                'status': 'h1_candidate',
            }).execute()
        except Exception as e:
            print(f"❌ Errore scrittura screening_candidates per {c['ticker']}: {e}")

    print(f"✅ H1: {len(candidates)} candidati grezzi trovati su {len(tickers)} ticker, "
          f"{len(top_candidates)} promossi a H2")


# ============================================================
# H2
# ============================================================

def fetch_news_light_count(ticker):
    """[Sezione 7, livello 1] Conteggio headline via Google News RSS.
    Fail-open: errore o timeout -> None, il ticker prosegue comunque (Sezione 19bis)."""
    url = NEWS_RSS_URL.format(query=quote(ticker))
    try:
        r = requests.get(url, timeout=NEWS_RSS_TIMEOUT_SECONDS)
        r.raise_for_status()
        return len(re.findall(r'<item>', r.text))
    except Exception as e:
        print(f"⚠️ RSS non disponibile per {ticker}: {e}")
        return None


_GDELT_COUNTRY_CACHE = {}  # cache per-run: evita chiamate ripetute per lo stesso paese

def fetch_gdelt_tone(country):
    """[GDELT - rischio geopolitico] Tono medio GDELT (DOC 2.0 API, gratis,
    nessuna chiave) sulle notizie economiche del paese, ultimi 7gg.
    Normalizzato da scala GDELT (-10/+10) a -1/+1. Una chiamata per paese
    per ciclo H2 (cache locale), non per ticker - i ticker .MI condividono
    'Italy', quelli USA 'United States'.
    Fail-open: errore/timeout -> 0.0 (neutro), non blocca H2."""
    if country in _GDELT_COUNTRY_CACHE:
        return _GDELT_COUNTRY_CACHE[country]

    try:
        r = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": f"{country} economy",
                "mode": "timelinetone",
                "format": "json",
                "timespan": "7d",
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        points = data["timeline"][0]["data"]
        values = [p["value"] for p in points if p.get("value") is not None]
        tone = sum(values) / len(values) if values else 0.0
        score = max(-1.0, min(1.0, tone / 10.0))
        _GDELT_COUNTRY_CACHE[country] = score
        return score
    except Exception as e:
        print(f"⚠️ GDELT non disponibile per {country}: {e}")
        _GDELT_COUNTRY_CACHE[country] = 0.0
        return 0.0


def get_country_for_ticker(ticker):
    """Mappatura minima ticker->paese, coerente con i due mercati coperti
    da universe.py (USA, IT). Da estendere se si aggiungono altri mercati."""
    return "Italy" if ticker.endswith(".MI") else "United States"


def compute_context_score(ticker):
    """
    [Sezione 7] Trend (SMA200, SMA50 vs SMA200) + distanza da massimi/minimi.
    Momentum e sector_relative restano fuori per ora (storico/confronto
    settoriale non ancora disponibili) - vedi nota in scoring_weights_v1.json.

    Scarica on-demand via yfinance SOLO per i ~20-30 candidati H1 (costo
    trascurabile, Sezione 19bis) - non l'intero universo. Da sostituire con
    lettura da 'prezzi' (interval='1d') quando lo storico bulk (STEP 11)
    sarà caricato, per evitare la chiamata yfinance ripetuta ogni ciclo.
    """
    try:
        df = yf.download(ticker, period="300d", interval="1d", auto_adjust=True, progress=False)
        if df.empty or len(df) < H2_MIN_DAILY_BARS_FOR_TREND:
            return None  # storico insufficiente per SMA200, non si inventa un valore

        close = df['Close']
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1])
        current = float(close.iloc[-1])

        trend_sma200 = 1.0 if current > sma200 else -1.0
        trend_sma50_vs_200 = 1.0 if sma50 > sma200 else -1.0

        window = close.tail(252) if len(close) >= 252 else close
        high_52w, low_52w = float(window.max()), float(window.min())
        span = high_52w - low_52w
        distance_norm = ((current - low_52w) / span * 2 - 1) if span > 0 else 0.0  # -1..+1

        gdelt_score = fetch_gdelt_tone(get_country_for_ticker(ticker))

        w = CONTEXT_WEIGHTS
        score = (
            w.get('trend_sma200', 0) * trend_sma200
            + w.get('trend_sma50_vs_200', 0) * trend_sma50_vs_200
            + w.get('distance_from_extremes', 0) * distance_norm
            + w.get('gdelt_tone', 0) * gdelt_score
        )
        return round(score, 4)
    except Exception as e:
        print(f"⚠️ Errore calcolo context_score per {ticker}: {e}")
        return None


def run_h2():
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    try:
        response = (supabase.table('screening_candidates')
                    .select('id, ticker')
                    .eq('status', 'h1_candidate')
                    .gte('timestamp', today_start)
                    .execute())
        rows = response.data or []
    except Exception as e:
        print(f"❌ Errore lettura screening_candidates: {e}")
        return

    if not rows:
        print("⚠️ Nessun candidato H1 da processare oggi")
        return

    enriched = []
    for row in rows:
        ticker = row['ticker']
        bars = get_recent_bars(ticker, H1_BARS_LOOKBACK)
        if len(bars) < H1_MIN_BARS_FOR_BASELINE:
            continue

        _, volume_ratio, price_change = compute_intraday_anomaly(
            bars, H2_VOLUME_ANOMALY_THRESHOLD, H2_PRICE_ANOMALY_THRESHOLD
        )
        anomaly_score = volume_ratio * abs(price_change) * 100

        context_score = compute_context_score(ticker)
        news_light_count = fetch_news_light_count(ticker)

        # Combinazione preliminare, NON la formula di ranking finale (quella
        # è compito del Modulo E/ranking, Sezione 16) - qui serve solo per
        # scegliere chi promuovere a B. Da validare col backtest (Sezione 22).
        combined_score = anomaly_score + (context_score or 0) * 10

        enriched.append({
            'id': row['id'],
            'ticker': ticker,
            'anomaly_score': round(anomaly_score, 3),
            'context_score': context_score,
            'news_light_count': news_light_count,
            'combined_score': combined_score,
        })

    enriched.sort(key=lambda c: c['combined_score'], reverse=True)
    promoted_ids = {c['id'] for c in enriched[:H2_TOP_N]}

    for c in enriched:
        status = 'promosso_a_B' if c['id'] in promoted_ids else 'scartato_h2'
        try:
            supabase.table('screening_candidates').update({
                'anomaly_score': c['anomaly_score'],
                'context_score': c['context_score'],
                'news_light_count': c['news_light_count'],
                'scoring_weights_version': SCORING_WEIGHTS_VERSION,
                'status': status,
            }).eq('id', c['id']).execute()
        except Exception as e:
            print(f"❌ Errore aggiornamento screening_candidates per {c['ticker']}: {e}")

    print(f"✅ H2: {len(enriched)} candidati processati, {len(promoted_ids)} promossi a Modulo B")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['h1', 'h2'], required=True)
    args = parser.parse_args()

    print(f"🚀 Modulo H ({args.stage.upper()}): {datetime.now(timezone.utc).isoformat()}")
    if args.stage == 'h1':
        run_h1()
    else:
        run_h2()
