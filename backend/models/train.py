import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np
import json
import xgboost as xgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score


BASE_DIR   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH  = os.path.join(BASE_DIR, "data", "master", "master_features.parquet")
MODELS_DIR = os.path.join(BASE_DIR, "backend", "models", "saved")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

FEATURE_COLS = [
    "return_1d", "return_7d", "return_30d", "log_return",
    "volatility_7d", "volatility_14d", "volatility_30d",
    "rsi_14", "rsi_7",
    "macd", "macd_signal", "macd_hist",
    "bb_width", "bb_position",
    "sma_7", "sma_21", "sma_50",
    "volume_ratio", "buy_pressure",
    "price_position", "atr_14",
    "above_sma50", "above_sma200",
    "golden_cross", "death_cross"
]


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    for lag in [1, 2, 3, 5, 7]:
        df[f"return_lag_{lag}"]  = df["return_1d"].shift(lag)
        df[f"rsi_lag_{lag}"]     = df["rsi_14"].shift(lag)
        df[f"macd_lag_{lag}"]    = df["macd_hist"].shift(lag)
        df[f"vol_lag_{lag}"]     = df["volatility_7d"].shift(lag)
    return df


def get_lag_cols():
    cols = []
    for lag in [1, 2, 3, 5, 7]:
        cols += [f"return_lag_{lag}", f"rsi_lag_{lag}",
                 f"macd_lag_{lag}", f"vol_lag_{lag}"]
    return cols


def build_7d_direction(df: pd.DataFrame):
    """Target: 1 if price higher in 7 days, else 0."""
    df = df.copy().sort_values("datetime").reset_index(drop=True)
    df = add_lag_features(df)
    df["target"] = (df["close"].shift(-7) > df["close"]).astype(int)

    all_features = FEATURE_COLS + get_lag_cols()
    df = df.dropna(subset=all_features + ["target"]).iloc[:-7]

    return df[all_features].values, df["target"].values, all_features


def build_volatility_regime(df: pd.DataFrame):
    """
    Target:
    0 = Low vol   (next 7d realized vol < 33rd pct)
    1 = Medium vol
    2 = High vol  (next 7d realized vol > 66th pct)
    """
    df = df.copy().sort_values("datetime").reset_index(drop=True)
    df = add_lag_features(df)

    # Realized vol = std of next 7 daily returns
    df["future_vol"] = df["log_return"].shift(-1).rolling(7).std().shift(-6)

    p33 = df["future_vol"].quantile(0.33)
    p66 = df["future_vol"].quantile(0.66)

    df["target"] = pd.cut(
        df["future_vol"],
        bins=[-np.inf, p33, p66, np.inf],
        labels=[0, 1, 2]
    ).astype(int)

    all_features = FEATURE_COLS + get_lag_cols()
    df = df.dropna(subset=all_features + ["target"]).iloc[:-7]

    return df[all_features].values, df["target"].values, all_features, p33, p66


def build_market_regime(df: pd.DataFrame):
    """
    Target:
    0 = Bearish  (7d return < -3%)
    1 = Neutral  (-3% to +3%)
    2 = Bullish  (> +3%)
    """
    df = df.copy().sort_values("datetime").reset_index(drop=True)
    df = add_lag_features(df)

    df["future_return_7d"] = df["close"].shift(-7) / df["close"] - 1

    df["target"] = pd.cut(
        df["future_return_7d"],
        bins=[-np.inf, -0.03, 0.03, np.inf],
        labels=[0, 1, 2]
    ).astype(int)

    all_features = FEATURE_COLS + get_lag_cols()
    df = df.dropna(subset=all_features + ["target"]).iloc[:-7]

    return df[all_features].values, df["target"].values, all_features


def train_model(X, y, n_classes=2):
    """Train XGBoost with time series CV."""
    tscv    = TimeSeriesSplit(n_splits=5)
    cv_accs = []

    params = dict(
        n_estimators     = 300,
        max_depth        = 4,
        learning_rate    = 0.05,
        subsample        = 0.8,
        colsample_bytree = 0.8,
        min_child_weight = 5,
        gamma            = 0.1,
        use_label_encoder= False,
        eval_metric      = "mlogloss" if n_classes > 2 else "logloss",
        objective        = "multi:softprob" if n_classes > 2 else "binary:logistic",
        num_class        = n_classes if n_classes > 2 else None,
        random_state     = 42,
        verbosity        = 0
    )
    if n_classes == 2:
        params.pop("num_class")

    for train_idx, val_idx in tscv.split(X):
        m = xgb.XGBClassifier(**params)
        m.fit(X[train_idx], y[train_idx])
        cv_accs.append(accuracy_score(y[val_idx], m.predict(X[val_idx])))

    # Final model on all data
    final = xgb.XGBClassifier(**params)
    final.fit(X, y)

    return final, np.mean(cv_accs), cv_accs


def run_training():
    print(f"\n{'='*54}")
    print(f"  IMIS — Multi-Target XGBoost Training")
    print(f"{'='*54}")

    master = pd.read_parquet(DATA_PATH)
    os.makedirs(MODELS_DIR, exist_ok=True)

    for symbol in SYMBOLS:
        print(f"\n{'─'*54}")
        print(f"  {symbol}")
        print(f"{'─'*54}")
        df = master[master["symbol"] == symbol].copy()

        # ── Model 1: 7-Day Direction ──────────────────────────
        print(f"\n  [1] 7-Day Direction")
        X, y, feats = build_7d_direction(df)
        model, acc, folds = train_model(X, y, n_classes=2)
        print(f"      CV Accuracy : {acc*100:.2f}%")
        print(f"      Folds       : {[f'{a*100:.1f}%' for a in folds]}")

        model.save_model(os.path.join(MODELS_DIR, f"{symbol}_7d.json"))
        json.dump({
            "symbol": symbol, "model": "7d_direction",
            "feature_names": feats,
            "cv_accuracy": round(acc, 4),
            "trained_at": pd.Timestamp.now().isoformat()
        }, open(os.path.join(MODELS_DIR, f"{symbol}_7d_meta.json"), "w"), indent=2)

        # ── Model 2: Volatility Regime ────────────────────────
        print(f"\n  [2] Volatility Regime (Low/Med/High)")
        X, y, feats, p33, p66 = build_volatility_regime(df)
        dist = pd.Series(y).value_counts().sort_index().to_dict()
        print(f"      Classes: {dist}")
        model, acc, folds = train_model(X, y, n_classes=3)
        print(f"      CV Accuracy : {acc*100:.2f}%")

        model.save_model(os.path.join(MODELS_DIR, f"{symbol}_vol.json"))
        json.dump({
            "symbol": symbol, "model": "volatility_regime",
            "feature_names": feats,
            "cv_accuracy": round(acc, 4),
            "thresholds": {"p33": float(p33), "p66": float(p66)},
            "trained_at": pd.Timestamp.now().isoformat()
        }, open(os.path.join(MODELS_DIR, f"{symbol}_vol_meta.json"), "w"), indent=2)

        # ── Model 3: Market Regime ────────────────────────────
        print(f"\n  [3] Market Regime (Bearish/Neutral/Bullish)")
        X, y, feats = build_market_regime(df)
        dist = pd.Series(y).value_counts().sort_index().to_dict()
        print(f"      Classes: {dist}")
        model, acc, folds = train_model(X, y, n_classes=3)
        print(f"      CV Accuracy : {acc*100:.2f}%")

        model.save_model(os.path.join(MODELS_DIR, f"{symbol}_regime.json"))
        json.dump({
            "symbol": symbol, "model": "market_regime",
            "feature_names": feats,
            "cv_accuracy": round(acc, 4),
            "trained_at": pd.Timestamp.now().isoformat()
        }, open(os.path.join(MODELS_DIR, f"{symbol}_regime_meta.json"), "w"), indent=2)

    print(f"\n{'='*54}")
    print(f"  All models saved to: {MODELS_DIR}")
    print(f"{'='*54}\n")


if __name__ == "__main__":
    run_training()