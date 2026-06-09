import sys 
import os 
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
import pandas as pd 
from datetime import datetime 


def print_header():
    print(f"""
╔══════════════════════════════════════════════════════╗
║           IMIS — Master Database Pipeline            ║
║     Binance USDT Futures Historical Data Builder     ║
╚══════════════════════════════════════════════════════╝
  Symbols  : BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT
  Interval : 1d
  Range    : 2019-09-08 → today
  Started  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """)
    
def print_step(n: int, title: str):
    print(f"\n{'-'*54}")    
    print(f" Step {n} - {title}")
    print(f"{'-'*54}")    

def print_summary(start_time: datetime):
    elapsed = datetime.now() - start_time
    minutes = int(elapsed.total_seconds() // 60)
    seconds = int(elapsed.total_seconds() % 60)
    
    print(f"""
╔══════════════════════════════════════════════════════╗
║                  Pipeline Complete                   ║
╠══════════════════════════════════════════════════════╣
║  Output Files:                                       ║
║  • data/master/master_all.parquet                    ║
║  • data/master/master_features.parquet               ║
║  • data/master/master_normalized.parquet             ║
║  • data/master/scaler_params.json                    ║
║                                                      ║
║  Logs:                                               ║
║  • logs/download_log.csv                             ║
║  • logs/extraction_log.csv                           ║
║  • logs/validation_report.csv                        ║
║                                                      ║
║  To update database tomorrow:                        ║
║  python scripts/updater.py                           ║
╚══════════════════════════════════════════════════════╝
  Total time : {minutes}m {seconds}s
""")
    
def run_pipeline(steps="all"):
    """ 
    Run the full pipeline or specific steps. 
    
    steps = "all"           → runs everything
    steps = "download"      → only download
    steps = "build"         → extract + validate + build
    steps = "features"      → features + normalize only
    steps = "update"        → run updater only
    """
    start_time = datetime.now()
    print_header()
    
    # Step 1: Download 
    if steps in ("all", "download"):
        print_step(1, "Downloading from Binance Data Vision")
        from scripts.downloader import run_bulk_download
        run_bulk_download()
        
    # Step 2: Extract 
    if steps in ("all", "build"):
        print_step(2, "Extracting ZIP files")
        from scripts.extractor import run_extraction
        run_extraction()
        
    # Step 3: Validate 
    if steps in ("all", "build"):
        print_step(3, "Validating data quality")
        from scripts.validator import run_validation
        run_validation()
        
    # Step 4: Build 
    if steps in ("all", "build"):
        print_step(4, "Building master Parquet database")
        from scripts.builder import run_build
        run_build()
    
    # Step 5: Features 
    if steps in ("all", "features"):
        print_step(5, "Engineering features")
        from scripts.features import run_features
        run_features()
        
    # Step 6: Normalize 
    if steps in ("all", "features"):
        print_step(6, "Normalizing for ML")
        from scripts.normalizer import run_normalization
        run_normalization()
        
    print_summary(start_time)
    
def run_updater():
    """Run updater only - use this daily."""
    from scripts.updater import run_updater
    run_updater()
    

# CLI

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="IMIS - Binance Futures Master Database Pipeline"
    )
    parser.add_argument(
        "--steps", 
        type=str, 
        default="all", 
        choices=["all", "download", "build", "features", "update"], 
        help=(
            "all      = full pipeline (default)\n"
            "download = download only\n"
            "build    = extract + validate + build parquet\n"
            "features = feature engineering + normalize\n"
            "update   = run daily updater"
        )
    )
    
    args = parser.parse_args()
    
    if args.steps == "update":
        run_updater()
    else:
        run_pipeline(steps=args.steps)