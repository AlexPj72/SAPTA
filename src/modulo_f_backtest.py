"""
Modulo F: Backtesting Engine — Walk-Forward (SAPTA — punto 6 audit ChatGPT 14/09)

Riscrittura completa. La versione precedente: backtest a finestra singola,
solo RSI, metriche win_rate/max_drawdown/sharpe_ratio hardcoded a 0.0 (mai
calcolate). Nessun workflow la richiamava — nessuna dipendenza da rompere.

Metodologia walk-forward: la storia (fino a 7 anni) viene divisa in finestre
sequenziali non sovrapposte (default 6 mesi ciascuna). La strategia (stessa
logica a punteggio di Modulo B: RSI+MACD+BB, SENZA sentiment — non
disponibile storicamente) viene simulata in ogni finestra separatamente,
poi i risultati si aggregano. Questo dà un'idea di come la strategia si
sarebbe comportata in periodi di mercato diversi, non solo nell'ultimo
semestre (che potrebbe essere anomalo).

Limite dichiarato: usa solo le feature tecniche (no sentiment/GDELT/IA),
perché quei segnali non hanno storico persistito abbastanza lungo per un
walk-forward multi-anno. Il confronto con i canali IA/XGBoost va fatto
separatamente, su dati live, non retroattivamente.
"""
import os
import json
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import pandas_ta_classic as ta
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

WINDOW_MONTHS = 6
MIN_BARS_PER_WINDOW = 60  # sotto questa soglia la finestra si scarta (troppo corta)
INITIAL_CAPITAL = 10000
REPORT_PATH = "BACKTEST_WALKFORWARD_REPORT.md"


def fetch_all_daily_prices():
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        response = (
            supabase.table("prezzi")
            .select("ticker, timestamp, close")
            .eq("interval", "1d")
            .order("ticker")
            .order("timestamp")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = response.data
        if not rows:
            break
        all_rows.extend(rows)
        offset += page_size
        if len(rows) < page_size:
            break
    df = pd.DataFrame(all_rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    print(f"📥 Scaricate {len(df)} righe di storico giornaliero")
    return df


def compute_indicators(g):
    """Stessa logica di Modulo B (RSI, MACD, BB), senza sentiment."""
    g = g.sort_values("timestamp").reset_index(drop=True)
    g["rsi"] = ta.rsi(g["close"], length=14)
    macd_df = ta.macd(g["close"])
    g["macd"] = macd_df.iloc[:, 0]
    g["macd_signal"] = macd_df.iloc[:, 2]
    bb_df = ta.bbands(g["close"], length=20)
    g["bb_position"] = (g["close"] - bb_df.iloc[:, 0]) / (bb_df.iloc[:, 2] - bb_df.iloc[:, 0])
    return g


def rule_based_score(row):
    """Stessa formula a punteggio di generate_signal() in modulo_b_analysis.py,
    senza il termine sentiment (non disponibile storicamente)."""
    score = 0
    if row["rsi"] < 30:
        score += 2
    elif row["rsi"] > 70:
        score -= 2
    if row["macd"] > row["macd_signal"]:
        score += 1
    else:
        score -= 1
    if row["bb_position"] < 0.2:
        score += 1
    elif row["bb_position"] > 0.8:
        score -= 1
    if score >= 2:
        return "BUY"
    if score <= -2:
        return "SELL"
    return "HOLD"


def simulate_window(g, initial_capital=INITIAL_CAPITAL):
    """Simula la strategia su una singola finestra temporale.
    Ritorna metriche vere (non più hardcoded)."""
    capital = initial_capital
    position = 0
    entry_price = 0
    equity_curve = [initial_capital]
    trade_returns = []

    for _, row in g.iterrows():
        if pd.isna(row["rsi"]) or pd.isna(row["macd"]) or pd.isna(row["bb_position"]):
            equity_curve.append(capital + (position * row["close"] if position > 0 else 0))
            continue

        action = rule_based_score(row)
        price = row["close"]

        if action == "BUY" and position == 0:
            shares = int(capital / price)
            if shares > 0:
                position = shares
                entry_price = price
                capital -= shares * price
        elif action == "SELL" and position > 0:
            capital += position * price
            trade_returns.append((price - entry_price) / entry_price)
            position = 0

        equity_curve.append(capital + (position * price if position > 0 else 0))

    final_value = capital + (position * g["close"].iloc[-1] if position > 0 else 0)
    total_return = (final_value - initial_capital) / initial_capital

    equity = pd.Series(equity_curve)
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    max_drawdown = drawdown.min()

    daily_returns = equity.pct_change().dropna()
    sharpe = (
        (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        if daily_returns.std() > 0 else 0.0
    )

    win_rate = (
        len([r for r in trade_returns if r > 0]) / len(trade_returns)
        if trade_returns else 0.0
    )

    return {
        "total_return": total_return,
        "max_drawdown": float(max_drawdown) if not pd.isna(max_drawdown) else 0.0,
        "sharpe_ratio": float(sharpe) if not pd.isna(sharpe) else 0.0,
        "win_rate": win_rate,
        "total_operations": len(trade_returns),
        "final_value": final_value,
    }


def run_walk_forward(df):
    all_results = []

    for ticker, g in df.groupby("ticker"):
        g = compute_indicators(g)
        start = g["timestamp"].min()
        end = g["timestamp"].max()

        window_start = start
        while window_start < end:
            window_end = window_start + pd.DateOffset(months=WINDOW_MONTHS)
            window = g[(g["timestamp"] >= window_start) & (g["timestamp"] < window_end)]

            if len(window) >= MIN_BARS_PER_WINDOW:
                result = simulate_window(window)
                result.update({
                    "ticker": ticker,
                    "start_date": window_start.date().isoformat(),
                    "end_date": window_end.date().isoformat(),
                })
                all_results.append(result)

            window_start = window_end

    return all_results


def save_results_and_report(results):
    if not results:
        print("⚠️ Nessun risultato da salvare")
        return

    for r in results:
        try:
            supabase.table("backtest_results").insert({
                "strategy_name": "rule_based_walkforward_v1",
                "start_date": r["start_date"],
                "end_date": r["end_date"],
                "gross_return": r["total_return"],
                "net_return": r["total_return"],
                "max_drawdown": r["max_drawdown"],
                "total_operations": r["total_operations"],
                "win_rate": r["win_rate"],
                "sharpe_ratio": r["sharpe_ratio"],
            }).execute()
        except Exception as e:
            print(f"⚠️ Errore salvataggio finestra {r['ticker']} {r['start_date']}: {e}")

    df_results = pd.DataFrame(results)
    n_windows = len(df_results)
    n_tickers = df_results["ticker"].nunique()
    avg_return = df_results["total_return"].mean()
    median_return = df_results["total_return"].median()
    avg_sharpe = df_results["sharpe_ratio"].mean()
    avg_max_dd = df_results["max_drawdown"].mean()
    avg_win_rate = df_results[df_results["total_operations"] > 0]["win_rate"].mean()
    pct_positive_windows = (df_results["total_return"] > 0).mean()

    report = f"""# Backtest Walk-Forward — Report

Generato automaticamente da `modulo_f_backtest.py` il {datetime.now(timezone.utc).isoformat()}.

## Metodologia
- Strategia: stessa formula a punteggio di Modulo B (RSI+MACD+Bollinger),
  **senza sentiment** (non disponibile storicamente)
- Finestre: {WINDOW_MONTHS} mesi ciascuna, sequenziali non sovrapposte,
  su tutto lo storico disponibile per ticker
- {n_windows} finestre totali su {n_tickers} ticker

## Risultati aggregati
- Rendimento medio per finestra: **{avg_return*100:.2f}%**
- Rendimento mediano per finestra: {median_return*100:.2f}%
- Sharpe ratio medio: {avg_sharpe:.2f}
- Max drawdown medio: {avg_max_dd*100:.2f}%
- Win rate medio (finestre con almeno un trade): {avg_win_rate*100:.1f}%
- % finestre con rendimento positivo: {pct_positive_windows*100:.1f}%

## Nota interpretativa
Questi numeri riguardano **solo il canale rule-based**, isolato dagli altri
due canali (IA, XGBoost) che oggi dipendono da dati (sentiment, contesto)
senza storico sufficiente per un walk-forward onesto. Non è quindi un
verdetto su "SAPTA funziona", ma sulla componente tecnica pura.
"""
    with open(REPORT_PATH, "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    print(f"🚀 Modulo F - Backtest Walk-Forward: {datetime.now(timezone.utc).isoformat()}")
    raw = fetch_all_daily_prices()
    if raw.empty:
        print("❌ Nessun dato scaricato, interrompo")
        exit(1)
    results = run_walk_forward(raw)
    print(f"📐 {len(results)} finestre simulate")
    save_results_and_report(results)
