# db.py
# Production-ready MySQL database layer with connection pooling
# Built by Aiclex Technologies

import streamlit as st
import mysql.connector
from mysql.connector import Error, pooling
from mysql.connector.pooling import MySQLConnectionPool
from contextlib import contextmanager
import time
import traceback

# Initialize connection pool (singleton pattern)
_pool = None

def get_pool():
    """Get or create MySQL connection pool (singleton)"""
    global _pool
    if _pool is None:
        try:
            config = {
                'host': st.secrets["mysql"]["host"],
                'port': st.secrets["mysql"]["port"],
                'user': st.secrets["mysql"]["user"],
                'password': st.secrets["mysql"]["password"],
                'database': st.secrets["mysql"]["database"],
                'charset': 'utf8mb4',
                'collation': 'utf8mb4_unicode_ci',
                'autocommit': False,
                'pool_name': st.secrets["mysql"].get("pool_name", "invoice_pool"),
                'pool_size': int(st.secrets["mysql"].get("pool_size", 5)),
                'pool_reset_session': st.secrets["mysql"].get("pool_reset_session", True),
            }
            _pool = MySQLConnectionPool(**config)
        except KeyError as e:
            st.error(f"Missing MySQL configuration in secrets: {e}")
            raise
        except Error as e:
            st.error(f"Error creating connection pool: {e}")
            raise
    return _pool

def get_connection():
    """
    Get a connection from the pool with auto-reconnect logic.
    Returns a connection object or None on failure.
    """
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            pool = get_pool()
            conn = pool.get_connection()
            
            # Test connection
            if not conn.is_connected():
                conn.reconnect(attempts=3, delay=1)
            
            return conn
        except Error as e:
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                # Reset pool on error
                global _pool
                _pool = None
            else:
                st.error(f"Failed to get database connection after {max_retries} attempts: {e}")
                return None
        except Exception as e:
            st.error(f"Unexpected error getting connection: {e}")
            return None
    
    return None

@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    Ensures connection is properly closed even on errors.
    
    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients")
            results = cursor.fetchall()
    """
    conn = None
    try:
        conn = get_connection()
        if conn is None:
            raise Exception("Failed to get database connection")
        yield conn
    except Error as e:
        if conn and conn.is_connected():
            conn.rollback()
        st.error(f"Database error: {e}")
        raise
    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
        st.error(f"Unexpected error: {e}")
        raise
    finally:
        if conn and conn.is_connected():
            conn.close()

def execute_query(query, params=None, commit=False):
    """
    Execute a query (INSERT, UPDATE, DELETE) and optionally commit.
    
    Args:
        query: SQL query string
        params: Tuple or list of parameters
        commit: Whether to commit the transaction
    
    Returns:
        cursor.lastrowid for INSERT, or number of affected rows
    """
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            result = cursor.lastrowid if cursor.lastrowid else cursor.rowcount
            if commit:
                conn.commit()
            cursor.close()
            return result
        except Error as e:
            conn.rollback()
            st.error(f"Query execution error: {e}")
            raise
        except Exception as e:
            conn.rollback()
            st.error(f"Unexpected error executing query: {e}")
            raise

def fetch_all(query, params=None):
    """
    Execute a SELECT query and return all results.
    Always fetches fresh data (no caching).
    
    Args:
        query: SQL query string
        params: Tuple or list of parameters
    
    Returns:
        List of tuples (rows)
    """
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            results = cursor.fetchall()
            cursor.close()
            return results
        except Error as e:
            st.error(f"Fetch error: {e}")
            return []
        except Exception as e:
            st.error(f"Unexpected error fetching data: {e}")
            return []

def fetch_one(query, params=None):
    """
    Execute a SELECT query and return first result.
    Always fetches fresh data (no caching).
    
    Args:
        query: SQL query string
        params: Tuple or list of parameters
    
    Returns:
        Single tuple (row) or None
    """
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            result = cursor.fetchone()
            cursor.close()
            return result
        except Error as e:
            st.error(f"Fetch error: {e}")
            return None
        except Exception as e:
            st.error(f"Unexpected error fetching data: {e}")
            return None

def safe_commit(conn):
    """
    Safely commit a transaction with error handling.
    
    Args:
        conn: Database connection object
    """
    try:
        if conn and conn.is_connected():
            conn.commit()
    except Error as e:
        conn.rollback()
        st.error(f"Commit error: {e}")
        raise
    except Exception as e:
        conn.rollback()
        st.error(f"Unexpected commit error: {e}")
        raise

# Database initialization and migration functions
def init_db():
    """Initialize database tables if they don't exist"""
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            
            # Create clients table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    name VARCHAR(255) NOT NULL,
                    gstin VARCHAR(15) UNIQUE,
                    pan VARCHAR(10),
                    address TEXT,
                    email VARCHAR(255),
                    purchase_order VARCHAR(255),
                    state_code VARCHAR(10),
                    graduate_qty VARCHAR(50),
                    graduate_rate VARCHAR(50),
                    undergraduate_qty VARCHAR(50),
                    undergraduate_rate VARCHAR(50),
                    candidates_qty VARCHAR(50),
                    candidates_rate VARCHAR(50),
                    exam_fee_qty VARCHAR(50),
                    exam_fee_rate VARCHAR(50),
                    handbooks_qty VARCHAR(50),
                    handbooks_rate VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_gstin (gstin),
                    INDEX idx_name (name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            # Create invoices table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS invoices (
                    id INT PRIMARY KEY AUTO_INCREMENT,
                    invoice_no VARCHAR(255) NOT NULL,
                    invoice_date DATE NOT NULL,
                    client_id INT,
                    subtotal DECIMAL(10,2) DEFAULT 0.00,
                    sgst DECIMAL(10,2) DEFAULT 0.00,
                    cgst DECIMAL(10,2) DEFAULT 0.00,
                    igst DECIMAL(10,2) DEFAULT 0.00,
                    total DECIMAL(10,2) DEFAULT 0.00,
                    pdf_path TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
                    INDEX idx_invoice_no (invoice_no),
                    INDEX idx_invoice_date (invoice_date),
                    INDEX idx_client_id (client_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            
            conn.commit()
            cursor.close()
        except Error as e:
            conn.rollback()
            st.error(f"Database initialization error: {e}")
            raise

def migrate_db_add_columns():
    """Migrate database schema - add columns if they don't exist"""
    with get_db_connection() as conn:
        try:
            cursor = conn.cursor()
            
            # Get existing columns
            cursor.execute("SHOW COLUMNS FROM clients")
            existing_cols = [row[0] for row in cursor.fetchall()]
            
            # Add missing columns
            columns_to_add = {
                'purchase_order': 'VARCHAR(255)',
                'state_code': 'VARCHAR(10)',
                'graduate_qty': 'VARCHAR(50)',
                'graduate_rate': 'VARCHAR(50)',
                'undergraduate_qty': 'VARCHAR(50)',
                'undergraduate_rate': 'VARCHAR(50)',
                'candidates_qty': 'VARCHAR(50)',
                'candidates_rate': 'VARCHAR(50)',
                'exam_fee_qty': 'VARCHAR(50)',
                'exam_fee_rate': 'VARCHAR(50)',
                'handbooks_qty': 'VARCHAR(50)',
                'handbooks_rate': 'VARCHAR(50)'
            }
            
            for col_name, col_type in columns_to_add.items():
                if col_name not in existing_cols:
                    try:
                        cursor.execute(f"ALTER TABLE clients ADD COLUMN {col_name} {col_type}")
                        conn.commit()
                    except Error:
                        pass  # Column might already exist
            
            cursor.close()
        except Error as e:
            st.error(f"Migration error: {e}")

