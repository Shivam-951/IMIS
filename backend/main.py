import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import pandas as pd
import numpy as np
import duckdb
import yfinance as yf
from datetime import datetime, timedelta
import threading
import time

app = FastAPI(title="IMIS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
MASTER_PATH  = os.path.join(BASE_DIR, "data", "master", "master_features.parquet")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

YFINANCE_MAP = {
    "BTCUSDT": "BTC-USD",
    "ETHUSDT": "ETH-USD",
    "SOLUSDT": "SOL-USD",
    "BNBUSDT": "BNB-USD",
    "XRPUSDT": "XRP-USD"
}

# ── In-memory data store ──────────────────────────────────────────────────────

_store = {
    "master"      : None,
    "last_updated": None,
    "source"      : None   # "parquet" or "live"
}
_store_lock = threading.Lock()


# ── Feature Engineering ───────────────────────────────────────────────────────

def compute_rsi(series, period=14):
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).round(4)


def compute_macd(series, fast=12, slow=26, signal=9):
    ema_fast    = series.ewm(span=fast,   adjust=False).mean()
    ema_slow    = series.ewm(span=slow,   adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line.round(4), signal_line.round(4), (macd_line - signal_line).round(4)


def engineer_features(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    df    = df.copy().sort_values("datetime").reset_index(drop=True)
    close = df["close"]
    vol   = df["volume"]

    df["symbol"]       = symbol
    df["return_1d"]    = close.pct_change(1).round(6)
    df["return_7d"]    = close.pct_change(7).round(6)
    df["return_30d"]   = close.pct_change(30).round(6)
    df["log_return"]   = np.log(close / close.shift(1)).round(6)

    df["volatility_7d"]  = df["log_return"].rolling(7).std().round(6)
    df["volatility_14d"] = df["log_return"].rolling(14).std().round(6)
    df["volatility_30d"] = df["log_return"].rolling(30).std().round(6)

    df["sma_7"]   = close.rolling(7).mean().round(4)
    df["sma_21"]  = close.rolling(21).mean().round(4)
    df["sma_50"]  = close.rolling(50).mean().round(4)
    df["sma_200"] = close.rolling(200).mean().round(4)
    df["ema_12"]  = close.ewm(span=12, adjust=False).mean().round(4)
    df["ema_26"]  = close.ewm(span=26, adjust=False).mean().round(4)

    df["rsi_14"] = compute_rsi(close, 14)
    df["rsi_7"]  = compute_rsi(close, 7)

    df["macd"], df["macd_signal"], df["macd_hist"] = compute_macd(close)

    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    df["bb_upper"]    = (sma20 + std20 * 2).round(4)
    df["bb_mid"]      = sma20.round(4)
    df["bb_lower"]    = (sma20 - std20 * 2).round(4)
    df["bb_width"]    = ((df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]).round(6)
    df["bb_position"] = ((close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])).round(6)

    high  = df["high"]
    low   = df["low"]
    tr    = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs()
    ], axis=1).max(axis=1)
    df["atr_14"] = tr.ewm(com=13, min_periods=14).mean().round(4)

    df["volume_sma_20"] = vol.rolling(20).mean().round(2)
    df["volume_ratio"]  = (vol / df["volume_sma_20"].replace(0, np.nan)).round(4)
    df["buy_pressure"]  = 0.5

    df["price_range"]    = (high - low).round(4)
    df["price_position"] = ((close - low) / df["price_range"].replace(0, np.nan)).round(4)
    df["gap"]            = (df["open"] - close.shift(1)).round(4)

    df["above_sma50"]  = (close > df["sma_50"]).astype(int)
    df["above_sma200"] = (close > df["sma_200"]).astype(int)
    df["golden_cross"] = ((df["sma_50"] > df["sma_200"]) &
                          (df["sma_50"].shift(1) <= df["sma_200"].shift(1))).astype(int)
    df["death_cross"]  = ((df["sma_50"] < df["sma_200"]) &
                          (df["sma_50"].shift(1) >= df["sma_200"].shift(1))).astype(int)

    return df


# ── Data Loading ──────────────────────────────────────────────────────────────

def load_from_parquet() -> pd.DataFrame:
    """Load from local parquet if available."""
    if os.path.exists(MASTER_PATH):
        print("Loading from parquet...")
        return pd.read_parquet(MASTER_PATH)
    return None


def load_from_yfinance() -> pd.DataFrame:
    """Fetch live data from yfinance as fallback."""
    print("Fetching live data from yfinance...")
    dfs = []

    for symbol, yticker in YFINANCE_MAP.items():
        try:
            raw = yf.download(yticker, period="2y", auto_adjust=True, progress=False)
            if raw.empty:
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.droplevel(1)

            df = pd.DataFrame({
                "datetime": pd.to_datetime(raw.index).tz_localize(None),
                "open"    : raw["Open"].values,
                "high"    : raw["High"].values,
                "low"     : raw["Low"].values,
                "close"   : raw["Close"].values,
                "volume"  : raw["Volume"].values,
            })

            df = df.dropna(subset=["close"])
            df = engineer_features(df, symbol)
            dfs.append(df)
            print(f"  ✓ {symbol}: {len(df)} rows")

        except Exception as e:
            print(f"  ✗ {symbol}: {e}")

    if not dfs:
        return None

    master = pd.concat(dfs, ignore_index=True)
    master.sort_values(["symbol", "datetime"], inplace=True)
    master.reset_index(drop=True, inplace=True)
    return master


def get_master() -> pd.DataFrame:
    """Get master dataframe from store. Refresh if stale."""
    with _store_lock:
        now = datetime.now()

        # Refresh every 6 hours
        if (
            _store["master"] is None or
            _store["last_updated"] is None or
            (now - _store["last_updated"]).seconds > 21600
        ):
            # Try parquet first, fall back to yfinance
            df = load_from_parquet()
            if df is not None:
                _store["source"] = "parquet"
            else:
                df = load_from_yfinance()
                _store["source"] = "live"

            _store["master"]       = df
            _store["last_updated"] = now
            print(f"Data loaded: {len(df):,} rows [{_store['source']}]")

        return _store["master"]


def query_df(symbol: str = None, days: int = None) -> pd.DataFrame:
    """Query master dataframe."""
    df = get_master()
    if df is None or df.empty:
        return pd.DataFrame()

    if "datetime" not in df.columns:
        df = df.reset_index()
        if "Date" in df.columns:
            df.rename(columns={"Date": "datetime"}, inplace=True)

    if symbol:
        df = df[df["symbol"] == symbol].copy()

    if days:
        df = df.sort_values("datetime")
        df = df.groupby("symbol").tail(days) if not symbol else df.tail(days)

    return df.sort_values("datetime")


# ── Serve Frontend ────────────────────────────────────────────────────────────

if os.path.exists(os.path.join(FRONTEND_DIR, "css")):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")

if os.path.exists(os.path.join(FRONTEND_DIR, "js")):
    app.mount("/js",  StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")),  name="js")


@app.get("/")
def serve_frontend():
    index = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "IMIS API running", "docs": "/docs"}


# ── API Routes ────────────────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    """Health check + data status."""
    master = _store["master"]
    return {
        "status"      : "running",
        "data_source" : _store["source"],
        "last_updated": str(_store["last_updated"])[:19] if _store["last_updated"] else None,
        "total_rows"  : len(master) if master is not None else 0,
        "symbols"     : SYMBOLS
    }


@app.get("/api/summary")
def summary():
    """Latest price, RSI, signal for all symbols."""
    result = []
    for symbol in SYMBOLS:
        df = query_df(symbol=symbol)
        if df.empty:
            continue

        row = df.iloc[-1]

        def safe(col, decimals=4):
            try:
                v = row[col]
                return round(float(v), decimals) if pd.notna(v) else 0
            except Exception:
                return 0

        rsi = safe("rsi_14", 2)
        if rsi < 30:
            signal, signal_color = "OVERSOLD",   "green"
        elif rsi > 70:
            signal, signal_color = "OVERBOUGHT", "red"
        else:
            signal, signal_color = "NEUTRAL",    "gray"

        result.append({
            "symbol"       : symbol,
            "price"        : safe("close", 4),
            "rsi"          : rsi,
            "macd"         : safe("macd", 4),
            "volume_ratio" : safe("volume_ratio", 2),
            "return_1d"    : round(safe("return_1d", 6) * 100, 2),
            "volatility"   : round(safe("volatility_30d", 6) * 100, 2),
            "above_sma200" : int(safe("above_sma200")),
            "signal"       : signal,
            "signal_color" : signal_color,
            "date"         : str(row["datetime"])[:10]
        })

    return result


@app.get("/api/chart/{symbol}")
def chart(symbol: str, days: int = 90):
    """OHLCV candlestick data."""
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not found")

    df = query_df(symbol=symbol, days=days)
    if df.empty:
        return {"symbol": symbol, "data": []}
    
    # Ensure datetime column exists
    if "datetime" not in df.columns:
        df = df.reset_index()
        df.rename(columns={"index": "datetime", "Date": "datetime"}, inplace=True)

    df = df.sort_values("datetime")

    return {
        "symbol": symbol,
        "data": [
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
    }


@app.get("/api/indicators/{symbol}")
def indicators(symbol: str, days: int = 90):
    """RSI, MACD, Bollinger Bands."""
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not found")

    df = query_df(symbol=symbol, days=days)
    if df.empty:
        return {"symbol": symbol, "data": []}

    if "datetime" not in df.columns:
        df = df.reset_index()
        df.rename(columns={"index": "datetime", "Date": "datetime"}, inplace=True)

    df = df.sort_values("datetime")
    
    def s(row, col, d=4):
        try:
            v = row[col]
            return round(float(v), d) if pd.notna(v) else None
        except Exception:
            return None

    return {
        "symbol": symbol,
        "data": [
            {
                "date"        : str(row["datetime"])[:10],
                "close"       : s(row, "close"),
                "rsi"         : s(row, "rsi_14", 2),
                "macd"        : s(row, "macd"),
                "macd_signal" : s(row, "macd_signal"),
                "macd_hist"   : s(row, "macd_hist"),
                "bb_upper"    : s(row, "bb_upper"),
                "bb_mid"      : s(row, "bb_mid"),
                "bb_lower"    : s(row, "bb_lower"),
                "sma_50"      : s(row, "sma_50"),
                "sma_200"     : s(row, "sma_200"),
                "volume_ratio": s(row, "volume_ratio", 2)
            }
            for _, row in df.iterrows()
        ]
    }


@app.get("/api/signals")
def signals():
    """Active trading signals across all symbols."""
    result = []

    for symbol in SYMBOLS:
        df = query_df(symbol=symbol, days=30)
        if df.empty:
            continue

        for _, row in df.iterrows():
            sig = []
            try:
                rsi      = float(row["rsi_14"])     if pd.notna(row["rsi_14"])     else 50
                macd_h   = float(row["macd_hist"])  if pd.notna(row["macd_hist"])  else 0
                macd_v   = float(row["macd"])       if pd.notna(row["macd"])       else 0
                vol_r    = float(row["volume_ratio"])if pd.notna(row["volume_ratio"])else 1
                gc       = float(row["golden_cross"])if pd.notna(row["golden_cross"])else 0
                dc       = float(row["death_cross"]) if pd.notna(row["death_cross"]) else 0

                if rsi < 30:
                    sig.append({"type": "RSI OVERSOLD",    "strength": "strong", "bias": "bullish"})
                if rsi > 70:
                    sig.append({"type": "RSI OVERBOUGHT",  "strength": "strong", "bias": "bearish"})
                if gc == 1:
                    sig.append({"type": "GOLDEN CROSS",    "strength": "strong", "bias": "bullish"})
                if dc == 1:
                    sig.append({"type": "DEATH CROSS",     "strength": "strong", "bias": "bearish"})
                if vol_r > 3:
                    sig.append({"type": "HIGH VOLUME",     "strength": "medium", "bias": "neutral"})
                if macd_h > 0 and macd_v < 0:
                    sig.append({"type": "MACD TURNING UP", "strength": "medium", "bias": "bullish"})
            except Exception:
                continue

            if sig:
                result.append({
                    "symbol" : symbol,
                    "date"   : str(row["datetime"])[:10],
                    "price"  : round(float(row["close"]), 4),
                    "signals": sig
                })

    return result


@app.get("/api/scores")
def scores():
    """Opportunity scores for all symbols."""
    try:
        from services.opportunity_score import get_all_scores
        return get_all_scores()
    except Exception as e:
        print(f"Scores error: {e}")
        return []


@app.get("/api/scores/{symbol}")
def score_symbol(symbol: str):
    """Opportunity score for one symbol."""
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    try:
        from services.opportunity_score import get_score
        return get_score(symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/intelligence")
def intelligence():
    """Market intelligence for all symbols."""
    try:
        from models.predict import get_all_intelligence
        return get_all_intelligence()
    except Exception as e:
        print(f"Intelligence error: {e}")
        return []


@app.get("/api/intelligence/{symbol}")
def intelligence_symbol(symbol: str):
    """Market intelligence for one symbol."""
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    try:
        from models.predict import get_intelligence
        return get_intelligence(symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/india/summary")
def india_summary():
    try:
        from services.india_data import (
            get_data, get_latest_row, ALL_SYMBOLS
        )
        from services.opportunity_score import compute_score

        data   = get_data()
        result = []

        for ticker, df in data.items():
            try:
                row        = get_latest_row(df)
                info       = ALL_SYMBOLS.get(ticker, {})
                score_row  = pd.Series({
                    "rsi_14"        : row["rsi_14"],
                    "macd"          : row["macd"],
                    "macd_signal"   : row["macd_signal"],
                    "macd_hist"     : row["macd_hist"],
                    "close"         : row["close"],
                    "sma_50"        : row["sma_50"],
                    "sma_200"       : row["sma_200"],
                    "above_sma50"   : row["above_sma50"],
                    "above_sma200"  : row["above_sma200"],
                    "golden_cross"  : row["golden_cross"],
                    "death_cross"   : row["death_cross"],
                    "volume_ratio"  : row["volume_ratio"],
                    "buy_pressure"  : 0.5,
                    "volatility_30d": row["volatility_30d"]
                })
                score = compute_score(score_row)
                rsi   = row["rsi_14"] or 50

                if rsi < 30:   signal, signal_color = "OVERSOLD",   "green"
                elif rsi > 70: signal, signal_color = "OVERBOUGHT", "red"
                else:          signal, signal_color = "NEUTRAL",    "gray"

                result.append({
                    "ticker"      : ticker,
                    "name"        : info.get("name", ticker),
                    "category"    : info.get("category", ""),
                    "price"       : round(float(row["close"]), 2),
                    "rsi"         : round(float(rsi), 2),
                    "return_1d"   : round(float(row["return_1d"] or 0) * 100, 2),
                    "return_7d"   : round(float(row["return_7d"] or 0) * 100, 2),
                    "volatility"  : round(float(row["volatility_30d"] or 0) * 100, 2),
                    "above_sma200": row["above_sma200"],
                    "signal"      : signal,
                    "signal_color": signal_color,
                    "score"       : score["total"],
                    "label"       : score["label"],
                    "color"       : score["color"],
                    "action"      : score["action"],
                    "breakdown"   : score["breakdown"],
                    "date"        : row["datetime"]
                })
            except Exception as e:
                print(f"India ticker error {ticker}: {e}")
                continue

        return sorted(result, key=lambda x: x["score"], reverse=True)

    except Exception as e:
        print(f"India summary error: {e}")
        return []


@app.get("/api/india/chart/{ticker}")
def india_chart(ticker: str, days: int = 90):
    try:
        from services.india_data import get_data, get_chart_data, ALL_SYMBOLS
        ticker = ticker.replace("__","=").replace("_NS",".NS").replace("_CARET_","^")
        data   = get_data()
        if ticker not in data:
            raise HTTPException(status_code=404, detail="Ticker not found")
        return {
            "ticker": ticker,
            "name"  : ALL_SYMBOLS.get(ticker, {}).get("name", ticker),
            "data"  : get_chart_data(data[ticker], days)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/india/indicators/{ticker}")
def india_indicators(ticker: str, days: int = 90):
    try:
        from services.india_data import get_data, get_indicator_data, ALL_SYMBOLS
        ticker = ticker.replace("__","=").replace("_NS",".NS").replace("_CARET_","^")
        data   = get_data()
        if ticker not in data:
            raise HTTPException(status_code=404, detail="Ticker not found")
        return {
            "ticker": ticker,
            "name"  : ALL_SYMBOLS.get(ticker, {}).get("name", ticker),
            "data"  : get_indicator_data(data[ticker], days)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/india/refresh")
def india_refresh():
    try:
        from services.india_data import get_data
        get_data(force_refresh=True)
        return {"status": "refreshed"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/sentiment")
def sentiment_all():
    try:
        from services.sentiment_service import get_all_sentiment, ASSET_KEYWORDS
        cache = get_all_sentiment(list(ASSET_KEYWORDS.keys()))
        return list(cache.values())
    except Exception as e:
        print(f"Sentiment error: {e}")
        return []


@app.get("/api/sentiment/{ticker}")
def sentiment_ticker(ticker: str):
    try:
        from services.sentiment_service import get_sentiment
        return get_sentiment(ticker)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/alerts")
def alerts(limit: int = 50):
    try:
        from services.alert_service import get_alerts
        return get_alerts(limit=limit)
    except Exception as e:
        return []


@app.get("/api/alerts/check")
def check_alerts_now():
    try:
        from services.alert_service import run_alert_check
        sum_data  = summary()
        sent_raw  = sentiment_all()
        sent_map  = {s["ticker"]: s for s in sent_raw}
        new       = run_alert_check(sum_data, sent_map)
        return {"triggered": len(new), "alerts": new}
    except Exception as e:
        return {"triggered": 0, "error": str(e)}


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    """Pre-load data on startup in background thread."""
    def preload():
        print("Pre-loading market data...")
        get_master()
        print("Startup complete.")

    t = threading.Thread(target=preload, daemon=True)
    t.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)