import time
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
    cursor.execute("""
        SELECT scopus_id
        FROM users
        WHERE scopus_id IS NOT NULL
    """)
    return [str(row[0]) for row in cursor.fetchall()]


def update_metrics(cursor, conn, scopus_id, citations, docs, hindex):
    cursor.execute("""
        UPDATE users
        SET citations = %s,
            docs_count = %s,
            h_index = %s
        WHERE scopus_id = %s
    """, (citations, docs, hindex, scopus_id))
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


def scrape_metrics(driver, scopus_id):
    driver.get(SCOPUS_URL.format(scopus_id))
    time.sleep(8)  # allow JS to load

    spans = driver.find_elements(By.CSS_SELECTOR, "span[data-testid='unclickable-count']")

    if len(spans) < 3:
        raise Exception("Metrics not found")

    citations = int(spans[0].text.replace(",", ""))
    documents = int(spans[1].text.replace(",", ""))
    h_index = int(spans[2].text.replace(",", ""))

    return citations, documents, h_index


def main():
    conn = connect_db()
    cursor = conn.cursor()

    scopus_ids = get_scopus_ids(cursor)
    print(f"Found {len(scopus_ids)} authors")

    driver = setup_driver()

    success = 0
    failed = 0

    for idx, scopus_id in enumerate(scopus_ids, start=1):
        print(f"[{idx}/{len(scopus_ids)}] {scopus_id}")

        try:
            citations, docs, hindex = scrape_metrics(driver, scopus_id)
            update_metrics(cursor, conn, scopus_id, citations, docs, hindex)
            print(f"  ✔ C={citations}, D={docs}, H={hindex}")
            success += 1

        except Exception as e:
            print(f"  ✖ Failed: {e}")
            failed += 1

        time.sleep(DELAY_SECONDS)

    driver.quit()
    cursor.close()
    conn.close()

    print("\nDONE")
    print(f"Success: {success}")
    print(f"Failed: {failed}")


if __name__ == "__main__":
    main()
