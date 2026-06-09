import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import requests
requests.adapters.DEFAULT_RETRIES = 1
import yfinance as yf 
import pandas as pd 
import numpy as np 
from datetime import datetime, timedelta


# Symbols Registry 

INDIA_SYMBOLS = {
    "indices": {
        "^NSEI"    : "NIFTY 50",
        "^BSESN"   : "SENSEX",
        "^NSEBANK" : "BANKNIFTY"
    },
    "stocks": {
        "RELIANCE.NS" : "Reliance",
        "TCS.NS"      : "TCS",
        "INFY.NS"     : "Infosys",
        "HDFCBANK.NS" : "HDFC Bank",
        "WIPRO.NS"    : "Wipro"
    },
    "commodities": {
        "GC=F" : "Gold",
        "SI=F" : "Silver"
    },
    "currency": {
        "INR=X" : "USD/INR"
    }
}

ALL_SYMBOLS = {}
for category, symbols in INDIA_SYMBOLS.items():
    for ticker, name in symbols.items():
        ALL_SYMBOLS[ticker] = {"name": name, "category": category}
        

# Feature Engineering 

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs  = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).round(4)


def compute_macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast    = series.ewm(span=fast,      adjust=False).mean()
    ema_slow    = series.ewm(span=slow,      adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.round(4), signal_line.round(4), histogram.round(4)


def compute_bollinger(series: pd.Series, period: int = 20, std_dev: float = 2):
    sma = series.rolling(period).mean()
    std = series.rolling(period).std()
    return (sma + std * std_dev).round(4), sma.round(4), (sma - std* std_dev).round(4)


def engineer_features(df: pd.DataFrame, ticker: str) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    
    df["ticker"]       = ticker
    df["name"]         = ALL_SYMBOLS.get(ticker, {}).get("name", ticker)
    df["category"]     = ALL_SYMBOLS.get(ticker, {}).get("category", "unknown")

    # Returns
    df["return_1d"]    = close.pct_change(1).round(6)
    df["return_7d"]    = close.pct_change(7).round(6)
    df["return_30d"]   = close.pct_change(30).round(6)
    df["log_return"]   = np.log(close / close.shift(1)).round(6)

    # Volatility
    df["volatility_7d"]  = df["log_return"].rolling(7).std().round(6)
    df["volatility_14d"] = df["log_return"].rolling(14).std().round(6)
    df["volatility_30d"] = df["log_return"].rolling(30).std().round(6)

    # Moving averages
    df["sma_7"]   = close.rolling(7).mean().round(4)
    df["sma_21"]  = close.rolling(21).mean().round(4)
    df["sma_50"]  = close.rolling(50).mean().round(4)
    df["sma_200"] = close.rolling(200).mean().round(4)
    df["ema_12"]  = close.ewm(span=12, adjust=False).mean().round(4)
    df["ema_26"]  = close.ewm(span=26, adjust=False).mean().round(4)

    # RSI
    df["rsi_14"] = compute_rsi(close, 14)
    df["rsi_7"]  = compute_rsi(close, 7)

    # MACD
    df["macd"], df["macd_signal"], df["macd_hist"] = compute_macd(close)

    # Bollinger
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = compute_bollinger(close)
    df["bb_width"]    = ((df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]).round(6)
    df["bb_position"] = ((close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])).round(6)

    # ATR
    high  = df["high"]
    low   = df["low"]
    tr    = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.ewm(com=13, min_periods=14).mean().round(4)

    # Volume
    volume = df["volume"]
    df["volume_sma_20"] = volume.rolling(20).mean().round(2)
    df["volume_ratio"]  = (volume / df["volume_sma_20"].replace(0, np.nan)).round(4)

    # Price position
    df["price_range"]    = (high - low).round(4)
    df["price_position"] = ((close - low) / df["price_range"].replace(0, np.nan)).round(4)

    # Trend signals
    df["above_sma50"]  = (close > df["sma_50"]).astype(int)
    df["above_sma200"] = (close > df["sma_200"]).astype(int)
    df["golden_cross"] = ((df["sma_50"] > df["sma_200"]) &
                          (df["sma_50"].shift(1) <= df["sma_200"].shift(1))).astype(int)
    df["death_cross"]  = ((df["sma_50"] < df["sma_200"]) &
                          (df["sma_50"].shift(1) >= df["sma_200"].shift(1))).astype(int)

    return df


# Data Fetcher 
def fetch_ticker(yTicker: str, period: str = "2y") -> pd.DataFrame:
    """Fetch historical data for one ticker via yfinance."""
    try:
        raw = yf.download(
            yTicker, 
            period=period, 
            auto_adjust=True, 
            progress=False, 
            timeout=30
        )
        
        if raw.empty:
            return None 
        
        # Flatten multi-level columns if present 
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.droplevel(1)
            
        df = pd.DataFrame({
            "datetime" : raw.index,
            "open"     : raw["Open"].values,
            "high"     : raw["High"].values,
            "low"      : raw["Low"].values,
            "close"    : raw["Close"].values,
            "volume"   : raw["Volume"].values if "Volume" in raw.columns else 0
        })
        
        df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)
        df = df.dropna(subset=["close"])
        df = df.sort_values("datetime").reset_index(drop=True)
        
        return engineer_features(df, ticker)
    
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None
    

def fetch_all() -> dict:
    """Fetch all India symbols. Returns dict of ticker → DataFrame"""
    results = {}
    for ticker in ALL_SYMBOLS:
        print(f" Fetching {ticker} ({ALL_SYMBOLS[ticker]['name']})...")
        df = fetch_ticker(ticker)
        if df is not None:
            results[ticker] = df 
            print(f" ✓ {ticker}: {len(df)} rows")
        else:
            print(f"  ✗ {ticker}: failed")
            
    return results


# Summary Buider 
def get_latest_row(df: pd.DataFrame) -> dict:
    """Extract latest row as clean dict."""
    row = df.iloc[-1]
    
    def safe(val):
        try: 
            if pd.isna(val):
                return None 
            return float(val)
        except Exception:
            return None 
    return {
        "datetime"      : str(row["datetime"])[:10],
        "open"          : safe(row["open"]),
        "high"          : safe(row["high"]),
        "low"           : safe(row["low"]),
        "close"         : safe(row["close"]),
        "volume"        : safe(row["volume"]),
        "rsi_14"        : safe(row["rsi_14"]),
        "macd"          : safe(row["macd"]),
        "macd_signal"   : safe(row["macd_signal"]),
        "macd_hist"     : safe(row["macd_hist"]),
        "sma_50"        : safe(row["sma_50"]),
        "sma_200"       : safe(row["sma_200"]),
        "bb_upper"      : safe(row["bb_upper"]),
        "bb_mid"        : safe(row["bb_mid"]),
        "bb_lower"      : safe(row["bb_lower"]),
        "volume_ratio"  : safe(row["volume_ratio"]),
        "return_1d"     : safe(row["return_1d"]),
        "return_7d"     : safe(row["return_7d"]),
        "volatility_30d": safe(row["volatility_30d"]),
        "above_sma50"   : int(row["above_sma50"]) if row["above_sma50"] is not None else 0,
        "above_sma200"  : int(row["above_sma200"]) if row["above_sma200"] is not None else 0,
        "golden_cross"  : int(row["golden_cross"]) if row["golden_cross"] is not None else 0,
        "death_cross"   : int(row["death_cross"])  if row["death_cross"]  is not None else 0,
    }


def get_chart_data(df: pd.DataFrame, days: int = 90) -> list:
    """Get OHLCV data for charting."""
    df = df.tail(days)
    return [
        {
            "date"  : str(row["datetime"])[:10],
            "open"  : round(float(row["open"]),  4),
            "high"  : round(float(row["high"]),  4),
            "low"   : round(float(row["low"]),   4),
            "close" : round(float(row["close"]), 4),
            "volume": round(float(row["volume"]),2)
        }
        for _, row in df.iterrows()
    ]


def get_indicator_data(df: pd.DataFrame, days: int = 90) -> list:
    """Get indicator data for RSI/MACD charts."""
    df = df.tail(days)

    result = []
    for _, row in df.iterrows():
        def s(col):
            try:
                v = row[col]
                return round(float(v), 4) if not pd.isna(v) else None
            except Exception:
                return None

        result.append({
            "date"        : str(row["datetime"])[:10],
            "close"       : s("close"),
            "rsi"         : s("rsi_14"),
            "macd"        : s("macd"),
            "macd_signal" : s("macd_signal"),
            "macd_hist"   : s("macd_hist"),
            "bb_upper"    : s("bb_upper"),
            "bb_mid"      : s("bb_mid"),
            "bb_lower"    : s("bb_lower"),
            "sma_50"      : s("sma_50"),
            "sma_200"     : s("sma_200"),
            "volume_ratio": s("volume_ratio")
        })
    return result


# ── Cache ─────────────────────────────────────────────────────────────────────

_cache = {}
_cache_time = None
CACHE_MINUTES = 30


def get_data(force_refresh: bool = False) -> dict:
    """
    Return cached data or fetch fresh.
    Cache expires every 30 minutes.
    """
    global _cache, _cache_time

    now = datetime.now()

    if (
        force_refresh or
        not _cache or
        _cache_time is None or
        (now - _cache_time).seconds > CACHE_MINUTES * 60
    ):
        print("Fetching fresh India data...")
        _cache      = fetch_all()
        _cache_time = now

    return _cache


# ── Test ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n--- Fetching India Market Data ---\n")
    data = fetch_all()

    print(f"\n--- Results ---")
    for ticker, df in data.items():
        name = ALL_SYMBOLS[ticker]["name"]
        row  = get_latest_row(df)
        print(f"{name:15} ({ticker:15}) "
              f"Price: {row['close']:>12,.2f}  "
              f"RSI: {row['rsi_14']:>6.2f}  "
              f"1d: {(row['return_1d'] or 0)*100:>+6.2f}%")

