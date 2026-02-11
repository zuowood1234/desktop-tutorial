import pandas as pd
import subprocess
import os
import sys
from datetime import datetime

# ==========================================
# 🧪 超级回测实验室 (Super Batch Runner)
# ==========================================

STOCK_POOL = [
    "000960", "002284", "002409", "002517", "002905", "002910", 
    "300102", "300115", "300274", "300442", "300456", "300620", 
    "300857", "301171", "600362", "600703", "600745", "600879", 
    "601126", "601698", "603308", "603598", "605136", "688141", 
    "688536", "688981"
]

START_DATE = "2025-01-01"
END_DATE = "2025-12-31"

# Phase Cutoff Dates
PHASE1_END = "2025-09-30"
PHASE2_START = "2025-10-01"

all_logs = []
summary_rows = []

print(f"🚀 开始超级回测: {len(STOCK_POOL)} 只股票 | {START_DATE} ~ {END_DATE}")
print("="*60)

for code in STOCK_POOL:
    print(f"Processing {code}...")
    
    # 1. Run Engines (V1, V2, V3)
    engines = {
        "V1 (MA5激进)": "backtest_engine.py",
        "V2 (MA10稳健)": "backtest_engine_v2.py",
        "V3 (布林震荡)": "backtest_engine_v3.py"
    }
    
    stock_results = {} # Store ROI for summary
    stock_benchmark_full = 0.0
    stock_benchmark_p1 = 0.0
    stock_benchmark_p2 = 0.0
    stock_name = code
    
    # Run each engine
    engine_dfs = {}
    
    for strategy_name, script in engines.items():
        try:
            # Execute script
            subprocess.run([sys.executable, script, code, "--start", START_DATE, "--end", END_DATE], 
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Read CSV
            csv_name = f"backtest_{script.split('.')[0].split('_')[-1]}_{code}.csv"
            # Special case for V1: backtest_engine.py -> backtest_v1
            if script == "backtest_engine.py": csv_name = f"backtest_v1_{code}.csv"
            
            if os.path.exists(csv_name):
                df = pd.read_csv(csv_name)
                df['date'] = pd.to_datetime(df['日期'])
                df['策略'] = strategy_name
                df['股票'] = code
                stock_name = df.iloc[0].get('股票名称', code) # Try get name
                if '收盘' not in df.columns:
                     # V3 might have different columns? V3 has '收盘'
                     pass
                
                engine_dfs[strategy_name] = df
                all_logs.append(df)
            else:
                print(f"⚠️ {strategy_name} for {code} produced no output.")
                engine_dfs[strategy_name] = pd.DataFrame()

        except Exception as e:
            print(f"❌ Error running {strategy_name} for {code}: {e}")
            engine_dfs[strategy_name] = pd.DataFrame()

    # 2. Calculate Stats (Full, P1, P2)
    # Using V1 data for benchmark is fine
    if "V1 (MA5激进)" in engine_dfs and not engine_dfs["V1 (MA5激进)"].empty:
        df_bench = engine_dfs["V1 (MA5激进)"]
        
        def calc_roi(df_segment):
            if df_segment.empty: return 0.0
            start_val = df_segment.iloc[0]['收盘']
            end_val = df_segment.iloc[-1]['收盘']
            return (end_val - start_val) / start_val * 100

        def calc_strategy_roi(df_full, start_d, end_d):
            if df_full.empty: return 0.0
            mask = (df_full['date'] >= start_d) & (df_full['date'] <= end_d)
            seg = df_full.loc[mask]
            if seg.empty: return 0.0
            # Strategy ROI is based on asset
            # But asset is cumulative. 
            # ROI for a period = (EndAsset - StartAsset) / StartAsset
            # Note: StartAsset for a period is the asset at the beginning of that period
            s_asset = seg.iloc[0]['总资产']
            e_asset = seg.iloc[-1]['总资产']
            return (e_asset - s_asset) / s_asset * 100

        # Benchmark Segments
        bench_full = calc_roi(df_bench)
        bench_p1 = calc_roi(df_bench[df_bench['date'] <= PHASE1_END])
        bench_p2 = calc_roi(df_bench[df_bench['date'] >= PHASE2_START])
        
        row_data = {
            "代码": code,
            "名称": stock_name,
            # Benchmark
            "基准_全": f"{bench_full:.2f}%",
            "基准_P1(1-9月)": f"{bench_p1:.2f}%",
            "基准_P2(10-12月)": f"{bench_p2:.2f}%",
        }
        
        # Strategy Stats
        for s_name, df_s in engine_dfs.items():
            roi_full = calc_strategy_roi(df_s, START_DATE, END_DATE)
            roi_p1 = calc_strategy_roi(df_s, START_DATE, PHASE1_END)
            roi_p2 = calc_strategy_roi(df_s, PHASE2_START, END_DATE)
            
            prefix = s_name.split(' ')[0] # V1, V2, V3
            row_data[f"{prefix}_全"] = f"{roi_full:.2f}%"
            row_data[f"{prefix}_P1"] = f"{roi_p1:.2f}%"
            row_data[f"{prefix}_P2"] = f"{roi_p2:.2f}%"
            
        summary_rows.append(row_data)

# 3. Save to Excel
print("\n💾 正在保存 Excel 报表...")
df_summary = pd.DataFrame(summary_rows)
# Reorder columns nicely
cols = ['代码', '名称', 
        '基准_全', 'V1_全', 'V2_全', 'V3_全',
        '基准_P1(1-9月)', 'V1_P1', 'V2_P1', 'V3_P1',
        '基准_P2(10-12月)', 'V1_P2', 'V2_P2', 'V3_P2']
# Filter existing cols
final_cols = [c for c in cols if c in df_summary.columns]
df_summary = df_summary[final_cols]

if all_logs:
    df_logs = pd.concat(all_logs, ignore_index=True)
else:
    df_logs = pd.DataFrame()

excel_file = "2025_Strategy_Grand_Battle.xlsx"
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df_summary.to_excel(writer, sheet_name="收益率大比拼", index=False)
    df_logs.to_excel(writer, sheet_name="交易流水详情", index=False)

print(f"✅ 任务完成！文件已生成: {excel_file}")
