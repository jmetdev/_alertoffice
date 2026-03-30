"""
Cisco Call Manager RIS SOAP API functions for device IP address lookups.
"""
import zeep
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep.transports import Transport
from typing import List, Dict, Optional
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _extract_ip_address(ip_address_obj) -> Optional[str]:
    """
    Helper function to extract IP address string from zeep complex type objects.
    
    The IP address object has structure: item[0]['IP']
    
    Args:
        ip_address_obj: The IP address object (could be ArrayOfIPAddressArrayType or similar)
        
    Returns:
        IP address as string, or None if extraction fails
    """
    if ip_address_obj is None:
        return None
    
    # Try accessing item attribute (common in zeep array types)
    # Structure: item[0]['IP'] or item[0].IP
    try:
        if hasattr(ip_address_obj, 'item'):
            items = ip_address_obj.item
            if items:
                # Handle list
                if isinstance(items, list) and len(items) > 0:
                    first_item = items[0]
                else:
                    first_item = items
                
                # Extract IP from the item (could be dict-like with 'IP' key or attribute)
                if hasattr(first_item, 'IP'):
                    return str(first_item.IP)
                elif isinstance(first_item, dict) and 'IP' in first_item:
                    return str(first_item['IP'])
                elif hasattr(first_item, '__getitem__'):
                    try:
                        return str(first_item['IP'])
                    except (KeyError, TypeError):
                        pass
    except Exception:
        pass
    
    # Try direct attribute access
    try:
        if hasattr(ip_address_obj, 'IP'):
            return str(ip_address_obj.IP)
    except Exception:
        pass
    
    # Try dictionary access
    try:
        if isinstance(ip_address_obj, dict) and 'IP' in ip_address_obj:
            return str(ip_address_obj['IP'])
    except Exception:
        pass
    
    # Try converting to string and checking if it's already an IP
    try:
        ip_str = str(ip_address_obj)
        # If it looks like an IP address, return it
        if ip_str and '.' in ip_str:
            ip_str = ip_str.strip()
            parts = ip_str.split('.')
            if len(parts) == 4 and all(p.isdigit() for p in parts):
                return ip_str
    except Exception:
        pass
    
    return None


def get_device_ip_addresses(
    cucm_host: str,
    username: str,
    password: str,
    device_names: List[str],
    verify_ssl: bool = False
) -> Dict[str, Optional[str]]:
    """
    Retrieves the IP addresses of specified devices from CUCM using the RIS SOAP API.

    Args:
        cucm_host: The hostname or IP address of the CUCM server.
        username: The username for CUCM authentication.
        password: The password for CUCM authentication.
        device_names: A list of device names to query (e.g., ['SEP001122334455', 'SEP005566778899']).
        verify_ssl: Whether to verify SSL certificates (default: False for self-signed certs).

    Returns:
        A dictionary mapping device names to their IP addresses.
        Devices not found will have None as their IP address value.

    Example:
        >>> device_names = ['SEP001122334455', 'SEP005566778899']
        >>> ip_addresses = get_device_ip_addresses(
        ...     'cucm.example.com', 'admin', 'password', device_names
        ... )
        >>> print(ip_addresses)
        {'SEP001122334455': '192.168.1.100', 'SEP005566778899': '192.168.1.101'}
    """
    wsdl_url = f'https://{cucm_host}:8443/realtimeservice2/services/RISService70?wsdl'

    # Create a Zeep client with authentication
    session = Session()
    session.verify = verify_ssl
    session.auth = HTTPBasicAuth(username, password)
    transport = Transport(session=session)
    
    try:
        client = zeep.Client(wsdl=wsdl_url, transport=transport)
    except Exception as e:
        raise ConnectionError(f"Failed to connect to CUCM RIS service: {e}")

    # Define the selection criteria
    selection_criteria = {
        'MaxReturnedDevices': 1000,
        'DeviceClass': 'Any',
        'Model': 255,  # Represents 'Any' model
        'Status': 'Any',
        'NodeName': '',
        'SelectBy': 'Name',
        'SelectItems': {'item': device_names},
        'Protocol': 'Any',
        'DownloadStatus': 'Any'
    }

    # Initialize result dictionary with None values
    ip_addresses = {device_name: None for device_name in device_names}

    # Perform the selectCmDevice request (note: lowercase 's')
    try:
        response = client.service.selectCmDevice(
            StateInfo='',
            CmSelectionCriteria=selection_criteria
        )
        
        # Extract device information from response
        if hasattr(response, 'SelectCmDeviceResult'):
            result = response.SelectCmDeviceResult
            if hasattr(result, 'CmNodes') and result.CmNodes:
                nodes = result.CmNodes.item if hasattr(result.CmNodes, 'item') else []
                if isinstance(nodes, list):
                    nodes = nodes
                else:
                    nodes = [nodes]
                
                for node in nodes:
                    if hasattr(node, 'CmDevices') and node.CmDevices:
                        devices = node.CmDevices.item if hasattr(node.CmDevices, 'item') else []
                        if isinstance(devices, list):
                            devices = devices
                        else:
                            devices = [devices]
                        
                        for device in devices:
                            if hasattr(device, 'Name') and hasattr(device, 'IPAddress'):
                                device_name = device.Name
                                ip_address_obj = device.IPAddress
                                ip_address = _extract_ip_address(ip_address_obj)
                                
                                if device_name in ip_addresses:
                                    ip_addresses[device_name] = ip_address

    except Exception as e:
        raise RuntimeError(f"Error querying RIS service: {e}")

    return ip_addresses


def get_device_ip_statuses(
    cucm_host: str,
    username: str,
    password: str,
    device_names: List[str],
    verify_ssl: bool = False
) -> Dict[str, Dict[str, Optional[str]]]:
    """
    Retrieves IP addresses and registration status for devices from CUCM RIS API.

    Returns:
        Dictionary mapping device name to {ip, status}.
    """
    wsdl_url = f'https://{cucm_host}:8443/realtimeservice2/services/RISService70?wsdl'

    session = Session()
    session.verify = verify_ssl
    session.auth = HTTPBasicAuth(username, password)
    transport = Transport(session=session)

    try:
        client = zeep.Client(wsdl=wsdl_url, transport=transport)
    except Exception as e:
        raise ConnectionError(f"Failed to connect to CUCM RIS service: {e}")

    selection_criteria = {
        'MaxReturnedDevices': 1000,
        'DeviceClass': 'Any',
        'Model': 255,
        'Status': 'Any',
        'NodeName': '',
        'SelectBy': 'Name',
        'SelectItems': {'item': device_names},
        'Protocol': 'Any',
        'DownloadStatus': 'Any'
    }

    device_info = {
        device_name: {"ip": None, "status": None} for device_name in device_names
    }

    try:
        response = client.service.selectCmDevice(
            StateInfo='',
            CmSelectionCriteria=selection_criteria
        )

        if hasattr(response, 'SelectCmDeviceResult'):
            result = response.SelectCmDeviceResult
            if hasattr(result, 'CmNodes') and result.CmNodes:
                nodes = result.CmNodes.item if hasattr(result.CmNodes, 'item') else []
                if not isinstance(nodes, list):
                    nodes = [nodes]

                for node in nodes:
                    if hasattr(node, 'CmDevices') and node.CmDevices:
                        devices = node.CmDevices.item if hasattr(node.CmDevices, 'item') else []
                        if not isinstance(devices, list):
                            devices = [devices]

                        for device in devices:
                            if hasattr(device, 'Name'):
                                device_name = device.Name
                                ip_address = None
                                status = None
                                if hasattr(device, 'IPAddress'):
                                    ip_address = _extract_ip_address(device.IPAddress)
                                if hasattr(device, 'Status'):
                                    status = str(device.Status)
                                if device_name in device_info:
                                    device_info[device_name] = {
                                        "ip": ip_address,
                                        "status": status
                                    }
    except Exception as e:
        raise RuntimeError(f"Error querying RIS service: {e}")

    return device_info


def get_and_store_device_ips(
    cucm_host: str,
    cucm_username: str,
    cucm_password: str,
    device_names: List[str],
    redis_host: str = 'localhost',
    redis_port: int = 6379,
    redis_db: int = 0,
    redis_password: Optional[str] = None,
    key_prefix: str = 'cucm:device:',
    verify_ssl: bool = False
) -> Dict[str, Optional[str]]:
    """
    Retrieves device IP addresses from CUCM and stores them in Redis.

    Args:
        cucm_host: The hostname or IP address of the CUCM server.
        cucm_username: The username for CUCM authentication.
        cucm_password: The password for CUCM authentication.
        device_names: A list of device names to query.
        redis_host: Redis server hostname (default: 'localhost').
        redis_port: Redis server port (default: 6379).
        redis_db: Redis database number (default: 0).
        redis_password: Redis password if required (default: None).
        key_prefix: Prefix for Redis keys (default: 'cucm:device:').
        verify_ssl: Whether to verify SSL certificates (default: False).

    Returns:
        Dictionary mapping device names to IP addresses.

    Example:
        >>> device_names = ['SEP001122334455', 'SEP005566778899']
        >>> device_ips = get_and_store_device_ips(
        ...     'cucm.example.com', 'admin', 'password', device_names
        ... )
    """
    # Import here to avoid circular imports
    from redis_store.device_ips import store_device_ips_redis
    
    # Get IP addresses from CUCM
    device_ips = get_device_ip_addresses(
        cucm_host, cucm_username, cucm_password, device_names, verify_ssl
    )

    # Store in Redis
    store_device_ips_redis(
        device_ips, redis_host, redis_port, redis_db, redis_password, key_prefix
    )

    return device_ips
