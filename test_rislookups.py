#!/usr/bin/env python3
"""
Test script for Cisco RIS lookups.
Requires environment variables: CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD
"""
import os
from dotenv import load_dotenv
from cisco.rislookups import get_device_ip_addresses
from redis_store.device_ips import store_device_ips_redis

# Load environment variables from .env file
load_dotenv()

# CUCM Configuration from environment
CUCM_HOST = os.getenv('CUCM_HOST')
CUCM_USERNAME = os.getenv('CUCM_USERNAME')
CUCM_PASSWORD = os.getenv('CUCM_PASSWORD')

if not all([CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD]):
    raise ValueError("Missing required environment variables: CUCM_HOST, CUCM_USERNAME, CUCM_PASSWORD")

# Test device names - UPDATE THESE with actual device names from your CUCM
# Example formats: ['SEP001122334455', 'SEP005566778899'] or ['BOT1234567890']
TEST_DEVICE_NAMES = ["SEP7081050BE42E",
"SEP7081050BFAFE",
"SEP7081050BF912",
"SEP00077D42ED3E",
"SEPC80084ECADEB",
"SEP7081050BE6A6",
"SEP503DE57DCDE2",
"SEP7081050C4896",
"SEP7081050C024C",
"SEP7081050C02CA",
"SEP7081050BF9F6",
"SEPCCEF48A24FAD",
"SEPE8B748EE43C1",
"SEP7081050BE902",
"SEP649EF3B681B7",
"SEPCCEF48A235A9",
"SEPCCEF48A235B9",
"SEP44D3CA7201B0",
"SEP7081050BFF6C",
"SEP7081050BFF30",
"SEP7081050BFCBE",
"SEP7081050BE5D6",
"SEP7081050C02E4",
"SEP7081050BE5CA"
]

# Redis Configuration from environment (with defaults)
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))


def main():
    """Test the RIS lookup functions."""
    
    if not TEST_DEVICE_NAMES:
        print("ERROR: Please add device names to TEST_DEVICE_NAMES in the script")
        print("Example: TEST_DEVICE_NAMES = ['SEP001122334455', 'SEP005566778899']")
        return
    
    print(f"Testing CUCM connection to {CUCM_HOST}")
    print(f"Looking up {len(TEST_DEVICE_NAMES)} device(s)...")
    print()
    
    try:
        # Step 1: Get IP addresses from CUCM
        print("Step 1: Fetching device IP addresses from CUCM...")
        device_ips = get_device_ip_addresses(
            CUCM_HOST,
            CUCM_USERNAME,
            CUCM_PASSWORD,
            TEST_DEVICE_NAMES,
            verify_ssl=False
        )
        
        print("\nResults from CUCM:")
        print("-" * 50)
        for device_name, ip_address in device_ips.items():
            if ip_address:
                print(f"  {device_name}: {ip_address}")
            else:
                print(f"  {device_name}: NOT FOUND")
        print("-" * 50)
        print()
        
        # Step 2: Store in Redis (optional - skip if Redis is not running)
        try:
            print("Step 2: Storing results in Redis...")
            stored_count = store_device_ips_redis(
                device_ips,
                redis_host=REDIS_HOST,
                redis_port=REDIS_PORT
            )
            print(f"Successfully stored {stored_count} device(s) in Redis")
        except ConnectionError as e:
            print(f"Warning: Could not connect to Redis: {e}")
            print("(This is okay if Redis is not running)")
        
    except ConnectionError as e:
        print(f"ERROR: Failed to connect to CUCM: {e}")
        print("\nTroubleshooting:")
        print("  - Check that CUCM is accessible at", CUCM_HOST)
        print("  - Verify credentials are correct")
        print("  - Check network connectivity")
    except RuntimeError as e:
        print(f"ERROR: Failed to query CUCM: {e}")
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")


if __name__ == '__main__':
    main()

