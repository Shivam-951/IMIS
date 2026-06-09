import sys 
import os 
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import time 
import csv 
from datetime import datetime, timedelta
from tqdm import tqdm 
from config import SYMBOLS, INTERVAL, START_DATE, END_DATE, BASE_URL, DIRS

def get_all_dates(start: str, end: str):
    """Generate every date between start and end."""
    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    dates = []
    current = start_dt 
    while current <= end_dt:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def download_file(symbol: str, interval: str, date_str: str, retries: int = 2):
    """
    Download one.zip file from Binance Data Vision. 
    Returns: 'downloaded', 'exists', 'failed', 'not_found'
    """
    filename = f"{symbol}-{interval}-{date_str}.zip"
    url = f"{BASE_URL}/{symbol}/{interval}/{filename}"
    
    save_dir = os.path.join(DIRS["raw"], symbol)
    save_path = os.path.join(save_dir, filename)
    
    os.makedirs(save_dir, exist_ok=True)
    
    # Skip if already downloaded
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return "exists"
    
    for attempt in range(1, retries+1):
        try:
            response = requests.get(url, timeout=5)
    
            if response.status_code == 200:
                with open(save_path, "wb") as f: 
                    f.write(response.content)
                return "downloaded"
            
            elif response.status_code == 404:
                return "not_found"     # File doesn't exist on Binance
            
            else: 
                time.sleep(1)  # Wait longer on each retry 
        
        except requests.exceptions.RequestException as e:
            print(f"\nERROR [{symbol}][{date_str}]: {e}")
            time.sleep(1)
    return "failed"
                
def log_result(log_path: str, symbol: str, date_str: str, status: str):
    """Append one row to download_log.csv"""
    file_exists = os.path.exists(log_path)
    with open(log_path, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["symbol", "date", "status", "timestamp"])
        writer.writerow([symbol, date_str, status, datetime.now().isoformat()])

from concurrent.futures import ThreadPoolExecutor, as_completed

def run_bulk_download():
    os.makedirs(DIRS["logs"], exist_ok=True)
    log_path = os.path.join(DIRS["logs"], "download_log.csv")
    
    dates = get_all_dates(START_DATE, END_DATE)
    tasks = [(s, d) for s in SYMBOLS for d in dates]
    total = len(tasks)
    stats = {"downloaded": 0, "exists": 0, "not_found": 0, "failed": 0}
    
    print(f"\n Starting bulk download")
    print(f"Symbols: {SYMBOLS}")
    print(f"Dates : {START_DATE} → {END_DATE} ({len(dates)} days)")
    print(f"Total :{total} files\n")
    
    with tqdm(total=total, unit="file") as pbar:
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(download_file, s, INTERVAL, d): (s, d)
                for s, d, in tasks 
            }
            for future in as_completed(futures):
                symbol, date_str = futures[future]
                try:
                    status = future.result()
                except Exception as e:
                    print(f"\nTHREAD ERROR: {e}")
                    status = "failed"
                stats[status] += 1
                log_result(log_path, symbol, date_str, status)
                pbar.set_postfix(stats)
                pbar.update(1)
                
    print(f"\n--- Download Complete ---")
    print(f"Downloaded : {stats['downloaded']}")
    print(f"Skipped    : {stats['exists']}")
    print(f"Not found  : {stats['not_found']}  (expected for early dates)")
    print(f"Failed     : {stats['failed']}")
    print(f"Log saved  : {log_path}")

# Test it 
if __name__ == "__main__":
    run_bulk_download()