import mysql.connector

# ---------------- CONFIG ----------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "port": 3306
}

OLD_DB = "scopus"
NEW_DB = "scopuss"
TABLE_NAME = "faculty_quartile_summary"
# --------------------------------------


def connect_db():
    return mysql.connector.connect(**DB_CONFIG)


def main():
    conn = connect_db()
    cursor = conn.cursor()

    # 1. Get CREATE TABLE statement from old DB
    cursor.execute(f"SHOW CREATE TABLE {OLD_DB}.{TABLE_NAME}")
    create_stmt = cursor.fetchone()[1]

    # 2. Create table in new DB
    cursor.execute(f"USE {NEW_DB}")
    cursor.execute(create_stmt)

    print(f"✔ Table `{TABLE_NAME}` created in `{NEW_DB}`")

    # 3. Copy data
    cursor.execute(f"""
        INSERT IGNORE INTO {NEW_DB}.{TABLE_NAME}
        SELECT *
        FROM {OLD_DB}.{TABLE_NAME}
    """)

    rows_copied = cursor.rowcount
    conn.commit()

    print(f"✔ Copied {rows_copied} rows into `{NEW_DB}.{TABLE_NAME}`")

    cursor.close()
    conn.close()

    print("DONE")


if __name__ == "__main__":
    main()
