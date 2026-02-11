from database import DBManager
from sqlalchemy import text
import sys

# 简单迁移脚本
try:
    db = DBManager()
    with db.engine.connect() as conn:
        print("Migrating daily_recommendations table...")
        # V3
        conn.execute(text("ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS v3_action TEXT"))
        conn.execute(text("ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS v3_reason TEXT"))
        # V4
        conn.execute(text("ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS v4_action TEXT"))
        conn.execute(text("ALTER TABLE daily_recommendations ADD COLUMN IF NOT EXISTS v4_reason TEXT"))
        conn.commit()
        print("Successfully added cols: v3_action, v3_reason, v4_action, v4_reason")
except Exception as e:
    print(f"Migration failed: {e}")
