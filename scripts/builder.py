import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd 
import duckdb 
from datetime import datetime
from tqdm import tqdm 
from config import SYMBOLS, DIRS

def get_validated_files(symbol: str):
    """Return all validated CSVs for a symbol sorted by date."""
    val_dir = os.path.join(DIRS["validated"], symbol)
    if not os.path.exists(val_dir):
        return []
    files = sorted([f for f in os.listdir(val_dir) if f.endswith(".csv")])
    return [os.path.join(val_dir, f) for f in files]

def build_symbol_parquet(symbol: str):
    """
    Merge all validated CSVs for one symbol into Parquet file. 
    Returns: (status, row_count) 
    """
    files = get_validated_files(symbol)
    if not files:
        return "no_files", 0 
    
    os.makedirs(DIRS["master"], exist_ok=True)
    out_path = os.path.join(DIRS["master"], f"{symbol}.parquet")
    
    # Skip if already built 
    if os.path.exists(out_path):
        df = pd.read_parquet(out_path)
        return "exists", len(df)
    
    dfs = []
    for f in tqdm(files, desc=f" {symbol}", unit="file", leave=False):
        try:
            df = pd.read_csv(f)
            dfs.append(df)
        except Exception:
            continue
    
    if not dfs:
        return "failed", 0 
    
    # Merge all days 
    merged = pd.concat(dfs, ignore_index=True)
    
    # Clean types 
    merged["open_time"] = pd.to_numeric(merged["open_time"], errors="coerce")
    merged["close_time"] = pd.to_numeric(merged["close_time"], errors="coerce")
    merged["daytime"] = pd.to_datetime(merged["open_time"], unit="ms")
    
    for col in ["open", "high", "low", "close", "volume", 
                "quote_volume", "trades", "taker_buy_base", "taker_buy_quote"]:
        merged[col] = pd.to_numeric(merged[col], errors="coerce")
        
    # Sort by time 
    merged.sort_values("datetime", inplace=True)
    merged.reset_index(drop=True, inplace=True)
    
    # Drop ignore column 
    if "ignore" in merged.columns:
        merged.drop(columns=["ignore"], inplace=True)
        
    # Save as Parquet
    merged.to_parquet(out_path, index=False, compression="snappy")
    
    return "built", len(merged)

def build_master_parquet():
    """Merge all symbol Parquets into one master file."""
    master_path = os.path.join(DIRS["master"], "master_all.parquet")
    
    dfs = []
    for symbol in SYMBOLS:
        path = os.path.join(DIRS["master"], f"{symbol}.parquet")
        if os.path.exists(path):
            df = pd.read_parquet(path)
            dfs.append(df)
            print(f"{symbol:10} : {len(df):,} rows loaded")
            
    if not dfs:
        print("No symbol parquets found.")
        return 
    
    master = pd.concat(dfs, ignore_index=True)
    master.sort_values(["symbol", "datetime"], inplace=True)
    master.reset_index(drop=True, inplace=True)
    
    master.to_parquet(master_path, index= False, compression="snappy")
    print(f"\n master_all.parquet : {len(master):,} total rows")
    
    return master_path

def run_sample_queries(master_path: str):
    """Run sample DuckDB queries to verify the database."""
    print(f"\n--- Sample Queries ---")
    con = duckdb.connect()
    
    # Query 1 - Row counts per symbol 
    print("\n[1] Row counts per symbol: ")
    result = con.execute(f"""
        SELECT symbol, COUNT(*) as days, 
        MIN(datetime) as from_date, 
        MAX(datetime) as to_date
        FROM read_parquet('{master_path}')
        GROUP BY symbol 
        ORDER BY symbol
    """).df()
    print(result.to_string(index=False))
    
    # Query 2 - Latest prices 
    print("\n[2] Latest closing prices: ")
    result = con.execute(f"""
        SELECT symbol, datetime, close
        FROM read_parquet('{master_path}')
        WHERE datetime = (
            SELECT MAX(datetime) FROM read_parquet('{master_path}')
        )
    """).df()
    print(result.to_string(index=False))
    
    # Query 3 - All time high per symbol 
    print("\n[3] All time highs: ")
    result = con.execute(f"""
        SELECT symbol, MAX(high) as all_time_high
        FROM read_parquet('{master_path}')
        GROUP BY symbol 
        ORDER BY symbol
    """).df()
    print(result.to_string(index=False))
    con.close()
    
def run_build():
    os.makedirs(DIRS["master"], exist_ok=True)
    stats = {"built": 0, "exists": 0, "failed": 0, "no_files": 0}
    
    print(f"\nBuilding master database")
    print(f"Symbols : {SYMBOLS}\n")
    
    for symbol in SYMBOLS:
        print(f"Processing {symbol}...")
        status, rows = build_symbol_parquet(symbol)
        stats[status] += 1 
        print(f"{symbol:10} : {status} ({rows:,} rows)")
        
    print(f"\n--Marging all symbols--")
    master_path = build_master_parquet()
    
    print(f"\n-- Build Complete --")
    
    print(f"\n--- Build Complete ---")
    print(f"Built   : {stats['built']}")
    print(f"Skipped : {stats['exists']}")
    print(f"Failed  : {stats['failed']}")
    
    # Fix path for DuckDb (forward slashes)
    master_path_fixed = master_path.replace("\\", "/")
    run_sample_queries(master_path_fixed)
    
    print(f"\nDatabase saved to : {master_path}")
    
if __name__ == "__main__":
    run_build()