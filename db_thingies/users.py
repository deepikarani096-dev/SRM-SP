import pandas as pd
import mysql.connector

# ================= CONFIG =================
EXCEL_FILE = "faculties.xlsx"   # <-- change path if needed

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": ""             # XAMPP default
}

DB_NAME = "scopuss"
DEFAULT_ACCESS_LEVEL = 3
# ==========================================


def clean_scopus_id(value):
    """
    Convert Excel float/string Scopus IDs to clean int.
    Returns None if invalid.
    """
    if pd.isna(value):
        return None
    try:
        return int(float(str(value).strip()))
    except:
        return None


# ---------- DB CONNECTION ----------
conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

# Create database
cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
cursor.execute(f"USE {DB_NAME}")

# Create users table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,

    faculty_id VARCHAR(50),
    faculty_name VARCHAR(255) NOT NULL,
    designation VARCHAR(255),
    mobile_no VARCHAR(20),
    email VARCHAR(255),
    doj DATE,

    scopus_id BIGINT NOT NULL UNIQUE,

    access_level INT DEFAULT 3,
    docs_count INT DEFAULT 0,
    citations INT DEFAULT 0,
    h_index INT DEFAULT 0
)
""")

# ---------- READ EXCEL ----------
df = pd.read_excel(EXCEL_FILE)

insert_query = """
INSERT IGNORE INTO users
(
    faculty_id,
    faculty_name,
    designation,
    mobile_no,
    email,
    doj,
    scopus_id,
    access_level,
    docs_count,
    citations,
    h_index
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

rows_inserted = 0

# ---------- PROCESS ROWS ----------
for _, row in df.iterrows():
    faculty_id = str(row["Faculty ID"]).strip() if pd.notna(row["Faculty ID"]) else None
    faculty_name = row["Faculty Name"]
    designation = row["Designation"]
    mobile = str(row["Mobile No"]).strip() if pd.notna(row["Mobile No"]) else None
    email = row["Email ID"]

    # Safe DOJ parsing
    doj = pd.to_datetime(row["DOJ"], errors="coerce")
    doj = doj.date() if pd.notna(doj) else None

    # Collect all Scopus IDs
    scopus_ids = []

    primary_id = clean_scopus_id(row["Scopus ID"])
    if primary_id:
        scopus_ids.append(primary_id)

    if pd.notna(row["Additional Scopus Id"]):
        extra_ids = str(row["Additional Scopus Id"]).split(", ")
        for eid in extra_ids:
            cleaned = clean_scopus_id(eid)
            if cleaned:
                scopus_ids.append(cleaned)

    # Insert one row per Scopus ID
    for sid in scopus_ids:
        cursor.execute(
            insert_query,
            (
                faculty_id,
                faculty_name,
                designation,
                mobile,
                email,
                doj,
                sid,
                DEFAULT_ACCESS_LEVEL,
                0,  # docs_count
                0,  # citations
                0   # h_index
            )
        )
        rows_inserted += cursor.rowcount

# ---------- COMMIT & CLOSE ----------
conn.commit()
cursor.close()
conn.close()

print(f"✅ DONE: Inserted {rows_inserted} rows into scopuss.users")
