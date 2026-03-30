"""
CRUD operations for ucm_devices table.
"""
from datetime import datetime
from typing import List, Dict, Optional
from .database import get_connection


def insert_ucm_device(
    device_name: str,
    model: Optional[str] = None,
    device_pool: Optional[str] = None,
    description: Optional[str] = None
) -> None:
    """
    Inserts or replaces a device record in the ucm_devices table.

    Args:
        device_name: Device name/identifier (primary key).
        model: Device model.
        device_pool: Device pool name.
        description: Device description.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO ucm_devices 
        (device_name, model, device_pool, description, updated_at)
        VALUES (?, ?, ?, ?, ?)
    """, (device_name, model, device_pool, description, datetime.now()))
    
    conn.commit()
    conn.close()


def get_ucm_device(device_name: str) -> Optional[Dict]:
    """
    Retrieves a single device record by device name.

    Args:
        device_name: Device name to lookup.

    Returns:
        Dictionary with device data, or None if not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT device_name, model, device_pool, description, updated_at
        FROM ucm_devices
        WHERE device_name = ?
    """, (device_name,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return None


def get_all_ucm_devices() -> List[Dict]:
    """
    Retrieves all device records from the ucm_devices table.

    Returns:
        List of dictionaries containing device data.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT device_name, model, device_pool, description, updated_at
        FROM ucm_devices
        ORDER BY device_name
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def search_ucm_devices(query: str, limit: int = 25) -> List[Dict]:
    """
    Searches devices by name and returns display info.

    Args:
        query: Search text (case-insensitive).
        limit: Max number of results.

    Returns:
        List of dictionaries with device_name, device_pool, description.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        like_query = f"%{query}%"
        cursor.execute(
            """
            SELECT device_name, device_pool, description
            FROM ucm_devices
            WHERE device_name LIKE ? OR description LIKE ?
            ORDER BY device_name
            LIMIT ?
            """,
            (like_query, like_query, limit)
        )
        return [
            {
                "device_name": row["device_name"],
                "device_pool": row["device_pool"],
                "description": row["description"],
            }
            for row in cursor.fetchall()
        ]
    finally:
        conn.close()


def update_ucm_device(
    device_name: str,
    model: Optional[str] = None,
    device_pool: Optional[str] = None,
    description: Optional[str] = None
) -> bool:
    """
    Updates an existing device record.

    Args:
        device_name: Device name to update.
        model: New device model (optional).
        device_pool: New device pool (optional).
        description: New description (optional).

    Returns:
        True if device was updated, False if device not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build dynamic update query
    updates = []
    params = []
    
    if model is not None:
        updates.append("model = ?")
        params.append(model)
    if device_pool is not None:
        updates.append("device_pool = ?")
        params.append(device_pool)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    
    if not updates:
        conn.close()
        return False
    
    updates.append("updated_at = ?")
    params.append(datetime.now())
    params.append(device_name)
    
    query = f"UPDATE ucm_devices SET {', '.join(updates)} WHERE device_name = ?"
    cursor.execute(query, params)
    
    updated = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return updated


def delete_ucm_device(device_name: str) -> bool:
    """
    Deletes a device record from the ucm_devices table.

    Args:
        device_name: Device name to delete.

    Returns:
        True if device was deleted, False if device not found.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM ucm_devices WHERE device_name = ?", (device_name,))
    
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return deleted
