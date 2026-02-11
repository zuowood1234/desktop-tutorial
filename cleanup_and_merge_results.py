import pandas as pd
import os
import glob
import subprocess
import sys

# 1. 目标股票池 (确保包含所有10只)
STOCK_POOL = {
    "000001": "平安银行",
    "600519": "贵州茅台",
    "300750": "宁德时代",
    "002594": "比亚迪",
    "601126": "四方股份",
    "002050": "三花智控",
    "601318": "中国平安",
    "000021": "深科技",   # 需检查
    "600030": "中信证券", # 需检查
    "300059": "东方财富"  # 需检查
}

START_DATE = "2025-01-01"
END_DATE = "2025-12-31"

print("🧹 开始执行数据清理与补全任务...")

# 2. 检查并补全缺失的回测
for code, name in STOCK_POOL.items():
    v1_file = f"backtest_v1_{code}.csv"
    v2_file = f"backtest_v2_{code}.csv"
    
    # 如果文件不存在，说明没跑或者是跑失败了 -> 重跑
    if not os.path.exists(v1_file) or not os.path.exists(v2_file):
        print(f"🔄 补全缺失回测: {name} ({code})...")
        try:
            # Run V1
            subprocess.run([sys.executable, "backtest_engine.py", code, "--start", START_DATE, "--end", END_DATE], check=True, stdout=subprocess.DEVNULL)
            # Run V2
            subprocess.run([sys.executable, "backtest_engine_v2.py", code, "--start", START_DATE, "--end", END_DATE], check=True, stdout=subprocess.DEVNULL)
            print(f"✅ {name} 补全成功")
        except Exception as e:
            print(f"❌ {name} 补全失败: {e}")

# 3. 合并所有结果
all_dfs = []
summary_data = []

print("\n📦 正在合并数据...")

for code, name in STOCK_POOL.items():
    v1_file = f"backtest_v1_{code}.csv"
    v2_file = f"backtest_v2_{code}.csv"
    
    if os.path.exists(v1_file) and os.path.exists(v2_file):
        # 读取 V1
        df_v1 = pd.read_csv(v1_file)
        df_v1['股票代码'] = code
        df_v1['股票名称'] = name
        df_v1['策略类型'] = 'V1_技术派_MA5'
        
        # 读取 V2
        df_v2 = pd.read_csv(v2_file)
        df_v2['股票代码'] = code
        df_v2['股票名称'] = name
        df_v2['策略类型'] = 'V2_稳健派_MA10'
        
        # 添加到大表
        all_dfs.extend([df_v1, df_v2])
        
        # 计算摘要数据
        initial = 100000
        v1_final = df_v1.iloc[-1]['总资产']
        v2_final = df_v2.iloc[-1]['总资产']
        
        v1_roi = (v1_final - initial) / initial * 100
        v2_roi = (v2_final - initial) / initial * 100
        
        # Benchmark
        c_start = df_v1.iloc[0]['收盘']
        c_end = df_v1.iloc[-1]['收盘']
        bench_roi = (c_end - c_start) / c_start * 100
        
        summary_data.append({
            "代码": code,
            "名称": name,
            "基准涨幅%": round(bench_roi, 2),
            "V1收益%": round(v1_roi, 2),
            "V2收益%": round(v2_roi, 2),
            "胜出策略": "V1" if v1_roi > v2_roi else "V2"
        })

# 4. 保存合并后的文件
if all_dfs:
    master_df = pd.concat(all_dfs, ignore_index=True)
    # 调整列顺序
    cols = ['股票代码', '股票名称', '策略类型', '日期', '收盘', 'AI建议', '操作', '持仓', '总资产']
    # 确保列存在
    final_cols = [c for c in cols if c in master_df.columns]
    master_df = master_df[final_cols]
    
    master_file = "backtest_results_2025_FULL.csv"
    master_df.to_csv(master_file, index=False, encoding='utf-8-sig')
    print(f"✅ 所有详情已合并至: {master_file}")
    
    # 保存摘要
    summary_df = pd.DataFrame(summary_data)
    summary_file = "backtest_summary_2025_FINAL.csv"
    summary_df.to_csv(summary_file, index=False, encoding='utf-8-sig')
    print(f"✅ 最终摘要已保存: {summary_file}")
    print("\n" + summary_df.to_markdown(index=False))

# 5. 清理零碎文件
print("\n🗑️ 开始清理临时文件...")
deleted_count = 0
for f in glob.glob("backtest_v*_[0-9]*.csv"):
    try:
        os.remove(f)
        deleted_count += 1
    except:
        pass
print(f"✨ 已删除 {deleted_count} 个临时 CSV 文件。")
print("🎉 任务全部完成！")
