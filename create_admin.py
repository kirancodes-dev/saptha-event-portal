from app import app, db
from models import SuperAdmin

# Create the admin user inside the app context
with app.app_context():
    # 1. Create Tables if they don't exist
    db.create_all()
    
    # 2. Check if admin exists
    if not SuperAdmin.query.filter_by(email='admin@portal.com').first():
        admin = SuperAdmin(
            email='admin@portal.com',
            password='admin',        # Simple password for testing
            secret_key='1234'        # The Secret Key for the login page
        )
        db.session.add(admin)
        db.session.commit()
        print("✅ Super Admin Created!")
        print("Email: admin@portal.com")
        print("Password: admin")
        print("Secret Key: 1234")
    else:
        print("⚠️ Admin already exists.")