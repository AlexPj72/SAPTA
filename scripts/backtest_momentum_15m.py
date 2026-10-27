#!/usr/bin/env python3
"""Read-only intraday momentum backtest for SAPTA's existing 15m bars.

No database writes and no orders. Writes CSV/JSON artifacts only.
"""
import json
import os
from pathlib import Path

import pandas as pd
from supabase import create_client

URL = os.environ["SUPABASE_URL"]
KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
START = os.getenv("BACKTEST_START", "2026-10-13T00:00:00+00:00")
END = os.getenv("BACKTEST_END", "2026-10-27T00:00:00+00:00")
OUT = Path(os.getenv("BACKTEST_OUT", "momentum-backtest-output"))
OUT.mkdir(parents=True, exist_ok=True)

client = create_client(URL, KEY)
rows = []
offset = 0
page_size = 1000
while True:
    response = (
        client.table("prezzi")
        .select("ticker,timestamp,open,high,low,close,volume,interval,data_quality_flag")
        .eq("interval", "15m")
        .gte("timestamp", START)
        .lt("timestamp", END)
        .order("ticker")
        .order("timestamp")
        .range(offset, offset + page_size - 1)
        .execute()
    )
    batch = response.data or []
    rows.extend(batch)
    if len(batch) < page_size:
        break
    offset += page_size

if not rows:
    raise SystemExit(f"No 15m bars returned for {START} through {END}")

df = pd.DataFrame(rows)
for col in ["open", "high", "low", "close", "volume"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")
df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
df = df.dropna(subset=["ticker", "timestamp", "close"]).sort_values(["ticker", "timestamp"])

# Signal only uses current and past bars. To reduce false signals from corrupt
# provider data, bars flagged other than 'ok'/NULL and zero-volume bars cannot trigger.
signals = []
for ticker, g in df.groupby("ticker", sort=True):
    g = g.reset_index(drop=True)
    close = g["close"]
    volume = g["volume"]
    # Momentum: >= +2% over the last 4 bars, close breaks above the prior 8-bar
    # high, and current volume >= 1.5x median of up to 20 previous nonzero bars.
    for i in range(20, len(g) - 4):
        current = g.iloc[i]
        if current.get("data_quality_flag") not in (None, "ok"):
            continue
        if pd.isna(volume.iloc[i]) or volume.iloc[i] <= 0:
            continue
        prior_vol = volume.iloc[max(0, i - 20):i]
        prior_vol = prior_vol[prior_vol > 0].dropna()
        if len(prior_vol) < 8:
            continue
        median_vol = float(prior_vol.median())
        prior_high = float(g["high"].iloc[i - 8:i].max()) if g["high"].iloc[i - 8:i].notna().all() else float(close.iloc[i - 8:i].max())
        momentum_4 = float(close.iloc[i] / close.iloc[i - 4] - 1)
        volume_ratio = float(volume.iloc[i] / median_vol) if median_vol else 0
        if momentum_4 < 0.02 or close.iloc[i] <= prior_high or volume_ratio < 1.5:
            continue

        entry = float(close.iloc[i])
        future = g.iloc[i + 1:i + 5]
        if future.empty:
            continue
        future_returns = (future["close"] / entry - 1) * 100
        # Forward outcome is diagnostic, not a simulated execution: max/min close
        # over the next 4 bars and close at the 4th subsequent bar.
        signals.append({
            "ticker": ticker,
            "signal_time_utc": current["timestamp"].isoformat(),
            "entry_close": entry,
            "momentum_4bar_pct": round(momentum_4 * 100, 3),
            "volume_vs_prior_median": round(volume_ratio, 3),
            "prior_8bar_high": round(prior_high, 5),
            "forward_1h_max_close_pct": round(float(future_returns.max()), 3),
            "forward_1h_min_close_pct": round(float(future_returns.min()), 3),
            "forward_1h_close_pct": round(float(future_returns.iloc[-1]), 3),
            "hit_plus_2pct_close": bool((future_returns >= 2).any()),
            "hit_minus_1_5pct_close": bool((future_returns <= -1.5).any()),
        })

sig = pd.DataFrame(signals)
sig.to_csv(OUT / "momentum_signals.csv", index=False)
if not sig.empty:
    summary = {
        "period_start_utc": START,
        "period_end_utc_exclusive": END,
        "bars_loaded": int(len(df)),
        "tickers_loaded": int(df["ticker"].nunique()),
        "signals": int(len(sig)),
        "unique_tickers_signaled": int(sig["ticker"].nunique()),
        "forward_1h_close_positive_pct": round(float((sig["forward_1h_close_pct"] > 0).mean() * 100), 2),
        "forward_1h_close_ge_2pct_pct": round(float((sig["forward_1h_close_pct"] >= 2).mean() * 100), 2),
        "hit_plus_2pct_close_rate_pct": round(float(sig["hit_plus_2pct_close"].mean() * 100), 2),
        "hit_minus_1_5pct_close_rate_pct": round(float(sig["hit_minus_1_5pct_close"].mean() * 100), 2),
        "mean_forward_1h_close_pct": round(float(sig["forward_1h_close_pct"].mean()), 3),
        "median_forward_1h_close_pct": round(float(sig["forward_1h_close_pct"].median()), 3),
        "warning": "Exploratory, short and incomplete 15m history; no fees/slippage; signals overlap; close-based outcomes are not execution simulation."
    }
else:
    summary = {
        "period_start_utc": START,
        "period_end_utc_exclusive": END,
        "bars_loaded": int(len(df)),
        "tickers_loaded": int(df["ticker"].nunique()),
        "signals": 0,
        "warning": "No signals met the predefined criteria; this is not evidence of no opportunity."
    }
(OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))
print(f"Artifacts written to {OUT}")
