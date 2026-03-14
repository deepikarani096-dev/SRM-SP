import time
import re
import json
import sys
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
DELAY_SECONDS = 6   # IMPORTANT: do not reduce
# --------------------------------------


def connect_db():
    return mysql.connector.connect(**DB_CONFIG)


def get_scopus_ids(cursor):
    """
    Returns scopus_ids for non-C.Tech faculty only.
    Strips dots, spaces and hyphens before comparing so that
    'C.Tech', 'C Tech', 'C-Tech', 'CTECH', 'ctech' are all excluded.
    """
    cursor.execute("""
        SELECT scopus_id
        FROM users
        WHERE scopus_id IS NOT NULL
          AND scopus_id != 0
          AND UPPER(REPLACE(REPLACE(REPLACE(TRIM(department), '.', ''), ' ', ''), '-', '')) != 'CTECH'
    """)
    return [str(row[0]) for row in cursor.fetchall()]


def ensure_chart_table_exists(cursor):
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


def update_metrics(cursor, conn, scopus_id, citations, docs, hindex):
    """Update total metrics in users table"""
    cursor.execute("""
        UPDATE users
        SET citations = %s,
            docs_count = %s,
            h_index = %s
        WHERE scopus_id = %s
    """, (citations, docs, hindex, scopus_id))
    conn.commit()


def upsert_chart_data(cursor, conn, scopus_id, year, documents, citations):
    """Insert/Update yearly chart data"""
    cursor.execute("""
        INSERT INTO scopus_chart_data (scopus_id, year, documents, citations)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            documents = VALUES(documents),
            citations = VALUES(citations)
    """, (scopus_id, year, documents, citations))
    conn.commit()


def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )


def scrape_total_metrics(driver, scopus_id):
    """
    Scrape total h-index, citations, and documents count.
    Returns: (citations, documents, h_index)
    """
    driver.get(SCOPUS_URL.format(scopus_id))
    time.sleep(8)  # allow JS to load

    spans = driver.find_elements(By.CSS_SELECTOR, "span[data-testid='unclickable-count']")

    if len(spans) < 3:
        raise Exception("Total metrics not found")

    citations = int(spans[0].text.replace(",", ""))
    documents = int(spans[1].text.replace(",", ""))
    h_index   = int(spans[2].text.replace(",", ""))

    return citations, documents, h_index


def extract_chart_data(driver):
    """
    Extract yearly chart data (documents and citations by year).
    Returns: { year: { 'documents': int, 'citations': int } }
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
            year  = int(m.group(1))
            cites = int(m.group(2))
            data.setdefault(year, {})["citations"] = cites

    return data


def log_json(message, status="INFO", **kwargs):
    """Log messages in JSON format for streaming"""
    output = {"message": message, "status": status}
    output.update(kwargs)
    print(json.dumps(output))
    sys.stdout.flush()


def main():
    conn   = connect_db()
    cursor = conn.cursor()

    ensure_chart_table_exists(cursor)
    conn.commit()

    scopus_ids  = get_scopus_ids(cursor)
    total_count = len(scopus_ids)
    log_json(f"Found {total_count} non-C.Tech authors", "INFO",
             total=total_count, processed=0)

    driver = setup_driver()

    success          = 0
    failed           = 0
    total_chart_rows = 0

    for idx, scopus_id in enumerate(scopus_ids, start=1):
        try:
            log_json(
                f"[{idx}/{total_count}] Processing {scopus_id}",
                "INFO",
                scopus_id=scopus_id,
                processed=idx,
                total=total_count
            )

            # Single page load — reused for both metrics and chart data
            driver.get(SCOPUS_URL.format(scopus_id))
            time.sleep(10)  # allow JS to fully render

            # Scrape total metrics
            citations, docs, hindex = scrape_total_metrics(driver, scopus_id)
            update_metrics(cursor, conn, scopus_id, citations, docs, hindex)

            # Extract and store yearly chart data
            chart_data  = extract_chart_data(driver)
            chart_count = 0

            for year, values in chart_data.items():
                upsert_chart_data(
                    cursor, conn,
                    scopus_id,
                    year,
                    values.get("documents", 0),
                    values.get("citations", 0)
                )
                chart_count      += 1
                total_chart_rows += 1

            log_json(
                f"✓ {scopus_id}: C={citations}, D={docs}, H={hindex}, {chart_count} years",
                "SUCCESS",
                scopus_id=scopus_id,
                citations=citations,
                documents=docs,
                h_index=hindex,
                chart_rows=chart_count,
                processed=idx,
                total=total_count
            )
            success += 1

        except Exception as e:
            log_json(
                f"✗ {scopus_id}: {str(e)}",
                "ERROR",
                scopus_id=scopus_id,
                error=str(e),
                processed=idx,
                total=total_count
            )
            failed += 1

        time.sleep(DELAY_SECONDS)

    driver.quit()
    cursor.close()
    conn.close()

    log_json(
        "COMPLETE",
        "COMPLETE",
        success=success,
        failed=failed,
        total_chart_rows=total_chart_rows,
        total=total_count,
        processed=total_count
    )


if __name__ == "__main__":
    main()