import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json 
import duckdb 
import pandas as pd 
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MASTER_PATH = os.path.join(BASE_DIR, "data", "master", "master_features.parquet")
ALERTS_FILE = os.path.join(BASE_DIR, "logs", "alerts.json")

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

# Alert Definations 

def check_alerts(summary_data: list, sentiment_data: dict) -> list:
    """ 
    Check all alert conditions against latest data. 
    Returns list of new alerts. 
    """
    alerts = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    for item in summary_data:
        symbol = item["symbol"]
        rsi    = item.get("rsi", 50)
        price  = item.get("price", 0)
        vol    = item.get("volume_ratio", 1)
        ret1d  = item.get("return_1d", 0)
        score  = item.get("score", 50)
        above200 = item.get("above_sma200", 1)
        
        # RSI Oversold 
        if rsi < 25:
            alerts.append({
                "id"       : f"{symbol}_rsi_oversold_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "RSI OVERSOLD",
                "severity" : "high",
                "color"    : "#ff4d6a",
                "message"  : f"RSI at {rsi} — extreme oversold territory",
                "value"    : rsi,
                "timestamp": now
            })
        elif rsi < 30: 
            alerts.append({
                "id"       : f"{symbol}_rsi_warning_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "RSI WARNING",
                "severity" : "medium",
                "color"    : "#ff8c42",
                "message"  : f"RSI at {rsi} — oversold",
                "value"    : rsi,
                "timestamp": now
            })
            
        # RSI Overbought 
        if rsi > 75: 
            alerts.append({
                "id"       : f"{symbol}_rsi_overbought_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "RSI OVERBOUGHT",
                "severity" : "medium",
                "color"    : "#ffaa00",
                "message"  : f"RSI at {rsi} — overbought territory",
                "value"    : rsi,
                "timestamp": now
            })
            
        # High Volume 
        if vol and vol > 3.0:
            alerts.append({
                "id"       : f"{symbol}_high_vol_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "HIGH VOLUME",
                "severity" : "medium",
                "color"    : "#4d9fff",
                "message"  : f"Volume {vol:.1f}x above 20-day average",
                "value"    : vol,
                "timestamp": now
            })
            
        # Large single day drop 
        if ret1d < -8:
            alerts.append({
                "id"       : f"{symbol}_crash_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "PRICE DROP",
                "severity" : "high",
                "color"    : "#ff4d6a",
                "message"  : f"Single day drop of {ret1d:.1f}%",
                "value"    : ret1d,
                "timestamp": now
            })
            
        # Large single day gain 
        if ret1d > 8:
            alerts.append({
                "id"       : f"{symbol}_surge_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "PRICE SURGE",
                "severity" : "medium",
                "color"    : "#00d97e",
                "message"  : f"Single day gain of +{ret1d:.1f}%",
                "value"    : ret1d,
                "timestamp": now
            })
            
        # Score dropped low 
        if score < 35:
            alerts.append({
                "id"       : f"{symbol}_low_score_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "LOW SCORE",
                "severity" : "low",
                "color"    : "#ff8c42",
                "message"  : f"Opportunity score dropped to {score}",
                "value"    : score,
                "timestamp": now
            })
        
        # Below SMA200 
        if above200 == 0: 
            alerts.append({
                "id"       : f"{symbol}_below_sma200_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "BELOW SMA200",
                "severity" : "low",
                "color"    : "#7a7f96",
                "message"  : f"Price below 200-day moving average",
                "value"    : price,
                "timestamp": now
            })
        
        # Sentiment bearish 
        sent = sentiment_data.get(symbol, {})
        if sent.get("label") == "Bearish" and sent.get("article_count", 0) >= 3:
            alerts.append({
                "id"       : f"{symbol}_sentiment_bearish_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "SENTIMENT BEARISH",
                "severity" : "medium",
                "color"    : "#ff4d6a",
                "message"  : f"News sentiment bearish ({sent['article_count']} articles, score {sent['score']:.2f})",
                "value"    : sent.get("score", 0),
                "timestamp": now
            })
            
        # Sentiment bullish 
        if sent.get("label") == "Bullish" and sent.get("article_count", 0) >= 3:
            alerts.append({
                "id"       : f"{symbol}_sentiment_bullish_{now[:10]}",
                "symbol"   : symbol,
                "type"     : "SENTIMENT BULLISH",
                "severity" : "low",
                "color"    : "#00d97e",
                "message"  : f"News sentiment bullish ({sent['article_count']} articles, score +{sent['score']:.2f})",
                "value"    : sent.get("score", 0),
                "timestamp": now
            })
            
    return alerts 

# Storage 

def load_alerts() -> list:
    if not os.path.exists(ALERTS_FILE):
        return []
    try:
        with open(ALERTS_FILE) as f:
            return json.load(f)
    except Exception:
        return []
    
def save_alerts(alerts: list):
    try:
        os.makedirs(os.path.dirname(ALERTS_FILE), exist_ok=True)
        with open(ALERTS_FILE, "w") as f:
            json.dump(alerts, f, indent=2)
    except Exception as e:
        print(f"Could not save alerts: {e}")
        
def merge_alerts(existing: list, new_alerts: list) -> list:
    """ 
    Merge new alerts into existing. 
    Deduplicate by ID so same alert doesn't appear twice per day.
    """
    existing_ids = {a["id"] for a in existing}
    for alert in new_alerts:
        if alert["id"] not in existing_ids:
            existing.append(alert)
            existing_ids.add(alert["id"])
            
    # Keep last 200 alerts only 
    return sorted(existing, key=lambda x: x["timestamp"], reverse=True)[:200]

def get_alerts(limit: int = 50, severity: str = None) -> list:
    """Get stored alerts with optimal severity filter."""
    alerts = load_alerts()
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]
    return alerts[:limit]

def run_alert_check(summary_data: list, sentiment_data: dict) -> list:
    """ 
    Run full alert check and save new alerts.
    Return list of newly triggered alerts. 
    """
    new_alerts = check_alerts(summary_data, sentiment_data)
    existing = load_alerts()
    merged = merge_alerts(existing, new_alerts)
    save_alerts(merged)
    
    print(f"Alert check: {len(new_alerts)} new alerts detected")
    return new_alerts

if __name__ == "__main__":
    # Test with dummy data 
    test_summary = [
        {"symbol": "BTCUSDT", "rsi": 15.6, "price": 61022,
         "volume_ratio": 2.7, "return_1d": -4.43,
         "score": 61.5, "above_sma200": 0},
        {"symbol": "ETHUSDT", "rsi": 13.04, "price": 1582,
         "volume_ratio": 3.03, "return_1d": -10.59,
         "score": 61.5, "above_sma200": 0},
    ]
    test_sentiment = {
         "BTCUSDT": {"label": "Neutral", "score": -0.111, "article_count": 47},
        "ETHUSDT": {"label": "Bullish", "score": 0.212,  "article_count": 6},
    }
    
    new = run_alert_check(test_summary, test_sentiment)
    print(f"\nTriggered {len(new)} alerts:")
    for a in new:
        print(f" [{a['severity'].upper():6}] {a['symbol']:10}"
              f"{a['type']:20} - {a['message']}")