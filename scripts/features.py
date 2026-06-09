import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd 
import numpy as np 
import duckdb 
from config import SYMBOLS, DIRS 

# RSI 
def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods= period).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.round(4)

# MACD 
def compute_macd(series: pd.Series, fast= 12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.round(4), signal_line.round(4), histogram.round(4)

# Bollinger Bands 
def compute_bollinger(series: pd.Series, period=20, std_dev=2):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper.round(4), sma.round(4), lower.round(4)

# ATR 
def compute_atr(df: pd.DataFrame, period=14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    tr = pd.concat([
        high - low, 
        (high - close.shift()).abs(), 
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    
    return tr.ewm(com=period - 1, min_periods=period).mean().round(4)

# Main Feature Engineering 
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.sort_values("datetime", inplace=True)
    df.reset_index(drop=True, inplace=True)
    
    close = df["close"]
    volume = df["volume"]
    
    # Returns 
    df["return_1d"] = close.pct_change(1).round(6)
    df["return_7d"] = close.pct_change(7).round(6)
    df["return_30d"] = close.pct_change(30).round(6)
    df["log_return"] = np.log(close / close.shift(1)).round(6)
    
    # Volatility 
    df["volatility_7d"] = df["log_return"].rolling(7).std().round(6)
    df["volatility_14d"] = df["log_return"].rolling(14).std().round(6)
    df["volatility_30d"] = df["log_return"].rolling(30).std().round(6)
    
    # Moving Averages 
    df["sma_7"] = close.rolling(7).mean().round(4)
    df["sma_21"] = close.rolling(21).mean().round(4)
    df["sma_50"] = close.rolling(50).mean().round(4)
    df["sma_200"] = close.rolling(200).mean().round(4)
    df["ema_12"] = close.ewm(span=12, adjust=False).mean().round(4)
    df["ema_26"] = close.ewm(span=26, adjust=False).mean().round(4)
    
    # RSI 
    df["rsi_14"] = compute_rsi(close, 14)
    df["rsi_7"] = compute_rsi(close, 7)
    
    # MACD 
    df["macd"], df["macd_signal"], df["macd_hist"] = compute_macd(close)
    
    # Bollinger Bands 
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = compute_bollinger(close)
    df["bb_width"] = ((df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]).round(6)
    df["bb_position"] = ((close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])).round(6)
    
    # ATR 
    df["atr_14"] = compute_atr(df, 14)
    
    # Volume Features 
    df["volume_sma_20"] = volume.rolling(20).mean().round(2)
    df["volume_ratio"] = (volume / df["volume_sma_20"]).round(4)
    df["buy_pressure"] = (df["taker_buy_base"] / volume.replace(0, np.nan)).round(4)
    
    # Price Position 
    df["price_range"] = (df["high"] - df["low"]).round(4)
    df["price_position"] = ((close - df["low"]) / df["price_range"].replace(0, np.nan)).round(4)
    df["gap"] = (df["open"] - close.shift(1)).round(4)
    
    # Trend Signals 
    df["above_sma50"] = (close > df["sma_50"]).astype(int)
    df["above_sma200"] = (close > df["sma_200"]).astype(int)
    df["golden_cross"] = ((df["sma_50"] > df["sma_200"]) & 
                          (df["sma_50"].shift(1) <= df["sma_200"].shift(1))).astype(int)
    df["death_cross"] = ((df["sma_50"] < df["sma_200"]) & 
                          (df["sma_50"].shift(1) >= df["sma_200"].shift(1))).astype(int)
    
    return df 


def run_features():
    master_path = os.path.join(DIRS["master"], "master_all.parquet")
    features_path = os.path.join(DIRS["master"], "master_features.parquet")
    
    if not os.path.exists(master_path):
        print("master_all.parquet not found. Run builder.py first")
        return 
    
    print(f"\nLoading master database...")
    master = pd.read_parquet(master_path)
    print(f"Loaded {len(master):,}  rows across {master['symbol'].nunique()} symbols")
    
    all_dfs = []
    
    for symbol in master["symbol"].unique():
        print(f"\nEngineering features for {symbol}...")
        df = master[master["symbol"] == symbol].copy()
        df = engineer_features(df) 
        all_dfs.append(df)
        print(f" {symbol:10} : {len(df):,} rows | {len(df.columns)} columns")
        
    final = pd.concat(all_dfs, ignore_index=True)
    final.sort_values(["symbol", "datetime"], inplace=True)
    
    final.to_parquet(features_path, index= False, compression="snappy")
    
    print(f"\n--- Feature Engineering Complete ---")
    print(f"Total rows    : {len(final):,}")
    print(f"Total columns : {len(final.columns)}")
    print(f"Saved to      : {features_path}")
    
    # Show column list 
    print(f"\n--- All Columns ---")
    for i, col in enumerate(final.columns, 1):
        print(f" {i:02d}. {col}")
        
    # Quick sanity check via DuckDB 
    print(f"\n--- Sanity Check: Latest BTC Features ---")
    con = duckdb.connect()
    fp = features_path.replace("\\", "/")
    result = con.execute(f"""
        SELECT datetime, close, rsi_14, macd, bb_position, 
            volatility_30d, above_sma200, volume_ratio
        FROM read_parquet('{fp}')
        WHERE symbol = 'BTCUSDT'
        ORDER BY datetime DESC 
        LIMIT 5 
    """).df()
    print(result.to_string(index=False))
    con.close()
    
if __name__ == "__main__":
    run_features()