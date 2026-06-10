import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np
import json
import xgboost as xgb


BASE_DIR   = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATH  = os.path.join(BASE_DIR, "data", "master", "master_features.parquet")
MODELS_DIR = os.path.join(BASE_DIR, "backend", "models", "saved")

_cache = {}


def load_model(symbol: str, model_type: str):
    key = f"{symbol}_{model_type}"
    if key in _cache:
        return _cache[key]

    model_path = os.path.join(MODELS_DIR, f"{symbol}_{model_type}.json")
    meta_path  = os.path.join(MODELS_DIR, f"{symbol}_{model_type}_meta.json")

    if not os.path.exists(model_path):
        return None, None

    model = xgb.XGBClassifier()
    model.load_model(model_path)

    with open(meta_path) as f:
        meta = json.load(f)

    _cache[key] = (model, meta)
    return model, meta


def get_features(df: pd.DataFrame, feature_names: list):
    """Add lag features and return latest row."""
    df = df.copy().sort_values("datetime").reset_index(drop=True)

    for lag in [1, 2, 3, 5, 7]:
        df[f"return_lag_{lag}"] = df["return_1d"].shift(lag)
        df[f"rsi_lag_{lag}"]    = df["rsi_14"].shift(lag)
        df[f"macd_lag_{lag}"]   = df["macd_hist"].shift(lag)
        df[f"vol_lag_{lag}"]    = df["volatility_7d"].shift(lag)

    latest = df[feature_names].dropna().iloc[-1:]
    return latest


def get_trend(row: pd.Series) -> dict:
    """Derive trend from technical indicators."""
    close      = row.get("close", 0)
    sma_50     = row.get("sma_50", 0)
    sma_200    = row.get("sma_200", 0)
    macd_hist  = row.get("macd_hist", 0)
    rsi        = row.get("rsi_14", 50)

    # Trend direction
    if close > sma_50 and close > sma_200:
        trend = "Bullish"
        trend_color = "#00d97e"
    elif close < sma_50 and close < sma_200:
        trend = "Bearish"
        trend_color = "#ff4d6a"
    else:
        trend = "Mixed"
        trend_color = "#ffaa00"

    # Momentum
    if macd_hist > 0 and rsi > 50:
        momentum = "Strong"
        momentum_color = "#00d97e"
    elif macd_hist > 0 or rsi > 50:
        momentum = "Moderate"
        momentum_color = "#ffaa00"
    elif macd_hist < 0 and rsi < 40:
        momentum = "Weak"
        momentum_color = "#ff4d6a"
    else:
        momentum = "Neutral"
        momentum_color = "#7a7f96"

    return {
        "trend"          : trend,
        "trend_color"    : trend_color,
        "momentum"       : momentum,
        "momentum_color" : momentum_color
    }


def get_volatility_regime(symbol: str, df: pd.DataFrame) -> dict:
    """Use ML model to predict volatility regime."""
    model, meta = load_model(symbol, "vol")

    labels = {
        0: {"label": "Low",    "color": "#00d97e"},
        1: {"label": "Medium", "color": "#ffaa00"},
        2: {"label": "High",   "color": "#ff4d6a"}
    }

    if model is None:
        return {"label": "Unknown", "color": "#7a7f96", "confidence": 0}

    X = get_features(df, meta["feature_names"])
    if X.empty:
        return {"label": "Unknown", "color": "#7a7f96", "confidence": 0}

    proba     = model.predict_proba(X)[0]
    predicted = int(np.argmax(proba))
    confidence = round(float(max(proba)) * 100, 1)

    return {
        "label"      : labels[predicted]["label"],
        "color"      : labels[predicted]["color"],
        "confidence" : confidence,
        "accuracy"   : round(meta["cv_accuracy"] * 100, 1)
    }


def get_market_regime(symbol: str, df: pd.DataFrame) -> dict:
    """Use ML model to predict market regime."""
    model, meta = load_model(symbol, "regime")

    labels = {
        0: {"label": "Bearish", "color": "#ff4d6a"},
        1: {"label": "Neutral", "color": "#ffaa00"},
        2: {"label": "Bullish", "color": "#00d97e"}
    }

    if model is None:
        return {"label": "Unknown", "color": "#7a7f96", "confidence": 0}

    X = get_features(df, meta["feature_names"])
    if X.empty:
        return {"label": "Unknown", "color": "#7a7f96", "confidence": 0}

    proba     = model.predict_proba(X)[0]
    predicted = int(np.argmax(proba))
    confidence = round(float(max(proba)) * 100, 1)

    return {
        "label"      : labels[predicted]["label"],
        "color"      : labels[predicted]["color"],
        "confidence" : confidence,
        "accuracy"   : round(meta["cv_accuracy"] * 100, 1)
    }


def get_master_df():
    """Get master dataframe from main memory store or parquet fallback."""
    try:
        import sys
        main_module = sys.modules.get('main')
        if main_module and hasattr(main_module, 'get_master'):
            return main_module.get_master()
    except Exception:
        pass
    if os.path.exists(DATA_PATH):
        return pd.read_parquet(DATA_PATH)
    return None


def get_intelligence(symbol: str) -> dict:
    """Full intelligence summary for one symbol."""
    master = get_master_df()

    if master is None or master.empty:
        return {
            "symbol"         : symbol,
            "trend"          : "Unknown",
            "trend_color"    : "#7a7f96",
            "momentum"       : "Unknown",
            "momentum_color" : "#7a7f96",
            "volatility"     : "Unknown",
            "volatility_color": "#7a7f96",
            "regime"         : "Unknown",
            "regime_color"   : "#7a7f96",
            "note"           : "Data not available"
        }

    if "datetime" not in master.columns:
        master = master.reset_index()
        if "Date" in master.columns:
            master.rename(columns={"Date": "datetime"}, inplace=True)

    df = master[master["symbol"] == symbol].copy()

    if df.empty:
        return None

    latest = df.sort_values("datetime").iloc[-1]

    trend      = get_trend(latest)
    volatility = get_volatility_regime(symbol, df)
    regime     = get_market_regime(symbol, df)

    return {
        "symbol"          : symbol,
        "date"            : str(latest["datetime"])[:10],
        "trend"           : trend["trend"],
        "trend_color"     : trend["trend_color"],
        "momentum"        : trend["momentum"],
        "momentum_color"  : trend["momentum_color"],
        "volatility"      : volatility["label"],
        "volatility_color": volatility["color"],
        "regime"          : regime["label"],
        "regime_color"    : regime["color"],
        "note"            : "ML-assisted regime detection. Not financial advice."
    }

def get_all_intelligence() -> list:
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    return [get_intelligence(s) for s in SYMBOLS]


if __name__ == "__main__":
    print("\n--- IMIS Market Intelligence ---\n")
    for intel in get_all_intelligence():
        print(f"{intel['symbol']}")
        print(f"  Trend      : {intel['trend']}")
        print(f"  Momentum   : {intel['momentum']}")
        print(f"  Volatility : {intel['volatility']}")
        print(f"  Regime     : {intel['regime']}")
        print()