import pandas as pd
import mysql.connector
from mysql.connector import Error

# ---------- CONFIG ----------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "scopus"
}
EXCEL_FILE = "../../new_faculties.xlsx"
ACCESS_LEVEL = 2
# ----------------------------

def connect_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        if conn.is_connected():
            print("✅ Connected to database.")
        return conn
    except Error as e:
        print("❌ Database connection failed:", e)
        exit(1)

def clean_id(val):
    """Clean and normalize any ID to remove .0, NaN, etc."""
    if pd.isna(val):
        return ""
    val = str(val).strip()
    # Remove trailing '.0' if Excel converted numbers to float
    if val.endswith(".0"):
        val = val[:-2]
    return val

def ensure_user_columns(conn):
    cursor = conn.cursor()
    alter_queries = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS faculty_id VARCHAR(50) NOT NULL AFTER scopus_id;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(100) NOT NULL AFTER name;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password VARCHAR(100) NOT NULL AFTER email;"
    ]
    for q in alter_queries:
        cursor.execute(q)
    conn.commit()
    print("✅ Users table columns checked/added.")

def populate_users(conn):
    df = pd.read_excel(EXCEL_FILE)
    cursor = conn.cursor()

    print("\n📥 Updating users table...")
    for _, row in df.iterrows():
        faculty_id = clean_id(row.get("Faculty ID"))
        name = str(row.get("Faculty Name", "")).strip()
        email = str(row.get("Email ID", "")).strip()
        scopus_id = clean_id(row.get("Scopus ID"))

        if not scopus_id:
            print(f"⚠️ Skipping {faculty_id or name}: No Scopus ID")
            continue

        # Check by Scopus ID or Faculty ID to prevent duplicates
        cursor.execute("""
            SELECT scopus_id FROM users 
            WHERE scopus_id = %s OR faculty_id = %s
        """, (scopus_id, faculty_id))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE users 
                SET faculty_id = %s, name = %s, email = %s, password = %s, access = %s
                WHERE scopus_id = %s OR faculty_id = %s
            """, (faculty_id, name, email, faculty_id, ACCESS_LEVEL, scopus_id, faculty_id))
            print(f"🔄 Updated: {faculty_id} ({name})")
        else:
            cursor.execute("""
                INSERT INTO users (scopus_id, faculty_id, name, email, password, access)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (scopus_id, faculty_id, name, email, faculty_id, ACCESS_LEVEL))
            print(f"➕ Added new faculty: {faculty_id} ({name})")

    conn.commit()
    print("✅ Users table populated successfully.")

def create_and_populate_mapping(conn):
    cursor = conn.cursor()

    # Create mapping table (no FK yet)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faculty_scopus_map (
            id INT AUTO_INCREMENT PRIMARY KEY,
            faculty_id VARCHAR(50),
            scopus_id VARCHAR(50)
        );
    """)
    conn.commit()
    print("\n📦 faculty_scopus_map table ready.")

    df = pd.read_excel(EXCEL_FILE)

    print("📥 Populating faculty_scopus_map...")
    for _, row in df.iterrows():
        faculty_id = clean_id(row.get("Faculty ID"))
        additional_ids = str(row.get("Additional Scopus Id", "")).strip()

        if not faculty_id or additional_ids.lower() == "nan" or additional_ids == "":
            continue

        for add_id in [clean_id(x) for x in additional_ids.split(";") if clean_id(x)]:
            cursor.execute("""
                SELECT id FROM faculty_scopus_map
                WHERE faculty_id = %s AND scopus_id = %s
            """, (faculty_id, add_id))
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO faculty_scopus_map (faculty_id, scopus_id)
                    VALUES (%s, %s)
                """, (faculty_id, add_id))
                print(f"↳ Mapped {faculty_id} → {add_id}")

    conn.commit()
    print("✅ faculty_scopus_map table populated.")

def main():
    print("🚀 Starting faculty data update process...\n")
    conn = connect_db()

    ensure_user_columns(conn)
    populate_users(conn)
    create_and_populate_mapping(conn)

    conn.close()
    print("\n🎉 All operations completed successfully (no duplicates, clean IDs)!")

if __name__ == "__main__":
    main()
