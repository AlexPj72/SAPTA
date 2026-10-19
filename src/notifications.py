"""
Notifiche operative di SAPTA (Telegram + email). Usate dal Modulo T per COMPRA ORA / VENDI ORA (PAPER).

Questo modulo NON legge ne' scrive il database e non decide nulla: costruisce i testi (specifica v0.3, §7) e li invia.
La gestione di duplicati, ritentativi e scadenza degli alert e' nel Modulo T (tabella trade_alerts).
Le credenziali si leggono al momento dell'invio (non all'import).
"""
import re
import os
import smtplib
from datetime import date, datetime, timezone
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo

import requests


def _fromiso(s):
    """fromisoformat tollerante: Python <3.11 accetta solo 3 o 6 cifre di frazione."""
    s = str(s).replace('Z', '+00:00')
    s = re.sub(r'\.(\d{1,6})\d*', lambda m: '.' + m.group(1).ljust(6, '0'), s, count=1)
    return datetime.fromisoformat(s)


ROME = ZoneInfo('Europe/Rome')
DEFAULT_DASHBOARD_BASE_URL = "https://www.pujia.it/sapta"        # stesso valore usato dagli alert di AI Watch

SENT, FAILED, NOT_CONFIGURED = 'SENT', 'FAILED', 'NOT_CONFIGURED'


def send_telegram(text):
    """Ritorna (stato, errore). Ok solo se Telegram risponde HTTP 200 E ok=true."""
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return NOT_CONFIGURED, 'TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID non configurati'
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=15)
        try:
            body = r.json()
        except Exception:
            body = {}
        if r.status_code == 200 and body.get("ok"):
            return SENT, None
        return FAILED, f"HTTP {r.status_code} {str(body.get('description') or r.text)[:200]}"
    except Exception as exc:
        return FAILED, f"{type(exc).__name__}: {str(exc)[:200]}"


def send_email(subject, body):
    host, user, pwd = os.getenv("SMTP_HOST", ""), os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", "")
    to = os.getenv("ALERT_EMAIL_TO", "")
    if not (host and user and pwd and to):
        return NOT_CONFIGURED, 'SMTP_HOST/SMTP_USER/SMTP_PASSWORD/ALERT_EMAIL_TO non configurati'
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"], msg["From"], msg["To"] = subject, user, to
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587") or 587), timeout=20) as server:
            server.starttls()
            server.login(user, pwd)
            server.sendmail(user, [to], msg.as_string())
        return SENT, None
    except Exception as exc:
        return FAILED, f"{type(exc).__name__}: {str(exc)[:200]}"


# ---------------------------------------------------------------- formattazione (italiano)
def _num(x, decimals):
    return f"{float(x):,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_price(x, currency):
    x = float(x)
    d = 2 if abs(x) >= 10 else (3 if abs(x) >= 1 else 4)
    return f"{_num(x, d)} {'$' if currency == 'USD' else '€'}"


def _hhmm(ts):
    if ts is None:
        return '?'
    if not isinstance(ts, datetime):
        ts = _fromiso(ts)
    return ts.astimezone(ROME).strftime('%H:%M')


def _ddmm(d):
    d = d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
    return d.strftime('%d/%m')


def _shares(q):
    q = float(q)
    n = int(q) if q == int(q) else q
    return f"{n} {'azione' if n == 1 else 'azioni'}"


def dashboard_url(ticker):
    base = os.getenv("DASHBOARD_BASE_URL", DEFAULT_DASHBOARD_BASE_URL).rstrip('/')
    return f"{base}/grafico.php?ticker={ticker}"


def _timing_line(bar_end, detected_at, delay):
    return (f"Candela 15m chiusa alle {_hhmm(bar_end)} · rilevata alle {_hhmm(detected_at)} · "
            f"ritardo {int(delay or 0)} min (ora italiana).")


EXIT_TEXT = {'STOP': 'STOP TOCCATO', 'TARGET': 'TARGET RAGGIUNTO', 'TEMPO': 'TEMPO MASSIMO (5 SEDUTE)',
             'SEGNALE': 'SEGNALE SELL DI SAPTA'}


def build_buy_alert(lc):
    cur = lc['currency']
    market = 'USA' if lc['market'] == 'USA' else 'Italia'
    subject = f"SAPTA — COMPRA ORA — {lc['ticker']}"
    text = "\n".join([
        f"🟢 COMPRA ORA · {lc['ticker']} ({market})",
        f"Acquista {_shares(lc['quantity'])} a circa {fmt_price(lc['entry_fill_price'], cur)} "
        f"(non pagare più di {fmt_price(lc['zone_high'], cur)}).",
        f"Controvalore ≈ {_num(lc['countervalue_eur'], 0)} € · Stop {fmt_price(lc['invalidation_price'], cur)} · "
        f"Target {fmt_price(lc['target_price'], cur)}",
        f"Uscita a tempo massimo: {_ddmm(lc['planned_time_exit_date'])} a fine seduta.",
        _timing_line(lc.get('trigger_bar_end'), lc.get('trigger_detected_at'), lc.get('trigger_delay_minutes')),
        "Prezzo = chiusura di quella candela, non prezzo attuale. Posizione virtuale (PAPER): nessun ordine reale.",
        dashboard_url(lc['ticker']),
    ])
    return subject, text


def build_sell_alert(lc):
    cur = lc['currency']
    reason = EXIT_TEXT.get(lc.get('exit_reason'), str(lc.get('exit_reason')))
    entry, exit_ = float(lc['entry_fill_price']), float(lc['exit_price'])
    per_share = exit_ - entry
    sign = '+' if per_share >= 0 else '−'
    subject = f"SAPTA — VENDI ORA — {lc['ticker']}"
    text = "\n".join([
        f"🔴 VENDI ORA · {lc['ticker']} — motivo: {reason}",
        f"Posizione virtuale (PAPER) chiusa a circa {fmt_price(exit_, cur)} (ingresso {fmt_price(entry, cur)}).",
        f"Risultato: {sign}{_num(abs(per_share), 2)} {'$' if cur == 'USD' else '€'} per azione "
        f"({sign}{_num(abs(float(lc['pnl_pct'])), 1)}%) ≈ {'+' if float(lc['pnl_eur']) >= 0 else '−'}{_num(abs(float(lc['pnl_eur'])), 2)} € "
        f"su {_shares(lc['quantity'])}.",
        _timing_line(lc.get('exit_bar_end'), lc.get('exit_detected_at'), lc.get('exit_delay_minutes')),
        "Nessun ordine reale.",
        dashboard_url(lc['ticker']),
    ])
    return subject, text


def build_test_alert(now=None):
    now = now or datetime.now(timezone.utc)
    return ("SAPTA — TEST NOTIFICHE",
            f"🧪 SAPTA — TEST NOTIFICHE ({_hhmm(now)} ora italiana)\n"
            "Nessuna azione richiesta: se leggi questo messaggio il canale funziona.\n"
            "PAPER: nessun ordine reale.")
