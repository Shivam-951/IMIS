import sys
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd 
import json 
from datetime import datetime, timedelta
from config import SYMBOLS, INTERVAL, DIRS 

from scripts.downloader import download_file, log_result as log_download 
from scripts.extractor  import extract_file, normalize_columns
from scripts.validator import validate_file, log_result as log_Validate 
from scripts.builder import build_symbol_parquet, build_master_parquet
from scripts.features import engineer_features
from scripts.normalizer import normalize_symbol


# Helpers 
def get_last_date(symbol: str) -> datetime:
    """Read the last date available in the master for a symbol."""
    path = os.path.join(DIRS["master"], f"{symbol}.parquet")
    if not os.path.exists(path):
        return None
    
    df = pd.read_parquet(path, columns=["datetime"])
    last = pd.to_datetime(df["datetime"]).max()
    return last 

def get_missing_dates(symbol: str) -> list:
    """Return list of date strings from last_date+1 to yersterday."""
    last = get_last_date(symbol)
    if last is None:
        return []
    
    yesterday = datetime.now() - timedelta(days=1)
    yesterday = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    
    if last.date() >= yesterday.date():
        return []
    
    dates = []
    current = last + timedelta(days=1)
    while current.date() <= yesterday.date():
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
        
    return dates

# Update Pipeline 

def update_symbol(symbol: str):
    """ 
    Run full update pipeline for one symbol.
    Download → Extract → Validate → Rebuild parquet
    """
    missing_dates = get_missing_dates(symbol)
    
    if not missing_dates:
        print(f"{symbol:10} : already up to date")
        return 0 
    
    print(f"{symbol:10} : {len(missing_dates)} new days to download")
    
    os.makedirs(DIRS["logs"], exist_ok=True)
    dl_log = os.path.join(DIRS["logs"], "download_log.csv")
    val_log = os.path.join(DIRS["logs"], "validation_report.csv")
    
    downloaded = 0 
    extracted = 0
    validated = 0
    
    for date_str in missing_dates:
        filename = f"{symbol}-{INTERVAL}-{date_str}.zip"
        
        # Step 1 
        dl_status = download_file(symbol, INTERVAL, date_str)
        log_download(dl_log, symbol, date_str, dl_status)
        
        if dl_status not in ("downloaded", "exists"):
            print(f"{date_str}:{dl_status} - skipping")
            continue
        downloaded += 1
        
        # Step 2 - Extract 
        ext_status = extract_file(symbol, filename)
        if ext_status in ("extracted", "exists"):
            csv_name = filename.replace(".zip", ".csv")
            csv_path = os.path.join(DIRS["extracted"], symbol, csv_name)
            normalize_columns(csv_path, symbol)
            extracted += 1
        else:
            print(f" {date_str} : extract failed - skipping")
            continue
        
        # Step 3 - Validate 
        csv_name = filename.replace(".zip", ".csv")
        val_status, issues = validate_file(symbol, csv_name)
        log_Validate(val_log, symbol, csv_name, val_status, issues)
        
        if val_status in ("clean", "fixed", "exists"):
            validated += 1
        else:
            print(f" {date_str} : validation failed - skipping")
            
    print(f" Downloaded: {downloaded} | "
          f"Extracted: {extracted} | "
          f"validated: {validated}")
    return validated

def rebuild_parquets():
    """Delete and rebuild all parquet files with new data included."""
    print(f"\nRebuilding parquet files...")
    
    # Delete existing symbol parquests so builder rebuilds them 
    for symbol in SYMBOLS:
        path = os.path.join(DIRS["master"], f"{symbol}.parquet")
        if os.path.exists(path):
            os.remove(path)
    
    # Delete master files 
    for fname in ["master_all.parquet", "master_features.parquet", 
                  "master_normalized.parquet"]:
        path = os.path.join(DIRS["master"], fname)
        if os.path.exists(path):
            os.remove(path)
            
    # Rebuild 
    for symbol in SYMBOLS:
        status, rows = build_symbol_parquet(symbol)
        print(f" {symbol:10} {status} ({rows:,} rows)")
        
    master_path = build_master_parquet()
    return master_path

def rebuild_features(master_path: str):
    """Re-engineer features on updated master."""
    print(f"\nRe-engineering features...")
    master = pd.read_parquet(master_path)
    
    all_dfs = []
    for symbol in master["symbol"].unique():
        df = master[master["symbol"] == symbol].copy()
        df = engineer_features(df)
        all_dfs.append(df)
        print(f" {symbol:10} : {len(df):,} rows | {len(df.columns)} columns")
        
    final = pd.concat(all_dfs, ignore_index=True)
    final.sort_values(["symbol", "datetime"], inplace=True)
    final.reset_index(drop=True, inplace=True)
    
    features_path = os.path.join(DIRS["master"], "master_features.parquet")
    final.to_parquet(features_path, index=False, compression="snappy")
    print(f" Features saved: {features_path}")
    return features_path

def rebuild_normalized(features_path: str):
    """Re-normalize updated features."""
    print(f"\nRe-normalizing...")
    df = pd.read_parquet(features_path)
    
    all_dfs = []
    all_params = {}
    
    for symbol in df["symbol"].unique():
        sym_df = df[df["symbol"] == symbol].copy()
        normalized_df, params = normalize_symbol(sym_df, symbol)
        all_dfs.append(normalized_df)
        all_params[symbol] = params
        print(f" {symbol:10} : normalized")
        
    final = pd.concat(all_dfs, ignore_index=True)
    final.sort_values(["symbol", "datetime"], inplace=True)
    final.reset_index(drop=True, inplace=True)
    normalized_path = os.path.join(DIRS["master"], "master_normalized.parquet")
    final.to_parquet(normalized_path, index=False, compression="snappy")
    
    # Save updated scaler program 
    def convert(obj):
        import numpy as np 
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        return obj 
    
    clean_params = {}
    for sym, p in all_params.items():
        clean_params[sym] = {
            "symbol": p["symbol"], 
            "minmax": {
                col: {"min": convert(v["min"]), "max": convert(v["max"])}
                for col, v in p["minmax"].items()
            },
            "zscore": {
                col: {"mean": convert(v["mean"]), "std": convert(v["std"])}
                for col, v in p["zscore"].items()
            }
        }
        
    params_path = os.path.join(DIRS["master"], "scaler_params.json")
    with open(params_path, "w") as f:
        json.dump(clean_params, f, indent=2)
        
    print(f"Normalized saved : {normalized_path}")
    print(f" Scaler params: {params_path}")
    

# Entry Point 
def run_updater():
    print(f"\n{'='*50}")
    print(f" IMIS Database Updater")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*50}")
     
    print(f"\nChecking for new data...")
    total_new = 0 
     
    for symbol in SYMBOLS:
        new_days = update_symbol(symbol)
        total_new += new_days
         
    if total_new == 0: 
        print(f"\nDatabase is already up to date. Nothing to rebuild.")
        return
        
    print(f"\nTotal new days added: {total_new}")
     
    # Rebuild full pipeline 
    master_path = rebuild_parquets()
    features_path = rebuild_features(master_path)
    rebuild_normalized(features_path)
    
    print(f"\n{'='*50}")
    print(f" Update Complete")
    print(f" New days added: {total_new}")
    print(f" Run again tommorow to stay current")
    print(f"{'='*50}\n")
    
if __name__ == "__main__":
    run_updater()