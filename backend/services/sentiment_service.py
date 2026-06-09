import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import feedparser 
import time 
from datetime import datetime, timedelta
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# RSS Feeds 

RSS_FEEDS = [
    # Crypto — these are stable
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
    "https://bitcoinmagazine.com/.rss/full/",

    # Financial news — verified working
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.moneycontrol.com/rss/technicalreports.xml",
    "https://www.livemint.com/rss/markets",

    # Business news
    "https://feeds.feedburner.com/ndtvprofit-latest",
    "https://www.business-standard.com/rss/markets-106.rss",
]

# Keywords to match each asset 
ASSET_KEYWORDS = {
    # Crypto 
    "BTCUSDT"  : ["bitcoin", "btc", "bitcoin price", "crypto"],
    "ETHUSDT"  : ["ethereum", "eth", "ether"],
    "SOLUSDT"  : ["solana", "sol"],
    "BNBUSDT"  : ["binance", "bnb", "binance coin"],
    "XRPUSDT"  : ["xrp", "ripple"],
    
    # India indices
    "^NSEI"    : ["nifty", "nifty50", "nse", "indian market", "india stocks"],
    "^BSESN"   : ["sensex", "bse", "bombay stock"],
    "^NSEBANK" : ["bank nifty", "banknifty", "banking stocks"],

    # India stocks
    "RELIANCE.NS" : ["reliance", "reliance industries", "mukesh ambani"],
    "TCS.NS"      : ["tcs", "tata consultancy"],
    "INFY.NS"     : ["infosys", "infy"],
    "HDFCBANK.NS" : ["hdfc bank", "hdfc"],
    "WIPRO.NS"    : ["wipro"],

    # Commodities
    "GC=F"  : ["gold", "gold price", "bullion", "xau"],
    "SI=F"  : ["silver", "silver price"],

    # Currency
    "INR=X" : ["rupee", "inr", "usd inr", "dollar rupee"],
}

# Fetcher 
def fetch_headlines(max_articles: int = 200) -> list:
    """ 
    Fetch recent headlines from all RSS feeds. 
    Returns list of {title, summary, published, source}
    """
    articles = []
    cutoff = datetime.now() - timedelta(days=3)
    
    for feed_url in RSS_FEEDS:
        try: 
            feed = feedparser.parse(feed_url)
            
            for entry in feed.entries[:50]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                
                # Parse date 
                published = datetime.now()
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass
                
                if published < cutoff:
                    continue
                
                articles.append({
                    "title"    : title,
                    "summary"  : summary[:300],
                    "published": published.strftime("%Y-%m-%d %H:%M"),
                    "source"   : feed.feed.get("title", feed_url)
                })
                
        except Exception as e:
            print(f"RSS error {feed_url}: {e}")
            continue
        
    return articles[:max_articles]


# Sentiment Scorer 

analyzer = SentimentIntensityAnalyzer()

def score_text(text: str) -> float:
    """Return compund VADER score (-1 to + 1).""" 
    return analyzer.polarity_scores(text)["compound"]

def get_asset_sentiment(ticker: str, articles: list) -> dict:
    """ 
    Filter articles mentioning this asset and score sentiment.
    """
    keywords = ASSET_KEYWORDS.get(ticker, [])
    if not keywords:
        return _empty_sentiment(ticker)
    
    matched = []
    scores = []
    
    for article in articles:
        text = (article["title"] + " " + article["summary"]).lower()
        
        if any(kw.lower() in text for kw in keywords):
            score = score_text(article["title"] + " " + article["summary"])
            scores.append(score)
            matched.append({
                "title"     : article["title"],
                "source"    : article["source"],
                "published" : article["published"],
                "score"     : round(score, 3)
            })
            
    if not scores:
        return _empty_sentiment(ticker)
    
    avg_score = sum(scores) / len(scores)
    
    # Label 
    if avg_score >= 0.15:
        label = "Bullish"
        color = "#00d97e"
        emoji = "📈"
        
    elif avg_score <= -0.15:
        label = "Bearish"
        color = "#ff4d6a"
        emoji = "📉"
    else:
        label = "Neutral"
        color = "#ffaa00"
        emoji = "➡️"
        
    return {
        "ticker"       : ticker,
        "score"        : round(avg_score, 3),
        "label"        : label,
        "color"        : color,
        "emoji"        : emoji,
        "article_count": len(matched),
        "articles"     : matched[:5],
        "updated"      : datetime.now().strftime("%Y-%m-%d %H:%M")
    }

def _empty_sentiment(ticker: str)-> dict:
    return{
        "ticker"       : ticker,
        "score"        : 0.0,
        "label"        : "No Data",
        "color"        : "#7a7f96",
        "emoji"        : "—",
        "article_count": 0,
        "articles"     : [],
        "updated"      : datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    
# Cache 

_sentiment_cache = {}
_sentiment_time = None 
CACHE_MINUTES = 30

def get_all_sentiment(tickers: list, force_refresh: bool = False) -> dict:
    """ 
    Get sentiment for all tickers.
    Fetchers RSS once and scores all assets from same batch.
    """
    global _sentiment_cache, _sentiment_time 
    
    now = datetime.now()
    
    if (
        force_refresh or 
        not _sentiment_cache or 
        _sentiment_time is None or 
        (now - _sentiment_time).total_seconds() > CACHE_MINUTES * 60
    ):
        print("Fetching fresh sentiment data...")
        articles = fetch_headlines()
        print(f"Fetched {len(articles)} articles")
        
        _sentiment_cache = {}
        for ticker in tickers:
            _sentiment_cache[ticker] = get_asset_sentiment(ticker, articles)
            
        
        _sentiment_time = now 
        
    return _sentiment_cache


def get_sentiment(ticker: str) -> dict: 
    """Get sentiment for one ticker."""
    all_tickers = list(ASSET_KEYWORDS.keys())
    cache = get_all_sentiment(all_tickers)
    return cache.get(ticker, _empty_sentiment(ticker))


# Test 

if __name__ == "__main__":
    print("\n--- IMIS Sentiment Analysis ---\n")
    
    tickers = list(ASSET_KEYWORDS.keys())
    articles = fetch_headlines()
    print(f"Total articles fetched: {len(articles)}\n")
    
    for ticker in tickers:
        result = get_asset_sentiment(ticker, articles)
        name = ticker.replace("USDT", "").replace(".NS", "").replace("^", "")
        print(f"{name:12} {result['emoji']} {result['label']:8}"
              f"score: {result['score']:+.3f}  "
              f"articles: {result['article_count']}")