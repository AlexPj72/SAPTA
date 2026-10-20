"""Modulo Rimbalzo (paper) - NUOVO 20/10/2026, specifica v0.1 approvata dall'utente.

Registra gli eventi "crollo a 5 sedute" e il loro esito a 5 sedute. NON invia ordini, NON usa portafogli,
NON modifica H1/H2/B/E/T: legge solo i prezzi giornalieri (prezzi, interval='1d') e scrive solo su rebound_events.

Evento: rendimento close-to-close a 5 sedute <= -15%, primo giorno sotto soglia (il giorno prima non lo era).
Ingresso simulato: apertura della seduta successiva. Uscita simulata: chiusura della 5a seduta (sedute del titolo
dopo il giorno dell'evento), senza stop ne' target. Stesso titolo: minimo 7 giorni tra eventi.
Controllo: rendimento medio, nella stessa finestra, degli altri titoli dello stesso mercato.
USA = mode PAPER (operativo in paper), Europa (.MI) = mode OBSERVE (sola registrazione).
Solo eventi dal FORWARD_START (12/10/2026) in poi: prima data con finestra a 5 sedute non ancora completa nell'analisi del 20/10/2026, quindi fuori campione."""
import argparse
import sys
from datetime import date, datetime, timedelta, timezone

FORWARD_START = date(2026, 10, 12)
DROP_THRESHOLD = -0.15
LOOKBACK = 5
HOLD_SESSIONS = 5
MIN_GAP_DAYS = 7
MAX_ENTRY_GAP_DAYS = 5     # evento -> ingresso: oltre = buco nei dati
MAX_EXIT_SPAN_DAYS = 9     # evento -> uscita: come nell'analisi
FETCH_DAYS = 60
PAGE = 1000
FINAL = ("CLOSED", "INVALID")


def market_of(ticker):
    return "EU" if ticker.endswith(".MI") else "US"


def mode_of(market):
    return "PAPER" if market == "US" else "OBSERVE"


def build_bars(rows):
    """rows: dict con ticker, timestamp, open, close, in ordine di id. -> {ticker: [(date, open, close), ...]} ordinato."""
    tmp = {}
    for r in rows:
        if r.get("open") is None or r.get("close") is None:
            continue
        d = date.fromisoformat(str(r["timestamp"])[:10])
        tmp.setdefault(r["ticker"], {})[d] = (float(r["open"]), float(r["close"]))
    return {t: [(d, v[0], v[1]) for d, v in sorted(days.items())] for t, days in tmp.items()}


def find_candidates(bars, start):
    """Indici i (su bars di un titolo) dove scatta l'evento, con data >= start."""
    out = []
    for i in range(LOOKBACK, len(bars)):
        if bars[i][0] < start:
            continue
        r5 = bars[i][2] / bars[i - LOOKBACK][2] - 1
        if r5 > DROP_THRESHOLD:
            continue
        prev = bars[i - 1][2] / bars[i - 1 - LOOKBACK][2] - 1 if i - 1 - LOOKBACK >= 0 else None
        if prev is None or prev > DROP_THRESHOLD:
            out.append((i, r5))
    return out


def window(bars, i):
    """Ingresso/uscita per l'evento all'indice i. Ritorna dict con status e campi (None se non ancora disponibili)."""
    d = bars[i][0]
    res = {"entry_date": None, "entry_open": None, "exit_date": None, "exit_close": None, "fwd_return": None}
    status = "DETECTED"
    if i + 1 < len(bars):
        ed, eo, _ = bars[i + 1]
        res.update(entry_date=ed, entry_open=eo)
        status = "ENTERED"
        if (ed - d).days > MAX_ENTRY_GAP_DAYS:
            return dict(res, status="INVALID")
    if i + HOLD_SESSIONS < len(bars):
        xd, _, xc = bars[i + HOLD_SESSIONS]
        res.update(exit_date=xd, exit_close=xc)
        if (xd - d).days > MAX_EXIT_SPAN_DAYS:
            return dict(res, status="INVALID")
        if res["entry_open"]:
            res["fwd_return"] = xc / res["entry_open"] - 1
            status = "CLOSED"
    return dict(res, status=status)


def control_return(all_bars, ticker, event_date):
    """Media dei rendimenti (apertura t+1 -> chiusura t+5) degli altri titoli dello stesso mercato alla stessa data."""
    mk = market_of(ticker)
    vals = []
    for t, bars in all_bars.items():
        if t == ticker or market_of(t) != mk:
            continue
        idx = next((j for j, b in enumerate(bars) if b[0] == event_date), None)
        if idx is None or idx + HOLD_SESSIONS >= len(bars) or not bars[idx + 1][1]:
            continue
        vals.append(bars[idx + HOLD_SESSIONS][2] / bars[idx + 1][1] - 1)
    return (sum(vals) / len(vals), len(vals)) if vals else (None, 0)


def build_rows(all_bars, existing, start, markets):
    """existing: {(ticker, event_date): status} da DB. Ritorna (righe da scrivere, saltati_per_distanza)."""
    existing_dates = {}
    for (t, d) in existing:
        existing_dates.setdefault(t, []).append(d)
    rows, skipped = [], 0
    for ticker, bars in sorted(all_bars.items()):
        mk = market_of(ticker)
        if mk not in markets:
            continue
        kept = list(existing_dates.get(ticker, []))
        for i, r5 in find_candidates(bars, start):
            d = bars[i][0]
            if (ticker, d) in existing:
                if existing[(ticker, d)] in FINAL:
                    continue
            elif any(0 <= (d - k).days < MIN_GAP_DAYS for k in kept):
                skipped += 1
                continue
            w = window(bars, i)
            ctrl, n = (None, 0)
            if w["status"] == "CLOSED":
                ctrl, n = control_return(all_bars, ticker, d)
            kept.append(d)
            rows.append({
                "market": mk, "mode": mode_of(mk), "ticker": ticker, "event_date": d.isoformat(),
                "r5": round(r5, 6),
                "entry_date": w["entry_date"].isoformat() if w["entry_date"] else None,
                "entry_open": w["entry_open"],
                "exit_date": w["exit_date"].isoformat() if w["exit_date"] else None,
                "exit_close": w["exit_close"],
                "fwd_return": round(w["fwd_return"], 6) if w["fwd_return"] is not None else None,
                "control_return": round(ctrl, 6) if ctrl is not None else None,
                "control_n": n if ctrl is not None else None,
                "status": w["status"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
    return rows, skipped


def fetch_prices(supabase, since):
    rows, a = [], 0
    while True:
        r = (supabase.table("prezzi").select("ticker,timestamp,open,close").eq("interval", "1d")
             .gte("timestamp", since.isoformat()).order("id").range(a, a + PAGE - 1).execute())
        rows += r.data
        if len(r.data) < PAGE:
            return rows
        a += PAGE


def fetch_existing(supabase):
    r = supabase.table("rebound_events").select("ticker,event_date,status").execute()
    return {(x["ticker"], date.fromisoformat(x["event_date"])): x["status"] for x in r.data}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["US", "EU", "ALL"], default="ALL")
    ap.add_argument("--since", default=FORWARD_START.isoformat(), help="prima data evento ammessa (default: inizio fuori campione)")
    ap.add_argument("--dry-run", action="store_true", help="non scrive su Supabase")
    a = ap.parse_args()
    start = date.fromisoformat(a.since)
    markets = {"US", "EU"} if a.market == "ALL" else {a.market}
    print(f"Modulo Rimbalzo: {datetime.now(timezone.utc).isoformat()} mercati={sorted(markets)} da={start} dry_run={a.dry_run}")
    try:
        from config import supabase
        since_fetch = min(start, date.today()) - timedelta(days=FETCH_DAYS)
        all_bars = build_bars(fetch_prices(supabase, since_fetch))
        for mk in sorted(markets):
            last = max((b[-1][0] for t, b in all_bars.items() if market_of(t) == mk and b), default=None)
            print(f"  {mk}: ultimo giorno prezzi {last}" + (" (ATTENZIONE: dati vecchi)" if last and (date.today() - last).days > 4 else ""))
        rows, skipped = build_rows(all_bars, fetch_existing(supabase), start, markets)
        print(f"  eventi da scrivere/aggiornare: {len(rows)}, saltati per distanza <{MIN_GAP_DAYS}gg: {skipped}")
        for r in rows:
            print(f"   {r['market']} {r['ticker']} {r['event_date']} r5={r['r5']:+.3f} {r['status']} fwd={r['fwd_return']} ctrl={r['control_return']}")
        if rows and not a.dry_run:
            supabase.table("rebound_events").upsert(rows, on_conflict="ticker,event_date").execute()
            print("  scritto su rebound_events")
    except Exception as e:  # non deve mai bloccare gli altri moduli
        print(f"ERRORE Modulo Rimbalzo (non bloccante): {e}")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
