from models import db

def wipe_database():
    print("🧹 Starting Database Factory Reset...")

    # 1. WIPE ALL EVENTS
    events_ref = db.collection('events').stream()
    event_count = 0
    for doc in events_ref:
        doc.reference.delete()
        event_count += 1
    print(f"✅ Deleted {event_count} Events.")

    # 2. WIPE ALL REGISTRATIONS (TICKETS)
    regs_ref = db.collection('registrations').stream()
    reg_count = 0
    for doc in regs_ref:
        doc.reference.delete()
        reg_count += 1
    print(f"✅ Deleted {reg_count} Team Registrations.")

    # 3. WIPE ALL USERS (EXCEPT SUPER ADMINS)
    users_ref = db.collection('users').stream()
    user_count = 0
    admin_count = 0
    for doc in users_ref:
        user_data = doc.to_dict()
        
        # 🛡️ The Protective Shield for Super Admins
        if user_data.get('role') in ['SuperAdmin', 'Super Admin']:
            admin_count += 1
            print(f"🛡️ Kept Super Admin safe: {doc.id}")
            continue
            
        doc.reference.delete()
        user_count += 1
        
    print(f"✅ Deleted {user_count} Users/Staff (Protected {admin_count} Super Admins).")
    print("✨ DATABASE WIPE COMPLETE! You have a perfectly clean slate. ✨")

if __name__ == '__main__':
    wipe_database()