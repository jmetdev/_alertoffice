#!/usr/bin/env python3
"""
Test script for Cisco AXL device sync to SQLite.
Requires environment variables: CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD
"""
import os
from dotenv import load_dotenv
from cisco.axl_devices import get_phone_list, sync_devices_to_sqlite
from sqlite_crud.ucm_devices import get_all_ucm_devices, get_ucm_device
from sqlite_crud.database import initialize_database

# Load environment variables from .env file
load_dotenv()

# CUCM Configuration from environment
CUCM_HOST = os.getenv('CUCM_HOST')
CUCM_USERNAME = os.getenv('CUCM_USERNAME')
CUCM_PASSWORD = os.getenv('CUCM_PASSWORD')

if not all([CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD]):
    raise ValueError("Missing required environment variables: CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD")

# CUCM Version for AXL API (options: '11.5', '12.0', '12.5', 'current')
# Must match a folder name in cisco/schema/
CUCM_VERSION = '11.5'
DEBUG_AXL = True


def main():
    """Test the AXL device sync."""
    
    print(f"Testing CUCM AXL connection to {CUCM_HOST}")
    print()
    
    try:
        # Initialize database
        print("Step 1: Initializing SQLite database...")
        initialize_database()
        print("✓ Database initialized")
        print()
        
        # Option 1: Get phone list without storing
        print("Step 2: Fetching phone list from CUCM AXL API...")
        try:
            devices = get_phone_list(
                CUCM_HOST,
                CUCM_USERNAME,
                CUCM_PASSWORD,
                verify_ssl=False,
                cucm_version=CUCM_VERSION,
                debug=DEBUG_AXL
            )
            print(f"✓ Retrieved {len(devices)} phones from CUCM")
            
            # Display first few devices
            if devices:
                print("\nFirst 5 devices:")
                print("-" * 80)
                print(f"{'Device Name':<30} {'Model':<20} {'Device Pool':<20} {'Description'}")
                print("-" * 80)
                for device in devices[:5]:
                    print(f"{device['device_name']:<30} "
                          f"{device['model'] or 'N/A':<20} "
                          f"{device['device_pool'] or 'N/A':<20} "
                          f"{device['description'] or 'N/A'}")
                print("-" * 80)
        except Exception as e:
            print(f"✗ Error fetching phone list: {e}")
            print("\nNote: AXL API endpoint may need adjustment for your CUCM version")
            return
        
        print()
        
        # Option 2: Sync to SQLite
        print("Step 3: Syncing devices to SQLite database...")
        try:
            count = sync_devices_to_sqlite(
                CUCM_HOST,
                CUCM_USERNAME,
                CUCM_PASSWORD,
                verify_ssl=False,
                cucm_version=CUCM_VERSION,
                debug=DEBUG_AXL
            )
            print(f"✓ Synced {count} devices to SQLite database")
        except Exception as e:
            print(f"✗ Error syncing to SQLite: {e}")
            return
        
        print()
        
        # Verify SQLite content
        print("Step 4: Verifying SQLite database content...")
        all_devices = get_all_ucm_devices()
        print(f"✓ Found {len(all_devices)} devices in SQLite database")
        
        if all_devices:
            print("\nSample from database:")
            print("-" * 80)
            print(f"{'Device Name':<30} {'Model':<20} {'Device Pool':<20} {'Description'}")
            print("-" * 80)
            for device in all_devices[:5]:
                print(f"{device['device_name']:<30} "
                      f"{device['model'] or 'N/A':<20} "
                      f"{device['device_pool'] or 'N/A':<20} "
                      f"{device['description'] or 'N/A'}")
            print("-" * 80)
        
    except ConnectionError as e:
        print(f"ERROR: Failed to connect to CUCM: {e}")
        print("\nTroubleshooting:")
        print("  - Check that CUCM is accessible at", CUCM_HOST)
        print("  - Verify credentials are correct")
        print("  - Check network connectivity")
        print("  - Ensure AXL service is enabled on CUCM")
    except RuntimeError as e:
        print(f"ERROR: Failed to query AXL service: {e}")
        print("\nNote: AXL API endpoint/version may need adjustment")
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
