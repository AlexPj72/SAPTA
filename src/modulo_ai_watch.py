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

[NUOVO 19/09 - ciclo di conferma] Un WATCH da solo non basta: il confronto
NFLX (movimento tenuto fino a chiusura) vs VZ (riassorbito quasi subito)
mostra che serve verificare la PERSISTENZA prima di dare peso a un'ipotesi.
Ad ogni run, prima di cercare nuove ipotesi, ricontrolla quelle già aperte
oggi (recheck_pending_hypotheses()): se il movimento ha tenuto/rinforzato
=> CONFERMATO (nuovo alert, più significativo); se si è riassorbito o
invertito => INVALIDATO (silenzioso, solo aggiornamento di stato); se resta
ambiguo per troppi giri => SCADUTO. Logica di confronto deterministica
(Python), non lasciata al giudizio libero di Gemini - stesso principio del
fix classify_anomaly() di oggi. Deliberatamente NON collegato a esecuzione
automatica di ordini: anche un'ipotesi CONFERMATA resta un'osservazione
qualitativa arricchita, non un ingresso operativo - quello resta compito
esclusivo della pipeline H1->H2->B->E con i suoi livelli calcolati sul serio.
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

# Stesse soglie esatte di modulo_h_anomaly.py (H1_VOLUME_ANOMALY_THRESHOLD,
# H1_PRICE_ANOMALY_THRESHOLD) - servono qui per ESCLUDERE dal giudizio
# qualitativo i ticker che le superano già entrambe: quelli sono compito di
# H1/H2 (pipeline rigida, con target/invalidazione veri), non di questo
# modulo. Prima di questo fix venivano inclusi comunque, causando frasi
# contraddittorie tipo "non supera la soglia" su variazioni che la
# superavano ampiamente (bug segnalato dall'utente il 19/09).
H1_VOLUME_THRESHOLD = 3.0
H1_PRICE_THRESHOLD_PCT = 1.5

# [NUOVO 19/09] Soglie del ciclo di conferma - placeholder ragionevoli, non
# calibrati su backtest (stesso principio di trasparenza di scoring_weights):
# CONFERMATO se la direzione è la stessa e la magnitudine è rimasta almeno
# al 60% di quella originale (o è cresciuta); INVALIDATO se si è ridotta
# sotto il 30% o la direzione si è invertita; altrimenti resta in
# osservazione fino a MAX_RECHECKS giri (1h a 15 min/giro).
CONFIRM_RATIO = 0.6
INVALIDATE_RATIO = 0.3
MAX_RECHECKS = 4

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
            'last_price': last_bar['close'],  # [NUOVO 19/09] prezzo assoluto al momento dell'alert, serve al Modulo EOD Verify
        })
    return metrics


def classify_anomaly(volume_ratio, price_change_pct):
    """[NUOVO 19/09] Classificazione deterministica, calcolata in Python -
    non lasciata al giudizio testuale di Gemini, per evitare che generi
    frasi che contraddicono i numeri reali.
    Ritorna None se il ticker supera GIA' entrambe le soglie H1 (è compito
    di H1/H2, va escluso da questo livello qualitativo - vedi nota sopra)."""
    vol_over = volume_ratio >= H1_VOLUME_THRESHOLD
    price_over = abs(price_change_pct) >= H1_PRICE_THRESHOLD_PCT
    if vol_over and price_over:
        return None  # già di competenza H1 - non duplicare qui
    if vol_over and not price_over:
        return 'volume'   # volume anomalo, prezzo ancora contenuto - aspettare conferma di prezzo
    if price_over and not vol_over:
        return 'prezzo'   # variazione di prezzo consistente, volume ancora nella norma - aspettare conferma di volume
    return 'debole'       # nessuno dei due sopra soglia singolarmente


def get_active_signal(ticker):
    """[NUOVO 19/09] Se esiste già un segnale operativo reale (Modulo E) per
    questo ticker, ritorna i suoi livelli VERI (target/invalidazione) invece
    di farne inventare di nuovi a Gemini in questo livello qualitativo."""
    try:
        rows = (supabase.table('signals_filtered')
                .select('filtered_action,target_price,invalidation_price,timestamp')
                .eq('ticker', ticker)
                .neq('filtered_action', 'HOLD')
                .order('timestamp', desc=True)
                .limit(1)
                .execute())
        return rows.data[0] if rows.data else None
    except Exception as e:
        print(f"⚠️ Errore controllo segnale attivo per {ticker}: {e}")
        return None


def get_pending_hypotheses(today):
    try:
        rows = supabase.table('ai_hypotheses').select('*').eq('hypothesis_date', today).eq('status', 'in_osservazione').execute()
        return rows.data or []
    except Exception as e:
        print(f"⚠️ Errore lettura ipotesi in osservazione: {e}")
        return []


def evaluate_confirmation(original_pct, latest_pct):
    """[NUOVO 19/09] Confronto deterministico direzione/magnitudine tra il
    valore al momento dell'alert e quello attuale. Ritorna 'confermato',
    'invalidato' o None (ancora ambiguo, resta in osservazione)."""
    same_direction = (original_pct >= 0) == (latest_pct >= 0)
    if original_pct == 0:
        return None
    ratio = abs(latest_pct) / abs(original_pct)
    if same_direction and ratio >= CONFIRM_RATIO:
        return 'confermato'
    if (not same_direction) or ratio <= INVALIDATE_RATIO:
        return 'invalidato'
    return None


def recheck_pending_hypotheses(current_metrics_by_ticker, today):
    """[NUOVO 19/09] Ricontrolla le ipotesi WATCH aperte oggi prima di
    cercarne di nuove. Ritorna la lista di quelle appena CONFERMATE in
    questo giro (per l'alert di conferma) - le INVALIDATE/SCADUTE si
    aggiornano silenziosamente, senza notifica."""
    pending = get_pending_hypotheses(today)
    if not pending:
        return []
    print(f"   Ricontrollo {len(pending)} ipotesi in osservazione...")

    newly_confirmed = []
    for h in pending:
        ticker = h['ticker']
        m = current_metrics_by_ticker.get(ticker)
        if not m:
            continue  # dati non ancora disponibili in questo giro, riprova al prossimo

        # Se nel frattempo il ticker ha raggiunto ENTRAMBE le soglie H1, è una
        # conferma ancora più forte (probabilmente ora è anche in H1/H2 vero)
        esito = 'confermato' if (m['volume_ratio'] >= H1_VOLUME_THRESHOLD and abs(m['price_change_pct']) >= H1_PRICE_THRESHOLD_PCT) \
            else evaluate_confirmation(h['price_change_pct'], m['price_change_pct'])

        checked_count = (h.get('checked_count') or 0) + 1
        update = {'checked_count': checked_count, 'price_change_pct_latest': m['price_change_pct'],
                  'volume_ratio_latest': m['volume_ratio']}

        if esito == 'confermato':
            update['status'] = 'confermato'
            update['resolved_at'] = datetime.now(timezone.utc).isoformat()
            newly_confirmed.append({**h, **update, 'active_signal': get_active_signal(ticker)})
        elif esito == 'invalidato':
            update['status'] = 'invalidato'
            update['resolved_at'] = datetime.now(timezone.utc).isoformat()
        elif checked_count >= MAX_RECHECKS:
            update['status'] = 'scaduto'
            update['resolved_at'] = datetime.now(timezone.utc).isoformat()
        # altrimenti resta 'in_osservazione', solo checked_count/latest aggiornati

        try:
            supabase.table('ai_hypotheses').update(update).eq('id', h['id']).execute()
        except Exception as e:
            print(f"⚠️ Errore aggiornamento stato per {ticker}: {e}")

    if newly_confirmed:
        print(f"   {len(newly_confirmed)} ipotesi appena CONFERMATE")
    return newly_confirmed


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
    tipo_label = {'volume': 'volume anomalo, prezzo ancora contenuto',
                  'prezzo': 'prezzo anomalo, volume ancora nella norma',
                  'debole': 'nessuno dei due sopra soglia singolarmente'}
    lines = [f"{m['ticker']} | settore={m['sector']} | volume_ratio={m['volume_ratio']}x | "
             f"var={m['price_change_pct']}% | categoria=[{tipo_label[m['tipo']]}]"
             for m in metrics]
    prompt = (
        "Sei un analista che monitora un radar di anomalie di mercato ogni 15 minuti.\n"
        "H1 (regola rigida) segnala solo se volume_ratio>=3.0 E variazione>=1.5% insieme - "
        "i ticker qui sotto NON superano già entrambe le soglie insieme (altrimenti sarebbero "
        "già gestiti da H1), la 'categoria' indicata per ciascuno è già calcolata e corretta: "
        "NON contraddirla e NON riscrivere se supera o non supera una soglia, usala solo come "
        "punto di partenza per la motivazione.\n\n"
        + "\n".join(lines) +
        "\n\nSegnala SOLO i ticker che secondo il tuo giudizio meritano davvero attenzione. "
        "Sii selettivo: se oggi non c'è nulla di interessante, rispondi con un array vuoto - "
        "non forzare segnalazioni. La motivazione deve dire COSA aspettare per una conferma "
        "(es. 'aspettare conferma sul volume' se categoria=prezzo, o 'aspettare conferma sul "
        "prezzo' se categoria=volume), MAI dare indicazioni di ingresso operativo (entry/stop/"
        "target) - questo livello è solo di osservazione, non genera segnali.\n"
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

    # [NUOVO 19/09] Ricontrollo delle ipotesi già aperte oggi PRIMA di
    # cercarne di nuove - usa i dati grezzi (non ancora classificati/filtrati)
    # così può rilevare anche il caso "ora supera entrambe le soglie H1".
    raw_metrics_by_ticker = {m['ticker']: m for m in metrics}
    newly_confirmed = recheck_pending_hypotheses(raw_metrics_by_ticker, today)

    # [NUOVO 19/09] Classificazione deterministica + esclusione dei ticker
    # che superano già entrambe le soglie H1 (competenza di H1/H2, non di
    # questo livello qualitativo - vedi classify_anomaly()).
    for m in metrics:
        m['tipo'] = classify_anomaly(m['volume_ratio'], m['price_change_pct'])
    n_escluse_h1 = sum(1 for m in metrics if m['tipo'] is None)
    metrics = [m for m in metrics if m['tipo'] is not None]
    if n_escluse_h1:
        print(f"   {n_escluse_h1} ticker esclusi perché già di competenza H1 (soglie entrambe superate)")

    metrics = [m for m in metrics if not already_flagged_today(m['ticker'], today)]

    new_items = []
    if metrics:
        flagged = call_gemini_watch(metrics)
        if flagged:
            metrics_by_ticker = {m['ticker']: m for m in metrics}
            for item in flagged:
                ticker = (item.get('ticker') or '').strip()
                m = metrics_by_ticker.get(ticker)
                if not m:
                    continue  # Gemini ha citato un ticker fuori dalla lista fornita: ignorato, mai inventare
                active_signal = get_active_signal(ticker)
                row = {
                    'hypothesis_date': today,
                    'ticker': ticker,
                    'motivazione': item.get('motivazione', ''),
                    'livello': item.get('livello', 'medio'),
                    'volume_ratio': m['volume_ratio'],
                    'price_change_pct': m['price_change_pct'],
                    'entry_price': m['last_price'],
                    'tipo_anomalia': m['tipo'],
                    'has_active_signal': active_signal is not None,
                    'linked_action': active_signal['filtered_action'] if active_signal else None,
                    'linked_target_price': active_signal.get('target_price') if active_signal else None,
                    'linked_invalidation_price': active_signal.get('invalidation_price') if active_signal else None,
                }
                try:
                    supabase.table('ai_hypotheses').insert(row).execute()
                    new_items.append({**item, **m, **row})
                except Exception as e:
                    # L'unique index (ticker, hypothesis_date) fa da rete di sicurezza anti-duplicati
                    print(f"⚠️ {ticker} non inserito (probabile duplicato già presente oggi): {e}")
        else:
            print("   Nessuna nuova ipotesi da segnalare in questo giro.")
    else:
        print("   Tutti i ticker con dati sufficienti sono già stati segnalati oggi.")

    if not new_items and not newly_confirmed:
        print("   Nessun alert da inviare in questo giro (nessuna novità, nessuna conferma).")
        return

    tipo_label = {'volume': 'volume↑ senza conferma di prezzo — aspetta variazione di prezzo',
                  'prezzo': 'prezzo↑ senza conferma di volume — aspetta conferma sui volumi',
                  'debole': 'segnale debole su entrambi i fronti'}
    lines = []

    for i in newly_confirmed:
        riga = (f"✅ CONFERMATO · *{i['ticker']}*\n"
                f"  Movimento persistente dopo {i['checked_count']} ricontrolli: "
                f"var {i['price_change_pct_latest']}% (era {i['price_change_pct']}% all'alert iniziale), "
                f"volume {i['volume_ratio_latest']}x")
        if i.get('active_signal'):
            s = i['active_signal']
            riga += (f"\n  🟢 C'è un segnale operativo attivo: {s['filtered_action']}"
                     f", target {s.get('target_price')}, invalidazione {s.get('invalidation_price')}")
        else:
            riga += "\n  Ancora nessun segnale operativo dalla pipeline principale - resta osservazione qualitativa rinforzata, non un ingresso"
        riga += f"\n  {DASHBOARD_BASE_URL}/grafico.php?ticker={i['ticker']}"
        lines.append(riga)

    for i in new_items:
        riga = (f"👀 WATCH · *{i['ticker']}* ({tipo_label[i['tipo_anomalia']]}, livello {i['livello']})\n"
                f"  {i['motivazione']}\n"
                f"  var {i['price_change_pct']}% · volume {i['volume_ratio']}x")
        if i['has_active_signal']:
            riga += (f"\n  🟢 C'è già un segnale operativo attivo: {i['linked_action']}"
                     f", target {i['linked_target_price']}, invalidazione {i['linked_invalidation_price']}"
                     f" (vedi dashboard per i dettagli)")
        riga += f"\n  {DASHBOARD_BASE_URL}/grafico.php?ticker={i['ticker']}"
        lines.append(riga)
    header = ("📡 SAPTA — Ipotesi qualitativa IA, solo osservazione (NON un segnale operativo, "
               "NON una previsione - i livelli reali esistono solo se indicato 'segnale attivo'):\n\n")
    message = header + "\n\n".join(lines)

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
