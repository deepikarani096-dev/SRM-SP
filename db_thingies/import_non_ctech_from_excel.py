#!/usr/bin/env python3
"""
Import non-CTECH faculty rows from the Excel responses file into the `users` table.

Usage: python import_non_ctech_from_excel.py

This script will:
- detect relevant columns from the Excel file
- skip rows whose department appears to be CTECH (case-insenstive match)
- insert new rows into `users` only if the Scopus ID does not already exist
- print a per-department and total summary of newly inserted records
"""
import os
import sys
from collections import defaultdict
from datetime import datetime

import pandas as pd
import mysql.connector


BASE_DIR = os.path.dirname(__file__)
EXCEL_FILENAME = "Faculty Scopus ID Collection Form (Responses).xlsx"
EXCEL_PATH = os.path.join(BASE_DIR, EXCEL_FILENAME)

# DB config (consistent with other scripts in this folder)
DB_CONFIG_TRIES = [
    {"host": "localhost", "user": "root", "password": "", "database": "scopuss", "port": 3307},
    {"host": "localhost", "user": "root", "password": "", "database": "scopuss"},
]

DEFAULT_ACCESS_LEVEL = 3


def clean_scopus_id(value):
    if pd.isna(value):
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def find_column(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    # case-insensitive fallback
    lower_map = {col.lower(): col for col in df.columns}
    for c in candidates:
        low = c.lower()
        if low in lower_map:
            return lower_map[low]
    return None


def connect_db():
    last_err = None
    for cfg in DB_CONFIG_TRIES:
        try:
            conn = mysql.connector.connect(**cfg)
            return conn
        except Exception as e:
            last_err = e
    print("ERROR: Unable to connect to database:", str(last_err), file=sys.stderr)
    sys.exit(1)


def main():
    if not os.path.exists(EXCEL_PATH):
        print(f"ERROR: Excel file not found at: {EXCEL_PATH}", file=sys.stderr)
        sys.exit(1)

    df = pd.read_excel(EXCEL_PATH)

    # discover columns
    faculty_name_col = find_column(df, ["Faculty Name", "Name", "Full Name", "faculty_name", "name"])
    faculty_id_col = find_column(df, ["Faculty ID", "FacultyID", "faculty_id", "faculty id"])
    scopus_col = find_column(df, ["Scopus ID", "ScopusID", "scopus_id", "Scopus id"])
    extra_scopus_col = find_column(df, ["Additional Scopus Id", "Additional Scopus IDs", "Additional Scopus Ids", "Additional Scopus ID"])
    dept_col = find_column(df, ["Department", "department", "Dept", "dept"])
    designation_col = find_column(df, ["Designation", "designation", "Position"])
    email_col = find_column(df, ["Email ID", "Email", "Email Address", "email"])
    mobile_col = find_column(df, ["Mobile No", "Mobile", "Mobile Number", "mobile_no"])
    doj_col = find_column(df, ["DOJ", "Date of Joining", "doj", "Joining Date"])

    conn = connect_db()
    cursor = conn.cursor()

    # check whether users table has `department` column
    cursor.execute("SHOW COLUMNS FROM users LIKE 'department'")
    has_department = cursor.fetchone() is not None

    if has_department:
        insert_columns = "faculty_id, faculty_name, designation, mobile_no, email, doj, scopus_id, access_level, docs_count, citations, h_index, department"
        insert_placeholders = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s"
    else:
        insert_columns = "faculty_id, faculty_name, designation, mobile_no, email, doj, scopus_id, access_level, docs_count, citations, h_index"
        insert_placeholders = "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s"

    insert_query = f"INSERT IGNORE INTO users ({insert_columns}) VALUES ({insert_placeholders})"

    dept_counts = defaultdict(int)
    total_inserted = 0

    for _, row in df.iterrows():
        dept = str(row[dept_col]).strip() if (dept_col and pd.notna(row[dept_col])) else None
        # skip CTECH rows
        if dept and "ctech" in dept.lower():
            continue

        faculty_id = str(row[faculty_id_col]).strip() if (faculty_id_col and pd.notna(row[faculty_id_col])) else None
        faculty_name = row[faculty_name_col] if faculty_name_col else None
        designation = row[designation_col] if designation_col and pd.notna(row[designation_col]) else None
        mobile = str(row[mobile_col]).strip() if (mobile_col and pd.notna(row[mobile_col])) else None
        email = row[email_col] if email_col and pd.notna(row[email_col]) else None

        doj = None
        if doj_col and pd.notna(row[doj_col]):
            try:
                d = pd.to_datetime(row[doj_col], errors="coerce")
                doj = d.date() if pd.notna(d) else None
            except Exception:
                doj = None

        # gather scopus ids
        scopus_ids = []
        if scopus_col and pd.notna(row[scopus_col]):
            sid = clean_scopus_id(row[scopus_col])
            if sid:
                scopus_ids.append(sid)

        if extra_scopus_col and pd.notna(row[extra_scopus_col]):
            raw = str(row[extra_scopus_col])
            for part in [p.strip() for p in raw.replace(';', ',').split(',') if p.strip()]:
                sid = clean_scopus_id(part)
                if sid:
                    scopus_ids.append(sid)

        # if no scopus ids, skip
        if not scopus_ids:
            continue

        for sid in scopus_ids:
            # check exists
            try:
                cursor.execute("SELECT scopus_id FROM users WHERE scopus_id = %s", (sid,))
                if cursor.fetchone():
                    continue

                params = [faculty_id, faculty_name, designation, mobile, email, doj, sid, DEFAULT_ACCESS_LEVEL, 0, 0, 0]
                if has_department:
                    params.append(dept or "Unknown")

                cursor.execute(insert_query, tuple(params))
                if cursor.rowcount and cursor.rowcount > 0:
                    dept_key = dept or "Unknown"
                    dept_counts[dept_key] += 1
                    total_inserted += cursor.rowcount
            except Exception as e:
                print(f"ERROR inserting scopus_id={sid}: {e}", file=sys.stderr)

    conn.commit()
    cursor.close()
    conn.close()

    # print summary
    print("Import summary:")
    for d, cnt in sorted(dept_counts.items()):
        print(f"- {d}: {cnt}")
    print(f"Total new faculties inserted: {total_inserted}")


if __name__ == '__main__':
    main()
