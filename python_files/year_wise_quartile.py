import time
import re
import requests
import pandas as pd
import mysql.connector
from collections import defaultdict
import logging

# ——— SETUP LOGGING ———
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("faculty_quartile_perpaper.log", encoding='utf-8'),
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
    2022: 'scimagojr2022.csv',
    2023: 'scimagojr2023.csv',
    2024: 'scimagojr2024.csv'
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

# ——— 1. Load SJR Files into ISSN→Quartile Maps ———
yearly_issn_quart = defaultdict(dict)

for year, filename in SJR_FILES.items():
    try:
        df = pd.read_csv(filename, delimiter=';', encoding='utf-8-sig')
        for raw_issns, q in zip(df['Issn'], df['SJR Best Quartile']):
            if pd.isna(raw_issns) or pd.isna(q): continue
            for part in re.split(r'[^0-9A-Za-z]+', str(raw_issns)):
                issn = clean_issn(part)
                if issn:
                    yearly_issn_quart[year][issn] = q
        logging.info(f"✅ Loaded {len(yearly_issn_quart[year])} ISSN→Quartile entries for {year}")
    except Exception as e:
        logging.error(f"❌ Failed to load {filename}: {e}")

# ——— 2. Connect to MySQL ———
try:
    cnx = mysql.connector.connect(**DB_CONFIG)
    logging.info("Connected to MySQL.")
except mysql.connector.Error as err:
    logging.critical(f"MySQL connection failed: {err}")
    exit(1)

cursor = cnx.cursor()

# ——— 3. Drop & Recreate Table ———
cursor.execute("DROP TABLE IF EXISTS faculty_quartile_summary")
cursor.execute("""
CREATE TABLE faculty_quartile_summary (
  scopus_id VARCHAR(50),
  doi VARCHAR(255),
  quartile_2024 VARCHAR(2),
  quartile_2023 VARCHAR(2),
  quartile_2022 VARCHAR(2),
  PRIMARY KEY (doi)
);
""")
cnx.commit()

# ——— 4. Fetch DOIs ———
cursor.execute("SELECT scopus_id, doi FROM papers WHERE doi IS NOT NULL;")
papers = cursor.fetchall()
logging.info(f"Fetched {len(papers)} papers with DOIs.")

# ——— 5. Process and Insert One by One ———
insert_sql = """
INSERT INTO faculty_quartile_summary (scopus_id, doi, quartile_2024, quartile_2023, quartile_2022)
VALUES (%s, %s, %s, %s, %s)
"""

for idx, (scopus_id, doi) in enumerate(papers, 1):
    if not doi:
        continue

    issn = fetch_first_issn(doi)
    if not issn:
        logging.warning(f"[{idx}] No ISSN found for DOI {doi}")
        continue

    quartiles = {}
    for year in [2024, 2023, 2022]:
        quart = yearly_issn_quart[year].get(issn)
        quartiles[year] = quart if quart else None

    try:
        cursor.execute(insert_sql, (
            scopus_id,
            doi,
            quartiles[2024],
            quartiles[2023],
            quartiles[2022]
        ))
        cnx.commit()
        logging.info(f"[{idx}] Inserted {doi} → 2024:{quartiles[2024]} 2023:{quartiles[2023]} 2022:{quartiles[2022]}")
    except mysql.connector.errors.IntegrityError as e:
        if e.errno == 1062:
            logging.warning(f"[{idx}] Skipped duplicate DOI: {doi}")
        else:
            logging.error(f"[{idx}] Failed to insert {doi}: {e}")

    if idx % 50 == 0:
        time.sleep(1)  # CrossRef throttle

# ——— 6. Cleanup ———
cursor.close()
cnx.close()
logging.info("Closed MySQL connection.")
