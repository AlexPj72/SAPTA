# XGBoost — Report di training e validazione

Generato automaticamente da `train_xgboost_model.py` il 2026-09-15T01:08:47.968521+00:00.

**Canale parallelo, non ancora integrato in produzione.** Prima di usarlo
per decisioni reali va confrontato con i canali esistenti (rule-based,
Modulo I) su dati live per un periodo congruo.

## Metodologia
- Split temporale: train fino a `2025-01-01`, validazione
  **out-of-sample** dopo quella data (no lookahead bias)
- Label: rendimento a 5 giorni, soglie ±2%
  (placeholder non calibrato)
- Feature: rsi, macd, macd_signal, bb_position, atr_pct

## Dimensione dataset
- Train: 29926 righe — distribuzione classi: {'HOLD': 13891, 'BUY': 8908, 'SELL': 7127}
- Test (out-of-sample): 56326 righe — distribuzione classi: {'HOLD': 23412, 'BUY': 18475, 'SELL': 14439}

## Classification report (out-of-sample)
```
              precision    recall  f1-score   support

        SELL       0.32      0.07      0.11     14439
        HOLD       0.47      0.76      0.58     23412
         BUY       0.40      0.34      0.36     18475

    accuracy                           0.44     56326
   macro avg       0.40      0.39      0.35     56326
weighted avg       0.41      0.44      0.39     56326

```

## Confusion matrix (righe=reale, colonne=predetto — ordine SELL/HOLD/BUY)
```
[[  953  8821  4665]
 [  820 17811  4781]
 [ 1171 11113  6191]]
```
