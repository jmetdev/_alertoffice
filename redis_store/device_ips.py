"""
Redis CRUD operations for CUCM device IP addresses.
"""
import redis
from typing import List, Dict, Optional


def _get_redis_client(
    redis_host: str = 'localhost',
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: Optional[str] = None
) -> redis.Redis:
    """
    Create and return a Redis client with connection test.
    
    Args:
        redis_host: Redis server hostname (default: 'localhost').
        redis_port: Redis server port (default: 6379).
        redis_db: Redis database number (default: 0).
        redis_password: Redis password if required (default: None).
        
    Returns:
        Redis client instance.
        
    Raises:
        ConnectionError: If connection to Redis fails.
    """
    try:
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=5
        )
        # Test connection
        r.ping()
        return r
    except redis.ConnectionError as e:
        raise ConnectionError(f"Failed to connect to Redis at {redis_host}:{redis_port} - {e}")
    except Exception as e:
        raise ConnectionError(f"Failed to connect to Redis at {redis_host}:{redis_port} - {type(e).__name__}: {e}")


def store_device_ips_redis(
    device_ips: Dict[str, Optional[str]],
    redis_host: str = 'localhost',
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: Optional[str] = None,
    key_prefix: str = 'cucm:device:',
    ttl_seconds: int = 86400
) -> int:
    """
    Stores device name:IP address pairs in Redis.

    Args:
        device_ips: Dictionary mapping device names to IP addresses.
        redis_host: Redis server hostname (default: 'localhost').
        redis_port: Redis server port (default: 6379).
        redis_db: Redis database number (default: 0).
        redis_password: Redis password if required (default: None).
        key_prefix: Prefix for Redis keys (default: 'cucm:device:').
        ttl_seconds: Expiry in seconds (default: 86400 = 24 hours).

    Returns:
        Number of devices successfully stored (excluding None values).

    Example:
        >>> device_ips = {'SEP001122334455': '192.168.1.100', 'SEP005566778899': '192.168.1.101'}
        >>> stored_count = store_device_ips_redis(device_ips, redis_host='localhost')
        >>> print(f"Stored {stored_count} devices")
    """
    r = _get_redis_client(redis_host, redis_port, redis_db, redis_password)

    stored_count = 0
    for device_name, ip_address in device_ips.items():
        if ip_address is not None:
            redis_key = f"{key_prefix}{device_name}"
            r.set(redis_key, ip_address, ex=ttl_seconds)
            stored_count += 1

    return stored_count


def get_device_ips_redis(
    device_names: List[str],
    redis_host: str = 'localhost',
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: Optional[str] = None,
    key_prefix: str = 'cucm:device:'
) -> Dict[str, Optional[str]]:
    """
    Retrieves device IP addresses from Redis.

    Args:
        device_names: List of device names to retrieve.
        redis_host: Redis server hostname (default: 'localhost').
        redis_port: Redis server port (default: 6379).
        redis_db: Redis database number (default: 0).
        redis_password: Redis password if required (default: None).
        key_prefix: Prefix for Redis keys (default: 'cucm:device:').

    Returns:
        Dictionary mapping device names to IP addresses (None if not found).

    Example:
        >>> device_names = ['SEP001122334455', 'SEP005566778899']
        >>> device_ips = get_device_ips_redis(device_names, redis_host='localhost')
    """
    r = _get_redis_client(redis_host, redis_port, redis_db, redis_password)

    device_ips = {}
    for device_name in device_names:
        redis_key = f"{key_prefix}{device_name}"
        ip_address = r.get(redis_key)
        device_ips[device_name] = ip_address

    return device_ips


def delete_device_ips_redis(
    device_names: List[str],
    redis_host: str = 'localhost',
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: Optional[str] = None,
    key_prefix: str = 'cucm:device:'
) -> int:
    """
    Deletes device IP addresses from Redis.

    Args:
        device_names: List of device names to delete.
        redis_host: Redis server hostname (default: 'localhost').
        redis_port: Redis server port (default: 6379).
        redis_db: Redis database number (default: 0).
        redis_password: Redis password if required (default: None).
        key_prefix: Prefix for Redis keys (default: 'cucm:device:').

    Returns:
        Number of devices successfully deleted.

    Example:
        >>> device_names = ['SEP001122334455', 'SEP005566778899']
        >>> deleted_count = delete_device_ips_redis(device_names)
    """
    r = _get_redis_client(redis_host, redis_port, redis_db, redis_password)

    deleted_count = 0
    for device_name in device_names:
        redis_key = f"{key_prefix}{device_name}"
        if r.delete(redis_key):
            deleted_count += 1

    return deleted_count


def get_all_device_keys_redis(
    redis_host: str = 'localhost',
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: Optional[str] = None,
    key_prefix: str = 'cucm:device:'
) -> List[str]:
    """
    Retrieves all device keys from Redis matching the prefix.

    Args:
        redis_host: Redis server hostname (default: 'localhost').
        redis_port: Redis server port (default: 6379).
        redis_db: Redis database number (default: 0).
        redis_password: Redis password if required (default: None).
        key_prefix: Prefix for Redis keys (default: 'cucm:device:').

    Returns:
        List of device keys (full keys with prefix).

    Example:
        >>> keys = get_all_device_keys_redis()
        >>> print(f"Found {len(keys)} devices in Redis")
    """
    r = _get_redis_client(redis_host, redis_port, redis_db, redis_password)

    pattern = f"{key_prefix}*"
    keys = r.keys(pattern)
    return keys
