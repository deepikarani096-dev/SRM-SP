import os
import pandas as pd
import mysql.connector

# MySQL DB connection setup
conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='',  # change this to your actual password
    database='scopus',
    port=3306
)
cursor = conn.cursor()

# Step 1: Add column citation_count if it doesn't exist
try:
    cursor.execute("""
        ALTER TABLE users
        ADD COLUMN citation_count INT DEFAULT 0
    """)
    conn.commit()
except mysql.connector.errors.ProgrammingError:
    pass  # Column probably already exists

# Step 2: Path to folder with CSV files
folder_path = r'backend\scopus_data'

# Step 3: Process each file and update citations
for file_name in os.listdir(folder_path):
    if file_name.endswith('_chart_data.csv'):
        scopus_id = file_name.split('_')[0]

        file_path = os.path.join(folder_path, file_name)
        df = pd.read_csv(file_path)

        if 'Citations' in df.columns:
            total_citations = int(df['Citations'].sum())

            cursor.execute(
                "UPDATE users SET citation_count = %s WHERE scopus_id = %s",
                (total_citations, scopus_id)
            )

# Step 4: Commit and close connection
conn.commit()
cursor.close()
conn.close()

print("Citation counts updated successfully.")
