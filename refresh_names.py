
import os
import json
from dotenv import load_dotenv
from database import DBManager
import stock_names

# 强制重新加载，确保用的是最新的逻辑
import importlib
importlib.reload(stock_names)

load_dotenv()

def refresh_all_stock_names():
    print("🧹 开始刷新所有自选股名称...")
    
    # 1. 连接数据库
    db = DBManager()
    
    # 2. 获取所有用户的自选股 (这里简化处理，获取所有 distinct 的股票代码)
    # 由于 DBManager 没有直接获取所有自选股的方法，我们先尝试获取当前用户的（假设只有一个用户，或遍历常见用户）
    # 或者直接操作数据库底层，但为了安全，我们通过 standard API
    # 假设我们只关心当前 active 的用户，或者我们可以读取 cache 文件里的所有 key 来刷新
    
    # 策略：
    # A. 刷新 stock_names_cache.json 中的所有 key
    # B. 如果能连接 DB，刷新 DB 中的 watchlist 表
    
    # A. 刷新本地缓存文件
    cache_file = "stock_names_cache.json"
    if os.path.exists(cache_file):
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        
        print(f"📦 本地缓存中有 {len(cache)} 个股票，正在检查...")
        
        updated_count = 0
        for code in list(cache.keys()):
            old_name = cache[code]
            # 如果旧名字是代码本身、乱码、或者含问号，强制刷新
            needs_refresh = (old_name == code) or ('?' in old_name) or ('' in old_name) or (len(old_name) < 2)
            
            if needs_refresh:
                print(f"   - 发现问题名称: {code} -> {old_name}，正在 AI 修正...")
                # 先从 cache 删掉，强制 get_stock_name_offline 走 AI 逻辑
                del stock_names.DYNAMIC_CACHE[code]
                
                new_name = stock_names.get_stock_name_offline(code)
                if new_name != old_name:
                    print(f"     ✅ 修正为: {new_name}")
                    updated_count += 1
        
        if updated_count > 0:
            print(f"🎉 已修正 {updated_count} 个本地缓存名称！")
        else:
            print("✅ 本地缓存名称看起来都很正常。")
            
    # B. 刷新数据库 (Watchlist)
    # 我们需要一个 session 来操作 DB。
    # 这里我们绕过 session，直接用 SQL 更新，或者模拟用户操作
    # 由于不知道具体 user_id，我们这里只做 cache 清洗。
    # 实际上，只要 Cache 清洗了，网页前端调用 get_stock_name_offline 时就会拿到新的（因为我们删除了坏的 cache）
    
    # 为了保险，我们手动删除 cache 文件让系统彻底重建
    print("\n🗑️  为了彻底解决问题，我建议直接删除旧的 'stock_names_cache.json'。")
    print("   这样下次您访问网页时，系统会重新用 AI 抓取最新的完美名字。")
    
    try:
        if os.path.exists(cache_file):
            os.remove(cache_file)
            print("✅ 已删除旧缓存文件。系统准备就绪，请刷新网页！")
    except Exception as e:
        print(f"Error removing cache: {e}")

if __name__ == "__main__":
    refresh_all_stock_names()
