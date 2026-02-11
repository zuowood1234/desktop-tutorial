import pandas as pd
import numpy as np

# ==========================================
# 📅 四策略月度对比（简化直接版）
# ==========================================

df_logs = pd.read_excel('2025_Complete_Strategy_Battle.xlsx', sheet_name='全部交易流水')

# 确保日期和月份列
df_logs['date'] = pd.to_datetime(df_logs['日期'] if '日期' in df_logs.columns else df_logs['date'])
df_logs['year_month'] = df_logs['date'].dt.to_period('M')

print("="*120)
print("📅 2025年月度收益率对比分析（V1/V2/V3/V4完整版）")
print("="*120)

# 所有月份
all_months = sorted(df_logs['year_month'].unique())
print(f"\n发现月份：{len(all_months)} 个月")

# 所有策略
all_strategies = ['V1 (MA5激进)', 'V2 (MA10稳健)', 'V3 (布林震荡)', 'V4 (增强趋势)']
print(f"策略：{all_strategies}\n")

# 存储每个策略每个月的收益率
monthly_data = {}

for strategy in all_strategies:
    monthly_returns = []
    
    # 该策略的所有股票
    strategy_logs = df_logs[df_logs['策略'] == strategy]
    stocks = strategy_logs['股票'].unique() if '股票' in strategy_logs.columns else strategy_logs['股票代码'].unique()
    
    print(f"{strategy}: {len(stocks)} 只股票")
    
    for month in all_months:
        month_rets = []
        
        # 每只股票在该月的收益
        for stock in stocks:
            stock_col = '股票' if '股票' in strategy_logs.columns else '股票代码'
            month_data = strategy_logs[(strategy_logs[stock_col] == stock) & (strategy_logs['year_month'] == month)]
            
            if not month_data.empty:
                start_asset = month_data.iloc[0]['总资产']
                end_asset = month_data.iloc[-1]['总资产']
                if start_asset > 0:
                    ret = (end_asset - start_asset) / start_asset * 100
                    month_rets.append(ret)
        
        # 该月平均收益
        if month_rets:
            monthly_returns.append(np.mean(month_rets))
        else:
            monthly_returns.append(0.0)
    
    monthly_data[strategy] = monthly_returns

# 创建DataFrame
df_monthly = pd.DataFrame(monthly_data, index=[str(m) for m in all_months])

# ==========================================
# 【一、月度收益率表格】
# ==========================================
print("\n\n【一、月度收益率对比表】")
print("-"*120)

# 打印表头
print(f"{'月份':<12}", end="")
for strategy in all_strategies:
    short = strategy.split(' ')[0]
    print(f"{short:>12}", end="")
print()
print("-"*120)

# 打印数据
for month in df_monthly.index:
    print(f"{month:<12}", end="")
    for strategy in all_strategies:
        val = df_monthly.loc[month, strategy]
        print(f"{val:>11.2f}%", end="")
    print()

# 年度平均
print("-" *120)
print(f"{'年度平均':<12}", end="")
for strategy in all_strategies:
    avg = df_monthly[strategy].mean()
    print(f"{avg:>11.2f}%", end="")
print("\n")

# ==========================================
# 【二、月度统计】
# ==========================================
print("\n【二、月度统计摘要】")
print("-"*120)

print(f"{'策略':<25} {'平均月收益%':<15} {'最佳月%':<15} {'最差月%':<15} {'盈利月数/12':<15} {'月胜率%':<10}")
print("-"*120)

for strategy in all_strategies:
    data = df_monthly[strategy]
    avg = data.mean()
    best = data.max()
    worst = data.min()
    win_months = (data > 0).sum()
    win_rate = win_months / 12 * 100
    
    short = strategy.split('(')[0].strip()
    print(f"{short:<25} {avg:>14.2f} {best:>14.2f} {worst:>14.2f} {win_months:>7}/12      {win_rate:>9.1f}")

# ==========================================
# 【三、策略对抗】
# ==========================================
print("\n\n【三、策略月度对抗矩阵】")
print("-"*120)

# V1 vs 其他
print(f"\nV1 月度胜率：")
v1_data = df_monthly['V1 (MA5激进)']
for other_name in ['V2 (MA10稳健)', 'V3 (布林震荡)', 'V4 (增强趋势)']:
    other_data = df_monthly[other_name]
    wins = (v1_data > other_data).sum()
    print(f"  V1 vs {other_name.split('(')[0].strip():<12}: {wins:>2}/12 月  ({wins/12*100:>5.1f}%)")

# V2 vs 其他
print(f"\nV2 月度胜率：")
v2_data = df_monthly['V2 (MA10稳健)']
for other_name in ['V1 (MA5激进)', 'V3 (布林震荡)', 'V4 (增强趋势)']:
    other_data = df_monthly[other_name]
    wins = (v2_data > other_data).sum()
    print(f"  V2 vs {other_name.split('(')[0].strip():<12}: {wins:>2}/12 月  ({wins/12*100:>5.1f}%)")

# V4 vs 其他
print(f"\nV4 月度胜率：")
v4_data = df_monthly['V4 (增强趋势)']
for other_name in ['V1 (MA5激进)', 'V2 (MA10稳健)', 'V3 (布林震荡)']:
    other_data = df_monthly[other_name]
    wins = (v4_data > other_data).sum()
    print(f"  V4 vs {other_name.split('(')[0].strip():<12}: {wins:>2}/12 月  ({wins/12*100:>5.1f}%)")

# ==========================================
# 【四、总结】
# ==========================================
print("\n\n【四、总结】")
print("="*120)

# 找出年度最佳/最差
best_avg = df_monthly.mean().max()
worst_avg = df_monthly.mean().min()
best_strategy = df_monthly.mean().idxmax()
worst_strategy = df_monthly.mean().idxmin()

print(f"\n🏆 年度最佳策略: {best_strategy.split('(')[0].strip()}  (平均月收益 {best_avg:.2f}%)")
print(f"📉 年度最差策略: {worst_strategy.split('(')[0].strip()}  (平均月收益 {worst_avg:.2f}%)")

# V4 vs V2 对比
v4_avg = df_monthly['V4 (增强趋势)'].mean()
v2_avg = df_monthly['V2 (MA10稳健)'].mean()
v4_wins_v2 = (df_monthly['V4 (增强趋势)'] > df_monthly['V2 (MA10稳健)']).sum()

print(f"\n🎯 V4 vs V2 详细对比:")
print(f"  平均月收益: V4={v4_avg:.2f}%  VS  V2={v2_avg:.2f}%")
print(f"  月度对抗:   V4 在 {v4_wins_v2}/12 个月跑赢 V2 ({v4_wins_v2/12*100:.1f}%)")
print(f"  结论: {'V4更优' if v4_avg > v2_avg else 'V2更优'}")

# 保存
df_monthly.to_csv('monthly_comparison_complete.csv')
print(f"\n💾 数据已保存至: monthly_comparison_complete.csv")

print("\n" + "="*120)
