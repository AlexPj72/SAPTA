"""
Training XGBoost (SAPTA — punto 2 audit ChatGPT 14/09).
Script OFFLINE/MANUALE — non gira nella pipeline schedulata (fast/slow).
Si lancia solo via workflow_dispatch (train_xgboost.yml), quando serve
ri-addestrare o validare il modello.

Canale PARALLELO: non sostituisce la formula a punteggio di Modulo B.
Il modello prodotto qui va integrato in futuro come terzo giudizio
indipendente (stesso principio del Modulo I), non come sostituzione diretta,
finché non si è confrontato con i canali esistenti su dati reali.

Metodologia (per evitare lookahead bias):
- Split TEMPORALE, non casuale: train su dati fino a TRAIN_CUTOFF_DATE,
  validazione out-of-sample sui dati successivi (walk-forward, stesso
  principio già previsto per il backtest in SAPTA_v4.md).
- Feature: stessi indicatori già usati da Modulo B (rsi, macd, macd_signal,
  bb_position, atr normalizzato sul prezzo) — cosi' il confronto fra i
  canali (rule-based, IA, XGBoost) è sugli stessi input.
- Label: rendimento a 5 giorni di trading avanti, soglie ±2% per
  BUY/SELL/HOLD (placeholder, non calibrato — stesso avviso già presente in
  scoring_weights_v1.json va esteso anche a questa soglia).
"""
import os
import json
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import pandas_ta_classic as ta
import xgboost as xgb
from sklearn.metrics import classification_report, confusion_matrix
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

TRAIN_CUTOFF_DATE = "2025-01-01"  # train prima di questa data, test dopo (out-of-sample)
FORWARD_DAYS = 5
RETURN_THRESHOLD = 0.02  # ±2% - placeholder non calibrato, vedi nota sopra
MIN_BARS_PER_TICKER = 250  # ~1 anno di dati, sotto questa soglia il ticker si scarta

MODEL_DIR = "models"
MODEL_PATH = f"{MODEL_DIR}/xgboost_v1.json"
META_PATH = f"{MODEL_DIR}/xgboost_v1_meta.json"
REPORT_PATH = "XGBOOST_TRAINING_REPORT.md"

FEATURE_COLUMNS = ["rsi", "macd", "macd_signal", "bb_position", "atr_pct"]
LABEL_MAP = {"SELL": 0, "HOLD": 1, "BUY": 2}
LABEL_MAP_INV = {v: k for k, v in LABEL_MAP.items()}


def fetch_all_daily_prices():
    """Scarica tutto lo storico giornaliero da Supabase, paginato (il client
    REST di default limita a 1000 righe per chiamata)."""
    all_rows = []
    page_size = 1000
    offset = 0
    while True:
        response = (
            supabase.table("prezzi")
            .select("ticker, timestamp, close, high, low")
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
    print(f"📥 Scaricate {len(all_rows)} righe di storico giornaliero")
    return pd.DataFrame(all_rows)


def build_features_and_labels(df):
    """Calcola indicatori tecnici e label per ogni ticker separatamente
    (le serie temporali non vanno mescolate tra ticker diversi)."""
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    all_frames = []

    for ticker, g in df.groupby("ticker"):
        g = g.sort_values("timestamp").reset_index(drop=True)
        if len(g) < MIN_BARS_PER_TICKER:
            continue

        g["rsi"] = ta.rsi(g["close"], length=14)
        macd_df = ta.macd(g["close"])
        g["macd"] = macd_df.iloc[:, 0]
        g["macd_signal"] = macd_df.iloc[:, 2]
        bb_df = ta.bbands(g["close"], length=20)
        bb_lower, bb_upper = bb_df.iloc[:, 0], bb_df.iloc[:, 2]
        g["bb_position"] = (g["close"] - bb_lower) / (bb_upper - bb_lower)
        g["atr"] = ta.atr(g["high"], g["low"], g["close"], length=14)
        g["atr_pct"] = g["atr"] / g["close"]

        g["forward_close"] = g["close"].shift(-FORWARD_DAYS)
        g["forward_return"] = (g["forward_close"] - g["close"]) / g["close"]

        def classify(r):
            if pd.isna(r):
                return None
            if r > RETURN_THRESHOLD:
                return "BUY"
            if r < -RETURN_THRESHOLD:
                return "SELL"
            return "HOLD"

        g["label"] = g["forward_return"].apply(classify)
        g["ticker"] = ticker
        all_frames.append(g)

    result = pd.concat(all_frames, ignore_index=True)
    result = result.dropna(subset=FEATURE_COLUMNS + ["label"])
    return result


def train_and_validate(df):
    """Split temporale (no lookahead): train prima del cutoff, test dopo."""
    train_df = df[df["timestamp"] < TRAIN_CUTOFF_DATE]
    test_df = df[df["timestamp"] >= TRAIN_CUTOFF_DATE]

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["label"].map(LABEL_MAP)
    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df["label"].map(LABEL_MAP)

    print(f"📊 Train: {len(X_train)} righe (fino a {TRAIN_CUTOFF_DATE})")
    print(f"📊 Test (out-of-sample): {len(X_test)} righe (da {TRAIN_CUTOFF_DATE})")

    model = xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        max_depth=4,
        n_estimators=200,
        learning_rate=0.05,
        eval_metric="mlogloss",
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    report = classification_report(
        y_test, y_pred, target_names=["SELL", "HOLD", "BUY"], zero_division=0
    )
    cm = confusion_matrix(y_test, y_pred)

    return model, report, cm, len(X_train), len(X_test), train_df["label"].value_counts(), test_df["label"].value_counts()


def save_model_and_report(model, report, cm, n_train, n_test, train_dist, test_dist):
    os.makedirs(MODEL_DIR, exist_ok=True)
    model.save_model(MODEL_PATH)

    meta = {
        "feature_columns": FEATURE_COLUMNS,
        "label_map": LABEL_MAP,
        "train_cutoff_date": TRAIN_CUTOFF_DATE,
        "forward_days": FORWARD_DAYS,
        "return_threshold": RETURN_THRESHOLD,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    report_md = f"""# XGBoost — Report di training e validazione

Generato automaticamente da `train_xgboost_model.py` il {datetime.now(timezone.utc).isoformat()}.

**Canale parallelo, non ancora integrato in produzione.** Prima di usarlo
per decisioni reali va confrontato con i canali esistenti (rule-based,
Modulo I) su dati live per un periodo congruo.

## Metodologia
- Split temporale: train fino a `{TRAIN_CUTOFF_DATE}`, validazione
  **out-of-sample** dopo quella data (no lookahead bias)
- Label: rendimento a {FORWARD_DAYS} giorni, soglie ±{RETURN_THRESHOLD*100:.0f}%
  (placeholder non calibrato)
- Feature: {', '.join(FEATURE_COLUMNS)}

## Dimensione dataset
- Train: {n_train} righe — distribuzione classi: {train_dist.to_dict()}
- Test (out-of-sample): {n_test} righe — distribuzione classi: {test_dist.to_dict()}

## Classification report (out-of-sample)
```
{report}
```

## Confusion matrix (righe=reale, colonne=predetto — ordine SELL/HOLD/BUY)
```
{cm}
```
"""
    with open(REPORT_PATH, "w") as f:
        f.write(report_md)

    print("✅ Modello e report salvati")


if __name__ == "__main__":
    raw = fetch_all_daily_prices()
    if raw.empty:
        print("❌ Nessun dato scaricato da Supabase, interrompo")
        exit(1)

    dataset = build_features_and_labels(raw)
    print(f"📐 Dataset finale (dopo feature engineering e dropna): {len(dataset)} righe")

    model, report, cm, n_train, n_test, train_dist, test_dist = train_and_validate(dataset)
    print(report)

    save_model_and_report(model, report, cm, n_train, n_test, train_dist, test_dist)
