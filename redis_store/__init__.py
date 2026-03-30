"""
Redis operations for CUCM device IP address storage.
"""
from .device_ips import (
    store_device_ips_redis,
    get_device_ips_redis,
    delete_device_ips_redis,
    get_all_device_keys_redis
)

__all__ = [
    'store_device_ips_redis',
    'get_device_ips_redis',
    'delete_device_ips_redis',
    'get_all_device_keys_redis',
]
