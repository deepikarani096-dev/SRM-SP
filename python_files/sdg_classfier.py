import requests
import mysql.connector
import re
import time

# ── CONFIG ──
dry_run   = False                          # False → actually write back to DB
HF_TOKEN  = "token"           # ← your Hugging Face token
API_URL   = "https://api-inference.huggingface.co/models/facebook/bart-large-mnli"
HEADERS   = {"Authorization": f"Bearer {HF_TOKEN}"}

# 1️⃣ zero‑shot candidate labels
sdg_labels = [f"SDG {i}" for i in range(1, 18)]

# 2️⃣ helper to pick out numeric SDG codes from labels above a threshold
def extract_sdg_numbers(labels, scores, threshold=0.3):
    out = []
    for lbl, score in zip(labels, scores):
        if score >= threshold:
            m = re.match(r"SDG\s*(\d+)", lbl)
            if m:
                out.append(m.group(1))
    return ",".join(sorted(set(out), key=int))

# 3️⃣ fallback: pick the top‑n labels even if below threshold
def top_n_sdg_numbers(labels, scores, n=1):
    pairs = sorted(zip(labels, scores), key=lambda x: x[1], reverse=True)[:n]
    nums = []
    for lbl, _ in pairs:
        m = re.match(r"SDG\s*(\d+)", lbl)
        if m:
            nums.append(m.group(1))
    return ",".join(sorted(set(nums), key=int))

# 4️⃣ zero‑shot call
def query_zero_shot(text):
    payload = {
        "inputs": text,
        "parameters": {
            "candidate_labels": sdg_labels,
            "multi_label": True
        }
    }
    resp = requests.post(API_URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return data["labels"], data["scores"]

# ── MAIN ──

# Connect to MySQL
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="scopus"
)
cursor = conn.cursor(dictionary=True)

# Fetch papers with missing SDGs
cursor.execute("""
    SELECT p.doi, p.title, i.qs_subject_field_name, i.asjc_field_name
    FROM papers p
    JOIN paper_insights i ON p.doi = i.doi
    WHERE TRIM(IFNULL(i.sustainable_development_goals, '')) IN ('', '-', 'UNSPECIFIED')
""")
papers = cursor.fetchall()

for paper in papers:
    doi  = paper['doi']
    text = (
        f"Title: {paper['title']}\n"
        f"QS Subject: {paper['qs_subject_field_name']}\n"
        f"ASJC Field: {paper['asjc_field_name']}"
    )
    try:
        labels, scores = query_zero_shot(text)

        # 1) try threshold-based extraction
        sdg_nums = extract_sdg_numbers(labels, scores, threshold=0.3)
        # 2) if none, fallback to top‑1
        if not sdg_nums:
            sdg_nums = top_n_sdg_numbers(labels, scores, n=1)

        # 3) format for DB: "SDG 3| SDG 9| SDG 13"
        sdg_db = ""
        if sdg_nums:
            sdg_db = "| ".join(f"SDG {n}" for n in sdg_nums.split(","))

        # 4) low‑confidence flag (optional)
        needs_review = max(scores) < 0.4

        print(f"[✓] {doi} → {sdg_db} {'(REVIEW)' if needs_review else ''}")

        # 5) write back if not dry run and we have something
        if not dry_run and sdg_db:
            cursor.execute("""
                UPDATE paper_insights
                SET sustainable_development_goals = %s
                WHERE doi = %s
            """, (sdg_db, doi))
            conn.commit()

        time.sleep(1.0)  # avoid rate limits

    except Exception as e:
        print(f"[!] Error with DOI {doi}: {e}")

cursor.close()
conn.close()
