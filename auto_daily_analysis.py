import time
import datetime
from database import DBManager
from main import get_stock_data
from backtest_engine import BacktestEngine
import pandas as pd

def run_auto_daily_analysis():
    print(f"🚀 [{datetime.datetime.now()}] 启动每日全量自选股自动分析任务 (V1-V3)...")
    
    db = DBManager()
    
    # 1. 获取所有用户
    users_df = db.get_all_users()
    if users_df.empty:
        print("ℹ️ 暂无用户，任务结束。")
        return

    # 2. 收集所有唯一的自选股 (去重分析)
    all_watchlist = []
    for _, user in users_df.iterrows():
        watchlist = db.get_user_watchlist(user['uid'])
        if not watchlist.empty:
            # 记录这只股票属于哪些用户
            for _, row in watchlist.iterrows():
                all_watchlist.append({
                    "uid": user['uid'],
                    "stock_code": row['stock_code']
                })
            
    if not all_watchlist:
        print("ℹ️ 暂无自选股数据。")
        return
        
    master_df = pd.DataFrame(all_watchlist)
    unique_stocks = master_df['stock_code'].unique()
    
    print(f"📊 共有 {len(users_df)} 名用户，共需分析 {len(unique_stocks)} 只唯一股票。")
    
    # 3. 逐个分析
    analysis_cache = {}
    
    for stock in unique_stocks:
        try:
            # 获取数据 (含实时)
            df, error = get_stock_data(stock)
            if df is not None and not df.empty:
                # 重命名列以适配 Engine
                rename_map = {
                    '日期': 'date', '收盘': 'close', '开盘': 'open',
                    '最高': 'high', '最低': 'low', '成交量': 'volume',
                    '涨跌幅': 'pctChg'
                }
                cols = df.columns.tolist()
                final_map = {}
                for k, v in rename_map.items():
                    if k in cols: final_map[k] = v
                if final_map: df = df.rename(columns=final_map)
                
                # 兼容性检查
                if 'close' not in df.columns: 
                    # 尝试查找大小写不敏感匹配
                    for col in df.columns:
                        if col.lower() == 'close':
                            df = df.rename(columns={col: 'close'})
                        elif col.lower() == 'volume':
                            df = df.rename(columns={col: 'volume'})
                
                if 'close' not in df.columns:
                    print(f"  - {stock}: 缺少 close 列，跳过")
                    continue
                
                # 初始化引擎
                engine = BacktestEngine(stock)
                engine.df = df
                engine._calculate_indicators()
                
                if len(engine.df) < 2: continue
                
                # 取最后一行
                latest_row = engine.df.iloc[-1]
                prev_row = engine.df.iloc[-2]
                
                # 运行 V1, V2, V3
                v1_act, v1_rsn, _ = engine.make_decision(latest_row, prev_row, 'Score_V1')
                v2_act, v2_rsn, _ = engine.make_decision(latest_row, prev_row, 'Trend_V2')
                v3_act, v3_rsn, _ = engine.make_decision(latest_row, prev_row, 'Oscillation_V3')
                
                date_val = latest_row['date']
                if hasattr(date_val, 'strftime'):
                    date_str = date_val.strftime('%Y-%m-%d')
                else:
                    date_str = str(date_val)
                    # 如果只有时间没有日期，可能需要前面补
                    if len(date_str) < 10: 
                        date_str = datetime.date.today().strftime('%Y-%m-%d')
                
                price = float(latest_row['close'])
                pct = float(latest_row['pctChg']) if 'pctChg' in latest_row else 0.0
                
                analysis_cache[stock] = {
                    "date": date_str,
                    "price": price,
                    "pct_chg": pct,
                    "v1_action": v1_act, "v1_reason": v1_rsn,
                    "v2_action": v2_act, "v2_reason": v2_rsn,
                    "v3_action": v3_act, "v3_reason": v3_rsn
                }
                print(f"  ✅ {stock}: {v1_act}/{v2_act}/{v3_act}")
            else:
                print(f"❌ 股票 {stock} 获取数据失败: {error}")
                
        except Exception as e:
            print(f"💥 股票 {stock} 分析异常: {e}")

    # 4. 分发结果到数据库
    count = 0
    for _, row in master_df.iterrows():
        uid = row['uid']
        stock = row['stock_code']
        
        if stock in analysis_cache:
            data = analysis_cache[stock]
            success = db.save_daily_recommendation(
                uid=uid, 
                stock_code=stock, 
                date=data['date'], 
                price=data['price'],
                pct_chg=data['pct_chg'],
                tech_action=data['v1_action'], tech_reason=data['v1_reason'][:50],
                sent_action=data['v2_action'], sent_reason=data['v2_reason'][:50],
                v3_action=data['v3_action'], v3_reason=data['v3_reason'][:50],
                v4_action="未运行", v4_reason=""
            )
            if success: count += 1
            
    print(f"✅ 任务完成！共成功记录 {count} 条每日建议。")

if __name__ == "__main__":
    run_auto_daily_analysis()
