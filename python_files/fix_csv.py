import csv
import pandas as pd

# Input file path (original downloaded from SCImago)
input_file = 'scimagojr2023.csv'

# Output file path (optional - cleaned version)
output_file = 'fixed_csv_2023.csv'

# Read the CSV with semicolon delimiter
df = pd.read_csv(input_file, delimiter=';')

# Show the first few rows to verify
print(df.head())

# Save cleaned version as a standard CSV (comma-separated)
df.to_csv(output_file, index=False)

print(f"\n✅ Cleaned CSV saved as: {output_file}")
