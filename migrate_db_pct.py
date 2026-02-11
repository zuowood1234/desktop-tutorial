from database import DBManager
from sqlalchemy import text

try:
    db = DBManager()
    with db._get_connection() as conn:
        print("Adding pct_chg column...")
        conn.execute(text("ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS pct_chg FLOAT"))
        conn.commit()
        print("Done!")
except Exception as e:
    print(f"Error: {e}")
