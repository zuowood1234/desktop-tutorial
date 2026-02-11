from database import DBManager
from sqlalchemy import text
from run_backfill import backfill_history

db = DBManager()

def clean_and_refill():
    print("🧹 清理指定日期的旧数据...")
    with db._get_connection() as conn:
        # 1. 删除 2-5, 2-6 (用户明确要求)
        conn.execute(text("DELETE FROM daily_recommendations WHERE date IN ('2026-02-05', '2026-02-06')"))
        
        # 2. 删除 2-9, 2-10, 2-11 (为了强制重新生成新策略)
        # 注意：如果2-9是周日，可能本来就没数据，删了也不报错
        conn.execute(text("DELETE FROM daily_recommendations WHERE date IN ('2026-02-09', '2026-02-10', '2026-02-11')"))
        
        conn.commit()
    print("✅ 清理完成！")
    
    print("🚀 重新运行回溯逻辑 (生成最新 V1-V3)...")
    backfill_history()

if __name__ == "__main__":
    clean_and_refill()
