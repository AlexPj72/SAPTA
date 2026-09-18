"""
Modulo AI Watch (NUOVO 18/09): valutazione qualitativa sotto-soglia + alert

Risponde alla richiesta esplicita dell'utente: H1 (vedi modulo_h_anomaly.py)
scatta solo con volume_ratio>=3.0 E price_change>=1.5% insieme - un titolo
che si muove parecchio ma non supera ENTRAMBE le soglie non genera nulla.
Questo modulo guarda TUTTI i ticker con dati sufficienti (stessa metrica di
H1: volume_ratio e price_change sugli stessi bar 15m), senza soglia rigida,
e lascia a Gemini il giudizio qualitativo su cosa merita attenzione.

Agganciato allo stesso step del workflow fast (ogni 15 minuti, 9-17 UTC
Lun-Ven) - stessa richiesta dell'utente ("solo quando ci sono dati nuovi,
solo a mercati aperti"), zero schedulazioni/costi aggiuntivi.

Un solo alert per ticker al giorno (vincolo unique ticker+data su
ai_hypotheses) - se un titolo resta interessante per ore, non spamma.
Non e' una previsione: e' un'ipotesi qualitativa, dichiarata come tale
anche nei messaggi di alert.

Canali di alert, entrambi opzionali/fail-open (se le credenziali mancano,
salta quel canale con un warning, non blocca il resto):
- Telegram (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- Email SMTP (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, ALERT_EMAIL_TO)
"""
import os
import json
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timezone
import requests
from config import supabase, GEMINI_API_KEY
from universe import get_universe

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent"
H1_BARS_LOOKBACK = 20
H1_MIN_BARS_FOR_BASELINE = 8

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587") or 587)
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")

DASHBOARD_BASE_URL = "https://www.pujia.it/sapta"


def get_universe_metrics():
    """Stessa metrica di H1 (volume_ratio, price_change su bar 15m), ma per
    OGNI ticker con dati sufficienti - non solo quelli sopra soglia."""
    try:
        response = (supabase.table('prezzi')
                    .select('ticker,timestamp,close,volume,data_quality_flag')
                    .eq('interval', '15m')
                    .order('timestamp', desc=True)
                    .limit(5000)
                    .execute())
    except Exception as e:
        print(f"⚠️ Errore lettura prezzi 15m: {e}")
        return []

    by_ticker = {}
    for row in response.data or []:
        t = row.get('ticker')
        if not t:
            continue
        by_ticker.setdefault(t, [])
        if len(by_ticker[t]) < H1_BARS_LOOKBACK:
            by_ticker[t].append(row)

    sectors_resp = supabase.table('ticker_sectors').select('ticker,sector').execute()
    sector_map = {r['ticker']: r.get('sector') or '—' for r in (sectors_resp.data or [])}

    metrics = []
    for t, bars in by_ticker.items():
        if len(bars) < H1_MIN_BARS_FOR_BASELINE:
            continue
        last_bar = bars[0]
        if last_bar.get('data_quality_flag') not in (None, 'ok'):
            continue  # stessa regola di H1: scarta se l'ultima barra non è affidabile (es. mercato chiuso)
        baseline = bars[1:]
        avg_vol = sum((b.get('volume') or 0) for b in baseline) / len(baseline) if baseline else 0
        if not avg_vol or last_bar.get('close') is None or baseline[-1].get('close') is None:
            continue
        ref_close = baseline[-1]['close']  # barra più vecchia del set = riferimento, come in H1
        price_change_pct = (last_bar['close'] / ref_close - 1) * 100 if ref_close else 0
        volume_ratio = (last_bar.get('volume') or 0) / avg_vol
        metrics.append({
            'ticker': t,
            'sector': sector_map.get(t, '—'),
            'volume_ratio': round(volume_ratio, 2),
            'price_change_pct': round(price_change_pct, 2),
        })
    return metrics


def already_flagged_today(ticker, today):
    try:
        rows = supabase.table('ai_hypotheses').select('id').eq('ticker', ticker).eq('hypothesis_date', today).execute()
        return len(rows.data or []) > 0
    except Exception as e:
        print(f"⚠️ Errore controllo duplicati per {ticker}: {e}")
        return False  # fail-open: in dubbio, valuta comunque (l'unique index sul DB fa comunque da rete di sicurezza)


def call_gemini_watch(metrics):
    if not GEMINI_API_KEY or not metrics:
        return []
    lines = [f"{m['ticker']} | settore={m['sector']} | volume_ratio={m['volume_ratio']}x | var={m['price_change_pct']}%"
             for m in metrics]
    prompt = (
        "Sei un analista che monitora un radar di anomalie di mercato ogni 15 minuti.\n"
        "H1 (regola rigida) segnala solo se volume_ratio>=3.0 E variazione>=1.5% insieme.\n"
        "Qui hai TUTTI i ticker con dati sufficienti, comprese le anomalie 'deboli' che H1 scarta:\n\n"
        + "\n".join(lines) +
        "\n\nSegnala SOLO i ticker che secondo il tuo giudizio meritano attenzione "
        "anche se non superano la soglia rigida (es. variazione consistente con volume "
        "anche solo lievemente sopra la norma, o viceversa). Sii selettivo: se oggi non "
        "c'è nulla di interessante, rispondi con un array vuoto - non forzare segnalazioni.\n"
        "Rispondi SOLO con un array JSON, nessun altro testo:\n"
        '[{"ticker": "XXX", "livello": "alto|medio", "motivazione": "..."}]'
    )
    try:
        r = requests.post(
            GEMINI_API_URL,
            headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=45,
        )
        r.raise_for_status()
        content = r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        content = content.replace('```json', '').replace('```', '').strip()
        return json.loads(content)
    except Exception as e:
        print(f"⚠️ Errore chiamata Gemini (AI Watch): {e}")
        return []


def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": True},
            timeout=15,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"⚠️ Errore invio Telegram: {e}")
        return False


def send_email(subject, body):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and ALERT_EMAIL_TO):
        return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = SMTP_USER
        msg['To'] = ALERT_EMAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, [ALERT_EMAIL_TO], msg.as_string())
        return True
    except Exception as e:
        print(f"⚠️ Errore invio email: {e}")
        return False


def run_ai_watch():
    print("👁️ Modulo AI Watch: avvio...")
    metrics = get_universe_metrics()
    if not metrics:
        print("   Nessun ticker con dati sufficienti, uscita.")
        return

    today = datetime.now(timezone.utc).date().isoformat()
    metrics = [m for m in metrics if not already_flagged_today(m['ticker'], today)]
    if not metrics:
        print("   Tutti i ticker con dati sufficienti sono già stati segnalati oggi.")
        return

    flagged = call_gemini_watch(metrics)
    if not flagged:
        print("   Nessuna ipotesi interessante in questo giro.")
        return

    metrics_by_ticker = {m['ticker']: m for m in metrics}
    new_items = []
    for item in flagged:
        ticker = (item.get('ticker') or '').strip()
        m = metrics_by_ticker.get(ticker)
        if not m:
            continue  # Gemini ha citato un ticker fuori dalla lista fornita: ignorato, mai inventare
        try:
            supabase.table('ai_hypotheses').insert({
                'hypothesis_date': today,
                'ticker': ticker,
                'motivazione': item.get('motivazione', ''),
                'livello': item.get('livello', 'medio'),
                'volume_ratio': m['volume_ratio'],
                'price_change_pct': m['price_change_pct'],
            }).execute()
            new_items.append({**item, **m})
        except Exception as e:
            # L'unique index (ticker, hypothesis_date) fa da rete di sicurezza anti-duplicati
            print(f"⚠️ {ticker} non inserito (probabile duplicato già presente oggi): {e}")

    if not new_items:
        print("   Nessuna nuova ipotesi da notificare (tutte già presenti).")
        return

    print(f"   {len(new_items)} nuova/e ipotesi da notificare")
    lines = [f"• *{i['ticker']}* ({i['livello']}): {i['motivazione']} "
             f"[var {i['price_change_pct']}%, vol {i['volume_ratio']}x] "
             f"— {DASHBOARD_BASE_URL}/grafico.php?ticker={i['ticker']}"
             for i in new_items]
    header = "📡 SAPTA — Ipotesi qualitativa IA (sotto soglia H1, NON una previsione):\n\n"
    message = header + "\n".join(lines)

    tg_ok = send_telegram(message)
    email_ok = send_email("SAPTA - Nuove ipotesi da valutare", message.replace('*', ''))
    print(f"   Telegram: {'inviato' if tg_ok else 'saltato/fallito'} · Email: {'inviata' if email_ok else 'saltata/fallita'}")

    if tg_ok or email_ok:
        for i in new_items:
            try:
                supabase.table('ai_hypotheses').update({
                    'alerted_telegram': tg_ok, 'alerted_email': email_ok
                }).eq('ticker', i['ticker']).eq('hypothesis_date', today).execute()
            except Exception:
                pass

    print("✅ AI Watch completato")


if __name__ == "__main__":
    run_ai_watch()
