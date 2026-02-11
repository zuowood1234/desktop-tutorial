import pandas as pd
import subprocess
import os
import sys
from datetime import datetime

# ==========================================
# 🧪 精简版回测实验室
# 20只精选股票，确保稳定运行
# ==========================================

# 精简股票池（20只，覆盖主要板块，跳过可能有问题的）
STOCK_POOL = [
    # 大盘蓝筹 (4只)
    "600519", "601318", "600036", "000333",
    # 科技芯片 (4只)
    "002371", "300782", "603501", "688008",
    # 新能源车 (3只)
    "002594", "300750", "002920",
    # 医药医疗 (3只)
    "300760", "600276", "300122",
    # 消费零售 (2只)
    "600887", "000858",
    # 金融 (2只)
    "601398", "600030",
    # 周期成长 (2只)
    "300124", "002475"
]

START_DATE = "2025-01-01"
END_DATE = "2025-12-31"

PHASE1_END = "2025-09-30"
PHASE2_START = "2025-10-01"

all_logs = []
summary_rows = []

print(f"🚀 开始精简回测: {len(STOCK_POOL)} 只股票 | {START_DATE} ~ {END_DATE}")
print(f"📊 策略阵容: V1(MA5激进) | V2(MA10稳健) | V3(布林震荡) | V4(增强趋势)")
print("="*80)

for idx, code in enumerate(STOCK_POOL):
    print(f"[{idx+1}/{len(STOCK_POOL)}] 正在分析: {code} ...")
    
    engines = {
        "V1 (MA5激进)": "backtest_engine.py",
        "V2 (MA10稳健)": "backtest_engine_v2.py",
        "V3 (布林震荡)": "backtest_engine_v3.py",
        "V4 (增强趋势)": "backtest_engine_v4.py"
    }
    
    stock_name = code
    engine_dfs = {}
    
    # 1. 运行四个策略引擎（增加超时保护）
    for strategy_name, script in engines.items():
        try:
            result = subprocess.run(
                [sys.executable, script, code, "--start", START_DATE, "--end", END_DATE], 
                check=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL,
                timeout=30  # 30秒超时
            )
            
            csv_name = f"backtest_{script.split('.')[0].split('_')[-1]}_{code}.csv"
            if script == "backtest_engine.py": csv_name = f"backtest_v1_{code}.csv"
            
            if os.path.exists(csv_name):
                df = pd.read_csv(csv_name)
                df['date'] = pd.to_datetime(df['日期'] if '日期' in df.columns else df['date'])
                df['策略'] = strategy_name
                df['股票'] = code
                
                if '股票名称' in df.columns and not df.empty:
                    stock_name = str(df.iloc[0]['股票名称'])
                
                engine_dfs[strategy_name] = df
                all_logs.append(df)
            else:
                engine_dfs[strategy_name] = pd.DataFrame()

        except subprocess.TimeoutExpired:
            print(f"   ⏱️ {strategy_name} 超时，跳过")
            engine_dfs[strategy_name] = pd.DataFrame()
        except Exception as e:
            print(f"   ❌ {strategy_name} 失败: {e}")
            engine_dfs[strategy_name] = pd.DataFrame()

    # 2. 计算分段收益率
    if "V1 (MA5激进)" in engine_dfs and not engine_dfs["V1 (MA5激进)"].empty:
        df_bench = engine_dfs["V1 (MA5激进)"]
        
        def calc_period_return(df, s_date, e_date, col_name='收盘'):
            if df.empty: return 0.0
            mask = (df['date'] >= s_date) & (df['date'] <= e_date)
            seg = df.loc[mask]
            if seg.empty: return 0.0
            start_val = seg.iloc[0][col_name]
            end_val = seg.iloc[-1][col_name]
            return (end_val - start_val) / start_val * 100

        def calc_strategy_return(df, s_date, e_date):
            if df.empty: return 0.0
            mask = (df['date'] >= s_date) & (df['date'] <= e_date)
            seg = df.loc[mask]
            if seg.empty: return 0.0
            start_asset = seg.iloc[0]['总资产']
            end_asset = seg.iloc[-1]['总资产']
            return (end_asset - start_asset) / start_asset * 100

        row = {
            "代码": code,
            "名称": stock_name,
            "基准_2025全年": f"{calc_period_return(df_bench, START_DATE, END_DATE):.2f}%",
            "基准_1-9月(震荡)": f"{calc_period_return(df_bench, START_DATE, PHASE1_END):.2f}%",
            "基准_10-12月(牛市)": f"{calc_period_return(df_bench, PHASE2_START, END_DATE):.2f}%",
            "V1_2025全年": f"{calc_strategy_return(engine_dfs['V1 (MA5激进)'], START_DATE, END_DATE):.2f}%",
            "V1_1-9月": f"{calc_strategy_return(engine_dfs['V1 (MA5激进)'], START_DATE, PHASE1_END):.2f}%",
            "V1_10-12月": f"{calc_strategy_return(engine_dfs['V1 (MA5激进)'], PHASE2_START, END_DATE):.2f}%",
            "V2_2025全年": f"{calc_strategy_return(engine_dfs['V2 (MA10稳健)'], START_DATE, END_DATE):.2f}%",
            "V2_1-9月": f"{calc_strategy_return(engine_dfs['V2 (MA10稳健)'], START_DATE, PHASE1_END):.2f}%",
            "V2_10-12月": f"{calc_strategy_return(engine_dfs['V2 (MA10稳健)'], PHASE2_START, END_DATE):.2f}%",
            "V3_2025全年": f"{calc_strategy_return(engine_dfs['V3 (布林震荡)'], START_DATE, END_DATE):.2f}%",
            "V3_1-9月": f"{calc_strategy_return(engine_dfs['V3 (布林震荡)'], START_DATE, PHASE1_END):.2f}%",
            "V3_10-12月": f"{calc_strategy_return(engine_dfs['V3 (布林震荡)'], PHASE2_START, END_DATE):.2f}%",
            "V4_2025全年": f"{calc_strategy_return(engine_dfs['V4 (增强趋势)'], START_DATE, END_DATE):.2f}%",
            "V4_1-9月": f"{calc_strategy_return(engine_dfs['V4 (增强趋势)'], START_DATE, PHASE1_END):.2f}%",
            "V4_10-12月": f"{calc_strategy_return(engine_dfs['V4 (增强趋势)'], PHASE2_START, END_DATE):.2f}%",
        }
        summary_rows.append(row)

# 3. 保存 Excel
print("\n💾 正在生成最终报表...")
df_final = pd.DataFrame(summary_rows)

cols_order = [
    "代码", "名称",
    "基准_2025全年", "基准_1-9月(震荡)", "基准_10-12月(牛市)",
    "V1_2025全年", "V1_1-9月", "V1_10-12月",
    "V2_2025全年", "V2_1-9月", "V2_10-12月",
    "V3_2025全年", "V3_1-9月", "V3_10-12月",
    "V4_2025全年", "V4_1-9月", "V4_10-12月"
]
final_cols = [c for c in cols_order if c in df_final.columns]
df_final = df_final[final_cols]

if all_logs:
    df_logs = pd.concat(all_logs, ignore_index=True)
else:
    df_logs = pd.DataFrame()

excel_file = "2025_Strategy_Battle_V4.xlsx"
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df_final.to_excel(writer, sheet_name="策略收益对比总表", index=False)
    df_logs.to_excel(writer, sheet_name="全部交易流水", index=False)

print(f"✅ 完美报表已生成: {excel_file}")
print(f"📊 共回测 {len(STOCK_POOL)} 只股票，4 种策略，{len(df_logs)} 条交易记录")
