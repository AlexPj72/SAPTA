"""
Modulo Briefing: shortlist pre-apertura (NUOVO 17/09)

Risponde alla richiesta esplicita dell'utente di un "briefing" mattutino che
proponga titoli da osservare per la giornata - ESPLICITAMENTE NON una
previsione di prezzo (chiarito più volte con l'utente, vedi
SAPTA_v5_1_1_STATO_IMPLEMENTAZIONE.md sezione 0/11): è un'ipotesi
qualitativa ragionata, nello stile di una nota mattutina di un analista,
non validata da backtest, che l'utente valuta con la propria testa.

Come funziona (una volta al giorno, prima dell'apertura):
1. Legge per ogni ticker dell'universo: variazione 1gg/5gg da 'prezzi'
   (interval=1d), settore da ticker_sectors.
2. GDELT tone per paese (Italia/USA, 2 chiamate totali - stessa funzione
   concettuale di modulo_h_anomaly.py, duplicata qui per restare uno script
   indipendente e non introdurre un import incrociato tra moduli).
3. 1 sola chiamata NewsAPI per gli headline macro del giorno (non per
   ticker - eviterebbe di bruciare la quota free/100gg che Modulo B già usa).
4. Earnings entro 1 giorno (yfinance), per segnalare titoli con un
   catalizzatore noto.
5. UNA sola chiamata Gemini con tutto il contesto in tabella compatta,
   che restituisce una shortlist JSON con motivazione per ciascun titolo.
6. Scrive su 'daily_briefing' (una riga per ticker in shortlist, per data).

Fail-open ovunque possibile: un ticker/paese/fonte che fallisce viene
saltato con un dato neutro, non blocca l'intero briefing.
"""
import os
import sys
import time
import json
import requests
from datetime import datetime, timedelta, timezone
import yfinance as yf
from config import supabase, NEWSAPI_KEY, GEMINI_API_KEY
from universe import get_universe, get_universe_metadata

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"
BRIEFING_TOP_N = 8
EARNINGS_HORIZON_DAYS = 1

_GDELT_CACHE = {}


def fetch_gdelt_tone(country):
    """Stessa logica di modulo_h_anomaly.py::fetch_gdelt_tone - fail-open a 0.0."""
    if country in _GDELT_CACHE:
        return _GDELT_CACHE[country]
    try:
        r = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": f"{country} economy", "mode": "timelinetone", "format": "json", "timespan": "7d"},
            timeout=10,
        )
        r.raise_for_status()
        points = r.json()["timeline"][0]["data"]
        values = [p["value"] for p in points if p.get("value") is not None]
        tone = sum(values) / len(values) if values else 0.0
        score = max(-1.0, min(1.0, tone / 10.0))
        _GDELT_CACHE[country] = score
        return score
    except Exception as e:
        print(f"⚠️ GDELT non disponibile per {country}: {e}")
        _GDELT_CACHE[country] = 0.0
        return 0.0


def fetch_macro_headlines(api_key, max_headlines=6):
    """Una sola chiamata NewsAPI per titoli macro/business del giorno -
    non per ticker, per non consumare la quota free (100/gg) già usata
    da Modulo B. Fail-open: nessuna chiave o errore -> lista vuota."""
    if not api_key:
        return []
    try:
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"category": "business", "language": "en", "pageSize": max_headlines, "apiKey": api_key},
            timeout=10,
        )
        r.raise_for_status()
        return [a.get("title", "") for a in r.json().get("articles", []) if a.get("title")]
    except Exception as e:
        print(f"⚠️ Errore NewsAPI (headline macro): {e}")
        return []


def get_daily_changes():
    """Una sola query su 'prezzi' (1d) per tutto l'universo invece di una
    per ticker: legge le ultime 6 barre giornaliere disponibili e calcola
    variazione 1gg e 5gg lato Python."""
    try:
        response = (supabase.table('prezzi')
                    .select('ticker,timestamp,close')
                    .eq('interval', '1d')
                    .order('timestamp', desc=True)
                    .limit(20000)
                    .execute())
    except Exception as e:
        print(f"⚠️ Errore lettura prezzi giornalieri: {e}")
        return {}

    by_ticker = {}
    for row in response.data or []:
        t = row.get('ticker')
        if not t or row.get('close') is None:
            continue
        by_ticker.setdefault(t, [])
        if len(by_ticker[t]) < 6:
            by_ticker[t].append(float(row['close']))

    changes = {}
    for t, closes in by_ticker.items():
        if len(closes) < 2:
            continue
        chg_1d = (closes[0] / closes[1] - 1) * 100
        chg_5d = (closes[0] / closes[-1] - 1) * 100 if len(closes) >= 5 else None
        changes[t] = {'chg_1d': round(chg_1d, 2), 'chg_5d': round(chg_5d, 2) if chg_5d is not None else None}
    return changes


def get_sectors():
    try:
        response = supabase.table('ticker_sectors').select('ticker,sector').execute()
        return {r['ticker']: r.get('sector') or '—' for r in (response.data or [])}
    except Exception as e:
        print(f"⚠️ Errore lettura settori: {e}")
        return {}


def has_earnings_soon(ticker, horizon_days=EARNINGS_HORIZON_DAYS):
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
    except Exception:
        return False  # fail-open, earnings non è il dato critico del briefing


def build_prompt(rows, headlines):
    lines = [f"{r['ticker']} | settore={r['sector']} | var1gg={r['chg_1d']}% | var5gg={r['chg_5d']}% "
             f"| gdelt_paese={r['gdelt']:.2f} | earnings_oggi={'sì' if r['earnings'] else 'no'}"
             for r in rows]
    headlines_txt = "\n".join(f"- {h}" for h in headlines) if headlines else "(nessun titolo macro disponibile oggi)"

    return f"""Sei un analista finanziario che scrive una nota mattutina pre-apertura.
Hai a disposizione SOLO i dati sotto (nessun altro dato, nessuna conoscenza
esterna su eventi specifici dei singoli titoli che non sia qui elencata).

Titoli macro/economici di oggi:
{headlines_txt}

Universo monitorato (variazioni giornaliere recenti, tono GDELT del paese
[-1 negativo, +1 positivo], earnings imminenti):
{chr(10).join(lines)}

Scegli i {BRIEFING_TOP_N} titoli più meritevoli di attenzione OGGI secondo
la tua analisi, spiegando il ragionamento in 1-2 frasi ciascuno in italiano.
Non stai prevedendo un rendimento preciso: stai segnalando dove il quadro
(trend recente + contesto macro/paese + eventuali earnings) rende la
giornata potenzialmente interessante da monitorare, in modo simile a una
nota di un analista - un'ipotesi ragionata, non una certezza.

Rispondi SOLO con un array JSON, nessun altro testo, in questo formato:
[{{"ticker": "XXX", "motivazione": "..."}}, ...]"""


def call_gemini(prompt, attempts=4, waits=(5, 15, 45)):
    """Chiamata Gemini con ritentativi (503/429/5xx, timeout, risposta non valida). Ritorna None solo se falliscono tutti."""
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY non configurata, briefing non generato")
        return None
    for n in range(1, attempts + 1):
        try:
            r = requests.post(
                GEMINI_API_URL,
                headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=45,
            )
            if r.status_code in (400, 401, 403, 404):      # errori non transitori: inutile ritentare
                r.raise_for_status()
            r.raise_for_status()
            content = r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            content = content.replace('```json', '').replace('```', '').strip()
            return json.loads(content)
        except Exception as e:
            code = getattr(getattr(e, 'response', None), 'status_code', None)
            print(f"⚠️ Errore chiamata Gemini per il briefing (tentativo {n}/{attempts}): {e}")
            if code in (400, 401, 403, 404) or n == attempts:
                return None
            time.sleep(waits[min(n - 1, len(waits) - 1)])
    return None


def run_briefing():
    print("📋 Modulo Briefing: avvio...")
    universe = get_universe()
    meta = get_universe_metadata()
    changes = get_daily_changes()
    sectors = get_sectors()
    headlines = fetch_macro_headlines(NEWSAPI_KEY)

    rows = []
    for ticker in universe:
        chg = changes.get(ticker)
        if not chg:
            continue
        country = "Italy" if meta[ticker]["market"] == "IT" else "United States"
        rows.append({
            'ticker': ticker,
            'sector': sectors.get(ticker, '—'),
            'chg_1d': chg['chg_1d'],
            'chg_5d': chg['chg_5d'],
            'gdelt': fetch_gdelt_tone(country),
            'earnings': has_earnings_soon(ticker),
        })

    if not rows:
        print("⚠️ Nessun dato di prezzo disponibile, briefing annullato")
        return False

    print(f"   {len(rows)} ticker con dati sufficienti, {len(headlines)} headline macro")
    prompt = build_prompt(rows, headlines)
    shortlist = call_gemini(prompt)
    if not shortlist:
        return False

    today = datetime.now(timezone.utc).date().isoformat()
    # Rimuove eventuale briefing già generato oggi (un solo run al giorno atteso,
    # ma idempotente in caso di rilancio manuale)
    try:
        supabase.table('daily_briefing').delete().eq('briefing_date', today).execute()
    except Exception as e:
        print(f"⚠️ Errore pulizia briefing precedente: {e}")

    scritti = 0
    for i, item in enumerate(shortlist[:BRIEFING_TOP_N], start=1):
        ticker = item.get('ticker', '').strip()
        if not ticker:
            continue
        row_data = next((r for r in rows if r['ticker'] == ticker), {})
        try:
            supabase.table('daily_briefing').insert({
                'briefing_date': today,
                'ticker': ticker,
                'rank': i,
                'motivazione': item.get('motivazione', ''),
                'chg_1d': row_data.get('chg_1d'),
                'chg_5d': row_data.get('chg_5d'),
                'gdelt_tone': row_data.get('gdelt'),
                'has_earnings': row_data.get('earnings', False),
                'generated_at': datetime.now(timezone.utc).isoformat(),
            }).execute()
            scritti += 1
            print(f"   {i}. {ticker}: {item.get('motivazione', '')[:80]}")
        except Exception as e:
            print(f"⚠️ Errore scrittura briefing per {ticker}: {e}")

    if scritti == 0:
        print("❌ Briefing non scritto: nessuna riga salvata")
        return False
    print("✅ Briefing completato")
    return True


if __name__ == "__main__":
    # Esce con errore se il briefing non e' stato scritto: cosi' il run diventa rosso e arriva l'email di GitHub
    sys.exit(0 if run_briefing() else 1)
