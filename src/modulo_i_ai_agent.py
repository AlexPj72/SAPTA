"""
Modulo I: AI Reasoning Agent (SAPTA v4, §3)
Riceve gli stessi dati grezzi del Modulo B (prezzo, indicatori tecnici, ATR,
sentiment aggregato, news recenti) ma ragiona in autonomia via LLM, senza
passare dalla logica di scoring rule-based/XGBoost di SAPTA.

Motore: Gemini API (Google), modello Flash Lite per restare comodamente
dentro il tier gratuito (RPD 500, vedi verifica manuale su
https://aistudio.google.com/rate-limit).

Nota autenticazione (2026): le chiavi Gemini generate oggi sono in formato
"AQ." (Auth key), non piu' "AIza..." (Standard key, dismesse da Google a
partire da settembre 2026). Le chiavi AQ. si passano nell'header HTTP
`x-goog-api-key`, NON nel query param `?key=...` (quello e' il metodo
legacy, valido solo per le vecchie chiavi AIza).

Esecuzione: stesso workflow "slow", dopo il Modulo B (da cui riusa i dati
gia' calcolati). Scrive in una nuova tabella `ai_agent_decisions`.
"""
import os
import json
import time
from datetime import datetime, timezone

import requests

from config import supabase, TICKERS

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

PROMPT_TEMPLATE = """Sei un analista finanziario. Ricevi dati grezzi di mercato per un titolo.
Ragiona in autonomia, SENZA applicare regole fisse tipo soglie RSI 30/70 o
incroci MACD standard: usa il tuo giudizio complessivo sui dati forniti.

Dati:
- Ticker: {ticker}
- Prezzo attuale: {close}
- RSI(14): {rsi}
- MACD: {macd} (signal: {macd_signal})
- Posizione nelle Bollinger Bands (0=banda bassa, 1=banda alta): {bb_position}
- ATR(14): {atr}
- Sentiment news aggregato (-1 molto negativo, +1 molto positivo): {sentiment}

Rispondi SOLO in formato JSON valido, senza markdown, senza testo fuori dal JSON,
con questa struttura esatta:
{{
  "decision": "BUY" | "SELL" | "HOLD",
  "confidence": <numero da 0.0 a 1.0>,
  "reasoning": "<motivazione testuale completa e onesta, anche se incerta>"
}}
"""


def build_prompt(ticker, indicators, sentiment):
    return PROMPT_TEMPLATE.format(
        ticker=ticker,
        close=indicators["close"],
        rsi=round(indicators["rsi"], 2),
        macd=round(indicators["macd"], 4),
        macd_signal=round(indicators["macd_signal"], 4),
        bb_position=round(indicators["bb_position"], 3),
        atr=round(indicators["atr"], 4),
        sentiment=round(sentiment, 3),
    )


def call_gemini(prompt, max_retries=2):
    """Chiama la Gemini API con la chiave AQ. via header x-goog-api-key.
    Ritorna il dict {decision, confidence, reasoning} oppure None in caso
    di errore persistente (fail-open: il ciclo prosegue senza bloccarsi,
    stesso principio gia' usato nel controllo di concentrazione settoriale
    del Modulo E, v3.2)."""
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY non configurata, salto il Modulo I per questo ciclo")
        return None

    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    for attempt in range(max_retries + 1):
        try:
            r = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=20)

            if r.status_code == 429:
                # Rate limit (RPM/RPD) raggiunto: non ha senso ritentare subito
                print(f"⚠️ Rate limit Gemini raggiunto (429), salto questo ticker")
                return None

            r.raise_for_status()
            data = r.json()

            text = data["candidates"][0]["content"]["parts"][0]["text"]
            # Il modello a volte avvolge il JSON in ```json ... ``` nonostante
            # l'istruzione di non farlo: ripulisco prima di parsare.
            cleaned = text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("```")[1]
                cleaned = cleaned.replace("json", "", 1).strip()

            parsed = json.loads(cleaned)

            decision = parsed.get("decision", "HOLD").upper()
            if decision not in ("BUY", "SELL", "HOLD"):
                decision = "HOLD"

            return {
                "decision": decision,
                "confidence": float(parsed.get("confidence", 0.5)),
                "reasoning": parsed.get("reasoning", ""),
            }

        except (KeyError, IndexError, json.JSONDecodeError) as e:
            print(f"⚠️ Risposta Gemini non parsabile (tentativo {attempt + 1}): {e}")
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Errore chiamata Gemini (tentativo {attempt + 1}): {e}")
            time.sleep(1)

    return None


def get_latest_signal_data(ticker):
    """Legge da signals_raw i dati gia' calcolati dal Modulo B per questo
    ticker nel ciclo corrente, cosi' il Modulo I non ricalcola nulla e non
    fa query aggiuntive costose."""
    try:
        response = (
            supabase.table("signals_raw")
            .select("*")
            .eq("ticker", ticker)
            .order("timestamp", desc=True)
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"⚠️ Errore lettura signals_raw per {ticker}: {e}")
        return None


def get_recent_sentiment(ticker):
    """Legge il sentiment aggregato piu' recente dalla tabella news (stesso
    dato gia' usato dal Modulo B), per non ricalcolarlo ne' richiamare la
    HuggingFace Inference API una seconda volta."""
    try:
        response = (
            supabase.table("news")
            .select("sentiment_score")
            .contains("related_tickers", [ticker])
            .order("timestamp", desc=True)
            .limit(10)
            .execute()
        )
        scores = [n["sentiment_score"] for n in (response.data or []) if n.get("sentiment_score") is not None]
        return sum(scores) / len(scores) if scores else 0.0
    except Exception as e:
        print(f"⚠️ Errore lettura sentiment per {ticker}: {e}")
        return 0.0


def write_decision_to_supabase(ticker, market, decision_data):
    """Scrive la decisione dell'agente AI in ai_agent_decisions (§10.3bis)."""
    try:
        supabase.table("ai_agent_decisions").insert({
            "ticker": ticker,
            "market": market,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_used": GEMINI_MODEL,
            "ai_decision": decision_data["decision"],
            "ai_confidence": decision_data["confidence"],
            "ai_reasoning": decision_data["reasoning"],
        }).execute()
        print(
            f"✅ {ticker}: {decision_data['decision']} "
            f"(confidence={decision_data['confidence']:.2f})"
        )
    except Exception as e:
        print(f"❌ Errore scrittura decisione AI per {ticker}: {e}")


def run(tickers=None):
    tickers_to_process = tickers or TICKERS
    print(f"🚀 Modulo I - AI Reasoning Agent ({GEMINI_MODEL}): "
          f"{datetime.now(timezone.utc).isoformat()}")

    for ticker in tickers_to_process:
        signal_row = get_latest_signal_data(ticker)
        if not signal_row or signal_row.get("atr") is None or signal_row.get("close_price") is None:
            print(f"⚠️ {ticker}: nessun dato recente da signals_raw, salto")
            continue

        # rsi/macd/macd_signal/bb_position sono persistiti in signals_raw dal
        # Modulo B (vedi migration_modulo_i.sql + modulo_b_analysis.py
        # aggiornato). Se per qualche motivo mancano (es. segnale scritto da
        # una versione precedente dello script prima della migrazione), si
        # salta il ticker invece di ragionare su dati inventati.
        required = ("rsi", "macd", "macd_signal", "bb_position")
        if any(signal_row.get(f) is None for f in required):
            print(f"⚠️ {ticker}: signals_raw senza rsi/macd/bb_position "
                  f"(rilancia il Modulo B aggiornato dopo la migrazione), salto")
            continue

        indicators = {
            "close": signal_row["close_price"],
            "atr": signal_row["atr"],
            "rsi": signal_row["rsi"],
            "macd": signal_row["macd"],
            "macd_signal": signal_row["macd_signal"],
            "bb_position": signal_row["bb_position"],
        }
        sentiment = get_recent_sentiment(ticker)

        prompt = build_prompt(ticker, indicators, sentiment)
        decision_data = call_gemini(prompt)

        if decision_data:
            market = "USA" if not ticker.endswith((".MI", ".T", ".HK", ".SS", ".NS", ".KS")) else "EU/ASIA"
            write_decision_to_supabase(ticker, market, decision_data)
        else:
            print(f"⚠️ {ticker}: nessuna decisione ottenuta da Gemini in questo ciclo")


if __name__ == "__main__":
    run()
