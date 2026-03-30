"""
SQLite operations for phone groups and group members.
"""
from typing import List, Dict, Optional
from datetime import datetime
from .database import get_connection


def create_phone_group(
    name: str,
    description: Optional[str],
    extension: Optional[str],
    device_names: List[str]
) -> int:
    """
    Creates a phone group and associates devices with it.

    Returns:
        The created group ID.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO phone_groups (name, description, extension, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name, description, extension, datetime.now())
        )
        group_id = cursor.lastrowid

        if device_names:
            cursor.executemany(
                """
                INSERT OR IGNORE INTO phone_group_devices (group_id, device_name, added_at)
                VALUES (?, ?, ?)
                """,
                [(group_id, device_name, datetime.now()) for device_name in device_names]
            )

        conn.commit()
        return int(group_id)
    finally:
        conn.close()


def get_phone_group(group_id: int) -> Optional[Dict]:
    """
    Retrieves a phone group and its devices.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, name, description, extension, created_at
            FROM phone_groups
            WHERE id = ?
            """,
            (group_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute(
            """
            SELECT device_name
            FROM phone_group_devices
            WHERE group_id = ?
            ORDER BY device_name
            """,
            (group_id,)
        )
        devices = [r["device_name"] for r in cursor.fetchall()]
        result = dict(row)
        result["devices"] = devices
        return result
    finally:
        conn.close()


def get_group_by_extension(extension: str) -> Optional[Dict]:
    """
    Retrieves a phone group by extension and its devices.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT id, name, description, extension, created_at
            FROM phone_groups
            WHERE extension = ?
            """,
            (extension,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        cursor.execute(
            """
            SELECT device_name
            FROM phone_group_devices
            WHERE group_id = ?
            ORDER BY device_name
            """,
            (row["id"],)
        )
        devices = [r["device_name"] for r in cursor.fetchall()]
        result = dict(row)
        result["devices"] = devices
        return result
    finally:
        conn.close()


def list_phone_groups() -> List[Dict]:
    """
    Lists all phone groups with device counts.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT g.id, g.name, g.description, g.extension, g.created_at,
                   COUNT(d.device_name) AS device_count
            FROM phone_groups g
            LEFT JOIN phone_group_devices d ON d.group_id = g.id
            GROUP BY g.id
            ORDER BY g.name
            """
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def update_phone_group(
    group_id: int,
    name: str,
    description: Optional[str],
    extension: Optional[str],
    device_names: List[str]
) -> bool:
    """
    Updates a phone group and replaces its device list.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE phone_groups
            SET name = ?, description = ?, extension = ?
            WHERE id = ?
            """,
            (name, description, extension, group_id)
        )
        if cursor.rowcount == 0:
            conn.commit()
            return False

        cursor.execute(
            """
            DELETE FROM phone_group_devices
            WHERE group_id = ?
            """,
            (group_id,)
        )

        if device_names:
            cursor.executemany(
                """
                INSERT OR IGNORE INTO phone_group_devices (group_id, device_name, added_at)
                VALUES (?, ?, ?)
                """,
                [(group_id, device_name, datetime.now()) for device_name in device_names]
            )

        conn.commit()
        return True
    finally:
        conn.close()
