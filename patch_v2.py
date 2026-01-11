from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        with db.engine.connect() as conn:
            # 1. Add 'tech_tags' to Team table (For AI categorization)
            conn.execute(text("ALTER TABLE team ADD COLUMN tech_tags VARCHAR(500) DEFAULT 'General'"))
            
            # 2. Add social link columns to EventSettings table
            conn.execute(text("ALTER TABLE event_settings ADD COLUMN whatsapp_link VARCHAR(500)"))
            conn.execute(text("ALTER TABLE event_settings ADD COLUMN instagram_link VARCHAR(500)"))
            
            conn.commit()
        print("✅ SUCCESS: J.A.R.V.I.S. Database Upgrade Complete!")
    except Exception as e:
        print(f"⚠️ Notice: {e}")
        print("If it says 'Duplicate column', you are already upgraded.")