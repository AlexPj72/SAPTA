# Backtest Walk-Forward — Report

Generato automaticamente da `modulo_f_backtest.py` il 2026-09-15T06:56:33.181176+00:00.

## Metodologia
- Strategia: stessa formula a punteggio di Modulo B (RSI+MACD+Bollinger),
  **senza sentiment** (non disponibile storicamente)
- Finestre: 6 mesi ciascuna, sequenziali non sovrapposte,
  su tutto lo storico disponibile per ticker
- 734 finestre totali su 134 ticker

## Risultati aggregati
- Rendimento medio per finestra: **4.69%**
- Rendimento mediano per finestra: 0.00%
- Sharpe ratio medio: 0.56
- Max drawdown medio: -8.41%
- Win rate medio (finestre con almeno un trade): 94.4%
- % finestre con rendimento positivo: 47.4%

## Nota interpretativa
Questi numeri riguardano **solo il canale rule-based**, isolato dagli altri
due canali (IA, XGBoost) che oggi dipendono da dati (sentiment, contesto)
senza storico sufficiente per un walk-forward onesto. Non è quindi un
verdetto su "SAPTA funziona", ma sulla componente tecnica pura.
