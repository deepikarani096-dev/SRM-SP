import sys
import os
import pandas as pd
import mysql.connector
import logging
from datetime import datetime
import re
import time
import requests

# ——— SETUP LOGGING ———
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("department_quartile_upload.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ——— CONFIG ———
DB_CONFIG = {
    'user':     'root',
    'password': '',
    'host':     'localhost',
    'database': 'scopuss',
    'port':3307
}

# CSV file configurations
CSV_FILES = {
    2022: '../scimagojr2022.csv',
    2023: '../scimagojr2023.csv',
    2024: '../scimagojr2024.csv'
}

CROSSREF_BASE = "https://api.crossref.org/works/"

# ——— HELPERS ———
def clean_issn(raw):
    """Extract and clean ISSN values"""
    if pd.isna(raw):
        return None
    s = str(raw).replace('-', '').strip().upper()
    return s if len(s) in (7, 8) else None

def fetch_first_issn(doi):
    """Fetch ISSN from CrossRef API using DOI"""
    try:
        url = CROSSREF_BASE + doi
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        issns = r.json().get('message', {}).get('ISSN', [])
        for i in issns:
            c = clean_issn(i)
            if c:
                return c
    except Exception as e:
        logging.warning(f"[CrossRef] Failed to fetch ISSN for DOI {doi}: {e}")
    return None

def load_csv_issn_quartiles(csv_path: str, year: int):
    """
    Load ISSN to Quartile mapping from ScimagoJR CSV
    Expected columns: Issn (or ISSN), SJR Best Quartile (or Quartile)
    """
    issn_quart = {}
    
    if not os.path.exists(csv_path):
        logging.error(f"CSV file not found: {csv_path}")
        return issn_quart
    
    try:
        df = pd.read_csv(csv_path, delimiter=';', encoding='utf-8')
        logging.info(f"Loaded {csv_path} with {len(df)} rows")
        
        # Identify ISSN column (could be 'Issn', 'ISSN', or similar)
        issn_col = None
        for col in df.columns:
            if 'issn' in col.lower():
                issn_col = col
                break
        
        # Identify Quartile column
        quart_col = None
        for col in df.columns:
            if 'quartile' in col.lower():
                quart_col = col
                break
        
        if not issn_col:
            logging.error(f"No ISSN column found in {csv_path}. Available columns: {df.columns.tolist()}")
            return issn_quart
        
        if not quart_col:
            logging.error(f"No Quartile column found in {csv_path}. Available columns: {df.columns.tolist()}")
            return issn_quart
        
        # Build ISSN→Quartile mapping
        for raw_issns, q in zip(df[issn_col], df[quart_col]):
            if pd.isna(raw_issns) or pd.isna(q):
                continue
            
            # Handle multiple ISSNs separated by commas or spaces
            for part in re.split(r'[^0-9A-Za-z]+', str(raw_issns)):
                issn = clean_issn(part)
                if issn:
                    issn_quart[issn] = str(q).strip()
        
        logging.info(f"✅ Loaded {len(issn_quart)} ISSN→Quartile entries for year {year}")
        
    except Exception as e:
        logging.error(f"Failed to read {csv_path}: {e}")
    
    return issn_quart

def process_all_years():
    """Process all three years of quartile data and update faculty_quartile_summary"""
    
    # Load all CSV files
    all_issn_quart = {}
    for year, csv_path in CSV_FILES.items():
        all_issn_quart[year] = load_csv_issn_quartiles(csv_path, year)
    
    # Check if we successfully loaded at least one year
    if not any(all_issn_quart.values()):
        logging.error("Failed to load any CSV files")
        return
    
    # Connect to database
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cursor = cnx.cursor()
        logging.info("Connected to MySQL.")
    except mysql.connector.Error as err:
        logging.critical(f"MySQL connection failed: {err}")
        return
    
    try:
        # Fetch all papers with DOIs
        cursor.execute("SELECT scopus_id, doi FROM papers WHERE doi IS NOT NULL;")
        papers = cursor.fetchall()
        logging.info(f"Fetched {len(papers)} papers with DOIs.")
        
        if not papers:
            logging.warning("No papers with DOIs found in database.")
            cursor.close()
            cnx.close()
            return
        
        # Process each paper
        for idx, (scopus_id, doi) in enumerate(papers, 1):
            # Fetch ISSN from CrossRef
            issn = fetch_first_issn(doi)
            if not issn:
                logging.warning(f"[{idx}] No ISSN found for DOI {doi}")
                continue
            
            # Build update data for all three years
            update_values = {}
            found_any_quartile = False
            
            for year in CSV_FILES.keys():
                quart = all_issn_quart[year].get(issn)
                if quart:
                    update_values[f"quartile_{year}"] = quart
                    found_any_quartile = True
            
            if not found_any_quartile:
                logging.warning(f"[{idx}] No quartile mapping found for ISSN {issn} (DOI: {doi})")
                continue
            
            # Build and execute update query
            try:
                # Insert or update row
                set_clause = ", ".join([f"{key} = %s" for key in update_values.keys()])
                values_list = [scopus_id, doi] + list(update_values.values())
                
                sql = f"""
                INSERT INTO faculty_quartile_summary (scopus_id, doi, {', '.join(update_values.keys())})
                VALUES ({', '.join(['%s'] * (len(update_values) + 2))})
                ON DUPLICATE KEY UPDATE {set_clause};
                """
                cursor.execute(sql, values_list + list(update_values.values()))
                cnx.commit()
                
                quartile_str = ", ".join([f"{k}:{v}" for k, v in update_values.items()])
                logging.info(f"[{idx}] {doi} → {quartile_str}")
            
            except Exception as e:
                logging.error(f"[{idx}] Failed to insert/update {doi}: {e}")
            
            if idx % 50 == 0:
                time.sleep(1)
        
        logging.info(f"✅ COMPLETED: Processed {len(papers)} papers and updated faculty_quartile_summary")
        
    except Exception as e:
        logging.error(f"Database operation failed: {e}")
        cnx.rollback()
    
    finally:
        cursor.close()
        cnx.close()

# ——— ENTRY POINT ———
if __name__ == "__main__":
    logging.info(f"Starting ScimagoJR quartile department update...")
    process_all_years()
    logging.info(f"Process completed.")
