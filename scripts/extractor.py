import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import zipfile 
import csv 
from datetime import datetime
from tqdm import tqdm 
from config import SYMBOLS, INTERVAL, DIRS, COLUMNS

def get_all_zips(symbol: str):
    """Return all .zip files for a symbol sorted by date."""
    raw_dir = os.path.join(DIRS["raw"], symbol)
    if not os.path.exists(raw_dir):
        return []
    files = [f for f in os.listdir(raw_dir) if f.endswith(".zip")]
    return sorted(files)

def extract_file(symbol: str, filename: str):
    """ 
    Extract one .zip file. 
    Returns: 'extracted', 'exists', 'corrupt', 'failed'
    """
    raw_dir = os.path.join(DIRS["raw"], symbol)
    out_dir = os.path.join(DIRS["extracted"], symbol)
    os.makedirs(out_dir, exist_ok=True)
    
    zip_path = os.path.join(raw_dir, filename)
    csv_name = filename.replace(".zip", ".csv")
    csv_path = os.path.join(out_dir, csv_name)
    
    # Skip if already extracted 
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        return "exists"
    
    try: 
        with zipfile.ZipFile(zip_path, "r") as z: 
            names = z.namelist()
            if not names:
                return "corrupt"
            
            # Extract thr first CSV inside the zip 
            z.extract(names[0], out_dir)
            
            # Rename to standard name if different 
            extracted_path = os.path.join(out_dir, names[0])
            if extracted_path != csv_path:
                os.rename(extracted_path, csv_path)
            
        return "extracted"
    
    except zipfile.BadZipFile:
        return "corrupt"
    except Exception:
        return "failed"
    
def normalize_columns(csv_path: str, symbol: str):
    """ 
    Ensure every CSV has standard columns. 
    Binance changed formats across years - this handles it. 
    """
    
    try: 
        with open(csv_path, "r") as f:
            first_line = f.readline().strip()
            
        # If first line is a header (contains letters), remove it 
        if any(c.isalpha() for c in first_line):
            with open(csv_path, "r") as f:
                lines = f.readlines()
            with open(csv_path, "w") as f: 
                f.writelines(lines[1:]) # Remove header row 
            
    except Exception:
        pass 
    
def log_result(log_path: str, symbol: str, filename: str, status: str):
    file_exists = os.path.exists(log_path)
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["symbol", "filename", "status", "timestamp"])
        writer.writerow([symbol, filename, status, datetime.now().isoformat()])
        

def run_extraction():
    os.makedirs(DIRS["logs"], exist_ok=True)
    log_path = os.path.join(DIRS["logs"], "extraction_log.csv")
    
    stats = {"extracted": 0, "exists": 0, "corrupt": 0, "failed": 0}
    
    # Count total files first 
    all_tasks = []
    for symbol in SYMBOLS:
        zips = get_all_zips(symbol)
        for filename in zips:
            all_tasks.append((symbol, filename))
    
    total = len(all_tasks)
    
    print(f"\nStarting extraction")
    print(f"Symbols : {SYMBOLS}")
    print(f"Total   : {total} zip files\n")
    
    with tqdm(total=total, unit="file") as pbar:
        for symbol, filename in all_tasks:
            status = extract_file(symbol, filename)
            
            # Normalize columns after extraction 
            if status == "extracted":
                csv_name = filename.replace(".zip", ".csv")
                csv_path = os.path.join(DIRS["extracted"], symbol, csv_name)
                normalize_columns(csv_path, symbol)
                
            stats[status] += 1 
            log_result(log_path, symbol, filename, status)
            pbar.set_postfix(stats)
            pbar.update(1)
            
    print(f"\n--- Extraction Complete ---")
    print(f"Extracted : {stats['extracted']}")
    print(f"Skipped   : {stats['exists']}")
    print(f"Corrupt   : {stats['corrupt']}")
    print(f"Failed    : {stats['failed']}")
    print(f"Log saved : {log_path}")

if __name__ == "__main__":
    run_extraction()