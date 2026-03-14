#!/usr/bin/env python3
import mysql.connector
from mysql.connector import Error
import sys
import json

def setup_pending_authors_table():
    """Create pending_faculty_approvals table if it doesn't exist"""
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="scopuss",
            port=3307
        )
        cursor = conn.cursor()
        
        # Create pending_faculty_approvals table
        create_table_query = """
        CREATE TABLE IF NOT EXISTS pending_faculty_approvals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(100) NOT NULL UNIQUE,
            faculty_name VARCHAR(150) NOT NULL,
            scopus_id VARCHAR(20) NOT NULL UNIQUE,
            faculty_id VARCHAR(10) NOT NULL UNIQUE,
            designation VARCHAR(100),
            mobile_no VARCHAR(10),
            doj DATE,
            status ENUM('pending', 'approved', 'rejected') DEFAULT 'pending',
            rejection_reason VARCHAR(500),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP NULL,
            reviewed_by VARCHAR(100),
            INDEX idx_status (status),
            INDEX idx_created_at (created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """
        
        cursor.execute(create_table_query)
        conn.commit()
        
        print(json.dumps({
            "status": "SUCCESS",
            "message": "pending_faculty_approvals table created successfully"
        }))
        
        cursor.close()
        conn.close()
        
    except Error as e:
        print(json.dumps({
            "status": "ERROR",
            "message": str(e)
        }), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    setup_pending_authors_table()

