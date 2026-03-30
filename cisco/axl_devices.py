"""
Cisco Call Manager AXL SOAP API functions for device configuration lookups.
"""
from pathlib import Path
from typing import List, Dict, Optional
import json

from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client, Settings
from zeep.helpers import serialize_object
from zeep.transports import Transport
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Default CUCM version for AXL API
DEFAULT_CUCM_VERSION = '11.5'

# Schema directory path
SCHEMA_DIR = Path(__file__).parent / 'schema'


def get_phone_list(
    cucm_host: str,
    username: str,
    password: str,
    verify_ssl: bool = False,
    cucm_version: Optional[str] = None,
    search_name: str = 'SEP%',
    debug: bool = False
) -> List[Dict[str, Optional[str]]]:
    """
    Retrieves a list of all phones from CUCM using the AXL SOAP API.

    Args:
        cucm_host: The hostname or IP address of the CUCM server.
        username: The username for CUCM authentication.
        password: The password for CUCM authentication.
        verify_ssl: Whether to verify SSL certificates (default: False for self-signed certs).
        cucm_version: CUCM version to use (e.g., '11.5', '12.0', '12.5'). 
                     Uses local WSDL from schema folder. Default: '11.5'
        search_name: Device name search pattern (default: 'SEP%').
        debug: When True, writes raw response to a JSON file for troubleshooting.
                     Can also use 'current' to use the current folder.

    Returns:
        List of dictionaries containing device information with keys:
        - device_name: Device name
        - model: Device model
        - device_pool: Device pool name
        - description: Device description

    Example:
        >>> devices = get_phone_list(
        ...     'cucm.example.com', 'admin', 'password', cucm_version='11.5'
        ... )
        >>> for device in devices:
        ...     print(f"{device['device_name']}: {device['model']}")
    """
    # Determine which version to use
    version = cucm_version or DEFAULT_CUCM_VERSION
    
    # Try to use local WSDL file from schema folder
    wsdl_path = SCHEMA_DIR / version / 'AXLAPI.wsdl'
    wsdl_location = None
    wsdl_location_remote = f'https://{cucm_host}:8443/axl/services/AXLAPIService?wsdl'
    
    if wsdl_path.exists():
        wsdl_location = str(wsdl_path.absolute())
    else:
        # Fall back to remote WSDL if local file doesn't exist
        wsdl_location = wsdl_location_remote
    
    # Create a Zeep client with authentication (modeled after the snippet)
    session = Session()
    session.verify = verify_ssl
    session.auth = HTTPBasicAuth(username, password)
    transport = Transport(session=session, operation_timeout=10)
    settings = Settings(strict=False)

    def _create_axl_client(wsdl_location_to_use: str) -> Client:
        client_obj = Client(wsdl_location_to_use, transport=transport, settings=settings)
        endpoint_url = f'https://{cucm_host}:8443/axl/services/AXLAPIService'
        if client_obj.service and hasattr(client_obj.service, '_binding_options'):
            client_obj.service._binding_options['address'] = endpoint_url
        return client_obj

    client = None
    try:
        # Create the client from the local or remote WSDL
        client = _create_axl_client(wsdl_location)
    except Exception as e:
        error_msg = f"Failed to connect to CUCM AXL service using {version} schema."
        error_msg += f"\nWSDL location: {wsdl_location}"
        error_msg += f"\nError: {e}"
        if not wsdl_path.exists():
            error_msg += f"\n\nNote: Local WSDL file not found at: {wsdl_path}"
            error_msg += "\nUsing remote WSDL as fallback."
        raise ConnectionError(error_msg) from e

    if client is None or not client.service:
        raise ConnectionError(f"Failed to create AXL client for version {version}")

    devices = []
    
    try:
        # Use listPhone operation to get all phones
        # Note: This may return in batches, so we handle pagination
        returned_tags = {
            'name': '',
            'model': '',
            'devicePoolName': '',
            'description': '',
        }

        # searchCriteria requires at least one element - use search_name to filter
        search_criteria = {'name': 'SEP%'}

        response = client.service.listPhone(
            searchCriteria=search_criteria,
            returnedTags=returned_tags
        )
    except Exception as e:
        # Retry with remote WSDL if namespace mismatch occurs
        if 'namespace mismatch' in str(e) and wsdl_location != wsdl_location_remote:
            try:
                client = _create_axl_client(wsdl_location_remote)
                response = client.service.listPhone(
                    searchCriteria=search_criteria,
                    returnedTags=returned_tags
                )
            except Exception as retry_error:
                raise RuntimeError(f"Error querying AXL service: {retry_error}") from retry_error
        else:
            raise RuntimeError(f"Error querying AXL service: {e}") from e
        
        # Extract phone list from response
        # Response structure varies by CUCM version
        phone_list = []
        response_data = serialize_object(response) if response else {}
        if response_data and 'return' in response_data and response_data['return']:
            return_obj = response_data['return']
            if 'phone' in return_obj and return_obj['phone']:
                phones = return_obj['phone']
                phone_list = phones if isinstance(phones, list) else [phones]

        if debug:
            debug_path = Path(__file__).parent / 'axl_last_response.json'
            with debug_path.open('w', encoding='utf-8') as debug_file:
                json.dump(response_data, debug_file, indent=2)
        
        # Process each phone
        for phone in phone_list:
            device_info = {
                'device_name': None,
                'model': None,
                'device_pool': None,
                'description': None,
            }
            
            # Extract device name
            if isinstance(phone, dict):
                device_info['device_name'] = str(phone.get('name')) if phone.get('name') else None
            elif hasattr(phone, 'name'):
                device_info['device_name'] = str(phone.name) if phone.name else None
            elif hasattr(phone, 'Name'):
                device_info['device_name'] = str(phone.Name) if phone.Name else None
            
            # Extract model
            if isinstance(phone, dict):
                device_info['model'] = str(phone.get('model')) if phone.get('model') else None
            elif hasattr(phone, 'model'):
                device_info['model'] = str(phone.model) if phone.model else None
            elif hasattr(phone, 'Model'):
                device_info['model'] = str(phone.Model) if phone.Model else None
            
            # Extract device pool
            if isinstance(phone, dict):
                pool_obj = phone.get('devicePoolName')
                if isinstance(pool_obj, dict):
                    device_info['device_pool'] = pool_obj.get('_value_1')
                elif pool_obj:
                    device_info['device_pool'] = str(pool_obj)
            elif hasattr(phone, 'devicePoolName'):
                device_info['device_pool'] = str(phone.devicePoolName) if phone.devicePoolName else None
            elif hasattr(phone, 'DevicePoolName'):
                device_info['device_pool'] = str(phone.DevicePoolName) if phone.DevicePoolName else None
            elif hasattr(phone, 'devicePool'):
                pool_obj = phone.devicePool
                if hasattr(pool_obj, 'name'):
                    device_info['device_pool'] = str(pool_obj.name) if pool_obj.name else None
            
            # Extract description
            if isinstance(phone, dict):
                device_info['description'] = str(phone.get('description')) if phone.get('description') else None
            elif hasattr(phone, 'description'):
                device_info['description'] = str(phone.description) if phone.description else None
            elif hasattr(phone, 'Description'):
                device_info['description'] = str(phone.Description) if phone.Description else None
            
            # Only add devices with at least a name
            if device_info['device_name']:
                devices.append(device_info)
                
    except Exception as e:
        raise RuntimeError(f"Error querying AXL service: {e}")

    return devices


def sync_devices_to_sqlite(
    cucm_host: str,
    username: str,
    password: str,
    verify_ssl: bool = False,
    cucm_version: Optional[str] = None,
    search_name: str = 'SEP%',
    debug: bool = False
) -> int:
    """
    Fetches all phones from CUCM AXL API and stores them in SQLite database.

    Args:
        cucm_host: The hostname or IP address of the CUCM server.
        username: The username for CUCM authentication.
        password: The password for CUCM authentication.
        verify_ssl: Whether to verify SSL certificates (default: False).
        cucm_version: CUCM version to use (e.g., '11.5', '12.0', '12.5').
                     Uses local WSDL from schema folder. Default: '11.5'
        search_name: Device name search pattern (default: 'SEP%').
        debug: When True, writes raw response to a JSON file for troubleshooting.

    Returns:
        Number of devices synced to database.

    Example:
        >>> count = sync_devices_to_sqlite(
        ...     'cucm.example.com', 'admin', 'password', cucm_version='11.5'
        ... )
        >>> print(f"Synced {count} devices")
    """
    from sqlite_crud.ucm_devices import insert_ucm_device
    from sqlite_crud.database import initialize_database
    
    # Ensure database is initialized
    initialize_database()
    
    # Get device list from CUCM
    devices = get_phone_list(
        cucm_host,
        username,
        password,
        verify_ssl,
        cucm_version,
        search_name,
        debug
    )
    
    # Store each device in SQLite
    for device in devices:
        insert_ucm_device(
            device_name=device['device_name'],
            model=device['model'],
            device_pool=device['device_pool'],
            description=device['description']
        )
    
    return len(devices)
