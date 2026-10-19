"""Report del portafoglio virtuale dell'IA (PAPER): equity su base 100, operazioni, posizioni aperte.
Invio su Telegram ed email con le stesse funzioni degli alert. Nessun ordine reale."""
import re
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notifications
from notifications import _num


def _fromiso(s):
    """fromisoformat tollerante: Python <3.11 accetta solo 3 o 6 cifre di frazione."""
    s = str(s).replace('Z', '+00:00')
    s = re.sub(r'\.(\d{1,6})\d*', lambda m: '.' + m.group(1).ljust(6, '0'), s, count=1)
    return datetime.fromisoformat(s)


CODE = 'PORTAFOGLIO_AI'


def _d(ts):
    return _fromiso(ts).astimezone(notifications.ROME).strftime('%d/%m %H:%M')


def build_report(sb, days):
    now = datetime.now(timezone.utc)
    summ = (sb.table('v_portfolio_summary').select('*').eq('code', CODE).execute().data or [None])[0]
    if not summ:
        return None, 'Portafoglio IA non trovato.'
    init, eq = float(summ['initial_capital_eur']), float(summ['equity_eur'])
    idx = eq / init * 100
    txs = (sb.table('v_portfolio_history').select('*').eq('portfolio_code', CODE)
           .gte('executed_at', (now - timedelta(days=days)).isoformat()).order('executed_at').execute().data or [])
    txs = [t for t in txs if t['tx_type'] in ('BUY', 'SELL')]
    pos = sb.table('v_portfolio_valuation').select('*').eq('portfolio_code', CODE).execute().data or []
    lines = [f"📊 SAPTA — portafoglio virtuale IA (PAPER) — ultimi {days} giorni",
             f"Valore: {_num(eq, 2)} € su base 100 = {_num(idx, 2)} ({'+' if idx >= 100 else '−'}{_num(abs(idx - 100), 2)}%)",
             f"Capitale iniziale {_num(init, 2)} € · liquidità {_num(summ['cash_available_eur'], 2)} € · "
             f"P&L realizzato {_num(summ['realized_pnl_eur'], 2)} € · non realizzato {_num(summ['unrealized_pnl_eur'], 2)} € · costi {_num(summ['fees_paid_eur'], 2)} €",
             "", f"Operazioni ({len(txs)}):"]
    if not txs:
        lines.append("— nessuna operazione nel periodo (nessun segnale valido).")
    for t in txs:
        side = 'COMPRATO' if t['tx_type'] == 'BUY' else 'VENDUTO'
        pnl = f" · risultato {_num(t['realized_pnl_eur'], 2)} €" if t['tx_type'] == 'SELL' else ''
        lines.append(f"• {_d(t['executed_at'])} {side} {t['ticker']} × {_num(t['quantity'], 0)} a {_num(t['price_local'], 2)} "
                     f"{'$' if t['currency'] == 'USD' else '€'}{pnl}")
    lines += ["", f"Posizioni aperte ({len(pos)}):"]
    if not pos:
        lines.append("— nessuna.")
    for p in pos:
        pct = p.get('unrealized_pnl_pct')
        lines.append(f"• {p['ticker']} × {_num(p['quantity'], 0)} · costo {_num(p['cost_basis_eur'], 2)} € · "
                     f"{'n.d.' if pct is None else _num(pct, 2) + '%'}")
    try:    # confronto parallelo stop fisso / stop dinamico: mai bloccante per il report
        import modulo_confronto_stop as conf
        lines += ["", "Confronto parallelo (PAPER): stop fisso (regole attuali) contro stop dinamico:"] + conf.testo(conf.confronto(sb, now))
    except Exception as e:
        lines += ["", f"Confronto stop non disponibile: {str(e)[:120]}"]
    lines += ["", "Simulazione: nessun ordine reale."]
    return f"SAPTA — report portafoglio IA ({now.astimezone(notifications.ROME):%d/%m})", "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--print-only', action='store_true')
    a = ap.parse_args()
    from config import supabase
    subject, text = build_report(supabase, a.days)
    print(text if subject else subject)
    if a.print_only or not subject:
        return
    print('Telegram:', notifications.send_telegram(text))
    print('Email:', notifications.send_email(subject, text))


if __name__ == '__main__':
    main()
