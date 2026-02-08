import time
import datetime
from database import DBManager
from main import get_stock_data, analyze_with_deepseek, get_market_status
import pandas as pd

def run_auto_daily_analysis():
    print(f"🚀 [{datetime.datetime.now()}] 启动每日全量自选股自动分析任务...")
    
    db = DBManager()
    
    # 获取当前市场日期
    now = datetime.datetime.now()
    # 如果是交易时段，保存为当日；如果是深夜，保存为当日收盘
    date_str = now.strftime('%Y-%m-%d')
    
    # 1. 获取所有用户
    users_df = db.get_all_users()
    if users_df.empty:
        print("ℹ️ 暂无用户，任务结束。")
        return

    # 简单的去重逻辑：按股票代码分析，然后同步给所有自选该股的用户
    # (为了节省 API 额度，不按用户跑，按股票跑)
    
    all_watchlist = []
    for _, user in users_df.iterrows():
        watchlist = db.get_user_watchlist(user['uid'])
        if not watchlist.empty:
            watchlist['uid'] = user['uid']
            all_watchlist.append(watchlist)
            
    if not all_watchlist:
        print("ℹ️ 暂无自选股数据。")
        return
        
    master_df = pd.concat(all_watchlist)
    unique_stocks = master_df['stock_code'].unique()
    
    print(f"📊 共有 {len(users_df)} 名用户，共需分析 {len(unique_stocks)} 只唯一股票。")
    
    # 存储分析结果缓存，避免重复请求同一只股票
    analysis_cache = {}
    
    for stock in unique_stocks:
        print(f"🔎 正在分析 {stock}...")
        try:
            df, error = get_stock_data(stock)
            if df is not None and not df.empty:
                # 获取双策略分析
                res_tech = analyze_with_deepseek(stock, df, strategy_type="technical")
                res_sent = analyze_with_deepseek(stock, df, strategy_type="sentiment")
                price = float(df.iloc[-1]['收盘'])
                
                analysis_cache[stock] = {
                    "tech": res_tech,
                    "sent": res_sent,
                    "price": price,
                    "date": df.iloc[-1]['日期'] # 使用数据真实日期
                }
                # 记录 Token 消耗 (由管理员触发或系统运行，归入管理员或系统统计)
                # 这里我们假设这种系统开销可以记录在触发者的 UID 下，或者单独记录
                # 暂且记录各维度的 usage
                time.sleep(1)
            else:
                print(f"❌ 股票 {stock} 获取数据失败: {error}")
        except Exception as e:
            print(f"💥 股票 {stock} 分析异常: {e}")

    # 分发结果到各用户数据库记录
    count = 0
    for _, row in master_df.iterrows():
        uid = row['uid']
        stock = row['stock_code']
        
        if stock in analysis_cache:
            data = analysis_cache[stock]
            success = db.save_daily_recommendation(
                uid, stock, data['date'], 
                data['tech'], data['sent'], data['price']
            )
            if success: count += 1
            
    print(f"✅ 任务完成！共成功记录 {count} 条每日建议。")

if __name__ == "__main__":
    run_auto_daily_analysis()
