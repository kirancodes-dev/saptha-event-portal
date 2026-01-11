from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        # This SQL command adds the 'feedback' column to your Team table
        with db.engine.connect() as conn:
            conn.execute(text("ALTER TABLE team ADD COLUMN feedback TEXT"))
            conn.commit()
        print("✅ SUCCESS: Database updated! 'feedback' column added.")
    except Exception as e:
        print(f"⚠️ Note: {e}")
        print("If it says 'Duplicate column name', that means you already have it. You are good to go!")