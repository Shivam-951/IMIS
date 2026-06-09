# IMIS — Update Guide

## Daily Update (Recommended)
Run once per day after 08:00 UTC (Binance publishes previous day's data):

    python main.py --steps update

Or directly:

    python scripts/updater.py

## What the updater does
1. Checks last date in each symbol's parquet
2. Downloads any missing days from Binance
3. Extracts, validates new files
4. Rebuilds all parquet files
5. Re-engineers features
6. Re-normalizes

## Full Rebuild From Scratch
If you need to rebuild everything:

    python main.py

## Adding New Symbols
1. Add symbol to SYMBOLS list in config.py
2. Run full pipeline: python main.py

## Changing Date Range
Update START_DATE or END_DATE in config.py
Then run: python main.py

## Changing Interval
Update INTERVAL in config.py (e.g. "1h", "4h", "1d")
Then run full pipeline: python main.py