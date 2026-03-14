import sys
import pandas as pd
import mysql.connector
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(message)s")

# ============================
# ARG CHECK
# ============================

if len(sys.argv) < 2:
    logging.error("❌ No Excel file provided.")
    sys.exit(1)

excel_file = sys.argv[1]

if not os.path.exists(excel_file):
    logging.error(f"❌ File not found: {excel_file}")
    sys.exit(1)

logging.info(f"📂 Processing file: {excel_file}")

# ============================
# READ EXCEL
# ============================

# ============================
# READ EXCEL OR CSV
# ============================

try:
    if excel_file.lower().endswith(".csv"):
        df = pd.read_csv(excel_file)
        logging.info("📄 CSV file detected.")
    elif excel_file.lower().endswith((".xlsx", ".xls", ".xlsm")):
        df = pd.read_excel(excel_file)
        logging.info("📊 Excel file detected.")
    else:
        logging.error(f"❌ Unsupported file format. Supported formats: CSV, XLSX, XLS, XLSM")
        sys.exit(1)
except Exception as e:
    logging.error(f"❌ Failed to read input file: {e}")
    sys.exit(1)


# ============================
# DYNAMIC SDG COLUMN DETECT
# ============================

sdg_col = None
for col in df.columns:
    if "Sustainable Development Goals" in col:
        sdg_col = col
        break

if not sdg_col:
    logging.error("❌ SDG column not found in Excel.")
    sys.exit(1)

logging.info(f"📌 Detected SDG column: {sdg_col}")

# ============================
# RENAME COLUMNS
# ============================

df = df.rename(columns={
    'DOI': 'doi',
    'Scopus Author ID First Author': 'scopus_author_id_first',
    'Scopus Author ID Corresponding Author': 'scopus_author_id_corresponding',
    sdg_col: 'sustainable_development_goals',
    'Quacquarelli Symonds (QS) Subject code': 'qs_subject_code',
    'Quacquarelli Symonds (QS) Subject field name': 'qs_subject_field_name',
    'All Science Journal Classification (ASJC) code': 'asjc_code',
    'All Science Journal Classification (ASJC) field name': 'asjc_field_name',
    'Number of Countries/Regions': 'no_of_countries',
    'Country/Region': 'country_list',
    'Number of Institutions': 'no_of_institutions',
    'Scopus Affiliation names': 'institution_list',
    'Number of Authors': 'total_authors'
})

# ============================
# REQUIRED COLUMNS
# ============================

required_cols = [
    'doi', 'scopus_author_id_first', 'scopus_author_id_corresponding',
    'sustainable_development_goals', 'qs_subject_code',
    'qs_subject_field_name', 'asjc_code', 'asjc_field_name',
    'no_of_countries', 'country_list',
    'no_of_institutions', 'institution_list', 'total_authors'
]

missing = [c for c in required_cols if c not in df.columns]

if missing:
    logging.error(f"❌ Missing required columns: {missing}")
    sys.exit(1)

df = df[required_cols]

df['doi'] = df['doi'].astype(str).str.strip()

# ============================
# DB CONNECTION
# ============================

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="scopuss"
)

cursor = conn.cursor()

# ============================
# FETCH EXISTING DOIS
# ============================

cursor.execute("SELECT doi FROM papers")
valid_dois = set(str(r[0]).strip() for r in cursor.fetchall())

cursor.execute("SELECT doi FROM paper_insights")
already_inserted_dois = set(str(r[0]).strip() for r in cursor.fetchall())

# ============================
# INSERT QUERY
# ============================

insert_query = """
INSERT INTO paper_insights (
    doi, scopus_author_id_first, scopus_author_id_corresponding,
    sustainable_development_goals, qs_subject_code,
    qs_subject_field_name, asjc_code, asjc_field_name,
    no_of_countries, country_list,
    no_of_institutions, institution_list, total_authors
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

# ============================
# INSERT LOOP
# ============================

inserted_count = 0

for _, row in df.iterrows():

    doi = str(row["doi"]).strip()

    if doi in ("", "-"):
        continue

    if doi not in valid_dois:
        continue

    if doi in already_inserted_dois:
        continue

    try:
        cursor.execute(insert_query, tuple(row.fillna("").values))
        inserted_count += 1
        logging.info(f"✅ Inserted DOI: {doi}")

    except mysql.connector.IntegrityError as e:

        if e.errno == 1062:
            logging.warning(f"⚠️ Duplicate DOI skipped: {doi}")
        else:
            logging.error(f"❌ DB insert failed for {doi}: {e}")

# ============================
# FINISH
# ============================

conn.commit()
cursor.close()
conn.close()

logging.info(f"🎉 Done. Inserted {inserted_count} new entries.")
