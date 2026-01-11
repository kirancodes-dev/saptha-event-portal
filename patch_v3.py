from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        with db.engine.connect() as conn:
            # Add 'votes' column to Team table
            conn.execute(text("ALTER TABLE team ADD COLUMN votes INTEGER DEFAULT 0"))
            conn.commit()
        print("✅ SUCCESS: Voting System Activated!")
    except Exception as e:
        print(f"⚠️ Notice: {e}")