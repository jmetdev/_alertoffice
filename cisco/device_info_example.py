#!/usr/bin/env python3
"""
Example script to inspect available device fields from RIS SOAP API.
Run this to see what fields are available in the device object.
Requires environment variables: CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD
"""
import os
from dotenv import load_dotenv
import zeep
from requests import Session
from requests.auth import HTTPBasicAuth
from zeep.transports import Transport
import urllib3

# Load environment variables from .env file
load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration from environment
CUCM_HOST = os.getenv('CUCM_HOST')
CUCM_USERNAME = os.getenv('CUCM_USERNAME')
CUCM_PASSWORD = os.getenv('CUCM_PASSWORD')
DEVICE_NAME = os.getenv('TEST_DEVICE_NAME', 'SEP7081050BE42E')  # Use one device for inspection

if not all([CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD]):
    raise ValueError("Missing required environment variables: CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD")

wsdl_url = f'https://{CUCM_HOST}:8443/realtimeservice2/services/RISService70?wsdl'

session = Session()
session.verify = False
session.auth = HTTPBasicAuth(CUCM_USERNAME, CUCM_PASSWORD)
transport = Transport(session=session)

client = zeep.Client(wsdl=wsdl_url, transport=transport)

selection_criteria = {
    'MaxReturnedDevices': 1000,
    'DeviceClass': 'Any',
    'Model': 255,
    'Status': 'Any',
    'NodeName': '',
    'SelectBy': 'Name',
    'SelectItems': {'item': [DEVICE_NAME]},
    'Protocol': 'Any',
    'DownloadStatus': 'Any'
}

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
                    print("=" * 60)
                    print("AVAILABLE DEVICE FIELDS:")
                    print("=" * 60)
                    print(f"\nDevice object type: {type(device)}")
                    print(f"\nDevice object attributes:\n")
                    
                    # List all attributes
                    for attr in dir(device):
                        if not attr.startswith('_'):
                            try:
                                value = getattr(device, attr)
                                if not callable(value):
                                    print(f"  {attr}: {value} (type: {type(value).__name__})")
                            except Exception as e:
                                print(f"  {attr}: <error accessing: {e}>")
                    
                    print("\n" + "=" * 60)



