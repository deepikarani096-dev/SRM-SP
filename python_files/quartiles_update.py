import time
import re
import sys
import os
import requests
import pandas as pd
import mysql.connector
from collections import defaultdict
import logging
from datetime import datetime

# ——— SETUP LOGGING ———
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("faculty_quartile_upload.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ——— CONFIG ———
DB_CONFIG = {
    'user':     'root',
    'password': '',
    'host':     'localhost',
    'database': 'scopuss'
}

CROSSREF_BASE = "https://api.crossref.org/works/"

# ——— HELPERS ———
def clean_issn(raw):
    if pd.isna(raw): return None
    s = str(raw).replace('-', '').strip().upper()
    return s if len(s) in (7, 8) else None

def fetch_first_issn(doi):
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

def infer_year_from_filename(filename: str):
    match = re.search(r"(20\d{2})", filename)
    if match:
        return int(match.group(1))
    else:
        return datetime.now().year - 1 # fallback

# ——— MAIN FUNCTION ———
def process_uploaded_file(file_path: str):
    if not os.path.exists(file_path):
        logging.error(f"File not found: {file_path}")
        return

    # Determine year from filename
    year = infer_year_from_filename(file_path)
    colname = f"quartile_{year}"
    logging.info(f"Processing upload for year {year} → column {colname}")

    # Load file
    try:
        df = pd.read_csv(file_path, delimiter=';', encoding='utf-8-sig')
    except Exception as e:
        logging.error(f"Failed to read {file_path}: {e}")
        return

    # Build ISSN→Quartile map
    issn_quart = {}
    for raw_issns, q in zip(df['Issn'], df['SJR Best Quartile']):
        if pd.isna(raw_issns) or pd.isna(q): continue
        for part in re.split(r'[^0-9A-Za-z]+', str(raw_issns)):
            issn = clean_issn(part)
            if issn:
                issn_quart[issn] = q
    logging.info(f"✅ Loaded {len(issn_quart)} ISSN→Quartile entries")

    # Connect DB
    try:
        cnx = mysql.connector.connect(**DB_CONFIG)
        cursor = cnx.cursor()
        logging.info("Connected to MySQL.")
    except mysql.connector.Error as err:
        logging.critical(f"MySQL connection failed: {err}")
        return

    # Ensure summary table exists
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faculty_quartile_summary (
        scopus_id VARCHAR(50),
        doi VARCHAR(255) PRIMARY KEY
    );
    """)
    cnx.commit()

    # Ensure new year column exists
    cursor.execute("SHOW COLUMNS FROM faculty_quartile_summary LIKE %s;", (colname,))
    if not cursor.fetchone():
        alter_sql = f"ALTER TABLE faculty_quartile_summary ADD COLUMN {colname} VARCHAR(2);"
        cursor.execute(alter_sql)
        cnx.commit()
        logging.info(f"✅ Added new column: {colname}")

    # Fetch DOIs
    cursor.execute("SELECT scopus_id, doi FROM papers WHERE doi IS NOT NULL;")
    papers = cursor.fetchall()
    logging.info(f"Fetched {len(papers)} papers with DOIs.")

    # Insert or update one by one
    for idx, (scopus_id, doi) in enumerate(papers, 1):
        issn = fetch_first_issn(doi)
        if not issn:
            logging.warning(f"[{idx}] No ISSN found for DOI {doi}")
            continue

        quart = issn_quart.get(issn)
        if not quart:
            logging.warning(f"[{idx}] No quartile mapping found for ISSN {issn}")
            continue

        try:
            # Insert if new row, else update
            sql = f"""
            INSERT INTO faculty_quartile_summary (scopus_id, doi, {colname})
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE {colname} = VALUES({colname});
            """
            cursor.execute(sql, (scopus_id, doi, quart))
            cnx.commit()
            logging.info(f"[{idx}] {doi} → {colname}:{quart}")
        except Exception as e:
            logging.error(f"[{idx}] Failed to insert/update {doi}: {e}")

        if idx % 50 == 0:
            time.sleep(1)

    cursor.close()
    cnx.close()
    logging.info("✅ Finished processing uploaded file")

# ——— ENTRY POINT ———
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python faculty_quartile_from_upload.py <csv_file>")
        sys.exit(1)
    process_uploaded_file(sys.argv[1])
