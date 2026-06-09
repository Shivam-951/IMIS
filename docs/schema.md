# IMIS — Database Schema

## master_all.parquet
Raw OHLCV data merged across all symbols.

| Column          | Type     | Description                        |
|-----------------|----------|------------------------------------|
| open_time       | int64    | Candle open timestamp (ms)         |
| open            | float64  | Opening price                      |
| high            | float64  | Highest price                      |
| low             | float64  | Lowest price                       |
| close           | float64  | Closing price                      |
| volume          | float64  | Base asset volume                  |
| close_time      | int64    | Candle close timestamp (ms)        |
| quote_volume    | float64  | Quote asset volume (USDT)          |
| trades          | int64    | Number of trades                   |
| taker_buy_base  | float64  | Taker buy base volume              |
| taker_buy_quote | float64  | Taker buy quote volume             |
| datetime        | datetime | Human-readable open timestamp      |
| symbol          | string   | Trading pair (e.g. BTCUSDT)        |

## master_features.parquet
All columns above plus 35 engineered features.

### Returns
| Column      | Description                        |
|-------------|------------------------------------|
| return_1d   | 1-day percentage return            |
| return_7d   | 7-day percentage return            |
| return_30d  | 30-day percentage return           |
| log_return  | Natural log return                 |

### Volatility
| Column         | Description                     |
|----------------|---------------------------------|
| volatility_7d  | 7-day rolling log return std    |
| volatility_14d | 14-day rolling log return std   |
| volatility_30d | 30-day rolling log return std   |

### Moving Averages
| Column  | Description                          |
|---------|--------------------------------------|
| sma_7   | 7-day simple moving average          |
| sma_21  | 21-day simple moving average         |
| sma_50  | 50-day simple moving average         |
| sma_200 | 200-day simple moving average        |
| ema_12  | 12-day exponential moving average    |
| ema_26  | 26-day exponential moving average    |

### Momentum
| Column      | Description                        |
|-------------|------------------------------------|
| rsi_14      | RSI 14-period                      |
| rsi_7       | RSI 7-period                       |
| macd        | MACD line (12/26)                  |
| macd_signal | MACD signal line (9)               |
| macd_hist   | MACD histogram                     |

### Bollinger Bands
| Column      | Description                        |
|-------------|------------------------------------|
| bb_upper    | Upper band (SMA20 + 2σ)            |
| bb_mid      | Middle band (SMA20)                |
| bb_lower    | Lower band (SMA20 - 2σ)            |
| bb_width    | Band width normalized              |
| bb_position | Price position within bands [0-1]  |

### Other
| Column        | Description                      |
|---------------|----------------------------------|
| atr_14        | Average True Range 14-period     |
| volume_sma_20 | 20-day volume moving average     |
| volume_ratio  | Volume vs 20-day average         |
| buy_pressure  | Taker buy ratio                  |
| price_range   | High minus low                   |
| price_position| Close position within day range  |
| gap           | Open vs previous close           |
| above_sma50   | 1 if close > SMA50 else 0        |
| above_sma200  | 1 if close > SMA200 else 0       |
| golden_cross  | 1 on SMA50 crossing above SMA200 |
| death_cross   | 1 on SMA50 crossing below SMA200 |

## master_normalized.parquet
Same as master_features.parquet with scaled values.
- Price/volume columns: MinMax scaled [0, 1]
- Returns/ratios/oscillators: Z-Score scaled [μ=0, σ=1]
- Binary and timestamp columns: unchanged

## scaler_params.json
Stores min/max and mean/std per symbol per column.
Use for inverse transforming model predictions back to real prices.