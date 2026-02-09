
import os
import pandas as pd
from database import DBManager
from stock_names import get_stock_name_offline, save_cache, DYNAMIC_CACHE
from sqlalchemy import text

def pre_fetch_all_names():
    print("🚀 开始为所有自选股预取 AI 名称...")
    db = DBManager()
    
    try:
        with db._get_connection() as conn:
            # 获取数据库中所有出现过的股票代码
            df_watchlist = pd.read_sql_query(text("SELECT DISTINCT stock_code FROM watchlist"), conn)
            df_recom = pd.read_sql_query(text("SELECT DISTINCT stock_code FROM daily_recommendations"), conn)
            
            all_codes = set(df_watchlist['stock_code'].tolist() + df_recom['stock_code'].tolist())
            print(f"统计：共有 {len(all_codes)} 个唯一股票代码需要注入名称。")
            
            count = 0
            for code in all_codes:
                # 这会触发 AI 查询并存入缓存
                name = get_stock_name_offline(code)
                print(f"  - [{code}] -> {name}")
                count += 1
                
            print(f"\n✅ 预取完成！共处理 {count} 个股票。")
            print("所有正确名称已存入 stock_names_cache.json。")
            print("您现在刷新网页，所有股票名称都将显示正确。")
            
    except Exception as e:
        print(f"❌ 预取过程中出错: {e}")

if __name__ == "__main__":
    pre_fetch_all_names()
