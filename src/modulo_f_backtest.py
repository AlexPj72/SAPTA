"""
Modulo F: Backtesting Engine
Esegue backtest on-demand della strategia su dati storici.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
from config import supabase, TICKERS

def fetch_historical_data(ticker, days=180):
    try:
        threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        response = (supabase.table('prezzi')
                    .select('timestamp, open, high, low, close, volume')
                    .eq('ticker', ticker)
                    .gte('timestamp', threshold)
                    .order('timestamp', asc=True)
                    .execute())
        if not response.data:
            return None
        df = pd.DataFrame(response.data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
        return df
    except Exception as e:
        print(f"✠ Errore dati storici {ticker}: {e}")
        return None

def simulate_strategy(df, initial_capital=10000):
    if df is None or len(df) < 30:
        return None
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    capital = initial_capital
    position = 0
    trades = []
    for i in range(30, len(df)):
        rsi = df['rsi'].iloc[i]
        price = df['close'].iloc[i]
        if rsi < 30 and position == 0:
            shares_to_buy = int(capital / price)
            if shares_to_buy > 0:
                position = shares_to_buy
                capital -= shares_to_buy * price
                trades.append({'date': df.index[i], 'action': 'BUY', 'price': price, 'shares': shares_to_buy, 'capital': capital})
        elif rsi > 70 and position > 0:
            capital += position * price
            trades.append({'date': df.index[i], 'action': 'SELL', 'price': price, 'shares': position, 'capital': capital})
            position = 0
    final_value = capital + (position * df['close'].iloc[-1] if position > 0 else 0)
    total_return = (final_value - initial_capital) / initial_capital
    return {
        'total_return': total_return,
        'total_operations': len([t for t in trades if t['action'] == 'SELL']),
        'final_value': final_value
    }

def run_backtest(ticker, days=180, initial_capital=10000):
    print(f"\n💪 Backtest {ticker} ({days} giorni)...")
    df = fetch_historical_data(ticker, days)
    if df is None:
        print(f"➘ Nessun dato per {ticker}")
        return None
    results = simulate_strategy(df, initial_capital)
    if results is None:
        return None
    try:
        supabase.table('backtest_results').insert({
            'strategy_name': 'rule_based_rsi',
            'start_date': df.index[0].date().isoformat(),
            'end_date': df.index[-1].date().isoformat(),
            'gross_return': results['total_return'],
            'net_return': results['total_return'],
            'max_drawdown': 0.0,
            'total_operations': results['total_operations'],
            'win_rate': 0.0,
            'sharpe_ratio': 0.0
        }).execute()
        print(f"↔ Backtest {ticker}: return={results['total_return']:.2%}, ops={results['total_operations']}")
        return results
    except Exception as e:
        print(f"❤ Errore salvataggio backtest: {e}")
        return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticker', type=str, default=None)
    parser.add_argument('--days', type=int, default=180)
    parser.add_argument('--capital', type=float, default=10000)
    args = parser.parse_args()
    print(f"🚠 Modulo F - Backtesting: {datetime.now(timezone.utc).isoformat()}")
    tickers_to_test = [args.ticker] if args.ticker else TICKERS
    for ticker in tickers_to_test:
        run_backtest(ticker, args.days, args.capital)
