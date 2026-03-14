import os
import pandas as pd
import mysql.connector

# MySQL DB connection setup
conn = mysql.connector.connect(
    host='localhost',
    user='root',
    password='',  # change this to your actual password
    database='scopus',
    port=3307
)
cursor = conn.cursor()

# Step 1: Create table if not exists
cursor.execute("""
    CREATE TABLE IF NOT EXISTS scopus_chart_data (
        id INT AUTO_INCREMENT PRIMARY KEY,
        scopus_id BIGINT NOT NULL,
        year INT NOT NULL,
        documents INT DEFAULT 0,
        citations INT DEFAULT 0,
        UNIQUE KEY uq_scopus_year (scopus_id, year)
    )
""")
conn.commit()

# Step 2: Path to folder with CSV files
folder_path = r'/Users/piyushraj/Desktop/SCOPUS_SRM/backend/scopus_data'

# Step 3: Process each file and insert/update into the table
for file_name in os.listdir(folder_path):
    if file_name.endswith('_chart_data.csv'):
        scopus_id = file_name.split('_')[0]  # extract scopus_id from filename
        file_path = os.path.join(folder_path, file_name)
        
        df = pd.read_csv(file_path)

        if all(col in df.columns for col in ['Year', 'Documents', 'Citations']):
            for _, row in df.iterrows():
                year = int(row['Year'])
                documents = int(row['Documents'])
                citations = int(row['Citations'])

                cursor.execute("""
                    INSERT INTO scopus_chart_data (scopus_id, year, documents, citations)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        documents = VALUES(documents),
                        citations = VALUES(citations)
                """, (scopus_id, year, documents, citations))

# Step 4: Commit and close connection
conn.commit()
cursor.close()
conn.close()

print("✅ Scopus chart data imported/updated successfully.")
