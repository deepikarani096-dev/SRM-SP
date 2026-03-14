import pandas as pd
import mysql.connector

# ====== DB CONFIG ======
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="scopuss"
)

cursor = conn.cursor()

# ====== CREATE TABLE ======
create_table_query = """
CREATE TABLE IF NOT EXISTS paper_domain (
    doi VARCHAR(255) PRIMARY KEY,
    domain VARCHAR(255)
);
"""

cursor.execute(create_table_query)

# ====== READ EXCEL ======
file_path = "papers_classified.xlsx"   # change if needed
df = pd.read_excel(file_path)

# ====== INSERT DATA ======
insert_query = """
INSERT INTO paper_domain (doi, domain)
VALUES (%s, %s)
ON DUPLICATE KEY UPDATE domain = VALUES(domain);
"""

for _, row in df.iterrows():
    doi = row["DOI"]
    domain = row["VERTICAL"]

    if pd.notna(doi) and pd.notna(domain):
        cursor.execute(insert_query, (doi, domain))

conn.commit()

cursor.close()
conn.close()

print("paper_domain table created and data inserted.")