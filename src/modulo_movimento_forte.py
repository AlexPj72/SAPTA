"""Modulo Movimento Forte (SOLA ALLERTA, dry-run) - NUOVO 27/10/2026.

Elenca i titoli che oggi stanno salendo forte rispetto alla chiusura precedente. NON genera BUY, NON invia ordini,
NON modifica H1/H2/B/E/T e NON scrive su Supabase: legge solo `prezzi` (1d e 15m) e stampa il risultato.
Motivo: i test storici (2019-2026) mostrano che comprare il rialzo +4%/+7% non rende in modo affidabile
(rendimento medio ~ +0,5% a fine giornata, -0,6% quando il rialzo non arriva a +7%), quindi qui si SEGNALA soltanto.
Prezzo = ultima barra 15m di oggi; riferimento = ultima chiusura 1d precedente.
Volume = volume 15m cumulato oggi / media volume 1d delle ultime 20 sedute (e' parziale: a meta' seduta e' < 1).
Soglie di default NON validate sul volume parziale: servono per osservare, non per decidere."""
import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

PRICE_THRESHOLD = 0.04
VOL_THRESHOLD = 0.5      # frazione della media 20gg gia' scambiata (parziale intraday)
AVG_SESSIONS = 20
PAGE = 1000


def evaluate(daily, intraday, price_thr=PRICE_THRESHOLD, vol_thr=VOL_THRESHOLD):
    """daily: {ticker: [(date, close, volume), ...] ordinato}; intraday: {ticker: [(ts, close, volume), ...] ordinato.
    Usa solo le barre 15m dell'ultimo giorno presente. Ritorna lista di dict ordinata per rialzo decrescente."""
    out = []
    for t, bars in intraday.items():
        if not bars or t not in daily:
            continue
        today = bars[-1][0].date()
        todays = [b for b in bars if b[0].date() == today]
        prev = [d for d in daily[t] if d[0] < today]
        if not todays or len(prev) < AVG_SESSIONS:
            continue
        pc = prev[-1][1]
        avg = sum(d[2] for d in prev[-AVG_SESSIONS:]) / AVG_SESSIONS
        if pc <= 0 or avg <= 0:
            continue
        last = todays[-1][1]
        pct = last / pc - 1
        vol = sum(b[2] for b in todays) / avg
        if pct >= price_thr and vol >= vol_thr:
            out.append({"ticker": t, "pct": pct, "vol_frac": vol, "last": last, "prev_close": pc, "ts": todays[-1][0]})
    return sorted(out, key=lambda r: -r["pct"])


def _fetch(supabase, interval, since):
    rows, a = [], 0
    while True:
        r = (supabase.table("prezzi").select("ticker,timestamp,close,volume").eq("interval", interval)
             .gte("timestamp", since.isoformat()).order("id").range(a, a + PAGE - 1).execute())
        rows += r.data
        if len(r.data) < PAGE:
            return rows
        a += PAGE


def _group(rows, daily):
    out = {}
    for r in rows:
        if r.get("close") is None:
            continue
        ts = datetime.fromisoformat(str(r["timestamp"]).replace("Z", "+00:00"))
        key = ts.date() if daily else ts
        out.setdefault(r["ticker"], {})[key] = (key, float(r["close"]), float(r.get("volume") or 0))
    return {t: [v for _, v in sorted(d.items())] for t, d in out.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--price", type=float, default=PRICE_THRESHOLD)
    ap.add_argument("--vol", type=float, default=VOL_THRESHOLD)
    args = ap.parse_args()
    from supabase import create_client
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    now = datetime.now(timezone.utc)
    daily = _group(_fetch(sb, "1d", now - timedelta(days=45)), True)
    intraday = _group(_fetch(sb, "15m", now - timedelta(days=4)), False)
    res = evaluate(daily, intraday, args.price, args.vol)
    print(f"Movimento forte (sola allerta): {len(res)} titoli con >= +{args.price*100:.1f}% e volume >= {args.vol:.2f}x media20")
    for r in res:
        print(f"  {r['ticker']:10s} {r['pct']*100:+6.2f}%  vol {r['vol_frac']:.2f}x  ultimo {r['last']:.2f} (prec. {r['prev_close']:.2f})  barra {r['ts']:%Y-%m-%d %H:%M}Z")
    return 0


if __name__ == "__main__":
    sys.exit(main())
