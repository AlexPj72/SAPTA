"""Avvisi sulle posizioni del portafoglio dell'UTENTE (PAPER), indipendenti dai segnali di SAPTA:
  - PERDITA_50 / PERDITA_100: la posizione ha perso il 50% / il 100% del rischio previsto (distanza fra prezzo medio e stop di SAPTA;
    per posizioni senza stop, rischio = 5% del prezzo medio). Un solo avviso per posizione e livello.
  - DISCESA_ANOMALA: il calo dell'ultima ora supera 2,5 volte la normale oscillazione oraria del titolo (minimo 1,5%). Al massimo uno al giorno.
Solo a borsa aperta (ultima candela da 15 minuti fresca). Mai ordini: sono solo avvisi."""
import os
import statistics
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notifications
import modulo_t_state_machine as T
from market_calendar import local_date

PORTFOLIO = 'PORTAFOGLIO_UTENTE'
FRESH_MIN = 35
DROP_MULT, DROP_MIN = 2.5, 0.015
DEFAULT_RISK_PCT = 0.05


def hourly_returns(bars, market):
    """Rendimenti su 4 candele (1 ora) calcolati dentro la stessa seduta."""
    out = []
    for i in range(4, len(bars)):
        a, b = bars[i - 4], bars[i]
        if local_date(market, a['start']) == local_date(market, b['start']) and a['c'] > 0:
            out.append(b['c'] / a['c'] - 1)
    return out


def evaluate(pos, stop, bars, now):
    """Ritorna l'elenco di (kind, event_key, testo) da inviare per UNA posizione (funzione pura, testabile)."""
    if not bars or bars[-1]['end'] < now - timedelta(minutes=FRESH_MIN):
        return []                                           # borsa chiusa o dati non freschi
    market, tk = pos['market'], pos['ticker']
    avg, last = float(pos['avg_cost_local']), bars[-1]['c']
    cur = '$' if pos['currency'] == 'USD' else '€'
    qty = float(pos['quantity'])
    qty_s = f"{qty:g}"
    ev = []
    risk = (avg - stop) if (stop is not None and avg - stop > 0) else avg * DEFAULT_RISK_PCT
    used = (avg - last) / risk if risk > 0 else 0
    pct = (last / avg - 1) * 100
    stop_txt = f"lo stop previsto da SAPTA è {notifications._num(stop, 2)} {cur}" if stop is not None else "per questa posizione non c'è uno stop SAPTA (rischio stimato 5%)"
    base = (f"Hai {qty_s} azioni con prezzo medio {notifications._num(avg, 2)} {cur}; ultimo prezzo {notifications._num(last, 2)} {cur} "
            f"({'+' if pct >= 0 else '−'}{notifications._num(abs(pct), 2)}%, candela chiusa alle {bars[-1]['end'].astimezone(notifications.ROME).strftime('%H:%M')}).")
    if used >= 1.0:
        ev.append(('PERDITA_100', f"{pos['id']}:PERDITA_100",
                   f"🔴 La tua posizione ha raggiunto la perdita massima prevista · {tk}\n{base}\nÈ stato perso il 100% del rischio previsto: {stop_txt}. Valuta se uscire.\nPosizione virtuale (PAPER)."))
    elif used >= 0.5:
        ev.append(('PERDITA_50', f"{pos['id']}:PERDITA_50",
                   f"🟠 La tua posizione sta perdendo · {tk}\n{base}\nÈ stato perso metà del rischio previsto: {stop_txt}. Tienila d'occhio.\nPosizione virtuale (PAPER)."))
    rets = hourly_returns(bars, market)
    if len(bars) > 4:
        drop = bars[-1]['c'] / bars[-5]['c'] - 1 if local_date(market, bars[-5]['start']) == local_date(market, bars[-1]['start']) else 0
        sd = statistics.pstdev(rets[:-1]) if len(rets) > 12 else 0.01
        thr = max(DROP_MULT * sd, DROP_MIN)
        if drop <= -thr:
            ev.append(('DISCESA_ANOMALA', f"{pos['id']}:DISCESA:{local_date(market, bars[-1]['start']).isoformat()}",
                       f"📉 Discesa anomala · {tk}\nNell'ultima ora il titolo è sceso del {notifications._num(abs(drop) * 100, 2)}%, molto più del normale (soglia {notifications._num(thr * 100, 2)}%).\n{base}\nPosizione virtuale (PAPER)."))
    return ev


def run(sb, now=None, dry=False):
    now = now or datetime.now(timezone.utc)
    pf = sb.table('portfolios').select('id').eq('code', PORTFOLIO).execute().data
    if not pf:
        return 0
    positions = sb.table('portfolio_positions').select('*').eq('portfolio_id', pf[0]['id']).eq('status', 'OPEN').execute().data or []
    store, sent = T.Store(sb), 0
    for pos in positions:
        stop = None
        if pos.get('lifecycle_id'):
            lc = sb.table('trade_lifecycle').select('invalidation_price').eq('id', pos['lifecycle_id']).execute().data
            stop = float(lc[0]['invalidation_price']) if lc and lc[0].get('invalidation_price') else None
        bars = [b for b in store.bars(pos['ticker'], now - timedelta(days=6)) if b['end'] <= now and b['v'] > 0]
        for kind, key, text in evaluate(pos, stop, bars, now):
            if dry:
                print(f"[prova] {key}\n{text}\n")
                continue
            try:
                sb.table('user_position_alerts').insert({'position_id': pos['id'], 'ticker': pos['ticker'], 'kind': kind,
                                                         'event_key': key, 'message': text}).execute()
            except Exception:
                continue                                     # evento gia' registrato: nessun duplicato
            subject = f"SAPTA — {kind.replace('_', ' ').title()} — {pos['ticker']}"
            tg, em = notifications.send_telegram(text), notifications.send_email(subject, text)
            sb.table('user_position_alerts').update({'telegram_status': str(tg)[:60], 'email_status': str(em)[:60]}).eq('event_key', key).execute()
            sent += 1
    print(f"Avvisi posizioni utente inviati: {sent}")
    return sent


if __name__ == '__main__':
    from config import supabase
    run(supabase, dry='--prova' in sys.argv)
