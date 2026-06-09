import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import pandas as pd 
import numpy as np 
import json 
import duckdb 
from config import SYMBOLS, DIRS


# Column Groups 

# MinMax scaling - price and volume based (bounded, non-negative)
MINMAX_COLS = [
    "open", "high", "low", "close", 
    "volume", "quote_volume", "taker_buy_base", "taker_buy_quote", 
    "sma_7", "sma_21", "sma_50", "sma_200", 
    "ema_12", "ema_26", 
    "bb_upper", "bb_mid", "bb_lower", 
    "atr_14", "volume_sma_20", 
    "price_range", "trades"
]

# Z-Score scaling - returns, ratios, oscilators (unbounded, can be negative)
ZSCORE_COLS = [
    "return_1d", "return_7d", "return_30d", "log_return", 
    "volatility_7d", "volatility_14d", "volatility_30d", 
    "rsi_14", "rsi_7", 
    "macd", "macd_signal", "macd_hist", 
    "bb_width", "bb_position", 
    "volume_ratio", "buy_pressure", 
    "price_position", "gap"
]

# Columns to keep as-is (binary, identifiers, timestamps)
PASSTHROUGH_COLS = [
    "symbol", "datetime", "open_time", "close_time", 
    "above_sma50", "above_sma200", 
    "golden_cross", "death_cross"
]

# Scalers 
def minmax_scale(series: pd.Series, min_val=None, max_val=None):
    """Scale series to [0, 1] range."""
    if min_val is None:
        min_val = series.min()
    if max_val is None:
        max_val = series.max()
        
    range_val = max_val - min_val
    if range_val == 0:
        return pd.Series(0.0, index=series.index), min_val, max_val
    
    scaled = (series - min_val) / range_val
    return scaled.round(6), min_val, max_val

def zscore_scale(series: pd.Series, mean=None, std=None):
    """Scale series to mean=0, std=1."""
    if mean is None:
        mean = series.mean()
    if std is None:
        std = series.std()
        
    if std == 0:
        return pd.Series(0.0, index=series.index), mean, std 
    
    scaled = (series - mean) / std 
    return scaled.round(6), mean, std 

# Per-Symbol Normalization 
def normalize_symbol(df: pd.DataFrame, symbol: str):
    """ 
    Normalize one symbol's data. 
    Returns normalised DataFrame + scaler params for inverse transform. 
    """
    df = df.copy()
    params = {"symbol": symbol, "minmax": {}, "zscore": {}}
    
    # Minimmize columns 
    for col in MINMAX_COLS:
        if col not in df.columns:
            continue
        df[col], mn, mx = minmax_scale(df[col].copy())
        params["minmax"][col] = {"min": mn, "max": mx}
        
    # Z-Score columns 
    for col in ZSCORE_COLS:
        if col not in df.columns:
            continue
        df[col], mean, std = zscore_scale(df[col].copy())
        params["zscore"][col] = {"mean": mean, "std": std}
    
    return df, params

# Inverse Transform 
def inverse_minmax(value, col:str, params: dict):
    """Convert normalized value back to orignal scale."""
    p = params["minmax"].get(col)
    if not p:
        return value 
    return value * (p["max"] - p["min"]) + p["min"]

def inverse_zscore(value, col:str, params: dict):
    """Convert z-scored value back to orignal scale."""
    p = params["zscore"].get(col)
    if not p:
        return value 
    return value * p["std"] + p["mean"]


# Maain 

def run_normalization():
    features_path = os.path.join(DIRS["master"], "master_features.parquet")
    normalized_path = os.path.join(DIRS["master"], "master_normalized.parquet")
    params_path = os.path.join(DIRS["master"], "master_params.json")
    
    if not os.path.exists(features_path): 
        print("master_features.parquet not found. Run features.py first.")
        return 
    
    print(f"\nLoading feature database...")
    df = pd.read_parquet(features_path)
    print(f"Loaded {len(df):,} rows | {len(df.columns)} columns")
    
    all_dfs = []
    all_params = {}
    
    for symbol in df["symbol"].unique():
        print(f"\nNormalizing {symbol}...")
        sym_df = df[df["symbol"] == symbol].copy()
        
        normalized_df, params = normalize_symbol(sym_df, symbol)
        all_dfs.append(normalized_df)
        all_params[symbol] = params
        
        print(f" {symbol:10} : {len(normalized_df):,} rows normalized")
        
    # Merge all 
    final = pd.concat(all_dfs, ignore_index=True)
    final.sort_values(["symbol", "datetime"], inplace=True)
    final.reset_index(drop=True, inplace=True)
    
    # save normalized parquet 
    final.to_parquet(normalized_path, index=False, compression="snappy")
    
    # Save scaler params as JSON for inverse transform later 
    # Convert numpy types to native Python for JSON serialization
    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        return obj 
    
    clean_params = {}
    for sym, p in all_params.items():
        clean_params[sym] = {
            "symbol": p["symbol"], 
            "minmax": {
                col: {"min": convert(v["min"]), "max": convert(v["max"])}
                for col, v in p["minmax"].items()
            }, 
            "zscore": {
                col: {"mean": convert(v["mean"]), "std": convert(v["std"])}
                for col, v in p["zscore"].items()
            },
        }
        
    with open(params_path, "w") as f:
        json.dump(clean_params, f, indent=2)    
    
    print(f"\n--- Normalization Complete ---")
    print(f"Total rows      : {len(final):,}")
    print(f"Total columns   : {len(final.columns)}")
    print(f"Normalized saved: {normalized_path}")
    print(f"Scaler params   : {params_path}")
    
    # Sanity check 
    print(f"\n--- Sanity Check: BTC Normalized Close (last 5) ---")
    con = duckdb.connect()
    np_ = normalized_path.replace("\\", "/")
    result = con.execute(f"""
        SELECT datetime, close, rsi_14, macd, volume_ratio, return_1d 
        FROM read_parquet('{np_}')
        WHERE symbol = 'BTCUSDT'
        ORDER BY datetime DESC
        LIMIT 5
    """).df()
    print(result.to_string(index=False))
    con.close()
    
    print(f"\n--- Scaler Params Sample (BTC close) ---")
    btc = clean_params["BTCUSDT"]
    print(f"  close minmax → min: {btc['minmax']['close']['min']:.2f}  "
          f"max: {btc['minmax']['close']['max']:.2f}")
    print(f"  return_1d zscore → mean: {btc['zscore']['return_1d']['mean']:.6f}  "
          f"std: {btc['zscore']['return_1d']['std']:.6f}")

    print(f"\n  To inverse transform a normalized close value:")
    print(f"  original_price = normalized_value × "
          f"({btc['minmax']['close']['max']:.2f} - "
          f"{btc['minmax']['close']['min']:.2f}) + "
          f"{btc['minmax']['close']['min']:.2f}")


if __name__ == "__main__":
    run_normalization()