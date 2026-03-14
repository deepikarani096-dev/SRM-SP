import mysql.connector

# ================= CONFIG =================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": ""   # XAMPP default
}

OLD_DB = "scopus"
NEW_DB = "scopuss"
# ==========================================


def clean_scopus_id(value):
    """
    Convert scopus_id from varchar/float-like strings to BIGINT.
    Returns None if invalid.
    """
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except:
        return None


conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor(dictionary=True)

# ---------- Create papers table in new DB ----------
cursor.execute(f"USE {NEW_DB}")
cursor.execute("""
CREATE TABLE IF NOT EXISTS papers (
    id INT AUTO_INCREMENT PRIMARY KEY,

    scopus_id BIGINT,
    doi VARCHAR(255),
    title VARCHAR(255) NOT NULL,
    type ENUM('Journal','Conference Proceeding') NOT NULL,
    publication_name VARCHAR(255) NOT NULL,
    date DATE NOT NULL,

    author1 VARCHAR(100),
    author2 VARCHAR(100),
    author3 VARCHAR(100),
    author4 VARCHAR(100),
    author5 VARCHAR(100),
    author6 VARCHAR(100),

    affiliation1 VARCHAR(255),
    affiliation2 VARCHAR(255),
    affiliation3 VARCHAR(255),

    quartile VARCHAR(4),

    INDEX idx_scopus_id (scopus_id),
    INDEX idx_date (date),
    INDEX idx_doi (doi)
)
""")

# ---------- Fetch from old DB ----------
cursor.execute(f"""
SELECT
    scopus_id,
    doi,
    title,
    type,
    publication_name,
    date,
    author1,
    author2,
    author3,
    author4,
    author5,
    author6,
    affiliation1,
    affiliation2,
    affiliation3,
    quartile
FROM {OLD_DB}.papers
""")

papers = cursor.fetchall()
print(f"Found {len(papers)} papers in old DB")

insert_query = """
INSERT IGNORE INTO papers
(
    scopus_id, doi, title, type, publication_name, date,
    author1, author2, author3, author4, author5, author6,
    affiliation1, affiliation2, affiliation3,
    quartile
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

rows_inserted = 0
rows_skipped = 0

for p in papers:
    sid = clean_scopus_id(p["scopus_id"])

    if sid is None:
        rows_skipped += 1
        continue

    cursor.execute(
        insert_query,
        (
            sid,
            p["doi"],
            p["title"],
            p["type"],
            p["publication_name"],
            p["date"],
            p["author1"],
            p["author2"],
            p["author3"],
            p["author4"],
            p["author5"],
            p["author6"],
            p["affiliation1"],
            p["affiliation2"],
            p["affiliation3"],
            p["quartile"]
        )
    )
    rows_inserted += cursor.rowcount

conn.commit()
cursor.close()
conn.close()

print(f"✅ Migrated {rows_inserted} papers")
print(f"⚠️ Skipped {rows_skipped} papers due to invalid scopus_id")
