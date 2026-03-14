import time
import re
import mysql.connector
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ---------------- CONFIG ----------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "scopuss",
    "port": 3307
}

SCOPUS_URL = "https://www.scopus.com/authid/detail.uri?authorId={}"
DELAY_SECONDS = 6
# --------------------------------------


def connect_db():
    return mysql.connector.connect(**DB_CONFIG)


def ensure_table_exists(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scopus_chart_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            scopus_id BIGINT NOT NULL,
            year INT NOT NULL,
            documents INT DEFAULT 0,
            citations INT DEFAULT 0,
            UNIQUE KEY uq_scopus_year (scopus_id, year),
            INDEX idx_scopus_id (scopus_id),
            INDEX idx_year (year)
        )
    """)


def get_scopus_ids(cursor):
    cursor.execute("""
        SELECT scopus_id
        FROM users
        WHERE scopus_id IS NOT NULL
    """)
    return [str(row[0]) for row in cursor.fetchall()]


def setup_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )


def extract_chart_data(driver):
    """
    Returns:
    { year: { 'documents': int, 'citations': int } }
    """
    data = {}

    # Documents (bar chart)
    doc_points = driver.find_elements(
        By.CSS_SELECTOR,
        ".highcharts-series-0.highcharts-column-series .highcharts-point"
    )

    for p in doc_points:
        aria = p.get_attribute("aria-label")
        if not aria:
            continue
        m = re.search(r"(\d{4}), (\d+)\. Documents", aria)
        if m:
            year = int(m.group(1))
            docs = int(m.group(2))
            data.setdefault(year, {})["documents"] = docs

    # Citations (line chart)
    cit_points = driver.find_elements(
        By.CSS_SELECTOR,
        ".highcharts-series-1.highcharts-line-series .highcharts-point"
    )

    for p in cit_points:
        aria = p.get_attribute("aria-label")
        if not aria:
            continue
        m = re.search(r"(\d{4}), (\d+)\. Citations", aria)
        if m:
            year = int(m.group(1))
            cites = int(m.group(2))
            data.setdefault(year, {})["citations"] = cites

    return data


def upsert_chart_data(cursor, conn, scopus_id, year, documents, citations):
    cursor.execute("""
        INSERT INTO scopus_chart_data (scopus_id, year, documents, citations)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            documents = VALUES(documents),
            citations = VALUES(citations)
    """, (scopus_id, year, documents, citations))
    conn.commit()


def main():
    conn = connect_db()
    cursor = conn.cursor()

    # Ensure table exists
    ensure_table_exists(cursor)
    conn.commit()

    scopus_ids = get_scopus_ids(cursor)
    print(f"Found {len(scopus_ids)} authors")

    driver = setup_driver()
    total_rows = 0

    for idx, scopus_id in enumerate(scopus_ids, start=1):
        print(f"[{idx}/{len(scopus_ids)}] {scopus_id}")

        try:
            driver.get(SCOPUS_URL.format(scopus_id))
            time.sleep(10)  # allow JS to load

            chart_data = extract_chart_data(driver)

            for year, values in chart_data.items():
                docs = values.get("documents", 0)
                cites = values.get("citations", 0)

                upsert_chart_data(
                    cursor,
                    conn,
                    scopus_id,
                    year,
                    docs,
                    cites
                )
                total_rows += 1

            print(f"  ✔ {len(chart_data)} years updated")

        except Exception as e:
            print(f"  ✖ Failed: {e}")

        time.sleep(DELAY_SECONDS)

    driver.quit()
    cursor.close()
    conn.close()

    print("\nDONE")
    print(f"Total rows written: {total_rows}")


if __name__ == "__main__":
    main()
