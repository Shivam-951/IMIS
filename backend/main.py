import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from models.predict import get_all_intelligence, get_intelligence
from services.sentiment_service import get_all_sentiment, get_sentiment, ASSET_KEYWORDS
from services.india_data import (
    get_data, get_latest_row, get_chart_data,
    get_indicator_data, ALL_SYMBOLS, INDIA_SYMBOLS
)
from services.opportunity_score import compute_score
from services.alert_service import get_alerts, run_alert_check
from services.opportunity_score import get_all_scores, get_score
import pandas as pd 
import duckdb 

app = FastAPI(title="IMIS API")

# Allow frontend to talk to backend 
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Paths 
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MASTER_PATH = os.path.join(BASE_DIR, "data", "master", "master_features.parquet")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# Check if master data exists
MASTER_EXISTS = os.path.exists(MASTER_PATH)

if not MASTER_EXISTS:
    print("WARNING: master_features.parquet not found.")
    print("Running in demo mode — API returns empty data.")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

def query(sql: str):
    if not MASTER_EXISTS:
        return pd.DataFrame()
    path = MASTER_PATH.replace("\\", "/")
    sql  = sql.replace("{PATH}", f"'{path}'")
    return duckdb.connect().execute(sql).df()

# Serve Frontend 
app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")

@app.get("/")
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# API Routes 
@app.get("/api/summary")
def summary():
    df = query("""
        SELECT symbol, datetime, close, rsi_14, macd,
        volume_ratio, return_1d, volatility_30d,
        above_sma200
        FROM {PATH}
        WHERE datetime = (SELECT MAX(datetime) FROM {PATH})
        ORDER BY symbol
    """)

    if df.empty:
        return []

    result = []
    for _, row in df.iterrows():
        rsi = row["rsi_14"]
        if rsi < 30:
            signal = "OVERSOLD"
            signal_color = "green"
        elif rsi > 70:
            signal = "OVERBOUGHT"
            signal_color = "red"
        else:
            signal = "NEUTRAL"
            signal_color = "gray"

        result.append({
            "symbol"       : row["symbol"],
            "price"        : round(float(row["close"]), 4),
            "rsi"          : round(float(row["rsi_14"]), 2),
            "macd"         : round(float(row["macd"]), 4),
            "volume_ratio" : round(float(row["volume_ratio"]), 2),
            "return_1d"    : round(float(row["return_1d"]) * 100, 2),
            "volatility"   : round(float(row["volatility_30d"]) * 100, 2),
            "above_sma200" : int(row["above_sma200"]),
            "signal"       : signal,
            "signal_color" : signal_color,
            "date"         : str(row["datetime"])[:10]
        })
    return result


@app.get("/api/chart/{symbol}")
def chart(symbol: str, days: int = 90):
    """OHLCV candlestick data for a symbol."""
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    
    df = query(f"""
        SELECT datetime, open, high, low, close, volume
        FROM {{PATH}}
        WHERE symbol = '{symbol}'
        ORDER BY datetime DESC
        LIMIT {days}
    """)
    
    df = df.sort_values("datetime")
    
    return {
        "symbol": symbol,
        "data": [
            {
                "date"  : str(row["datetime"])[:10],
                "open"  : round(float(row["open"]),   4),
                "high"  : round(float(row["high"]),   4),
                "low"   : round(float(row["low"]),    4),
                "close" : round(float(row["close"]),  4),
                "volume": round(float(row["volume"]), 2)
            }
            for _, row in df.iterrows()
        ]
    }

@app.get("/api/indicators/{symbol}")
def indicators(symbol: str, days: int = 90):
    """RSI, MACD, Bollinger Bands for a symbol."""
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    
    df = query(f"""
        SELECT datetime, close, rsi_14, macd, macd_signal,
               macd_hist, bb_upper, bb_mid, bb_lower,
               sma_50, sma_200, volume, volume_ratio
        FROM {{PATH}}
        WHERE symbol = '{symbol}'
        ORDER BY datetime DESC
        LIMIT {days}
    """)
    
    df = df.sort_values("datetime")
    
    return{
        "symbol": symbol,
        "data": [
            {
                "date"        : str(row["datetime"])[:10],
                "close"       : round(float(row["close"]),       4),
                "rsi"         : round(float(row["rsi_14"]),      2),
                "macd"        : round(float(row["macd"]),        4),
                "macd_signal" : round(float(row["macd_signal"]), 4),
                "macd_hist"   : round(float(row["macd_hist"]),   4),
                "bb_upper"    : round(float(row["bb_upper"]),    4),
                "bb_mid"      : round(float(row["bb_mid"]),      4),
                "bb_lower"    : round(float(row["bb_lower"]),    4),
                "sma_50"      : round(float(row["sma_50"]),      4),
                "sma_200"     : round(float(row["sma_200"]),     4),
                "volume_ratio": round(float(row["volume_ratio"]),2)
            }
            for _, row in df.iterrows()
        ]
    }
    
@app.get("/api/scores")
def scores():
    """Opportunity scores for all symbols."""
    return get_all_scores()


@app.get("/api/scores/{symbol}")
def score_symbol(symbol: str):
    """Opportunity score for one symbol."""
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    result = get_score(symbol)
    if not result:
        raise HTTPException(status_code=404, detail="Score not found")
    return result
    
    
@app.get("/api/signals")
def signals():
    """All active trading signals across symbols."""
    df = query("""
    SELECT symbol, datetime, close, rsi_14, macd,
           macd_hist, volume_ratio, return_1d,
           golden_cross, death_cross, above_sma200
    FROM {PATH}
    WHERE CAST(datetime AS TIMESTAMP) >= (
        SELECT MAX(CAST(datetime AS TIMESTAMP)) - INTERVAL '30' DAY
        FROM {PATH}
    )
    ORDER BY symbol, datetime
""")
    
    result = [] 
    for _, row in df.iterrows():
        sig = []
        rsi = float(row["rsi_14"])
        if rsi < 30:
            sig.append({"type": "RSI OVERSOLD",    "strength": "strong", "bias": "bullish"})
        if rsi > 70:
            sig.append({"type": "RSI OVERBOUGHT",  "strength": "strong", "bias": "bearish"})
        if float(row["golden_cross"]) == 1:
            sig.append({"type": "GOLDEN CROSS",    "strength": "strong", "bias": "bullish"})
        if float(row["death_cross"]) == 1:
            sig.append({"type": "DEATH CROSS",     "strength": "strong", "bias": "bearish"})
        if float(row["volume_ratio"]) > 3:
            sig.append({"type": "HIGH VOLUME",     "strength": "medium", "bias": "neutral"})
        if float(row["macd_hist"]) > 0 and float(row["macd"]) < 0:
            sig.append({"type": "MACD TURNING UP", "strength": "medium", "bias": "bullish"})

        if sig: 
            result.append({
                "symbol"  : row["symbol"],
                "date"    : str(row["datetime"])[:10],
                "price"   : round(float(row["close"]), 4),
                "signals" : sig
            })
            
    return result


# ── India Routes ──────────────────────────────────────────────────────────────

@app.get("/api/india/summary")
def india_summary():
    """Latest price, RSI, score for all India symbols."""
    data = get_data()
    result = []

    for ticker, df in data.items():
        try:
            row   = get_latest_row(df)
            info  = ALL_SYMBOLS.get(ticker, {})

            # Build score-compatible row
            score_row = {
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
            }

            score = compute_score(pd.Series(score_row))

            # RSI signal
            rsi = row["rsi_14"] or 50
            if rsi < 30:
                signal = "OVERSOLD"
                signal_color = "green"
            elif rsi > 70:
                signal = "OVERBOUGHT"
                signal_color = "red"
            else:
                signal = "NEUTRAL"
                signal_color = "gray"

            result.append({
                "ticker"       : ticker,
                "name"         : info.get("name", ticker),
                "category"     : info.get("category", ""),
                "price"        : round(float(row["close"]), 2),
                "rsi"          : round(float(rsi), 2),
                "return_1d"    : round(float(row["return_1d"] or 0) * 100, 2),
                "return_7d"    : round(float(row["return_7d"] or 0) * 100, 2),
                "volatility"   : round(float(row["volatility_30d"] or 0) * 100, 2),
                "above_sma200" : row["above_sma200"],
                "signal"       : signal,
                "signal_color" : signal_color,
                "score"        : score["total"],
                "label"        : score["label"],
                "color"        : score["color"],
                "action"       : score["action"],
                "breakdown"    : score["breakdown"],
                "date"         : row["datetime"]
            })

        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            continue

    return sorted(result, key=lambda x: x["score"], reverse=True)


@app.get("/api/india/chart/{ticker}")
def india_chart(ticker: str, days: int = 90):
    """OHLCV chart data for one India symbol."""
    ticker = ticker.replace("__", "=").replace("_NS", ".NS").replace("_CARET_", "^")
    data   = get_data()

    if ticker not in data:
        raise HTTPException(status_code=404, detail="Ticker not found")

    return {
        "ticker": ticker,
        "name"  : ALL_SYMBOLS.get(ticker, {}).get("name", ticker),
        "data"  : get_chart_data(data[ticker], days)
    }


@app.get("/api/india/indicators/{ticker}")
def india_indicators(ticker: str, days: int = 90):
    """RSI + MACD indicators for one India symbol."""
    ticker = ticker.replace("__", "=").replace("_NS", ".NS").replace("_CARET_", "^")
    data   = get_data()

    if ticker not in data:
        raise HTTPException(status_code=404, detail="Ticker not found")

    return {
        "ticker": ticker,
        "name"  : ALL_SYMBOLS.get(ticker, {}).get("name", ticker),
        "data"  : get_indicator_data(data[ticker], days)
    }


@app.get("/api/india/refresh")
def india_refresh():
    """Force refresh India data cache."""
    get_data(force_refresh=True)
    return {"status": "refreshed"}


@app.get("/api/intelligence")
def intelligence():
    """Market intelligence for all crypto symbols."""
    return get_all_intelligence()


@app.get("/api/intelligence/{symbol}")
def intelligence_symbol(symbol: str):
    """Market intelligence for one symbol."""
    if symbol not in SYMBOLS:
        raise HTTPException(status_code=404, detail="Symbol not found")
    return get_intelligence(symbol)


@app.get("/api/sentiment")
def sentiment_all():
    """Sentiment scores for all assets."""
    tickers = list(ASSET_KEYWORDS.keys())
    cache   = get_all_sentiment(tickers)
    return list(cache.values())


@app.get("/api/sentiment/{ticker}")
def sentiment_ticker(ticker: str):
    """Sentiment for one ticker."""
    return get_sentiment(ticker)


@app.get("/api/alerts")
def alerts(limit: int = 50):
    """Get stored alerts."""
    return get_alerts(limit=limit)


@app.get("/api/alerts/check")
def check_alerts_now():
    """Manually trigger alert check."""
    summary  = summary()
    sent_raw = sentiment_all()
    sent_map = {s["ticker"]: s for s in sent_raw}
    new      = run_alert_check(summary, sent_map)
    return {"triggered": len(new), "alerts": new}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)