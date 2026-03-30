"""
SQLite database connection and initialization.
"""
import sqlite3
import os
from pathlib import Path
from typing import Optional

# Database file path - store in data directory
DATA_DIR = Path(os.getcwd()) / 'data'
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / 'ucm_devices.db'


def get_connection() -> sqlite3.Connection:
    """
    Returns a SQLite connection to the database.
    
    Returns:
        SQLite connection object with row_factory set to Row.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Access rows like dicts
    return conn


def initialize_database() -> None:
    """
    Creates the ucm_devices table if it doesn't exist.
    
    Table schema:
        - device_name (TEXT PRIMARY KEY): Device name/identifier
        - model (TEXT): Device model
        - device_pool (TEXT): Device pool name
        - description (TEXT): Device description
        - updated_at (TIMESTAMP): Last update timestamp
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ucm_devices (
            device_name TEXT PRIMARY KEY,
            model TEXT,
            device_pool TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS phone_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            extension TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS phone_group_devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            device_name TEXT NOT NULL,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_id, device_name),
            FOREIGN KEY(group_id) REFERENCES phone_groups(id)
        )
    """)
    
    # Create index on device_pool for faster queries
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_device_pool 
        ON ucm_devices(device_pool)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_phone_group_name
        ON phone_groups(name)
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_phone_group_devices_group
        ON phone_group_devices(group_id)
    """)
    
    conn.commit()
    conn.close()
