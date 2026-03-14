import pandas as pd
import mysql.connector

# DB CONFIG
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'scopus'
}

# Load allowed Scopus IDs from database
def get_scopus_ids_from_db():
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT scopus_id FROM users")
    ids = {str(row[0]).strip() for row in cursor.fetchall()}
    conn.close()
    return ids

# Filter Excel rows
def filter_excel_by_scopus_ids(excel_path, output_path):
    allowed_ids = get_scopus_ids_from_db()
    df = pd.read_excel(excel_path)

    def row_has_valid_id(cell):
        if pd.isna(cell):
            return False
        raw_ids = str(cell).replace("\r", "").replace("\n", "").split("|")
        cleaned_ids = [id.strip() for id in raw_ids if id.strip()]
        return any(id in allowed_ids for id in cleaned_ids)

    filtered_df = df[df['Scopus Author Ids'].apply(row_has_valid_id)]
    filtered_df.to_excel(output_path, index=False)
    print(f"✅ Filtered data saved to: {output_path}")

# Usage
filter_excel_by_scopus_ids('scival.xlsx', 'filtered_output.xlsx')
