import requests
import mysql.connector
import time
import logging
import os
import json

# ================= LOAD CONFIG =================

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
config_path = os.path.join(BASE_DIR, "config.json")

with open(config_path) as f:
    config = json.load(f)

API_KEY = config.get("apikey")

if not API_KEY:
    raise Exception("API key is missing in config.json")

# ================= DB CONFIG =================

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "scopuss",
    "port": 3307
}

DELAY_SECONDS = 0.5

# ================= LOGGING =================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)

# ================= DB CONNECTION =================

def connect_db():
    return mysql.connector.connect(**DB_CONFIG)

# ================= GET PAPERS WITH BLANK TYPE =================

def get_blank_type_papers(cursor):
    cursor.execute("""
        SELECT id, doi
        FROM papers
        WHERE (type IS NULL OR TRIM(type) = '')
        AND doi IS NOT NULL
    """)
    return cursor.fetchall()

# ================= CLASSIFY TYPE =================

def classify_type(api_type_string):
    if not api_type_string:
        return None

    t = api_type_string.strip().lower()

    # 1️⃣ Conference first (highest priority)
    if "conference" in t:
        return "Conference Proceeding"

    # 2️⃣ Journal / Article
    if "journal" in t or "article" in t or "review" in t:
        return "Journal"

    # 3️⃣ Pure book types only
    if t == "book" or "book chapter" in t:
        return "Book"

    # 4️⃣ Default fallback
    return "Journal"


# ================= FETCH FROM SCOPUS ABSTRACT API =================

def fetch_type_from_api(doi):
    try:
        headers = {
            "X-ELS-APIKey": API_KEY,
            "Accept": "application/json"
        }

        clean_doi = doi.replace("https://doi.org/", "").strip()
        url = f"https://api.elsevier.com/content/abstract/doi/{clean_doi}"

        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            logging.warning(f"FAILED {doi} | STATUS: {response.status_code}")
            return None

        data = response.json()

        coredata = (
            data.get("abstracts-retrieval-response", {})
                .get("coredata", {})
        )

        # 🔥 USE subtypeDescription FIRST
        subtype = coredata.get("subtypeDescription")

        if subtype:
            return subtype

        # fallback to aggregationType
        return coredata.get("prism:aggregationType")

    except Exception as e:
        logging.error(f"Error for {doi}: {e}")
        return None


# ================= UPDATE DATABASE =================

def update_type(cursor, conn, paper_id, new_type):
    cursor.execute("""
        UPDATE papers
        SET type = %s
        WHERE id = %s
    """, (new_type, paper_id))
    conn.commit()

# ================= MAIN =================

def main():
    conn = connect_db()
    cursor = conn.cursor()

    papers = get_blank_type_papers(cursor)
    logging.info(f"Found {len(papers)} papers with blank type.")

    updated_count = 0

    for paper_id, doi in papers:

        logging.info(f"Checking DOI: {doi}")

        api_type = fetch_type_from_api(doi)

        if not api_type:
            continue

        classified_type = classify_type(api_type)

        if classified_type:
            update_type(cursor, conn, paper_id, classified_type)
            logging.info(f"Updated ID {paper_id} → {classified_type}")
            updated_count += 1

        time.sleep(DELAY_SECONDS)

    logging.info(f"Finished. Total Updated: {updated_count}")

    cursor.close()
    conn.close()

# ================= RUN =================

if __name__ == "__main__":
    main()
