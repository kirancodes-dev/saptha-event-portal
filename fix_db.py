from app import app, db
from sqlalchemy import text

with app.app_context():
    print("🔧 STARTING DATABASE REPAIR...")
    try:
        with db.engine.connect() as conn:
            # 1. Add 'role' to Admin table
            try:
                print("1. Adding 'role' column to Admin table...")
                conn.execute(text("ALTER TABLE admin ADD COLUMN role VARCHAR(50) DEFAULT 'Super'"))
                print("   ✅ Done.")
            except Exception as e:
                print(f"   ℹ️ Skipped (might already exist): {e}")

            # 2. Add 'domain', 'venue', 'rules' to EventSettings
            try:
                print("2. Adding columns to EventSettings...")
                conn.execute(text("ALTER TABLE event_settings ADD COLUMN domain VARCHAR(50) DEFAULT 'Tech'"))
                conn.execute(text("ALTER TABLE event_settings ADD COLUMN venue VARCHAR(100)"))
                conn.execute(text("ALTER TABLE event_settings ADD COLUMN rules TEXT"))
                print("   ✅ Done.")
            except Exception as e:
                print(f"   ℹ️ Skipped: {e}")

            # 3. Create Event Manager Table
            try:
                print("3. Creating EventManager table...")
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS event_manager (
                        id INTEGER PRIMARY KEY AUTO_INCREMENT,
                        email VARCHAR(120) UNIQUE NOT NULL,
                        name VARCHAR(100),
                        password VARCHAR(200),
                        assigned_domain VARCHAR(50),
                        phone VARCHAR(20)
                    )
                """))
                print("   ✅ Done.")
            except Exception as e:
                print(f"   ℹ️ Skipped: {e}")

            conn.commit()
            print("\n🎉 DATABASE REPAIR COMPLETE! You can now run app.py")
    except Exception as e:
        print(f"\n❌ CRITICAL DATABASE ERROR: {e}")