import pandas as pd
import os
import glob

# ==========================================
# 🔧 完整数据合并修复脚本
# 从所有 backtest_v*.csv 文件中提取数据并合并
# ==========================================

print("🔧 开始合并所有策略的回测数据...")

# 股票池（20只）
STOCK_POOL = [
    "600519", "601318", "600036", "000333", "002371",
    "300782", "603501", "688008", "002594", "300750",
    "002920", "300760", "600276", "300122", "600887",
    "000858", "601398", "600030", "300124", "002475"
]

START_DATE = "2025-01-01"
END_DATE = "2025-12-31"
PHASE1_END = "2025-09-30"
PHASE2_START = "2025-10-01"

all_logs = []
summary_rows = []

# ==========================================
# 1. 读取所有CSV文件
# ==========================================

print("\n【一、读取所有策略CSV文件】")
print("-"*80)

for idx, code in enumerate(STOCK_POOL):
    print(f"[{idx+1}/{len(STOCK_POOL)}] 处理股票: {code} ...")
    
    stock_name = code
    engine_dfs = {}
    
    # V1
    v1_file = f"backtest_v1_{code}.csv"
    if os.path.exists(v1_file):
        df = pd.read_csv(v1_file)
        df['date'] = pd.to_datetime(df['日期'] if '日期' in df.columns else df['date'])
        df['策略'] = "V1 (MA5激进)"
        df['股票'] = code
        if '股票名称' in df.columns and not df.empty:
            stock_name = str(df.iloc[0]['股票名称'])
        engine_dfs["V1 (MA5激进)"] = df
        all_logs.append(df)
        print(f"  ✅ V1: {len(df)} 条记录")
    else:
        print(f"  ⚠️ V1: 文件不存在")
    
    # V2
    v2_file = f"backtest_v2_{code}.csv"
    if os.path.exists(v2_file):
        df = pd.read_csv(v2_file)
        df['date'] = pd.to_datetime(df['日期'] if '日期' in df.columns else df['date'])
        df['策略'] = "V2 (MA10稳健)"
        df['股票'] = code
        if '股票名称' in df.columns and not df.empty:
            stock_name = str(df.iloc[0]['股票名称'])
        engine_dfs["V2 (MA10稳健)"] = df
        all_logs.append(df)
        print(f"  ✅ V2: {len(df)} 条记录")
    else:
        print(f"  ⚠️ V2: 文件不存在")
    
    # V3
    v3_file = f"backtest_v3_{code}.csv"
    if os.path.exists(v3_file):
        df = pd.read_csv(v3_file)
        df['date'] = pd.to_datetime(df['日期'] if '日期' in df.columns else df['date'])
        df['策略'] = "V3 (布林震荡)"
        df['股票'] = code
        if '股票名称' in df.columns and not df.empty:
            stock_name = str(df.iloc[0]['股票名称'])
        engine_dfs["V3 (布林震荡)"] = df
        all_logs.append(df)
        print(f"  ✅ V3: {len(df)} 条记录")
    else:
        print(f"  ⚠️ V3: 文件不存在")
    
    # V4
    v4_file = f"backtest_v4_{code}.csv"
    if os.path.exists(v4_file):
        df = pd.read_csv(v4_file)
        df['date'] = pd.to_datetime(df['日期'] if '日期' in df.columns else df['date'])
        df['策略'] = "V4 (增强趋势)"
        df['股票'] = code
        if '股票名称' in df.columns and not df.empty:
            stock_name = str(df.iloc[0]['股票名称'])
        engine_dfs["V4 (增强趋势)"] = df
        all_logs.append(df)
        print(f"  ✅ V4: {len(df)} 条记录")
    else:
        print(f"  ⚠️ V4: 文件不存在")
    
    # ==========================================
    # 2. 计算分段收益率
    # ==========================================
    
    if engine_dfs:
        # 使用任一有数据的策略作为基准数据源
        df_bench = None
        for df in engine_dfs.values():
            if not df.empty:
                df_bench = df
                break
        
        if df_bench is not None:
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
            }
            
            # 添加各策略数据
            for strategy_name in ["V1 (MA5激进)", "V2 (MA10稳健)", "V3 (布林震荡)", "V4 (增强趋势)"]:
                if strategy_name in engine_dfs:
                    df = engine_dfs[strategy_name]
                    prefix = strategy_name.split(' ')[0]
                    row[f"{prefix}_2025全年"] = f"{calc_strategy_return(df, START_DATE, END_DATE):.2f}%"
                    row[f"{prefix}_1-9月"] = f"{calc_strategy_return(df, START_DATE, PHASE1_END):.2f}%"
                    row[f"{prefix}_10-12月"] = f"{calc_strategy_return(df, PHASE2_START, END_DATE):.2f}%"
                else:
                    prefix = strategy_name.split(' ')[0]
                    row[f"{prefix}_2025全年"] = "N/A"
                    row[f"{prefix}_1-9月"] = "N/A"
                    row[f"{prefix}_10-12月"] = "N/A"
            
            summary_rows.append(row)

# ==========================================
# 3. 保存完整Excel
# ==========================================

print("\n【二、生成Excel报表】")
print("-"*80)

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
    print(f"✅ 成功合并 {len(df_logs)} 条交易记录")
else:
    df_logs = pd.DataFrame()
    print("⚠️ 没有找到任何交易记录")

excel_file = "2025_Complete_Strategy_Battle.xlsx"
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df_final.to_excel(writer, sheet_name="策略收益对比总表", index=False)
    df_logs.to_excel(writer, sheet_name="全部交易流水", index=False)

print(f"\n✅ 完整报表已生成: {excel_file}")
print(f"📊 汇总表: {len(df_final)} 只股票")
print(f"📊 交易流水: {len(df_logs)} 条记录")

# 统计各策略记录数
if not df_logs.empty and '策略' in df_logs.columns:
    print("\n各策略记录统计:")
    for strategy in df_logs['策略'].unique():
        if pd.notna(strategy):
            count = (df_logs['策略'] == strategy).sum()
            print(f"  {strategy}: {count} 条")

print("\n🎉 任务完成！")
