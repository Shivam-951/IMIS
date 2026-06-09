# IMIS — Pipeline Architecture

## Data Flow

    Binance Data Vision (public)
            ↓
    downloader.py  →  data/raw/{SYMBOL}/*.zip
            ↓
    extractor.py   →  data/extracted/{SYMBOL}/*.csv
            ↓
    validator.py   →  data/validated/{SYMBOL}/*.csv
            ↓
    builder.py     →  data/master/{SYMBOL}.parquet
                   →  data/master/master_all.parquet
            ↓
    features.py    →  data/master/master_features.parquet
            ↓
    normalizer.py  →  data/master/master_normalized.parquet
                   →  data/master/scaler_params.json

## Script Responsibilities

| Script         | Input                    | Output                        |
|----------------|--------------------------|-------------------------------|
| downloader.py  | Binance URLs             | data/raw/*.zip                |
| extractor.py   | data/raw/*.zip           | data/extracted/*.csv          |
| validator.py   | data/extracted/*.csv     | data/validated/*.csv          |
| builder.py     | data/validated/*.csv     | data/master/*.parquet         |
| features.py    | master_all.parquet       | master_features.parquet       |
| normalizer.py  | master_features.parquet  | master_normalized.parquet     |
| updater.py     | All of the above         | Keeps database current        |
| main.py        | config.py                | Runs full pipeline            |

## Logs

| Log file               | Tracks                              |
|------------------------|-------------------------------------|
| download_log.csv       | Every file: downloaded/skipped/404  |
| extraction_log.csv     | Every zip: extracted/skipped/corrupt|
| validation_report.csv  | Every csv: clean/fixed/failed       |