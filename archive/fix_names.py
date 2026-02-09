#!/usr/bin/env python3
import pandas as pd
from stock_names import STOCK_NAMES

# 读取并修正汇总数据
print("处理汇总数据...")
df = pd.read_csv('backtest_compare_summary.csv', encoding='utf-8-sig')

# 修正名称
df['名称'] = df['代码'].astype(str).apply(lambda x: STOCK_NAMES.get(x, x))

print("修正后的数据：")
print(df)

# 保存
df.to_csv('backtest_final_summary.csv', index=False, encoding='utf-8-sig')
print("\n✅ 保存成功: backtest_final_summary.csv")

# 读取并修正明细数据  
print("\n处理明细数据...")
df_detail = pd.read_csv('backtest_compare_details.csv', encoding='utf-8-sig')

if '名称' not in df_detail.columns:
    df_detail['名称'] = df_detail['代码'].astype(str).apply(lambda x: STOCK_NAMES.get(x, x))
else:
    df_detail['名称'] = df_detail['代码'].astype(str).apply(lambda x: STOCK_NAMES.get(x, x))

df_detail.to_csv('backtest_final_details.csv', index=False, encoding='utf-8-sig')
print(f"✅ 保存成功: backtest_final_details.csv ({len(df_detail)} 条记录)")
