import sys
import io
import mysql.connector
from elsapy.elsclient import ElsClient
from elsapy.elsprofile import ElsAuthor
import json
import os
from datetime import datetime

# ---------------- UTF-8 fix for Windows console ----------------
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
# ---------------------------------------------------------------

LOG_FILE = "progress_log.jsonl"  # JSONL log file
ACCESS_LEVEL = 2  # Default access for new authors

# ---------- UTILITY FUNCTIONS ----------

def log_progress(status: str, progress: float = None, details: dict = None):
    """Log progress to file and stdout."""
    entry = {
        "time": datetime.now().isoformat(),
        "status": status,
        "progress": progress,
        "details": details or {}
    }
    # Save to file (UTF-8)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        # Fallback log if file write fails
        print(json.dumps({
            "time": datetime.now().isoformat(),
            "status": f"Log write error: {e}",
            "progress": progress
        }, ensure_ascii=False), flush=True)
    # Print to console for SSE-like streaming
    print(json.dumps(entry, ensure_ascii=False), flush=True)

def clear_progress_log():
    if os.path.exists(LOG_FILE):
        os.remove(LOG_FILE)

def load_config():
    try:
        with open("./config.json") as con_file:
            return json.load(con_file)
    except FileNotFoundError:
        print("Config file not found. Please ensure 'backend/config.json' exists.")
        exit(1)

def connect_to_database():
    try:
        return mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="scopuss",
            port=3306
        )
    except mysql.connector.Error as err:
        print(f"Database connection failed: {err}")
        exit(1)

def initialize_elsclient(config):
    try:
        return ElsClient(config['apikey'])
    except KeyError:
        print("API key not found in config file.")
        exit(1)

def clean_scopus_id(val):
    """Normalize IDs to string, remove .0 added by Excel/DB float conversions."""
    if val is None:
        return ""
    val = str(val).strip()
    if val.endswith(".0"):
        val = val[:-2]
    return val

# ---------- DATABASE FUNCTIONS ----------

def get_existing_papers(cursor):
    """Return a dict: {scopus_id: set of DOIs}"""
    cursor.execute("SELECT scopus_id, doi FROM papers;")
    existing = {}
    for row in cursor.fetchall():
        scopus_id, doi = row
        if scopus_id not in existing:
            existing[scopus_id] = set()
        if doi:
            existing[scopus_id].add(doi)
    return existing

def get_existing_authors(cursor):
    cursor.execute("SELECT scopus_id FROM users;")
    return {row[0] for row in cursor.fetchall()}

def get_all_faculty_scopus_ids(cursor):
    """
    Return a dict: {faculty_id: {'main': main_scopus_id, 'all_ids': [main + additional]}}
    """
    cursor.execute("""
        SELECT u.faculty_id, u.scopus_id AS main_scopus_id, f.scopus_id AS additional_id
        FROM users u
        LEFT JOIN faculty_scopus_map f ON u.faculty_id = f.faculty_id;
    """)
    result = cursor.fetchall()
    faculty_map = {}
    for faculty_id, main_id, additional_id in result:
        faculty_id = clean_scopus_id(faculty_id)
        main_id = clean_scopus_id(main_id)
        additional_id = clean_scopus_id(additional_id)
        if faculty_id not in faculty_map:
            faculty_map[faculty_id] = {'main': main_id, 'all_ids': [main_id]}
        if additional_id and additional_id != main_id and additional_id not in faculty_map[faculty_id]['all_ids']:
            faculty_map[faculty_id]['all_ids'].append(additional_id)
    return faculty_map

def insert_user(cursor, conn, scopus_id, name, docs_count):
    cursor.execute("""
        INSERT INTO users (scopus_id, name, docs_count, access)
        VALUES (%s, %s, %s, 2)
        ON DUPLICATE KEY UPDATE name = VALUES(name), docs_count = VALUES(docs_count)
    """, (scopus_id, name, docs_count))
    conn.commit()

def insert_paper(cursor, conn, scopus_id, doi, title, pub_type, pub_name, date, authors, affiliations):
    authors += [""] * (6 - len(authors))
    affiliations += [""] * (3 - len(affiliations))
    cursor.execute("""
        INSERT INTO papers (scopus_id, doi, title, type, publication_name, date,
                            author1, author2, author3, author4, author5, author6,
                            affiliation1, affiliation2, affiliation3)
        VALUES (%s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s)
        ON DUPLICATE KEY UPDATE title = VALUES(title), type = VALUES(type),
                                publication_name = VALUES(publication_name), date = VALUES(date)
    """, (scopus_id, doi if doi else None, title, pub_type, pub_name, date,
          *authors[:6], *affiliations[:3]))
    conn.commit()

# ---------- MAIN FETCH FUNCTION ----------

def fetch_new_papers():
    clear_progress_log()
    log_progress("Starting Scopus paper update...", 0)

    config = load_config()
    conn = connect_to_database()
    cursor = conn.cursor()
    client = initialize_elsclient(config)

    existing_papers = get_existing_papers(cursor)
    existing_authors = get_existing_authors(cursor)
    faculty_map = get_all_faculty_scopus_ids(cursor)

    total_faculty = len(faculty_map)
    total_new_papers = 0
    total_updated_authors = 0
    authors_with_new_papers = set()

    for idx, (faculty_id, ids_dict) in enumerate(faculty_map.items(), start=1):
        main_id = ids_dict['main']
        scopus_ids_to_check = ids_dict['all_ids']
        progress = idx / total_faculty
        log_progress(f"Processing faculty {idx}/{total_faculty} ({faculty_id})", progress)

        # Fetch profile using main_id
        my_auth = ElsAuthor(uri=f'https://api.elsevier.com/content/author/author_id/{main_id}')
        if not my_auth.read(client):
            log_progress(f"Failed to read author data for {faculty_id}", progress)
            continue

        author_name = my_auth.full_name
        docs_count = int(my_auth.data.get('coredata', {}).get('document-count', 0))

        # Insert/update main user
        insert_user(cursor, conn, main_id, author_name, docs_count)
        total_updated_authors += 1

        # For each Scopus ID of this faculty (main + additional)
        new_papers_for_author = 0
        for scopus_id in scopus_ids_to_check:
            temp_auth = ElsAuthor(uri=f'https://api.elsevier.com/content/author/author_id/{scopus_id}')
            if not temp_auth.read_docs(client):
                continue

            for doc in temp_auth.doc_list:
                doi = doc.get("prism:doi")
                is_new_paper = (
                    main_id not in existing_papers or 
                    (doi and doi not in existing_papers.get(main_id, set()))
                )
                if is_new_paper:
                    title = doc.get("dc:title", "Unknown Title")
                    pub_type = doc.get("prism:aggregationType", "journal").lower()
                    pub_name = doc.get("prism:publicationName", "Unknown Journal")
                    date = doc.get("prism:coverDate", "0000-00-00")
                    authors = [a.get("authname", "Unknown Author") for a in doc.get("author", [])[:6]]
                    affiliations = [a.get("affilname", "Unknown Affiliation") for a in doc.get("affiliation", [])[:3]]

                    insert_paper(cursor, conn, main_id, doi, title, pub_type, pub_name, date, authors, affiliations)
                    new_papers_for_author += 1
                    total_new_papers += 1
                    log_progress(f"Added new paper: {title}", progress)

        if new_papers_for_author > 0:
            authors_with_new_papers.add(author_name)

    summary_msg = f"Update complete: {total_new_papers} new papers, {len(authors_with_new_papers)} authors updated."
    log_progress(summary_msg, 1, {
        "total_new_papers": total_new_papers,
        "authors_with_new_papers": list(authors_with_new_papers),
        "authors_updated": total_updated_authors
    })

    cursor.close()
    conn.close()
    log_progress("Database connection closed.", 1)

# ---------- ENTRY POINT ----------
if __name__ == "__main__":
    fetch_new_papers()
