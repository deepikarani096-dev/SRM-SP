import time
import re
import requests
import pandas as pd
import mysql.connector
from mysql.connector import errorcode
import logging

# ——— SETUP LOGGING ———
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("quartile_updater.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# ——— CONFIG ———
DB_CONFIG = {
    'user':     'root',
    'password': '',
    'host':     'localhost',
    'database': 'scopus'
}

SJR_FILES = {
    2024: 'scimagojr2024.csv',
    2023: 'scimagojr2023.csv',
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
                logging.debug(f"DOI {doi} → ISSN {c}")
                return c
    except requests.exceptions.RequestException as e:
        logging.warning(f"[fetch_first_issn] Request failed for DOI {doi}: {e}")
    except Exception as e:
        logging.warning(f"[fetch_first_issn] Unexpected error for DOI {doi}: {e}")
    return None

# ——— 1. Build combined ISSN→Quartile map ———
issn_to_quart = {}
for year in sorted(SJR_FILES.keys()):
    try:
        df = pd.read_csv(SJR_FILES[year], delimiter=';', encoding='utf-8-sig')
        added = 0
        for raw_issns, q in zip(df['Issn'], df['SJR Best Quartile']):
            if pd.isna(raw_issns): continue
            for part in re.split(r'[^0-9A-Za-z]+', str(raw_issns)):
                clean = clean_issn(part)
                if clean:
                    if clean not in issn_to_quart or year == max(SJR_FILES):
                        issn_to_quart[clean] = q
                        added += 1
        logging.info(f"Loaded {added} quartile entries from {SJR_FILES[year]}")
    except Exception as e:
        logging.error(f"Failed to load {SJR_FILES[year]}: {e}")

# ——— Debug check ———
test_issn = "14327643"
if test_issn in issn_to_quart:
    logging.info(f"✅ ISSN {test_issn} is in the quartile map with value: {issn_to_quart[test_issn]}")
else:
    logging.error(f"[DEBUG] ISSN {test_issn} is NOT in the quartile map")

# ——— 2. Connect to MySQL ———
try:
    cnx = mysql.connector.connect(**DB_CONFIG)
    logging.info("Connected to MySQL.")
except mysql.connector.Error as err:
    logging.critical(f"MySQL connection failed: {err}")
    exit(1)

cursor = cnx.cursor()

# ——— 3. Ensure 'quartile' column exists ———
try:
    cursor.execute("ALTER TABLE papers ADD COLUMN quartile VARCHAR(4) NULL;")
    cnx.commit()
    logging.info("Added `quartile` column to papers table.")
except mysql.connector.Error as err:
    if err.errno == errorcode.ER_DUP_FIELDNAME:
        logging.info("`quartile` column already exists, skipping ALTER.")
    else:
        raise

# ——— 4. Fetch DOIs ———
cursor.execute("SELECT doi FROM papers;")
papers = cursor.fetchall()
logging.info(f"Fetched {len(papers)} papers from DB.")

# ——— 5. Loop and update ———
update_sql = "UPDATE papers SET quartile = %s WHERE doi = %s;"
matched = 0
unmatched = 0
missing_doi = 0

for idx, (doi,) in enumerate(papers, start=1):
    if not doi:
        missing_doi += 1
        logging.warning(f"[{idx}] Paper has no DOI, skipping.")
        continue

    issn = fetch_first_issn(doi)
    issn_clean = clean_issn(issn)
    quart = issn_to_quart.get(issn_clean)

    if quart:
        matched += 1
        logging.info(f"[{idx}] Match: DOI {doi} → ISSN {issn_clean} → Quartile {quart}")
        cursor.execute(update_sql, (quart, doi))
    else:
        unmatched += 1
        logging.warning(f"[{idx}] No quartile match for ISSN {issn_clean} (DOI: {doi})")

    if idx % 100 == 0:
        cnx.commit()
        logging.info(f"Committed batch up to paper #{idx}")

cnx.commit()
logging.info("✅ Final commit complete.")
logging.info(f"Total: {len(papers)} | Matched: {matched} | Unmatched ISSN: {unmatched} | Missing DOI: {missing_doi}")

# ——— 6. Cleanup ———
cursor.close()
cnx.close()
logging.info("Closed MySQL connection.")
