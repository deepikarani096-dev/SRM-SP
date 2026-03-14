import mysql.connector

# DB config — update these!
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'scopus'
}

# Table/column config
table_name = 'paper_insights'
column_name = 'country_list'  # Column with country names separated by '|'

# Connect to DB
conn = mysql.connector.connect(**db_config)
cursor = conn.cursor()

# Fetch country strings
query = f"SELECT {column_name} FROM {table_name} WHERE {column_name} IS NOT NULL"
cursor.execute(query)
rows = cursor.fetchall()

unique_countries = set()

for row in rows:
    country_str = row[0]
    countries = [c.strip() for c in country_str.split('|')]
    unique_countries.update(countries)

# Print sorted unique countries
print("Unique Countries:\n")
for country in sorted(unique_countries):
    print(country)

# Cleanup
cursor.close()
conn.close()
