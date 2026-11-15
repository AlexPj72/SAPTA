#!/usr/bin/env python3
"""Passo 1 - verifica a mano (da lanciare sul PC, sola lettura, nessun database coinvolto).

1) Intervallo realmente restituito da Yahoo per le barre 15m (prima e ultima barra, numero di barre) con --range (es. 60d).
2) Confronto tra due scarichi INDIPENDENTI delle stesse barre: yfinance (come fa il Modulo A) e l'API grafici di Yahoo (JSON grezzo),
   passati nello stesso filtro del Modulo A (barre chiuse, regolari). Riporta barre solo in uno dei due e valori diversi.
Uso:  python3 scripts/confronta_scarico_yahoo.py --range 5d --tickers ENI.MI,ISP.MI,AAPL,MSFT
Richiede: pip install yfinance pandas
"""
import argparse, json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from bar_ingestion_core import build_records, frame_rows, new_counters  # noqa: E402


def chart_rows(t, rng):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(t) + f"?range={rng}&interval=15m")
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
        res = json.load(r)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    return [(datetime.fromtimestamp(ts, timezone.utc), q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i])
            for i, ts in enumerate(res.get("timestamp") or [])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--range', default='5d')
    ap.add_argument('--tickers', default='ENI.MI,ISP.MI,AAPL,MSFT')
    a = ap.parse_args()
    import yfinance as yf
    now = datetime.now(timezone.utc)
    for t in a.tickers.split(','):
        raw = chart_rows(t, a.range)
        print(f"{t}: Yahoo (chart API) range={a.range}: {len(raw)} barre, prima={raw[0][0] if raw else '-'}, ultima={raw[-1][0] if raw else '-'}")
        df = yf.download(t, period=a.range, interval='15m', auto_adjust=True, progress=False, threads=False)
        if hasattr(df.columns, 'levels'):
            df.columns = df.columns.get_level_values(0)
        c1, c2 = new_counters(), new_counters()
        r1 = {r['timestamp']: r for r in build_records(t, frame_rows(df, t), now, False, c1)}
        r2 = {r['timestamp']: r for r in build_records(t, raw, now, False, c2)}
        diff = [k for k in r1.keys() & r2.keys()
                if any(abs(r1[k][f] - r2[k][f]) > 1e-4 * max(1, abs(r1[k][f])) for f in ('open', 'high', 'low', 'close', 'volume'))]
        print(f"   yfinance={len(r1)} chart={len(r2)} solo_yfinance={len(r1.keys() - r2.keys())} solo_chart={len(r2.keys() - r1.keys())} "
              f"valori_diversi={len(diff)} (su {len(r1.keys() & r2.keys())} barre in comune)")


if __name__ == '__main__':
    main()
