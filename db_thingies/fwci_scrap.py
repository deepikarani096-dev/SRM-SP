"""
scrape_fwci.py
==============
Scrapes FWCI from the Scopus author profile Impact tab.

Based on debug output, the exact DOM structure is:

OVERALL FWCI:
  <span class="Typography-module__ix7bs ...">2.34</span>
  inside a container with data-testid="author-metrics-fwci"

YEARLY FWCI:
  SVG path elements with aria-label like:
    aria-label="2019, 2.42. FWCI."
    aria-label="2021, 6.52. FWCI."
  — zero values appear as: aria-label="2015, 0. FWCI."
  We skip 0 values since they add no information.

Requirements:
    pip install selenium webdriver-manager mysql-connector-python

Run:
    python3 scrape_fwci.py
"""

import time
import re
import logging
import mysql.connector
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

# ── DB config ──────────────────────────────────────────────────────────────────
DB_HOST     = "localhost"
DB_PORT     = 3307
DB_USER     = "root"
DB_PASSWORD = ""        # ← add if root has a password
DB_NAME     = "scopuss"

# ── Scraper config ─────────────────────────────────────────────────────────────
SCOPUS_IMPACT_URL = "https://www.scopus.com/authid/detail.uri?authorId={sid}#tab=impact"
PAGE_LOAD_WAIT    = 40
RENDER_WAIT       = 8    # seconds after tab click for Highcharts to render
BETWEEN_REQ       = 5
HEADLESS          = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# DATABASE
# ══════════════════════════════════════════════════════════════════════════════

def get_db():
    return mysql.connector.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset="utf8mb4",
    )


def ensure_columns(cursor):
    for table, after in [("users", "h_index"), ("scopus_chart_data", "citations")]:
        cursor.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME='fwci'
        """, (DB_NAME, table))
        if cursor.fetchone()[0] == 0:
            cursor.execute(f"""
                ALTER TABLE `{table}`
                ADD COLUMN fwci DECIMAL(10,4) DEFAULT NULL
                COMMENT 'Field-Weighted Citation Impact from Scopus'
                AFTER `{after}`
            """)
            log.info(f"  Added column {table}.fwci")
        else:
            log.info(f"  Column {table}.fwci already exists")


def fetch_faculty(cursor):
    cursor.execute("""
        SELECT faculty_id, scopus_id FROM users
        WHERE scopus_id IS NOT NULL AND scopus_id <> 0
        ORDER BY faculty_id
    """)
    return cursor.fetchall()


def fetch_years_for_scopus(cursor, scopus_id):
    cursor.execute(
        "SELECT year FROM scopus_chart_data WHERE scopus_id=%s ORDER BY year",
        (scopus_id,)
    )
    return [r[0] for r in cursor.fetchall()]


def save_overall_fwci(cursor, scopus_id, fwci):
    cursor.execute(
        "UPDATE users SET fwci=%s WHERE scopus_id=%s",
        (fwci, scopus_id)
    )


def save_yearly_fwci(cursor, scopus_id, year, fwci):
    cursor.execute(
        "UPDATE scopus_chart_data SET fwci=%s WHERE scopus_id=%s AND year=%s",
        (fwci, scopus_id, year)
    )


# ══════════════════════════════════════════════════════════════════════════════
# BROWSER
# ══════════════════════════════════════════════════════════════════════════════

def make_driver():
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()), options=opts
    )


def click_impact_tab(driver):
    xpaths = [
        "//button[normalize-space()='Impact']",
        "//a[normalize-space()='Impact']",
        "//*[@role='tab'][normalize-space()='Impact']",
        "//a[contains(@href,'tab=impact')]",
    ]
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, xp))
            )
            driver.execute_script("arguments[0].click();", el)
            log.info("  ✓ Clicked Impact tab")
            return True
        except (TimeoutException, NoSuchElementException):
            continue
    log.warning("  Could not click Impact tab")
    return False


# ══════════════════════════════════════════════════════════════════════════════
# EXTRACTION — using exact selectors from debug output
# ══════════════════════════════════════════════════════════════════════════════

def extract_overall_fwci(driver, page_source):
    """
    From debug output, the overall FWCI value (e.g. 2.34) is a <span>
    inside a container with data-testid="author-metrics-fwci".

    The value span has class containing 'ix7bs' (the bold/large variant)
    while the 'FWCI' label is a <p> with class containing 'fRnrd'.

    We find the container by data-testid, then grab the span whose text
    is a decimal number.
    """

    # ── Method 1: data-testid container (most reliable) ───────────────────
    try:
        container = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='author-metrics-fwci']"
        )
        # Find all spans/elements inside — the value is the decimal number one
        children = container.find_elements(By.XPATH, ".//*")
        for el in children:
            txt = el.text.strip()
            if re.fullmatch(r"\d+\.\d+", txt):
                v = float(txt)
                log.info(f"  Method1 (testid container): FWCI={v}")
                return v
    except NoSuchElementException:
        pass

    # ── Method 2: span with class ix7bs (the large value typography class) ─
    # From debug: class='Typography-module__lVnit Typography-module__ix7bs Typography'
    try:
        spans = driver.find_elements(
            By.XPATH,
            "//span[contains(@class,'ix7bs')]"
        )
        for span in spans:
            txt = span.text.strip()
            if re.fullmatch(r"\d+\.\d+", txt):
                # Verify FWCI is nearby — check parent or sibling contains "FWCI"
                try:
                    parent = span.find_element(By.XPATH, "../..")
                    parent_txt = parent.text
                    if "FWCI" in parent_txt:
                        v = float(txt)
                        log.info(f"  Method2 (ix7bs span): FWCI={v}")
                        return v
                except Exception:
                    pass
    except Exception:
        pass

    # ── Method 3: find <p> with text exactly 'FWCI', then get sibling span ─
    # From debug: <p class="...fRnrd...">FWCI</p> is the label
    try:
        fwci_labels = driver.find_elements(
            By.XPATH, "//p[normalize-space(text())='FWCI']"
        )
        for label in fwci_labels:
            # The value is in a sibling or preceding element
            try:
                # Try grandparent text — should be "2.34\nFWCI\nNote:..."
                gp = label.find_element(By.XPATH, "../..")
                gp_text = gp.text.strip()
                lines = [l.strip() for l in gp_text.split("\n") if l.strip()]
                for i, line in enumerate(lines):
                    if line == "FWCI" and i > 0:
                        cand = lines[i - 1]
                        if re.fullmatch(r"\d+\.\d+", cand):
                            v = float(cand)
                            log.info(f"  Method3 (fRnrd label sibling): FWCI={v}")
                            return v
            except Exception:
                pass
    except Exception:
        pass

    # ── Method 4: regex on raw HTML — data-testid="author-metrics-fwci" block ─
    # From debug raw source, the container has data-testid="author-metrics-fwci"
    try:
        m = re.search(
            r'data-testid="author-metrics-fwci"[^>]*>.*?(\d+\.\d+)',
            page_source,
            re.DOTALL
        )
        if m:
            v = float(m.group(1))
            log.info(f"  Method4 (raw HTML regex): FWCI={v}")
            return v
    except Exception:
        pass

    return None


def extract_yearly_fwci(page_source, known_years):
    """
    From debug output, Highcharts renders each data point as an SVG path with:
      aria-label="2019, 2.42. FWCI."
      aria-label="2021, 6.52. FWCI."
      aria-label="2015, 0. FWCI."   ← zero, skip these

    Pattern: aria-label="YEAR, VALUE. FWCI."

    We parse ALL such aria-labels from the raw HTML and keep only the years
    that exist in the database (known_years).
    """
    known_set = set(known_years)
    yearly    = {}

    # Match: aria-label="2019, 2.42. FWCI."  or  aria-label="2018, 0. FWCI."
    pattern = re.compile(
        r'aria-label="(\d{4}),\s*([\d.]+)\.\s*FWCI\."'
    )

    for m in pattern.finditer(page_source):
        year  = int(m.group(1))
        value = m.group(2)

        # Skip zero values — they mean no data that year
        if value == "0" or value == "0.0":
            continue

        fv = float(value)
        if fv <= 0:
            continue

        if year in known_set:
            yearly[year] = fv

    return yearly


# ══════════════════════════════════════════════════════════════════════════════
# MAIN SCRAPE
# ══════════════════════════════════════════════════════════════════════════════

def scrape_fwci(driver, scopus_id, known_years):
    url = SCOPUS_IMPACT_URL.format(sid=scopus_id)
    log.info(f"  URL: {url}")
    driver.get(url)

    overall_fwci = None
    yearly_fwci  = {}

    try:
        WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        click_impact_tab(driver)

        # Wait for Highcharts to fully render the FWCI chart
        try:
            WebDriverWait(driver, PAGE_LOAD_WAIT).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "[data-testid='author-metrics-fwci']"
                ))
            )
            log.info("  ✓ FWCI section loaded")
        except TimeoutException:
            log.warning("  FWCI section not found by testid — waiting extra time")

        # Extra time for Highcharts SVG to render
        time.sleep(RENDER_WAIT)

        page_source = driver.page_source

        # Extract overall FWCI
        overall_fwci = extract_overall_fwci(driver, page_source)
        log.info(f"  Overall FWCI = {overall_fwci}")

        # Extract yearly FWCI from SVG aria-labels
        yearly_fwci = extract_yearly_fwci(page_source, known_years)
        log.info(f"  Yearly FWCI  = {yearly_fwci}")

    except TimeoutException:
        log.warning(f"  Timed out for scopus_id={scopus_id}")
    except Exception as exc:
        log.error(f"  Error for scopus_id={scopus_id}: {exc}", exc_info=False)

    return overall_fwci, yearly_fwci


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    log.info(f"Connecting to '{DB_NAME}' on {DB_HOST}:{DB_PORT} …")
    db     = get_db()
    cursor = db.cursor()

    ensure_columns(cursor)
    db.commit()

    faculty_list = fetch_faculty(cursor)
    log.info(f"Found {len(faculty_list)} faculty members\n")

    driver = make_driver()

    try:
        for i, (faculty_id, scopus_id) in enumerate(faculty_list, 1):
            log.info(f"[{i}/{len(faculty_list)}]  faculty_id={faculty_id}  scopus_id={scopus_id}")

            known_years = fetch_years_for_scopus(cursor, scopus_id)
            log.info(f"  DB years: {known_years if known_years else 'none'}")

            overall_fwci, yearly_fwci = scrape_fwci(driver, scopus_id, known_years)

            if overall_fwci is not None:
                save_overall_fwci(cursor, scopus_id, overall_fwci)
                log.info(f"  ✓ users.fwci = {overall_fwci}")
            else:
                log.warning(f"  ✗ Overall FWCI not found for scopus_id={scopus_id}")

            for year, fv in yearly_fwci.items():
                save_yearly_fwci(cursor, scopus_id, year, fv)
                log.info(f"  ✓ chart_data year={year} fwci={fv}")

            db.commit()
            log.info(f"  ✓ Committed — sleeping {BETWEEN_REQ}s\n")
            time.sleep(BETWEEN_REQ)

    finally:
        driver.quit()
        cursor.close()
        db.close()
        log.info("All done.")


if __name__ == "__main__":
    main()