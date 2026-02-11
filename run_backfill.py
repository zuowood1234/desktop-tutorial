import pandas as pd
from database import DBManager
from backtest_engine import BacktestEngine
from main import get_stock_data
from sqlalchemy import text

db = DBManager()

def backfill_history():
    print("STARTING BACKFILL...")
    
    with db._get_connection() as conn:
        users = conn.execute(text("SELECT uid FROM users WHERE status='active'")).fetchall()
    
    for user_row in users:
        uid = user_row.uid
        print(f"User: {uid}")
        
        watchlist = db.get_user_watchlist(uid)
        if watchlist.empty: continue
        
        codes = watchlist['stock_code'].tolist()
        for code in codes:
            try:
                # Get historical data
                df, _ = get_stock_data(code)
                if df is None or df.empty: continue
                
                # Standardize columns (handle both Chinese and English)
                rename_map = {
                    '日期': 'date', '收盘': 'close', '开盘': 'open', 
                    '最高': 'high', '最低': 'low', '成交量': 'volume'
                }
                # Check existance first
                cols = df.columns.tolist()
                final_map = {}
                for k, v in rename_map.items():
                    if k in cols: final_map[k] = v
                
                if final_map:
                    df = df.rename(columns=final_map)
                
                # If already English, ensure lower case? Assuming get_stock_data returns consistent cols.
                if 'close' not in df.columns: continue

                # Initialize Engine
                engine = BacktestEngine(code)
                engine.df = df
                engine._calculate_indicators()
                
                # Iterate last 3 days
                if len(engine.df) < 5: continue
                
                # Calculate signals for index [-3], [-2], [-1]
                # Use max(-3, -len)
                start_i = max(len(engine.df)-3, 1)
                
                for i in range(start_i, len(engine.df)):
                    row = engine.df.iloc[i]
                    prev_row = engine.df.iloc[i-1]
                    # date might be timestamp or string
                    date_val = row['date']
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)
                        
                    price = float(row['close'])
                    
                    # Run V1, V2, V3
                    v1_act, v1_rsn, _ = engine.make_decision(row, prev_row, 'Score_V1')
                    v2_act, v2_rsn, _ = engine.make_decision(row, prev_row, 'Trend_V2')
                    v3_act, v3_rsn, _ = engine.make_decision(row, prev_row, 'Oscillation_V3')
                    
                    # Save
                    print(f"  Saving {code} @ {date_str} -> V1:{v1_act}, V2:{v2_act}, V3:{v3_act}")
                    
                    # Shorten reason
                    db.save_daily_recommendation(
                        uid=uid, 
                        stock_code=code, 
                        date=date_str, 
                        price=price,
                        tech_action=v1_act, tech_reason=v1_rsn[:50],
                        sent_action=v2_act, sent_reason=v2_rsn[:50],
                        v3_action=v3_act, v3_reason=v3_rsn[:50],
                        v4_action="未运行", v4_reason=""
                    )
            except Exception as e:
                print(f"Error {code}: {e}")

if __name__ == "__main__":
    backfill_history()
