import os
import sys
import json

# Ensure project root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Load env variables
from dotenv import load_dotenv
load_dotenv()

from app import app
from models import db

def test_endpoints():
    print("Initializing Flask test client...")
    client = app.test_client()
    
    with app.app_context():
        # Setup a dummy registration in Firestore to test webhook
        dummy_email = "test-webhook@demo.com"
        dummy_reg_id = "REG-TEST-WEBHOOK-9999"
        
        print(f"Creating dummy registration {dummy_reg_id} for {dummy_email}...")
        db.collection('registrations').document(dummy_reg_id).set({
            'reg_id': dummy_reg_id,
            'lead_email': dummy_email,
            'lead_name': "Webhook Test User",
            'registered_at': "2026-06-10 18:00:00",
            'status': 'Confirmed',
            'delivery_status': 'Sent'
        })
        
        # Test 1: Brevo Webhook Delivered Event
        print("\n--- Test 1: Testing Brevo Webhook ---")
        brevo_payload = {
            "event": "delivered",
            "email": dummy_email,
            "id": 12345,
            "date": "2026-06-10 18:05:00",
            "ts": 1773229600,
            "message-id": "<test-brevo-id@brevo.com>"
        }
        
        response = client.post(
            '/api/v1/webhooks/email',
            data=json.dumps(brevo_payload),
            content_type='application/json'
        )
        print("Status Code:", response.status_code)
        print("Response Body:", response.get_data(as_text=True))
        
        # Verify status in DB
        updated_reg = db.collection('registrations').document(dummy_reg_id).get().to_dict()
        print("Updated delivery_status in DB:", updated_reg.get('delivery_status'))
        assert updated_reg.get('delivery_status') == 'Delivered', "Status was not updated to Delivered"
        
        # Test 2: Resend Webhook Opened Event
        print("\n--- Test 2: Testing Resend Webhook ---")
        resend_payload = {
            "type": "email.opened",
            "created_at": "2026-06-10T18:06:00Z",
            "data": {
                "email_id": "resend-test-id",
                "to": [dummy_email],
                "subject": "Test subject"
            }
        }
        
        response = client.post(
            '/api/v1/webhooks/email',
            data=json.dumps(resend_payload),
            content_type='application/json'
        )
        print("Status Code:", response.status_code)
        print("Response Body:", response.get_data(as_text=True))
        
        # Verify status in DB
        updated_reg = db.collection('registrations').document(dummy_reg_id).get().to_dict()
        print("Updated delivery_status in DB:", updated_reg.get('delivery_status'))
        assert updated_reg.get('delivery_status') == 'Opened', "Status was not updated to Opened"
        
        # Test 3: SPOC Blast Preview Route
        print("\n--- Test 3: Testing SPOC Blast Preview Route ---")
        # We find a valid event in DB to preview
        events = list(db.collection('events').limit(1).stream())
        if events:
            event_id = events[0].id
            print(f"Testing preview on event: {events[0].to_dict().get('title')} ({event_id})...")
            
            # Since SPOC preview requires login, let's bypass by setting session
            with client.session_transaction() as sess:
                sess['user_id'] = events[0].to_dict().get('spoc_id', 'spoc@demo.com')
                sess['role'] = 'ClubSPOC'
                sess['name'] = 'Test SPOC'
            
            preview_payload = {
                "subject": "Important Event Update!",
                "body": "Hi team, please note that the venue has changed to Hall B. See you there!"
            }
            
            response = client.post(
                f'/spoc/blast_preview/{event_id}',
                data=json.dumps(preview_payload),
                content_type='application/json'
            )
            print("Status Code:", response.status_code)
            res_data = json.loads(response.get_data(as_text=True))
            print("Preview HTML exists in response:", 'html' in res_data)
            if 'html' in res_data:
                print("HTML snippet (truncated):", res_data['html'][:250].replace('\n', ' '))
        else:
            print("No events found in DB to test preview.")
            
        # Clean up dummy registration
        print(f"\nCleaning up dummy registration {dummy_reg_id}...")
        db.collection('registrations').document(dummy_reg_id).delete()
        print("DONE.")

if __name__ == "__main__":
    test_endpoints()
