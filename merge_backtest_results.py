#!/usr/bin/env python3
"""
合并两批回测数据，并修正股票名称
"""

import pandas as pd
from stock_names import STOCK_NAMES

# 读取现有的CSV文件
print("📂 正在读取CSV文件...")

# 1. 查找所有的summary文件
import glob
import os

summary_files = glob.glob("backtest_compare_summary*.csv")
detail_files = glob.glob("backtest_compare_details*.csv")

print(f"找到 {len(summary_files)} 个汇总文件")
print(f"找到 {len(detail_files)} 个明细文件")

# 2. 合并所有汇总数据
all_summaries = []
for file in summary_files:
    try:
        df = pd.read_csv(file, encoding='utf-8-sig')
        print(f"  ✅ {file}: {len(df)} 条记录")
        all_summaries.append(df)
    except Exception as e:
        print(f"  ❌ {file}: {e}")

# 3. 合并所有明细数据
all_details = []
for file in detail_files:
    try:
        df = pd.read_csv(file, encoding='utf-8-sig')
        print(f"  ✅ {file}: {len(df)} 条记录")
        all_details.append(df)
    except Exception as e:
        print(f"  ❌ {file}: {e}")

# 4. 合并DataFrame并去重
if all_summaries:
    merged_summary = pd.concat(all_summaries, ignore_index=True)
    # 按代码去重，保留最新的
    merged_summary = merged_summary.drop_duplicates(subset=['代码'], keep='last')
    
    # 修正股票名称
    merged_summary['名称'] = merged_summary['代码'].apply(
        lambda x: STOCK_NAMES.get(x, x)
    )
    
    print(f"\n✅ 汇总数据合并完成：{len(merged_summary)} 只股票")
    print(merged_summary[['代码', '名称', '纯技术(90天)', '情绪增强(90天)', '基准(90天)']])
    
    # 保存
    merged_summary.to_csv('backtest_final_summary.csv', index=False, encoding='utf-8-sig')
    print("\n💾 已保存: backtest_final_summary.csv")

if all_details:
    merged_details = pd.concat(all_details, ignore_index=True)
    # 按代码+日期去重
    merged_details = merged_details.drop_duplicates(subset=['代码', '日期'], keep='last')
    
    # 修正股票名称
    if '名称' in merged_details.columns:
        merged_details['名称'] = merged_details['代码'].apply(
            lambda x: STOCK_NAMES.get(x, x)
        )
    
    print(f"\n✅ 明细数据合并完成：{len(merged_details)} 条记录")
    
    # 保存
    merged_details.to_csv('backtest_final_details.csv', index=False, encoding='utf-8-sig')
    print("💾 已保存: backtest_final_details.csv")

print("\n🎉 合并完成！")
print("\n生成的文件：")
print("  📊 backtest_final_summary.csv - 完整汇总")
print("  📋 backtest_final_details.csv - 完整明细")
