import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import duckdb 
import pandas as pd 
from config import DIRS

def get_path(filename: str) -> str:
    path = os.path.join(DIRS["master"], filename)
    return path.replace("\\", "/")

def connect():
    return duckdb.connect()

# ══════════════════════════════════════════════════════
#  SECTION 1 — Basic Queries
# ══════════════════════════════════════════════════════


def summary():
    """Row counts, date ranges, latest prices for all symbols."""
    con = connect()
    return con.execute(f"""
        SELECT
            symbol,
            COUNT(*)        AS total_days,
            MIN(datetime)   AS from_date,
            MAX(datetime)   AS to_date,
            ROUND(MIN(close), 2) AS min_price,
            ROUND(MAX(close), 2) AS max_price,
            ROUND(LAST(close ORDER BY datetime), 2) AS latest_price
        FROM read_parquet('{get_path("master_all.parquet")}')
        GROUP BY symbol
        ORDER BY symbol           
    """).df()
    
def get_symbol(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """Get OHLCV data for one symbol with optional data filter."""
    con = connect()
    where = f"WHERE symbol = '{symbol}'"
    if start:
        where += f" AND datetime >= '{start}'"
    if end:
        where += f" AND datetime <= '{end}'"
        
    return con.execute(f"""
        SELECT datetime, open, high, low, close, volume, trades 
        FROM read_parquet('{get_path("master_all.parquet")}')
        {where}
        ORDER BY datetime
    """).df()
    
def latest_prices() -> pd.DataFrame:
    """Latest closing price for all symbols."""
    con = connect()
    return con.execute(f"""
        SELECT symbol, datetime, close AS latest_close
        FROM read_parquet('{get_path("master_all.parquet")}')
        WHERE datetime = (
            SELECT MAX(datetime)
            FROM read_parquet('{get_path("master_all.parquet")}')
        )
        ORDER BY symbol
    """).df()
    
def all_time_highs() -> pd.DataFrame:
    """All time high price and date for each symbol."""
    con =connect()
    return con.execute(f"""
        SELECT symbol,
               ROUND(MAX(high), 4) AS all_time_high,
               FIRST(datetime ORDER BY high DESC) AS ath_date
        FROM read_parquet('{get_path("master_all.parquet")}')
        GROUP BY symbol
        ORDER BY symbol
    """).df()


# ══════════════════════════════════════════════════════
#  SECTION 2 — Feature Queries
# ══════════════════════════════════════════════════════

def get_features(symbol: str, start: str = None, end: str = None) -> pd.DataFrame:
    """Get full feature set for one symbol."""
    con = connect()
    where = f"WHERE symbol = '{symbol}'"
    if start:
        where += f" AND datetime >= '{start}'"
    if end:
        where += f" AND datetime <= '{end}'"
        
    return con.execute(f"""
        SELECT * 
        FROM read_parquet('{get_path("master_features.parquet")}')
        {where}
        ORDER BY datetime
    """).df()
    
def oversold_signals(rsi_threshold: float = 30.0) -> pd.DataFrame:
    """Find all dates where RSI dropped below threshold."""
    con = connect()
    return con.execute(f"""
        SELECT symbol, datetime, close, rsi_14, macd, volume_ratio 
        FROM read_parquet('{get_path("master_features.parquet")}')
        WHERE rsi_14 < {rsi_threshold}
        ORDER BY symbol, datetime
    """).df()
    
def overbought_signals(rsi_threshold: float = 70.0) -> pd.DataFrame:
    """Find all dates where RSI exceeded threshold."""
    con = connect()
    return con.execute(f"""
        SELECT symbol, datetime, close, rsi_14, macd, volume_ratio 
        FROM read_parquet('{get_path("master_features.parquet")}')
        WHERE rsi_14 > {rsi_threshold}
        ORDER BY symbol, datetime
    """).df()
    
def golden_crosses() -> pd.DataFrame:
    """All golden cross events - SMA50 crossing above SMA200."""
    con = connect()
    return con.execute(f"""
        SELECT symbol, datetime, close, sma_50, sma_200
        FROM read_parquet('{get_path("master_features.parquet")}')
        WHERE golden_cross = 1
        ORDER BY symbol, datetime
    """).df()
    
def death_crosses() -> pd.DataFrame:
    """All death cross events - SMA50 crossing below SMA200."""
    con = connect()
    return con.execute(f"""
        SELECT symbol, datetime, close, sma_50, sma_200
        FROM read_parquet('{get_path("master_features.parquet")}')
        WHERE death_cross = 1
        ORDER BY symbol, datetime
    """).df()
    
def high_volume_days(ratio_threshold: float = 3.0) -> pd.DataFrame:
    """Days where volume was unusually high vs 20-day average."""
    con = connect()
    return con.execute(f"""
        SELECT symbol, datetime, close, volume, 
               ROUND(volume_ratio, 2) AS volume_ratio, 
               ROUND(return_1d * 100, 2) AS return_pct
        FROM read_parquet('{get_path("master_features.parquet")}')
        WHERE volume_ratio > {ratio_threshold}
        ORDER BY volume_ratio DESC
    """).df()
    
def high_volatility_regime(symbol: str) -> pd.DataFrame:
    """Monthly average volatility for a symbol."""
    con = connect()
    return con.execute(f"""
        SELECT 
            symbol, 
                STRFTIME(datetime,'%Y-%m') AS month, 
                ROUND(AVG(volatility_30d) * 100, 4) AS avg_volatility_pct, 
                ROUND(AVG(close), 2)                AS avg_prices
            FROM read_parquet('{get_path("master_features.parquet")}')
            WHERE symbol = '{symbol}'
            GROUP BY symbol, month
            ORDER BY month
    """).df()
    
# ══════════════════════════════════════════════════════
#  SECTION 3 — Correlation & Comparison
# ══════════════════════════════════════════════════════

def price_correlation() -> pd.DataFrame:
    """Daily return correlation matrix across all symbols."""
    con = connect()
    df = con.execute(f"""
        SELECT symbol, datetime, return_1d
        FROM read_parquet('{get_path("master_features.parquet")}')
        WHERE return_1d IS NOT NULL
        ORDER BY datetime
    """).df()
    
    pivot = df.pivot(index="datetime", columns="symbol", values="return_1d")
    return pivot.corr().round(4)

def yearly_return() -> pd.DataFrame:
    """Yearly return per symbol."""
    con = connect()
    return con.execute(f"""
        WITH yearly AS(
            SELECT 
                symbol, 
                YEAR(CAST(datetime AS TIMESTAMP)) AS year, 
                FIRST(close ORDER BY datetime) AS open_price,
                LAST(close ORDER BY datetime) AS close_price
            FROM read_parquet('{get_path("master_features.parquet")}')
            GROUP BY symbol, year
        )
        SELECT 
            symbol, 
                year, 
                ROUND(open_price, 2) AS open_price, 
                ROUND(close_price, 2) AS close_price, 
                Round(((close_price - open_price) / open_price) * 100, 2) AS return_pct
            FROM yearly
            ORDER BY symbol, year
    """).df()
    
def drawdown(symbol: str) -> pd.DataFrame:
    """Maximum drawdown from rolling peak for a symbol."""
    con = connect()
    return con.execute(f"""
        SELECT
            symbol,
            datetime,
            close,
            ROUND(MAX(close) OVER (
                PARTITION BY symbol
                ORDER BY datetime
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ), 2) AS rolling_peak,
            ROUND((close - MAX(close) OVER (
                PARTITION BY symbol
                ORDER BY datetime
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )) / MAX(close) OVER (
                PARTITION BY symbol
                ORDER BY datetime
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ) * 100, 2) AS drawdown_pct
        FROM read_parquet('{get_path("master_features.parquet")}')
        WHERE symbol = '{symbol}'
        ORDER BY datetime
    """).df()


# ══════════════════════════════════════════════════════
#  SECTION 4 — ML Dataset Queries
# ══════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════
#  SECTION 4 — ML Dataset Queries
# ══════════════════════════════════════════════════════

def get_training_data(symbol: str) -> pd.DataFrame:
    """
    Get normalized ML-ready dataset for one symbol.
    Drops NaN rows from early indicator warmup period.
    """
    con = connect()
    df  = con.execute(f"""
        SELECT *
        FROM read_parquet('{get_path("master_normalized.parquet")}')
        WHERE symbol = '{symbol}'
        ORDER BY datetime
    """).df()

    before = len(df)
    df.dropna(inplace=True)
    after  = len(df)

    print(f"{symbol} training rows: {after:,} "
          f"(dropped {before - after} NaN warmup rows)")
    return df


def get_all_training_data() -> pd.DataFrame:
    """Get normalized ML-ready dataset for all symbols combined."""
    con = connect()
    df  = con.execute(f"""
        SELECT *
        FROM read_parquet('{get_path("master_normalized.parquet")}')
        ORDER BY symbol, datetime
    """).df()

    before = len(df)
    df.dropna(inplace=True)
    after  = len(df)

    print(f"All symbols training rows: {after:,} "
          f"(dropped {before - after} NaN warmup rows)")
    return df


# ══════════════════════════════════════════════════════
#  Run Sample Queries
# ══════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n[1] Database Summary")
    print(summary().to_string(index=False))

    print("\n[2] Latest Prices")
    print(latest_prices().to_string(index=False))

    print("\n[3] All Time Highs")
    print(all_time_highs().to_string(index=False))

    print("\n[4] Golden Crosses (all symbols)")
    print(golden_crosses().to_string(index=False))

    print("\n[5] Oversold Signals — RSI < 30")
    print(oversold_signals(30).tail(10).to_string(index=False))

    print("\n[6] High Volume Days (ratio > 3x)")
    print(high_volume_days(3.0).head(10).to_string(index=False))

    print("\n[7] Yearly Return — BTC")
    print(yearly_return()[yearly_return()["symbol"] == "BTCUSDT"].to_string(index=False))

    print("\n[8] Price Correlation Matrix")
    print(price_correlation().to_string())

    print("\n[9] BTC Drawdown — last 10 rows")
    print(drawdown("BTCUSDT").tail(10).to_string(index=False))

    print("\n[10] ML Training Data — BTC")
    df = get_training_data("BTCUSDT")
    print(f"Shape: {df.shape}")
    print(df[["datetime", "close", "rsi_14", "macd", "return_1d"]].tail(5).to_string(index=False))