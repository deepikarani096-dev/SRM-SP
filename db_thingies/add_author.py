#!/usr/bin/env python3
import sys
import json
import mysql.connector
from mysql.connector import Error
from datetime import datetime

def connect_to_database():
    """Connect to database using same config as scopus_sync.py"""
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="scopuss",
            port=3307
        )
        return conn
    except mysql.connector.Error as err:
        error_msg = {
            "error": "database_connection_failed",
            "message": str(err),
            "details": f"MySQL Error: {err}"
        }
        print(json.dumps(error_msg), file=sys.stderr, flush=True)
        sys.exit(1)

def add_author_to_database(name, scopus_id, faculty_id, email, designation, mobile_no, doj):
    """
    Add a new author to the users table
    Table structure from users.py:
    - faculty_id
    - faculty_name
    - designation
    - mobile_no
    - email
    - doj
    - scopus_id (unique)
    - access_level
    - docs_count
    - citations
    - h_index
    """
    connection = None
    cursor = None
    
    try:
        connection = connect_to_database()
        cursor = connection.cursor()
        
        # Check if author already exists by scopus_id
        check_query = "SELECT scopus_id, faculty_name, faculty_id FROM users WHERE scopus_id = %s"
        cursor.execute(check_query, (scopus_id,))
        existing = cursor.fetchone()
        
        if existing:
            error_msg = {
                "error": "already exists",
                "message": f"Author with Scopus ID {scopus_id} already exists",
                "existing_scopus_id": existing[0],
                "existing_name": existing[1],
                "existing_faculty_id": existing[2]
            }
            print(json.dumps(error_msg), file=sys.stderr, flush=True)
            sys.exit(1)
        
        # Check if faculty_id already exists
        check_faculty_query = "SELECT scopus_id, faculty_name FROM users WHERE faculty_id = %s"
        cursor.execute(check_faculty_query, (faculty_id,))
        existing_faculty = cursor.fetchone()
        
        if existing_faculty:
            error_msg = {
                "error": "faculty_id exists",
                "message": f"Faculty ID {faculty_id} is already assigned to another author",
                "existing_scopus_id": existing_faculty[0],
                "existing_name": existing_faculty[1]
            }
            print(json.dumps(error_msg), file=sys.stderr, flush=True)
            sys.exit(1)
        
        # Insert new author
        insert_query = """
            INSERT INTO users (faculty_id, faculty_name, designation, mobile_no, email, doj, scopus_id, access_level, docs_count) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (faculty_id, name, designation or None, mobile_no or None, email or None, doj or None, scopus_id, 2, 0))
        connection.commit()
        
        # Return success response
        result = {
            "success": True,
            "scopus_id": scopus_id,
            "faculty_name": name,
            "faculty_id": faculty_id,
            "email": email,
            "designation": designation,
            "mobile_no": mobile_no,
            "doj": doj,
            "access_level": 3,
            "docs_count": 0,
            "message": f"Author '{name}' added successfully with Scopus ID {scopus_id} and Faculty ID {faculty_id}"
        }
        
        print(json.dumps(result, ensure_ascii=False), flush=True)
        sys.exit(0)
        
    except Error as e:
        error_response = {
            "error": "database_error",
            "message": str(e),
            "error_code": e.errno if hasattr(e, 'errno') else None,
            "sql_state": e.sqlstate if hasattr(e, 'sqlstate') else None
        }
        print(json.dumps(error_response), file=sys.stderr, flush=True)
        sys.exit(1)
        
    except Exception as e:
        error_response = {
            "error": "unexpected_error",
            "message": str(e),
            "type": type(e).__name__
        }
        print(json.dumps(error_response), file=sys.stderr, flush=True)
        sys.exit(1)
        
    finally:
        if cursor:
            cursor.close()
        if connection and connection.is_connected():
            connection.close()

if __name__ == "__main__":
    # Check command line arguments
    if len(sys.argv) != 8:
        error = {
            "error": "invalid_arguments",
            "message": "Usage: python add_author.py <name> <scopus_id> <faculty_id> <email> <designation> <mobile_no> <doj>",
            "received_args": sys.argv[1:] if len(sys.argv) > 1 else []
        }
        print(json.dumps(error), file=sys.stderr, flush=True)
        sys.exit(1)
    
    name = sys.argv[1]
    scopus_id = sys.argv[2]
    faculty_id = sys.argv[3]
    email = sys.argv[4]
    designation = sys.argv[5]
    mobile_no = sys.argv[6]
    doj = sys.argv[7]
    
    # Validate inputs
    if not name or not name.strip():
        error = {
            "error": "invalid_name",
            "message": "Author name cannot be empty"
        }
        print(json.dumps(error), file=sys.stderr, flush=True)
        sys.exit(1)
    
    if not scopus_id or not scopus_id.strip():
        error = {
            "error": "invalid_scopus_id",
            "message": "Scopus ID cannot be empty"
        }
        print(json.dumps(error), file=sys.stderr, flush=True)
        sys.exit(1)
    
    if not scopus_id.strip().isdigit():
        error = {
            "error": "invalid_scopus_id_format",
            "message": "Scopus ID must contain only numbers",
            "received": scopus_id
        }
        print(json.dumps(error), file=sys.stderr, flush=True)
        sys.exit(1)
    
    if not faculty_id or not faculty_id.strip():
        error = {
            "error": "invalid_faculty_id",
            "message": "Faculty ID cannot be empty"
        }
        print(json.dumps(error), file=sys.stderr, flush=True)
        sys.exit(1)
    
    if email and email.strip() and not email.strip().endswith("@srmist.edu.in"):
        error = {
            "error": "invalid_email",
            "message": "Email must end with @srmist.edu.in",
            "received": email
        }
        print(json.dumps(error), file=sys.stderr, flush=True)
        sys.exit(1)
    
    if mobile_no and mobile_no.strip() and not mobile_no.strip().isdigit() or (mobile_no.strip() and len(mobile_no.strip()) != 10):
        error = {
            "error": "invalid_mobile_no",
            "message": "Mobile number must be exactly 10 digits",
            "received": mobile_no
        }
        print(json.dumps(error), file=sys.stderr, flush=True)
        sys.exit(1)
    
    # Add author to database
    add_author_to_database(name.strip(), scopus_id.strip(), faculty_id.strip(), email.strip() if email else None, designation.strip() if designation else None, mobile_no.strip() if mobile_no else None, doj.strip() if doj else None)