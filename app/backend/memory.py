"""
Memory & Persistence Module
SQLite-based caching layer for storing secure solutions.
"""

import sqlite3
import hashlib
import os
from typing import Optional, Tuple


# Database file path
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "solutions.db")


def init_db():
    """
    Initialize the SQLite database and create the solutions table if it doesn't exist.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create solutions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS solutions (
                query_hash TEXT PRIMARY KEY,
                code TEXT NOT NULL,
                explanation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  Database initialization error: {e}")


def get_solution(query: str) -> Optional[Tuple[str, str]]:
    """
    Retrieve a cached solution for a given query.
    
    Args:
        query: The user's query string
        
    Returns:
        Tuple of (code, explanation) if found, else None
    """
    try:
        # Hash the query
        query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()
        
        # Look up in database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT code, explanation FROM solutions WHERE query_hash = ?
        """, (query_hash,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return (result[0], result[1] if result[1] else "")
        else:
            return None
            
    except Exception as e:
        print(f"⚠️  Database query error: {e}")
        return None


def save_solution(query: str, code: str, explanation: str = ""):
    """
    Save a secure solution to the database.
    
    Args:
        query: The user's query string
        code: The Terraform code (or solution code)
        explanation: Optional explanation or validation notes
    """
    try:
        # Hash the query
        query_hash = hashlib.sha256(query.encode('utf-8')).hexdigest()
        
        # Insert or replace in database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO solutions (query_hash, code, explanation)
            VALUES (?, ?, ?)
        """, (query_hash, code, explanation))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️  Database save error: {e}")
