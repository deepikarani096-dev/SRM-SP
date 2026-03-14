import sys
import io
import mysql.connector
from elsapy.elsclient import ElsClient
from elsapy.elsprofile import ElsAuthor
import json
import os
from datetime import datetime

# ---------------- UTF-8 fix ----------------
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# ------------------------------------------

LOG_FILE = "progress_log.jsonl"

# ---------- LOGGING ----------

def log_progress(status, progress=None, details=None):
    entry = {
        "time": datetime.now().isoformat(),
        "status": status,
        "progress": progress,
        "details": details or {}
    }
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    print(json.dumps(entry, ensure_ascii=False), flush=True)


def clear_progress_log():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

# ---------- CONFIG ----------

def load_config():
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../"))
    config_path = os.path.join(BASE_DIR, "config.json")
    with open(config_path) as f:
        return json.load(f)


def connect_to_database():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="scopuss",
        port=3307
    )


def initialize_elsclient(config):
    return ElsClient(config["apikey"])

# ---------- HELPERS ----------

def clean_scopus_id(val):
    if val is None:
        return None
    try:
        return int(float(str(val)))
    except:
        return None

# ---------- TYPE CLASSIFIER ----------

def classify_type(aggregation_type):
    if not aggregation_type:
        return "Journal"

    t = aggregation_type.strip().lower()

    # 1️⃣ Conference first (highest priority)
    if "conference" in t:
        return "Conference Proceeding"

    # 2️⃣ Journal / Article / Review
    if "journal" in t or "article" in t or "review" in t:
        return "Journal"

    # 3️⃣ Pure Book types
    if t == "book" or "book chapter" in t:
        return "Book"

    # 4️⃣ Default fallback
    return "Journal"


# ---------- DB QUERIES ----------

def get_existing_papers(cursor):
    cursor.execute("SELECT scopus_id, doi FROM papers")
    return {(sid, doi) for sid, doi in cursor.fetchall() if doi}


def get_faculty_scopus_map(cursor):
    cursor.execute("""
        SELECT faculty_id, scopus_id
        FROM users
        WHERE faculty_id IS NOT NULL
    """)
    faculty_map = {}
    for faculty_id, scopus_id in cursor.fetchall():
        scopus_id = clean_scopus_id(scopus_id)
        if scopus_id:
            faculty_map.setdefault(faculty_id, []).append(scopus_id)
    return faculty_map

# ---------- INSERT PAPER ----------

def insert_paper(cursor, scopus_id, doi, title, pub_type, pub_name, date, authors, affiliations):
    authors += [""] * (6 - len(authors))
    affiliations += [""] * (3 - len(affiliations))

    cursor.execute("""
        INSERT IGNORE INTO papers (
            scopus_id, doi, title, type, publication_name, date,
            author1, author2, author3, author4, author5, author6,
            affiliation1, affiliation2, affiliation3
        )
        VALUES (%s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s)
    """, (
        scopus_id,
        doi,
        title,
        pub_type,
        pub_name,
        date,
        *authors[:6],
        *affiliations[:3]
    ))

# ---------- MONTHLY AUTHOR REPORT ----------

def get_previous_month():
    today = datetime.today()
    year = today.year
    month = today.month - 1
    if month == 0:
        month = 12
        year -= 1
    return year, month


def get_last_snapshot(cursor, scopus_id, year, month):
    cursor.execute("""
        SELECT total_docs, total_citations
        FROM monthly_author_report
        WHERE scopus_id = %s
          AND (report_year < %s
               OR (report_year = %s AND report_month < %s))
        ORDER BY report_year DESC, report_month DESC
        LIMIT 1
    """, (scopus_id, year, year, month))

    row = cursor.fetchone()
    return (int(row[0]), int(row[1])) if row else (0, 0)


def generate_monthly_author_report(cursor, conn):
    report_year, report_month = get_previous_month()

    log_progress(
        f"Generating monthly author report for {report_month}/{report_year}",
        0.90
    )

    cursor.execute("""
        SELECT faculty_id, scopus_id, docs_count, citations
        FROM users
        WHERE scopus_id IS NOT NULL
    """)
    authors = cursor.fetchall()

    total = len(authors)
    processed = 0

    for faculty_id, scopus_id, docs_count, citations in authors:
        if not scopus_id:
            continue

        current_docs = int(docs_count or 0)
        current_citations = int(citations or 0)

        last_docs, last_citations = get_last_snapshot(
            cursor, scopus_id, report_year, report_month
        )

        docs_added = max(current_docs - last_docs, 0)
        citations_added = max(current_citations - last_citations, 0)

        cursor.execute("""
            INSERT INTO monthly_author_report
            (scopus_id, faculty_id, report_year, report_month,
             docs_added, citations_added,
             total_docs, total_citations)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                docs_added = VALUES(docs_added),
                citations_added = VALUES(citations_added),
                total_docs = VALUES(total_docs),
                total_citations = VALUES(total_citations)
        """, (
            scopus_id,
            faculty_id,
            report_year,
            report_month,
            docs_added,
            citations_added,
            current_docs,
            current_citations
        ))

        conn.commit()
        processed += 1

        log_progress(
            f"Monthly report ({processed}/{total})",
            0.90 + (processed / total) * 0.10
        )

    log_progress(
        "Monthly author report completed",
        1,
        {"authors_processed": processed}
    )

# ---------- MAIN SCOPUS SYNC ----------

def fetch_new_papers():
    clear_progress_log()
    log_progress("Starting Scopus fetch", 0)

    config = load_config()
    client = initialize_elsclient(config)

    conn = connect_to_database()
    cursor = conn.cursor()

    faculty_map = get_faculty_scopus_map(cursor)
    existing_papers = get_existing_papers(cursor)

    total_new_papers = 0

    for idx, (faculty_id, scopus_ids) in enumerate(faculty_map.items(), start=1):
        log_progress(f"Faculty {faculty_id}", idx / len(faculty_map))

        for scopus_id in scopus_ids:
            author = ElsAuthor(
                uri=f"https://api.elsevier.com/content/author/author_id/{scopus_id}"
            )

            if not author.read_docs(client):
                continue

            for doc in author.doc_list:
                doi = doc.get("prism:doi")
                if not doi or (scopus_id, doi) in existing_papers:
                    continue

                raw_type = doc.get("subtypeDescription") or doc.get("prism:aggregationType")
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
                    [a.get("affilname", "") for a in doc.get("affiliation", [])[:3]]
                )

                existing_papers.add((scopus_id, doi))
                total_new_papers += 1

        conn.commit()

    log_progress(
        "Scopus fetch completed",
        0.95,
        {"total_new_papers": total_new_papers}
    )

    generate_monthly_author_report(cursor, conn)

    cursor.close()
    conn.close()
    log_progress("DB closed", 1)

# ---------- ENTRY ----------

if __name__ == "__main__":
    fetch_new_papers()
