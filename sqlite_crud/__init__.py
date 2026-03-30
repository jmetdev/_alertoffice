"""
SQLite database operations for CUCM device storage.
"""
from .database import get_connection, initialize_database
from .ucm_devices import (
    insert_ucm_device,
    get_ucm_device,
    get_all_ucm_devices,
    update_ucm_device,
    delete_ucm_device,
    search_ucm_devices
)
from .groups import (
    create_phone_group,
    get_phone_group,
    list_phone_groups
)

__all__ = [
    'get_connection',
    'initialize_database',
    'insert_ucm_device',
    'get_ucm_device',
    'get_all_ucm_devices',
    'update_ucm_device',
    'delete_ucm_device',
    'search_ucm_devices',
    'create_phone_group',
    'get_phone_group',
    'list_phone_groups',
]
