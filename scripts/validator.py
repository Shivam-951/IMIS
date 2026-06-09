import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd 
import csv 
from datetime import datetime, timedelta
from tqdm import tqdm 
from config import SYMBOLS, INTERVAL, DIRS, COLUMNS

EXPECTED_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", 
    "close_time", "quote_volume", "trades", 
    "taker_buy_base", "taker_buy_quote", "ignore"
]

def load_csv(csv_path: str):
    """Load a CSV file into a DataFrame with standard columns."""
    try:
        df = pd.read_csv(csv_path, header=None)
        
        # Assign standard column names
        if len(df.columns) == len(EXPECTED_COLUMNS):
            df.columns = EXPECTED_COLUMNS
        elif len(df.columns) > len(EXPECTED_COLUMNS):
            df = df.iloc[:, :len(EXPECTED_COLUMNS)]
            df.columns = EXPECTED_COLUMNS
        else:
            return None, "wrong_column_count"
        
        return df, "ok"
    
    except Exception as e:
        return None, f"load_error: {e}"
    
def validate_file(symbol: str, filename:str):
    """
    Run all quality checks on one CSV file.
    Returns: (status, issues_list) 
    """
    ext_dir = os.path.join(DIRS["extracted"], symbol)
    val_dir = os.path.join(DIRS["validated"], symbol)
    os.makedirs(val_dir, exist_ok=True)
    
    csv_path = os.path.join(ext_dir, filename)
    out_path = os.path.join(val_dir, filename)
    
    # Skip if already validated 
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        return "exists", []
    
    issues = [] 
    
    # Load file 
    df, load_status = load_csv(csv_path)
    if df is None:
        return "failed", [load_status]
    
    # Check 1: Empty file 
    if len(df) == 0: 
        return "failed", ["empty_file"]
    
    # Check 2: Null values
    null_counts = df.isnull().sum()
    if null_counts.any():
        issues.append(f"nulls:{null_counts[null_counts > 0].to_dict()}")
        df.dropna(inplace=True)
        
    # Check 3: Duplicate rows 
    dupes = df.duplicated(subset=["open_time"]).sum()
    if dupes > 0: 
        issues.append(f"duplicated: {dupes}")
        df.drop_duplicates(subset=["open_time"], inplace=True)
        
    # Check 4: Timestamp validity 
    try: 
        df["open_time"] = pd.to_numeric(df["open_time"])
        df["close_time"] = pd.to_numeric(df["close_time"])
        
        # convert ms timestamp to datetime 
        df["datetime"] = pd.to_datetime(df["open_time"], unit="ms")
        
    except Exception:
        return "failed", ["invalid_timestamps"]

    # Check 5: Price sanity 
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        
    if (df["low"] > df["high"]).any():
        issues.append("zero_or_negative_prices")
        df = df[(df[["open", "high", "low", "close"]] > 0).all(axis=1)]
        
    # Check 6: Volume sanity 
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    if(df["volume"] < 0).any():
        issues.append("negative_volume")
        df = df[df["volume"] >= 0]
        
    # Check 7: Add symbol column 
    df["symbol"] = symbol
    
    # Save validated file 
    df.to_csv(out_path, index=False)
    
    if issues:
        return "fixed", issues
    return "clean", []

def check_missing_days(symbol: str):
    """Check for gaps in the date sequence."""
    val_dir = os.path.join(DIRS["validated"], symbol)
    if not os.path.exists(val_dir):
        return []
    
    files = sorted([f for f in os.listdir(val_dir) if f.endswith(".csv")])
    
    # Extract dates from filenames 
    dates = []
    for f in files:
        try:
            date_str = f.replace(f"{symbol}-{INTERVAL}-", "").replace(".csv", "")
            dates.append(datetime.strptime(date_str, "%Y-%m-%d"))
        except Exception:
            continue
    
    if len(dates) < 2:
        return []
    
    # Find gaps 
    missing = []
    for i in range(1, len(dates)):
        delta = (dates[i] - dates[i-1]).days
        if delta > 1:
            for d in range(1, delta):
                missing_date = dates[i-1] + timedelta(days=d)
                missing.append(missing_date.strftime("%Y-%m-%d"))
                
    return missing

def log_result(log_path, symbol, filename, status, issues):
    file_exists = os.path.exists(log_path)
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["symbol", "filename", "status", "issues", "timestamp"])
        writer.writerow([
            symbol, filename, status, 
            "|".join(issues) if issues else "", 
            datetime.now().isoformat()
        ]) 
def run_validation():
    os.makedirs(DIRS["logs"], exist_ok=True)
    log_path = os.path.join(DIRS["logs"], "validation_report.csv")
    
    stats = {"clean": 0, "fixed": 0, "exists": 0, "failed": 0}
    
    # Collect all tasks
    all_tasks = []
    for symbol in SYMBOLS:
        ext_dir = os.path.join(DIRS["extracted"], symbol)
        if not os.path.exists(ext_dir):
            continue
        files = sorted([f for f in os.listdir(ext_dir) if f.endswith(".csv")])
        for filename in files:
            all_tasks.append((symbol, filename))
            
    total = len(all_tasks)
    
    print(f"\nStarting validation")
    print(f"Symbols: {SYMBOLS}")
    print(f"Total : {total} files\n")
    
    with tqdm(total=total, unit="file") as pbar:
        for symbol, filename in all_tasks:
            status, issues = validate_file(symbol, filename)
            stats[status] += 1
            log_result(log_path, symbol, filename, status, issues)
            pbar.set_postfix(stats)
            pbar.update(1)
            
    # Missing days report
    print(f"\n--- Validation Complete ---")
    print(f"Clean   : {stats['clean']}")
    print(f"Fixed   : {stats['fixed']}  (had issues, auto-corrected)")
    print(f"Skipped : {stats['exists']}")
    print(f"Failed  : {stats['failed']}")
    print(f"Log     : {log_path}")

    print(f"\n--- Missing Days Report ---")
    for symbol in SYMBOLS:
        missing = check_missing_days(symbol)
        print(f"{symbol:10} : {len(missing)} missing days")
        if missing and len(missing) <= 10:
            for d in missing:
                print(f"             {d}")

if __name__ == "__main__":
    run_validation()