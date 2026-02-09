
import os
import json
import pandas as pd
from database import DBManager
from sqlalchemy import text
from stock_names import STOCK_NAMES, load_cache

def sync_names_to_cloud():
    print("🌐 开始同步股票名称到 Supabase 云端...")
    db = DBManager()
    
    # 1. 创建云端表
    create_sql = """
    CREATE TABLE IF NOT EXISTS stock_info (
        code TEXT PRIMARY KEY,
        name TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    
    try:
        with db._get_connection() as conn:
            conn.execute(text(create_sql))
            conn.commit()
            print("✅ 云端 stock_info 表检查/创建成功。")
            
            # 2. 汇总所有名称 (硬编码 + 本地缓存)
            all_names = STOCK_NAMES.copy()
            local_cache = load_cache()
            all_names.update(local_cache)
            
            print(f"📦 准备同步 {len(all_names)} 个名称到云端...")
            
            # 3. 批量插入/更新
            upsert_sql = """
            INSERT INTO stock_info (code, name)
            VALUES (:code, :name)
            ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name;
            """
            
            for code, name in all_names.items():
                if name and name != code:
                    conn.execute(text(upsert_sql), {"code": code, "name": name})
            
            conn.commit()
            print(f"🚀 同步完成！现在互联网端也能看到正确的名称了。")

    except Exception as e:
        print(f"❌ 同步失败: {e}")

if __name__ == "__main__":
    sync_names_to_cloud()
