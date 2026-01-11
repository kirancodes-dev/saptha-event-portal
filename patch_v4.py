from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        with db.engine.connect() as conn:
            # 1. Update Admin Table to support Super vs Domain Admins
            # Role: 'Super', 'Tech', 'Sports', 'Cultural'
            try:
                conn.execute(text("ALTER TABLE admin ADD COLUMN role VARCHAR(50) DEFAULT 'Super'"))
            except: pass

            # 2. Add Domain column to EventSettings
            try:
                conn.execute(text("ALTER TABLE event_settings ADD COLUMN domain VARCHAR(50) DEFAULT 'Tech'"))
                conn.execute(text("ALTER TABLE event_settings ADD COLUMN venue VARCHAR(100)"))
                conn.execute(text("ALTER TABLE event_settings ADD COLUMN rules TEXT"))
            except: pass

            # 3. Create Event Managers Table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS event_manager (
                    id INTEGER PRIMARY KEY,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    name VARCHAR(100),
                    password VARCHAR(200),
                    assigned_domain VARCHAR(50),
                    phone VARCHAR(20)
                )
            """))
            
            conn.commit()
        print("✅ SUCCESS: Hierarchy System & Event Managers Added!")
    except Exception as e:
        print(f"⚠️ Notice: {e}")