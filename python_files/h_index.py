from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import mysql.connector
import time
import os

# --- DB CONFIG ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # Set your MySQL password
    'database': 'scopus',
}

# --- SETUP SELENIUM WITH FAKE USER AGENT ---
chrome_options = Options()
# chrome_options.add_argument('--headless')  # Uncomment for headless mode
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# --- CONNECT TO DATABASE ---
conn = mysql.connector.connect(**DB_CONFIG)
cursor = conn.cursor()

# --- ADD h_index COLUMN IF MISSING ---
cursor.execute("SHOW COLUMNS FROM users LIKE 'h_index'")
if not cursor.fetchone():
    cursor.execute("ALTER TABLE users ADD COLUMN h_index INT DEFAULT NULL")
    conn.commit()
    print("✅ Added 'h_index' column to 'users' table.")

# --- FETCH ALL scopus_ids ---
cursor.execute("SELECT scopus_id FROM users")
author_ids = [row[0] for row in cursor.fetchall()]

# --- MAIN LOOP ---
for author_id in author_ids:
    url = f"https://www.scopus.com/authid/detail.uri?authorId={author_id}"
    print(f"\n🌐 Accessing: {url}")
    driver.get(url)

    try:
        # Wait for at least one span to load
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'span[data-testid="unclickable-count"]'))
        )
        spans = driver.find_elements(By.CSS_SELECTOR, 'span[data-testid="unclickable-count"]')

        if len(spans) >= 3:
            h_index = int(spans[2].text.strip())
            print(f"✅ Author ID {author_id} | h-index: {h_index}")

            cursor.execute("""
                UPDATE users SET h_index = %s WHERE scopus_id = %s
            """, (h_index, author_id))
            conn.commit()
        else:
            print(f"⚠️ Could not find expected element structure for {author_id} (found {len(spans)})")
            driver.save_screenshot(f"{author_id}_hindex_missing.png")

    except Exception as e:
        print(f"❌ Error for {author_id}: {e}")
        driver.save_screenshot(f"{author_id}_error.png")

# --- CLEANUP ---
cursor.close()
conn.close()
driver.quit()
print("\n✅ Done updating all h-index values.")
