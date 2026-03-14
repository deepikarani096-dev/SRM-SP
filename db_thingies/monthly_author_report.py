import mysql.connector
from datetime import datetime

# ---------- DATABASE CONNECTION ----------

def connect_to_database():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="scopuss",
        port=3307
    )

# ---------- DATE UTILITY ----------

def get_previous_month():
    today = datetime.today()
    year = today.year
    month = today.month - 1
    if month == 0:
        month = 12
        year -= 1
    return year, month

# ---------- DB HELPERS ----------

def get_last_snapshot(cursor, scopus_id):
    cursor.execute("""
        SELECT total_docs, total_citations
        FROM monthly_author_report
        WHERE scopus_id = %s
        ORDER BY report_year DESC, report_month DESC
        LIMIT 1
    """, (scopus_id,))
    row = cursor.fetchone()
    if row:
        return int(row[0]), int(row[1])
    return 0, 0

def insert_monthly_report(
    cursor, conn,
    scopus_id, faculty_id,
    year, month,
    docs_added, citations_added,
    total_docs, total_citations
):
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
        scopus_id, faculty_id,
        year, month,
        docs_added, citations_added,
        total_docs, total_citations
    ))
    conn.commit()

# ---------- MAIN LOGIC ----------

def generate_monthly_author_report():
    conn = connect_to_database()
    cursor = conn.cursor()

    report_year, report_month = get_previous_month()

    print(f"Generating monthly author report for {report_month}/{report_year}")

    # Fetch current author totals
    cursor.execute("""
        SELECT faculty_id, scopus_id, docs_count, citations
        FROM users
        WHERE scopus_id IS NOT NULL
    """)
    authors = cursor.fetchall()

    processed = 0

    for faculty_id, scopus_id, docs_count, citations in authors:
        if not scopus_id:
            continue

        docs_count = int(docs_count or 0)
        citations = int(citations or 0)

        last_docs, last_citations = get_last_snapshot(cursor, scopus_id)

        docs_added = max(docs_count - last_docs, 0)
        citations_added = max(citations - last_citations, 0)

        insert_monthly_report(
            cursor, conn,
            scopus_id, faculty_id,
            report_year, report_month,
            docs_added, citations_added,
            docs_count, citations
        )

        processed += 1

    print(f"Monthly author report generated successfully")
    print(f"Authors processed: {processed}")

    cursor.close()
    conn.close()

# ---------- ENTRY POINT ----------

if __name__ == "__main__":
    generate_monthly_author_report()
