"""
scopus_full_sync.py

Does TWO things for every non-CTECH faculty member (matched by scopus_id):
  1. Fetches new papers from the Scopus API and inserts them into `papers`
  2. Scrapes live citations / docs_count / h_index from the Scopus website
     and updates the `users` table

Then generates the monthly author report.

Usage:
    pip install elsapy mysql-connector-python selenium webdriver-manager
    python scopus_full_sync.py
"""

import sys
import io
import time
import json
import os
from datetime import datetime

import mysql.connector
from elsapy.elsclient import ElsClient
from elsapy.elsprofile import ElsAuthor
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ── UTF-8 stdout fix ──────────────────────────────────────────────────────────
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ── CONFIG ────────────────────────────────────────────────────────────────────

LOG_FILE      = "progress_log.jsonl"
SCOPUS_URL    = "https://www.scopus.com/authid/detail.uri?authorId={}"
DELAY_SECONDS = 6   # polite delay between Scopus page requests — do not reduce

DB_CONFIG = {
    "host":     "localhost",
    "user":     "root",
    "password": "",        # ← your MySQL password
    "database": "scopuss",
    "port":     3307,
}

# ── LOGGING ───────────────────────────────────────────────────────────────────

def log_progress(status, progress=None, details=None):
    entry = {
        "time":     datetime.now().isoformat(),
        "status":   status,
        "progress": progress,
        "details":  details or {},
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def clear_progress_log():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

# ── HELPERS ───────────────────────────────────────────────────────────────────

def load_config():
    base_dir    = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
    config_path = os.path.join(base_dir, "config.json")
    with open(config_path) as f:
        return json.load(f)


def connect_db():
    return mysql.connector.connect(**DB_CONFIG)


def clean_scopus_id(val):
    if val is None:
        return None
    try:
        return int(float(str(val)))
    except Exception:
        return None


def classify_type(aggregation_type):
    """Map Scopus aggregationType to a human-readable publication type."""
    if not aggregation_type:
        return "Journal"
    t = aggregation_type.strip().lower()
    if "conference" in t:
        return "Conference Proceeding"
    if "journal" in t or "article" in t or "review" in t:
        return "Journal"
    if t == "book" or "book chapter" in t:
        return "Book"
    return "Journal"

# ── DB HELPERS ────────────────────────────────────────────────────────────────

def get_faculty_list(cursor):
    """
    Returns a list of dicts for every non-CTECH faculty member
    who has a valid scopus_id.
    Each dict: { faculty_id, scopus_id, department }
    """
    cursor.execute("""
        SELECT faculty_id, scopus_id, department
        FROM   users
        WHERE  scopus_id  IS NOT NULL
          AND  scopus_id  != 0
          AND  UPPER(REPLACE(REPLACE(REPLACE(TRIM(department), '.', ''), ' ', ''), '-', '')) != 'CTECH'
    """)
    result = []
    for faculty_id, scopus_id, department in cursor.fetchall():
        sid = clean_scopus_id(scopus_id)
        dept_normalized = (department or "").replace(".", "").replace(" ", "").replace("-", "").upper()
        if sid and dept_normalized != "CTECH":
            result.append({
                "faculty_id":  faculty_id,
                "scopus_id":   sid,
                "department":  department,
            })
    return result


def get_existing_papers(cursor):
    cursor.execute("SELECT scopus_id, doi FROM papers")
    return {(sid, doi) for sid, doi in cursor.fetchall() if doi}


def insert_paper(cursor, scopus_id, doi, title, pub_type, pub_name,
                 date, authors, affiliations):
    authors      += [""] * (6 - len(authors))
    affiliations += [""] * (3 - len(affiliations))
    cursor.execute("""
        INSERT IGNORE INTO papers (
            scopus_id, doi, title, type, publication_name, date,
            author1, author2, author3, author4, author5, author6,
            affiliation1, affiliation2, affiliation3
        ) VALUES (%s,%s,%s,%s,%s,%s, %s,%s,%s,%s,%s,%s, %s,%s,%s)
    """, (
        scopus_id, doi, title, pub_type, pub_name, date,
        *authors[:6],
        *affiliations[:3],
    ))


def update_metrics(cursor, conn, scopus_id, citations, docs, hindex):
    cursor.execute("""
        UPDATE users
        SET    citations  = %s,
               docs_count = %s,
               h_index    = %s
        WHERE  scopus_id  = %s
    """, (citations, docs, hindex, scopus_id))
    conn.commit()

# ── MONTHLY REPORT ────────────────────────────────────────────────────────────

def get_previous_month():
    today = datetime.today()
    year, month = today.year, today.month - 1
    if month == 0:
        month, year = 12, year - 1
    return year, month


def get_last_snapshot(cursor, scopus_id, year, month):
    cursor.execute("""
        SELECT total_docs, total_citations
        FROM   monthly_author_report
        WHERE  scopus_id = %s
          AND  (report_year < %s
                OR (report_year = %s AND report_month < %s))
        ORDER  BY report_year DESC, report_month DESC
        LIMIT  1
    """, (scopus_id, year, year, month))
    row = cursor.fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def generate_monthly_author_report(cursor, conn):
    report_year, report_month = get_previous_month()
    log_progress(
        f"Generating monthly author report for {report_month}/{report_year}", 0.90
    )

    cursor.execute("""
        SELECT faculty_id, scopus_id, docs_count, citations
        FROM   users
        WHERE  scopus_id IS NOT NULL
    """)
    authors  = cursor.fetchall()
    total    = len(authors)

    for processed, (faculty_id, scopus_id, docs_count, citations) in enumerate(authors, 1):
        if not scopus_id:
            continue

        current_docs      = int(docs_count  or 0)
        current_citations = int(citations   or 0)

        last_docs, last_citations = get_last_snapshot(
            cursor, scopus_id, report_year, report_month
        )

        docs_added      = max(current_docs      - last_docs,      0)
        citations_added = max(current_citations - last_citations, 0)

        cursor.execute("""
            INSERT INTO monthly_author_report
                (scopus_id, faculty_id, report_year, report_month,
                 docs_added, citations_added, total_docs, total_citations)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                docs_added      = VALUES(docs_added),
                citations_added = VALUES(citations_added),
                total_docs      = VALUES(total_docs),
                total_citations = VALUES(total_citations)
        """, (
            scopus_id, faculty_id,
            report_year, report_month,
            docs_added, citations_added,
            current_docs, current_citations,
        ))
        conn.commit()

        log_progress(
            f"Monthly report ({processed}/{total})",
            0.90 + (processed / total) * 0.10,
        )

    log_progress("Monthly author report completed", 1,
                 {"authors_processed": total})

# ── SELENIUM SETUP ────────────────────────────────────────────────────────────

def setup_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts,
    )


def scrape_metrics(driver, scopus_id):
    driver.get(SCOPUS_URL.format(scopus_id))
    time.sleep(8)  # allow JS to render
    spans = driver.find_elements(
        By.CSS_SELECTOR, "span[data-testid='unclickable-count']"
    )
    if len(spans) < 3:
        raise Exception("Metrics not found (fewer than 3 metric spans on page)")
    citations = int(spans[0].text.replace(",", ""))
    documents = int(spans[1].text.replace(",", ""))
    h_index   = int(spans[2].text.replace(",", ""))
    return citations, documents, h_index

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    clear_progress_log()
    log_progress("Starting full Scopus sync (non-CTECH faculty only)", 0)

    config = load_config()
    client = initialize_elsclient(config)

    conn   = connect_db()
    cursor = conn.cursor()

    # Fetch all non-CTECH faculty with valid scopus_ids
    faculty_list    = get_faculty_list(cursor)
    existing_papers = get_existing_papers(cursor)

    total_faculty   = len(faculty_list)
    log_progress(f"Found {total_faculty} non-CTECH faculty to process", 0)

    # ── Phase 1: Paper fetch via Scopus API ───────────────────────────────────
    log_progress("Phase 1: Fetching new papers via Scopus API", 0.01)

    total_new_papers = 0
    api_failed       = 0

    for idx, faculty in enumerate(faculty_list, start=1):
        faculty_id = faculty["faculty_id"]
        scopus_id  = faculty["scopus_id"]
        dept       = faculty["department"]

        phase_progress = 0.01 + (idx / total_faculty) * 0.44  # Phase 1: 1%–45%
        log_progress(
            f"[API {idx}/{total_faculty}] {faculty_id} | {dept} | Scopus: {scopus_id}",
            phase_progress,
        )

        try:
            author = ElsAuthor(
                uri=f"https://api.elsevier.com/content/author/author_id/{scopus_id}"
            )
            if not author.read_docs(client):
                log_progress(f"  ⚠ No docs returned for {scopus_id}")
                api_failed += 1
                continue

            new_for_author = 0
            for doc in author.doc_list:
                doi = doc.get("prism:doi")
                if not doi or (scopus_id, doi) in existing_papers:
                    continue

                raw_type   = doc.get("subtypeDescription") or doc.get("prism:aggregationType")
                final_type = classify_type(raw_type)

                insert_paper(
                    cursor,
                    scopus_id,
                    doi,
                    doc.get("dc:title", "Unknown"),
                    final_type,
                    doc.get("prism:publicationName", "Unknown"),
                    doc.get("prism:coverDate"),
                    [a.get("authname", "") for a in doc.get("author", [])[:6]],
                    [a.get("affilname", "") for a in doc.get("affiliation", [])[:3]],
                )
                existing_papers.add((scopus_id, doi))
                new_for_author  += 1
                total_new_papers += 1

            conn.commit()
            log_progress(f"  ✔ {new_for_author} new paper(s) added")

        except Exception as e:
            log_progress(f"  ✖ API error for {scopus_id}: {e}")
            api_failed += 1

    log_progress(
        "Phase 1 complete",
        0.45,
        {"total_new_papers": total_new_papers, "api_failures": api_failed},
    )

    # ── Phase 2: Scrape live metrics via Selenium ─────────────────────────────
    log_progress("Phase 2: Scraping live metrics (citations/docs/h-index)", 0.46)

    driver         = setup_driver()
    scrape_success = 0
    scrape_failed  = 0

    for idx, faculty in enumerate(faculty_list, start=1):
        scopus_id = faculty["scopus_id"]
        faculty_id = faculty["faculty_id"]
        dept       = faculty["department"]

        phase_progress = 0.46 + (idx / total_faculty) * 0.44  # Phase 2: 46%–90%
        log_progress(
            f"[Scrape {idx}/{total_faculty}] {faculty_id} | {dept} | Scopus: {scopus_id}",
            phase_progress,
        )

        try:
            citations, docs, hindex = scrape_metrics(driver, scopus_id)
            update_metrics(cursor, conn, scopus_id, citations, docs, hindex)
            log_progress(f"  ✔ C={citations}  D={docs}  H={hindex}")
            scrape_success += 1
        except Exception as e:
            log_progress(f"  ✖ Scrape failed for {scopus_id}: {e}")
            scrape_failed += 1

        time.sleep(DELAY_SECONDS)

    driver.quit()

    log_progress(
        "Phase 2 complete",
        0.90,
        {"scrape_success": scrape_success, "scrape_failed": scrape_failed},
    )

    # ── Phase 3: Monthly author report ───────────────────────────────────────
    generate_monthly_author_report(cursor, conn)

    cursor.close()
    conn.close()

    log_progress(
        "Full sync completed",
        1,
        {
            "faculty_processed":  total_faculty,
            "new_papers_added":   total_new_papers,
            "api_failures":       api_failed,
            "scrape_success":     scrape_success,
            "scrape_failed":      scrape_failed,
        },
    )
    print("\n✅ DONE")


def initialize_elsclient(config):
    return ElsClient(config["apikey"])


if __name__ == "__main__":
    main()