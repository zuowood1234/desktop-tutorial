from database import DBManager
from sqlalchemy import text
from main import get_stock_data
from backtest_engine import BacktestEngine
import pandas as pd

# 允许的日期列表 (仅保留最近2天，过滤掉旧日期和周末干扰)
ALLOWED_DATES = ['2026-02-10', '2026-02-11']

db = DBManager()

def clean_rebuild():
    print("🧹 正在彻底清空每日建议数据库 (daily_recommendations)...")
    with db._get_connection() as conn:
        conn.execute(text("TRUNCATE TABLE daily_recommendations CASCADE")) 
        conn.commit()
    print("✅ 数据库已清空")

    print(f"🚀 开始强制生成指定日期的数据: {ALLOWED_DATES}")
    
    with db._get_connection() as conn:
         # 获取所有活跃用户
         users = conn.execute(text("SELECT uid FROM users WHERE status='active'")).fetchall()
    
    for user_row in users:
        uid = user_row.uid
        
        watchlist = db.get_user_watchlist(uid)
        if watchlist.empty: continue
        
        codes = watchlist['stock_code'].tolist()
        print(f"Processing user {uid}, {len(codes)} stocks...")
        
        for code in codes:
            try:
                df, _ = get_stock_data(code)
                if df is None or df.empty: continue
                
                # column mapping
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
                
                if 'close' not in df.columns: continue

                engine = BacktestEngine(code)
                engine.df = df
                engine._calculate_indicators()
                
                # 遍历每一行，检查日期是否在 ALLOWED_DATES
                # 不需要只看最后3行，看最近10行是否包含目标日期即可
                start_i = max(len(engine.df)-10, 1)
                
                for i in range(start_i, len(engine.df)):
                    row = engine.df.iloc[i]
                    date_val = str(row['date'])
                    
                    # ⚠️ 强校验：只处理 2-10 和 2-11
                    if date_val not in ALLOWED_DATES:
                        continue
                        
                    prev = engine.df.iloc[i-1]
                    price = float(row['close'])
                    pct = float(row['pctChg']) if 'pctChg' in row else 0.0
                    
                    # Run V1, V2, V3
                    v1_act, v1_rsn, _ = engine.make_decision(row, prev, 'Score_V1')
                    v2_act, v2_rsn, _ = engine.make_decision(row, prev, 'Trend_V2')
                    v3_act, v3_rsn, _ = engine.make_decision(row, prev, 'Oscillation_V3')
                    
                    print(f"  Writing {code} @ {date_val} -> V1:{v1_act} | V2:{v2_act} | V3:{v3_act}")
                    
                    db.save_daily_recommendation(
                        uid=uid, stock_code=code, date=date_val, price=price, pct_chg=pct,
                        tech_action=v1_act, tech_reason=v1_rsn[:50],
                        sent_action=v2_act, sent_reason=v2_rsn[:50],
                        v3_action=v3_act, v3_reason=v3_rsn[:50],
                        v4_action="未运行", v4_reason=""
                    )
            except Exception as e:
                print(f"Error {code}: {e}")

if __name__ == "__main__":
    clean_rebuild()
