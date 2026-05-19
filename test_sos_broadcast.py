"""
Quick test script to verify SOS broadcasting flow
"""

import requests
import json

BASE_URL = "http://127.0.0.1:5501"  # Frontend URL (assuming running locally)
API_URL = "http://127.0.0.1:8000/api"  # Backend API

# Test with demo credentials
CUSTOMER_PHONE = "9876543210"
CUSTOMER_TOKEN = "your_token_here"  # Get from login

# Test data
test_sos_data = {
    "lat": 23.0225,
    "lng": 72.5714,
    "address": "Sola Road, Ahmedabad",
    "vehicle_type": "four_wheeler",
    "vehicle_number": "GJ-01-AB-1234",
    "vehicle_model": "Honda City",
    "description": "Engine not starting",
    "radius_km": 2.0
}

def test_sos_broadcast():
    """Test SOS broadcasting"""
    
    print("\n" + "="*60)
    print("🆘 Testing SOS Broadcasting Flow")
    print("="*60)
    
    # Step 1: Create SOS
    print("\n📍 Step 1: Creating SOS...")
    response = requests.post(
        f"{API_URL}/sos/create",
        json=test_sos_data,
        headers={
            "Authorization": f"Bearer {CUSTOMER_TOKEN}",
            "Content-Type": "application/json"
        }
    )
    
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    if response.status_code != 200:
        print("❌ SOS creation failed!")
        return
    
    sos_id = data.get('id') or data.get('sos_id') or data.get('booking_id')
    nearby_count = len(data.get('nearby_garages', []))
    
    print(f"\n✅ SOS Created!")
    print(f"   SOS ID: {sos_id}")
    print(f"   SOS Number: {data.get('sos_number')}")
    print(f"   Nearby Garages: {nearby_count}")
    
    if nearby_count > 0:
        print(f"\n📢 Broadcast to:")
        for g in data.get('nearby_garages', [])[:3]:
            print(f"   • {g['garage_name']} ({g['distance_km']}km away)")
    else:
        print("\n⚠️ No nearby garages found!")
    
    # Step 2: Check SOS status
    print(f"\n📍 Step 2: Checking SOS status...")
    response = requests.get(
        f"{API_URL}/sos/customer/{sos_id}",
        headers={"Authorization": f"Bearer {CUSTOMER_TOKEN}"}
    )
    
    if response.status_code == 200:
        status_data = response.json()
        print(f"✅ Status: {status_data.get('status')}")
        print(f"   Garage: {status_data.get('garage_name') or 'Waiting for acceptance...'}")
    else:
        print(f"❌ Error: {response.status_code}")
    
    print("\n" + "="*60)
    print("Test Complete!")
    print("="*60 + "\n")

if __name__ == "__main__":
    print("\n⚠️  Before running:")
    print("1. Update CUSTOMER_TOKEN with a valid auth token")
    print("2. Ensure backend is running on http://127.0.0.1:8000")
    print("3. Database should have at least 2 garages within 2km of location")
    
    # test_sos_broadcast()  # Uncomment to run
