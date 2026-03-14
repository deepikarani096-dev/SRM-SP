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


conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor(dictionary=True)

# ---------- Create paper_insights table ----------
cursor.execute(f"USE {NEW_DB}")
cursor.execute("""
CREATE TABLE IF NOT EXISTS paper_insights (
    doi VARCHAR(255) PRIMARY KEY,

    scopus_author_id_first VARCHAR(50),
    scopus_author_id_corresponding VARCHAR(50),

    sustainable_development_goals TEXT,

    qs_subject_code VARCHAR(100),
    qs_subject_field_name VARCHAR(255),

    asjc_code VARCHAR(100),
    asjc_field_name VARCHAR(255),

    no_of_countries INT,
    country_list TEXT,

    no_of_institutions INT,
    institution_list TEXT,

    total_authors INT
)
""")

# ---------- Fetch from old DB ----------
cursor.execute(f"""
SELECT
    doi,
    scopus_author_id_first,
    scopus_author_id_corresponding,
    sustainable_development_goals,
    qs_subject_code,
    qs_subject_field_name,
    asjc_code,
    asjc_field_name,
    no_of_countries,
    country_list,
    no_of_institutions,
    institution_list,
    total_authors
FROM {OLD_DB}.paper_insights
""")

rows = cursor.fetchall()
print(f"Found {len(rows)} paper_insights rows in old DB")

insert_query = """
INSERT IGNORE INTO paper_insights
(
    doi,
    scopus_author_id_first,
    scopus_author_id_corresponding,
    sustainable_development_goals,
    qs_subject_code,
    qs_subject_field_name,
    asjc_code,
    asjc_field_name,
    no_of_countries,
    country_list,
    no_of_institutions,
    institution_list,
    total_authors
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

rows_inserted = 0

for r in rows:
    cursor.execute(
        insert_query,
        (
            r["doi"],
            r["scopus_author_id_first"],
            r["scopus_author_id_corresponding"],
            r["sustainable_development_goals"],
            r["qs_subject_code"],
            r["qs_subject_field_name"],
            r["asjc_code"],
            r["asjc_field_name"],
            r["no_of_countries"],
            r["country_list"],
            r["no_of_institutions"],
            r["institution_list"],
            r["total_authors"]
        )
    )
    rows_inserted += cursor.rowcount

conn.commit()
cursor.close()
conn.close()

print(f"✅ Migrated {rows_inserted} rows into scopuss.paper_insights")
