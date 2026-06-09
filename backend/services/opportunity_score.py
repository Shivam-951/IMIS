import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import duckdb
import pandas as pd
import numpy as np


BASE_DIR    = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MASTER_PATH = os.path.join(BASE_DIR, "data", "master", "master_features.parquet")


def get_path():
    return MASTER_PATH.replace("\\", "/")


def compute_rsi_score(rsi: float) -> float:
    """
    RSI Score — 30 points max
    Oversold (RSI < 30)  → high score
    Overbought (RSI > 70) → low score
    """
    if rsi is None or np.isnan(rsi):
        return 15.0

    if rsi <= 20:
        return 30.0
    elif rsi <= 30:
        return 25.0 + (30 - rsi) * 0.5
    elif rsi <= 45:
        return 20.0
    elif rsi <= 55:
        return 15.0
    elif rsi <= 70:
        return 10.0
    elif rsi <= 80:
        return 5.0
    else:
        return 0.0


def compute_macd_score(macd: float, macd_signal: float, macd_hist: float) -> float:
    """
    MACD Score — 20 points max
    Histogram turning positive = bullish momentum
    """
    if any(v is None or np.isnan(v) for v in [macd, macd_signal, macd_hist]):
        return 10.0

    score = 10.0

    # Histogram positive = momentum building
    if macd_hist > 0:
        score += 5.0

    # MACD crossing above signal = bullish
    if macd > macd_signal:
        score += 3.0

    # MACD above zero = uptrend
    if macd > 0:
        score += 2.0

    return min(score, 20.0)


def compute_trend_score(
    close: float, sma_50: float, sma_200: float,
    above_sma50: int, above_sma200: int,
    golden_cross: int, death_cross: int
) -> float:
    """
    Trend Score — 20 points max
    Strong uptrend = high score
    """
    score = 0.0

    if above_sma50:
        score += 6.0
    if above_sma200:
        score += 8.0
    if golden_cross:
        score += 6.0
    if death_cross:
        score -= 6.0

    # Price momentum vs SMA50
    if sma_50 and sma_50 > 0:
        pct_vs_sma50 = (close - sma_50) / sma_50
        if pct_vs_sma50 > 0.05:
            score += 2.0
        elif pct_vs_sma50 < -0.10:
            score -= 2.0

    return max(0.0, min(score, 20.0))


def compute_volume_score(volume_ratio: float, buy_pressure: float) -> float:
    """
    Volume Score — 15 points max
    High volume confirms signals
    """
    if volume_ratio is None or np.isnan(volume_ratio):
        return 7.5

    score = 0.0

    if volume_ratio >= 3.0:
        score += 10.0
    elif volume_ratio >= 2.0:
        score += 7.0
    elif volume_ratio >= 1.5:
        score += 5.0
    elif volume_ratio >= 1.0:
        score += 3.0
    else:
        score += 1.0

    # Buy pressure bonus
    if buy_pressure and not np.isnan(buy_pressure):
        if buy_pressure > 0.55:
            score += 5.0
        elif buy_pressure > 0.45:
            score += 2.5

    return min(score, 15.0)


def compute_volatility_score(volatility_30d: float) -> float:
    """
    Volatility Score — 15 points max
    Lower volatility = safer entry = higher score
    """
    if volatility_30d is None or np.isnan(volatility_30d):
        return 7.5

    vol_pct = volatility_30d * 100

    if vol_pct < 1.0:
        return 15.0
    elif vol_pct < 2.0:
        return 12.0
    elif vol_pct < 3.0:
        return 9.0
    elif vol_pct < 5.0:
        return 6.0
    elif vol_pct < 8.0:
        return 3.0
    else:
        return 1.0


def score_to_label(score: float) -> dict:
    """Convert numeric score to label, color, and action."""
    if score >= 80:
        return {"label": "Strong Buy Zone",  "color": "#00d97e", "action": "BUY"}
    elif score >= 65:
        return {"label": "Buy Zone",          "color": "#4d9fff", "action": "BUY"}
    elif score >= 50:
        return {"label": "Neutral",           "color": "#ffaa00", "action": "WATCH"}
    elif score >= 35:
        return {"label": "Caution",           "color": "#ff8c42", "action": "WAIT"}
    else:
        return {"label": "Avoid",             "color": "#ff4d6a", "action": "AVOID"}


def compute_score(row: pd.Series) -> dict:
    """Compute full opportunity score for one row."""

    rsi_score  = compute_rsi_score(row.get("rsi_14"))
    macd_score = compute_macd_score(
        row.get("macd"), row.get("macd_signal"), row.get("macd_hist")
    )
    trend_score = compute_trend_score(
        row.get("close"), row.get("sma_50"), row.get("sma_200"),
        row.get("above_sma50"), row.get("above_sma200"),
        row.get("golden_cross"), row.get("death_cross")
    )
    volume_score = compute_volume_score(
        row.get("volume_ratio"), row.get("buy_pressure")
    )
    volatility_score = compute_volatility_score(row.get("volatility_30d"))

    total = rsi_score + macd_score + trend_score + volume_score + volatility_score
    total = round(min(100.0, max(0.0, total)), 1)

    label_data = score_to_label(total)

    return {
        "total"      : total,
        "label"      : label_data["label"],
        "color"      : label_data["color"],
        "action"     : label_data["action"],
        "breakdown"  : {
            "rsi"        : round(rsi_score, 1),
            "macd"       : round(macd_score, 1),
            "trend"      : round(trend_score, 1),
            "volume"     : round(volume_score, 1),
            "volatility" : round(volatility_score, 1)
        }
    }


def get_all_scores() -> list:
    """Get opportunity scores for all symbols — latest data only."""
    con  = duckdb.connect()
    path = get_path()

    df = con.execute(f"""
        SELECT symbol, datetime, close, rsi_14, macd, macd_signal,
               macd_hist, sma_50, sma_200, above_sma50, above_sma200,
               golden_cross, death_cross, volume_ratio, buy_pressure,
               volatility_30d, return_1d, return_7d, atr_14
        FROM read_parquet('{path}')
        WHERE CAST(datetime AS TIMESTAMP) = (
            SELECT MAX(CAST(datetime AS TIMESTAMP))
            FROM read_parquet('{path}')
        )
        ORDER BY symbol
    """).df()

    results = []
    for _, row in df.iterrows():
        score = compute_score(row)
        results.append({
            "symbol"      : row["symbol"],
            "date"        : str(row["datetime"])[:10],
            "price"       : round(float(row["close"]), 4),
            "score"       : score["total"],
            "label"       : score["label"],
            "color"       : score["color"],
            "action"      : score["action"],
            "breakdown"   : score["breakdown"],
            "rsi"         : round(float(row["rsi_14"]), 2),
            "return_1d"   : round(float(row["return_1d"]) * 100, 2),
            "return_7d"   : round(float(row["return_7d"]) * 100, 2),
        })

    return sorted(results, key=lambda x: x["score"], reverse=True)


def get_score(symbol: str) -> dict:
    """Get opportunity score for one symbol."""
    all_scores = get_all_scores()
    for s in all_scores:
        if s["symbol"] == symbol:
            return s
    return None


if __name__ == "__main__":
    print("\n--- IMIS Opportunity Scores ---\n")
    scores = get_all_scores()
    for s in scores:
        bar = "█" * int(s["score"] / 5)
        print(f"{s['symbol']:10} {s['score']:5.1f}/100  {bar}")
        print(f"           {s['label']} | {s['action']}")
        print(f"           RSI:{s['breakdown']['rsi']}  MACD:{s['breakdown']['macd']}  "
              f"Trend:{s['breakdown']['trend']}  Vol:{s['breakdown']['volume']}  "
              f"Volatility:{s['breakdown']['volatility']}")
        print()