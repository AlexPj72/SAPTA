"""Confronto PARALLELO in PAPER fra stop/target FISSI (regole attuali di SAPTA) e STOP DINAMICO.
Non modifica regole, cicli o portafogli: rilegge i cicli con ingresso reale e rigioca le candele storiche da 15 minuti.
Stesso ingresso, stessa uscita a tempo (5 sedute), stessa uscita su SELL approvato, stesse commissioni e stessa slippage
di uscita in entrambe le varianti; cambia solo la regola di stop/target.
Stop dinamico: stop iniziale uguale; quando il massimo raggiunto sale di una distanza pari al rischio iniziale (ingresso - stop)
lo stop segue il massimo a quella distanza (da li' non puo' piu' scendere); nessun obiettivo fisso. Lo stop si aggiorna con
i massimi delle candele GIA' chiuse (nessun uso di dati futuri). Il cambio dei titoli USA e' quello dell'ingresso in entrambe."""
import os
import sys
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import modulo_t_state_machine as T
import notifications
from market_calendar import last_regular_bar_start, local_date


def replay(lc, bars, sells, dynamic):
    """Ritorna (motivo, livello, candela) oppure (None, ultimo_prezzo, ultima_candela) se ancora aperta."""
    market = lc['market']
    entry, stop0, tgt = float(lc['entry_fill_price']), float(lc['invalidation_price']), float(lc['target_price'])
    stop, risk, hwm = stop0, entry - stop0, entry
    planned = date.fromisoformat(str(lc['planned_time_exit_date'])[:10])
    last = None
    for bar in bars:
        sess = local_date(market, bar['start'])
        reason = level = None
        if bar['o'] <= stop:
            reason, level = 'STOP', bar['o']                 # gap sotto lo stop: prezzo di apertura (peggiore)
        elif bar['l'] <= stop:
            reason, level = 'STOP', stop                     # stop e (se previsto) target nella stessa candela: vince lo stop
        elif not dynamic and bar['h'] >= tgt:
            reason, level = 'TARGET', tgt
        if reason == 'STOP' and dynamic and stop > stop0:
            reason = 'STOP DINAMICO'
        if not reason and sess > planned:
            reason, level = 'TEMPO', bar['o']
        if not reason and sess == planned and bar['start'] == last_regular_bar_start(market, sess):
            reason, level = 'TEMPO', bar['c']
        if not reason:
            sell = next((s for s in sells if T.parse_ts(s['timestamp']) <= bar['start']), None)
            if sell:
                reason, level = 'SEGNALE', bar['c']
        if reason:
            return reason, level, bar
        last = bar
        if dynamic:                                          # aggiornamento a fine candela: vale dalla successiva
            hwm = max(hwm, bar['h'])
            if risk > 0 and hwm >= entry + risk:
                stop = max(stop, hwm - risk)
    return None, (last['c'] if last else entry), last


def net_result(lc, level, fees_fn):
    """Risultato netto in euro: slippage di uscita e commissioni di ingresso e uscita applicate allo stesso modo."""
    qty, entry, fx = float(lc['quantity']), float(lc['entry_fill_price']), float(lc['fx_eur_per_local'])
    fill = T.sell_fill(level, float(lc.get('slippage_pct') or 0))
    market = lc['market']
    net = qty * (fill - entry) * fx - fees_fn(market, qty * entry * fx) - fees_fn(market, qty * fill * fx)
    return round(net, 2), fill


def confronto(sb, now=None):
    now = now or datetime.now(timezone.utc)
    store, ex = T.Store(sb), T.PortfolioExecutor(sb)
    lcs = sb.table('trade_lifecycle').select('*').in_('state', ['ACTIVE', 'EXIT']).not_.is_('entry_fill_price', 'null') \
        .order('id').execute().data or []
    out = []
    for lc in lcs:
        entry_end = T.parse_ts(lc['trigger_bar_end'])
        bars = [b for b in store.bars(lc['ticker'], entry_end) if b['start'] >= entry_end and b['end'] <= now]
        sells = store.approved_sells(lc['ticker'], entry_end)
        row = {'id': lc['id'], 'ticker': lc['ticker']}
        for name, dyn in (('fisso', False), ('dinamico', True)):
            reason, level, bar = replay(lc, bars, sells, dyn)
            net, fill = net_result(lc, level, ex._fees)
            row[name] = {'motivo': reason or 'APERTA', 'netto': net, 'prezzo': fill, 'quando': bar['end'] if bar else None}
        out.append(row)
    return out


def eur(x):
    return ('+' if x >= 0 else '−') + notifications._num(abs(x), 2) + ' €'


def testo(rows):
    if not rows:
        return ["— nessuna operazione da confrontare."]
    lines, tf, td = [], 0.0, 0.0
    for r in rows:
        f, d = r['fisso'], r['dinamico']
        tf += f['netto']; td += d['netto']
        lines.append(f"• {r['ticker']}: fisso {f['motivo']} {eur(f['netto'])} · dinamico {d['motivo']} {eur(d['netto'])} · differenza {eur(d['netto'] - f['netto'])}")
    lines.append(f"Totale netto: fisso {eur(tf)} · dinamico {eur(td)} · differenza {eur(td - tf)} (a favore del {'dinamico' if td > tf else 'fisso' if tf > td else 'pari'})")
    lines.append("Simulazione in PAPER: stesse commissioni, slippage e uscita a 5 sedute; le posizioni APERTE sono valutate all'ultimo prezzo.")
    return lines


def salva(sb, rows):
    """Scrive i risultati in stop_comparison (una riga per ciclo) per la dashboard."""
    for r in rows:
        sb.table('stop_comparison').upsert({
            'lifecycle_id': r['id'], 'ticker': r['ticker'], 'fixed_reason': r['fisso']['motivo'], 'fixed_net_eur': r['fisso']['netto'],
            'dynamic_reason': r['dinamico']['motivo'], 'dynamic_net_eur': r['dinamico']['netto'],
            'updated_at': datetime.now(timezone.utc).isoformat()}, on_conflict='lifecycle_id').execute()


if __name__ == '__main__':
    from config import supabase
    rows = confronto(supabase)
    print("\n".join(testo(rows)))
    if '--salva' in sys.argv:
        salva(supabase, rows)
        print(f"Salvate {len(rows)} righe in stop_comparison")
