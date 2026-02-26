import os
import time
import datetime
import pandas as pd
import akshare as ak
from tqdm import tqdm

from data_fetcher_v2 import fetch_stock_history_dual, calc_daily_limits_and_flags
from super_factor_engine import calculate_super_features

DATA_DIR = "backtest_data"
SCANNER_FILE = os.path.join(DATA_DIR, "today_scanner.parquet")
os.makedirs(DATA_DIR, exist_ok=True)

def build_scanner_snapshot(pool="hs300"):
    print("=== 🎯 开始构建 雷达选股器 每日快照 ===")
    
    if pool == "hs300":
        print("模式: 沪深300 (快速模式)")
        cons_df = ak.index_stock_cons(symbol="000300")
        codes = cons_df['品种代码'].tolist()
        names = cons_df['品种名称'].tolist()
        code_name_map = dict(zip(codes, names))
    elif pool == "test":
        print("模式: 极速测试 (仅10只核心池)")
        codes = ["600519", "000001", "300750", "002050", "002460", "601012", "002456", "002920", "000333", "300999"]
        code_name_map = {c: c for c in codes}
    else:
        print("模式: 全市场 A 股")
        spot_df = ak.stock_zh_a_spot_em()
        # 过滤北交所等不活跃的标的 (代码以 8, 4 开头的)
        spot_df = spot_df[~spot_df['代码'].str.startswith(('8', '4'))]
        codes = spot_df['代码'].tolist()
        code_name_map = dict(zip(spot_df['代码'], spot_df['名称']))
        
    print(f"需要扫描清洗: {len(codes)} 只股票\n")
    
    # 只要 300 个交易日的数据，足以满足 MA250 和大周期因子的计算
    # 安全起见拿过去 450 天日历日的数据
    start_dt = (datetime.datetime.now() - datetime.timedelta(days=450)).strftime("%Y%m%d")
    
    latest_snapshots = []
    
    for code in tqdm(codes, desc="盘后因子生成中"):
        try:
            # 1. 取短期历史数据 (带前复权)
            df = fetch_stock_history_dual(code, start_date=start_dt)
            if df is None or df.empty or len(df) < 60:
                continue
            
            # 2. 算涨跌停限制与交易标志
            df = calc_daily_limits_and_flags(df)
            df['is_trading'] = df['Close_Raw'].notna() & (df['Volume'] > 0)
            
            # 3. 计算全部技术指标与动能因子
            df = calculate_super_features(df)
            
            # 4. 基本面估值补充 (每天都在变，所以用最新一天的即可)
            # 通过 AKShare 的 stock_value_em 获取现在的 PE, PB 等
            # 注定会有些耗时，如果追求极致速度可注释本段，利用回测舱里的季报数据拼接 
            val_df = ak.stock_value_em(symbol=code)
            if not val_df.empty:
                val_df = val_df.rename(columns={
                    'PE(TTM)': 'PE_TTM', '市净率': 'PB', '总市值': 'Total_MV'
                })
                latest_val = val_df.iloc[-1]
                df.loc[df.index[-1], 'PE_TTM'] = latest_val.get('PE_TTM', pd.NA)
                df.loc[df.index[-1], 'PB'] = latest_val.get('PB', pd.NA)
                # 统一为【元】，方便跟选股器对应
                df.loc[df.index[-1], 'Total_MV'] = latest_val.get('Total_MV', pd.NA) 
                
            # 5. 我们只需截取【最后一天】的切片保存！
            last_row = df.iloc[-1].to_dict()
            last_row['Stock_Name'] = code_name_map.get(code, code)
            
            latest_snapshots.append(last_row)
            
            time.sleep(0.1) # 保护性限流
            
        except Exception as e:
            # print(f"Error on {code}: {e}")
            continue
            
    # 合并成大表
    if latest_snapshots:
        snap_df = pd.DataFrame(latest_snapshots)
        snap_df.to_parquet(SCANNER_FILE, engine="pyarrow", index=False)
        print(f"\n[√] 成功生成 {len(snap_df)} 只股票的横截面数据快照！")
        print(f"数据总大小仅为: {os.path.getsize(SCANNER_FILE) / 1024 / 1024:.2f} MB")
        print(f"文件保存路径 -> {SCANNER_FILE}")
    else:
        print("\n[!] 扫描失败，没有合法的股票数据。")

if __name__ == "__main__":
    # ========================================================
    # 设置你要重构全库的心智：
    # "test": 极速测试 10 只票 (10秒钟)
    # "hs300": 沪深300指数 300 只票 (1分钟)
    # "all": 全市场近 5100 只票 (20分钟，注意 API 频率限制风险)
    # ========================================================
    build_scanner_snapshot(pool="hs300")
