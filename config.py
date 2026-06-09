SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
INTERVAL = "1d" 
START_DATE = "2019-09-08"    # Binance Futures launch date 
END_DATE = "2026-06-05"      # Today

BASE_URL = "https://data.binance.vision/data/futures/um/daily/klines"

DIRS = {
    "raw"           :  "data/raw", 
    "extracted"     :  "data/extracted", 
    "validated"     :  "data/validated", 
    "master"        :  "data/master", 
    "logs"          :  "logs"
}

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", 
    "close_time", "quote_volume", "trades", 
    "taker_buy_base", "taker_buy_quote", "ignore"
]