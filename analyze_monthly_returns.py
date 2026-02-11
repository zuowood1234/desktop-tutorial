import pandas as pd
import numpy as np
import os

# ==========================================
# 📅 月度收益率对比分析（优化版）
# ==========================================

EXCEL_FILE = "2025_Complete_Strategy_Battle.xlsx"

if not os.path.exists(EXCEL_FILE):
    print("❌ 找不到回测文件！")
    exit(1)

# 读取交易流水数据
df_logs = pd.read_excel(EXCEL_FILE, sheet_name="全部交易流水")

# 确保日期列格式正确
if '日期' in df_logs.columns:
    df_logs['date'] = pd.to_datetime(df_logs['日期'])
else:
    df_logs['date'] = pd.to_datetime(df_logs['date'])

# 提取年月
df_logs['year_month'] = df_logs['date'].dt.to_period('M')

# 策略列名
strategy_col = '策略类型' if '策略类型' in df_logs.columns else '策略'
stock_col = '股票代码' if '股票代码' in df_logs.columns else ('股票' if '股票' in df_logs.columns else '代码')

print("="*120)
print("📅 2025年月度收益率对比分析")
print("="*120)

# 策略列表
strategies = df_logs[strategy_col].unique()
strategies_sorted = sorted([s for s in strategies if isinstance(s, str) and s])

print(f"\n发现策略：{strategies_sorted}")

# 获取所有月份
all_months = sorted(df_logs['year_month'].unique())
print(f"月份范围：{all_months[0]} ~ {all_months[-1]}")

# ==========================================
# 核心：计算每个策略每个月的平均收益率
# 逻辑：每个策略可能同时操作多只股票，我们需要先算出每只股票每月的收益，再平均
# ==========================================

monthly_returns_dict = {}

for strategy in strategies_sorted:
    print(f"\n处理策略: {strategy}...")
    
    monthly_rets_all_stocks = []
    
    # 获取该策略涉及的所有股票
    stocks = df_logs[df_logs[strategy_col] == strategy][stock_col].unique()
    print(f"  包含 {len(stocks)} 只股票")
    
    for month in all_months:
        month_returns = []
        
        # 对每只股票计算该月收益
        for stock in stocks:
            mask = (df_logs[strategy_col] == strategy) & (df_logs[stock_col] == stock) & (df_logs['year_month'] == month)
            stock_month_data = df_logs[mask]
            
            if stock_month_data.empty:
                continue
            
            # 该股票该月的收益率
            start_asset = stock_month_data.iloc[0]['总资产']
            end_asset = stock_month_data.iloc[-1]['总资产']
            
            if start_asset > 0:
                ret = (end_asset - start_asset) / start_asset * 100
                month_returns.append(ret)
        
        # 所有股票的平均月收益
        if month_returns:
            avg_month_ret = np.mean(month_returns)
        else:
            avg_month_ret = 0.0
        
        monthly_rets_all_stocks.append(avg_month_ret)
    
    monthly_returns_dict[strategy] = monthly_rets_all_stocks

# ==========================================
# 1. 月度收益率表格
# ==========================================
print("\n\n【一、月度收益率对比表】")
print("-"*120)

# 构建DataFrame
df_monthly = pd.DataFrame(monthly_returns_dict, index=[str(m) for m in all_months])

# 打印表头
print(f"{'月份':<15}", end="")
for strategy in strategies_sorted:
    short_name = strategy.replace(' (', '\n(').split('\n')[0]  # 去掉括号部分
    print(f"{short_name:>15}", end="")
print()
print("-"*120)

# 打印数据
for month in df_monthly.index:
    print(f"{month:<15}", end="")
    for strategy in strategies_sorted:
        val = df_monthly.loc[month, strategy]
        print(f"{val:>14.2f}%", end="")
    print()

# 打印年度总计
print("-"*120)
print(f"{'年度平均':<15}", end="")
for strategy in strategies_sorted:
    avg = df_monthly[strategy].mean()
    print(f"{avg:>14.2f}%", end="")
print()

# ==========================================
# 2. 月度统计
# ==========================================
print("\n\n【二、月度统计摘要】")
print("-"*120)

print(f"\n{'策略':<25} {'平均月收益%':<15} {'最佳月%':<15} {'最差月%':<15} {'盈利月数':<12} {'月胜率%':<10}")
print("-"*120)

for strategy in strategies_sorted:
    data = df_monthly[strategy]
    avg = data.mean()
    best = data.max()
    worst = data.min()
    win_months = (data > 0).sum()
    win_rate = win_months / len(data) * 100
    
    short_name = strategy.split('(')[0].strip()
    print(f"{short_name:<25} {avg:>14.2f} {best:>14.2f} {worst:>14.2f} {win_months:>11} {win_rate:>9.1f}")

# ==========================================
# 3. V4 vs 其他策略
# ==========================================
print("\n\n【三、V4 月度对抗胜率】")
print("-"*120)

v4_strategy = [s for s in strategies_sorted if 'V4' in s]
if v4_strategy:
    v4_strategy = v4_strategy[0]
    v4_data = df_monthly[v4_strategy]
    
    print(f"\nV4 在每个月打败其他策略的次数：")
    for strategy in strategies_sorted:
        if strategy == v4_strategy:
            continue
        
        other_data = df_monthly[strategy]
        wins = (v4_data > other_data).sum()
        total = len(v4_data)
        win_rate = wins / total * 100
        
        short_name = strategy.split('(')[0].strip()
        print(f"  V4 vs {short_name:<12}: {wins:>2}/{total} 月  ({win_rate:>5.1f}%)")

# ==========================================
# 4. 保存到CSV
# ==========================================
csv_file = "monthly_returns_comparison.csv"
df_monthly.to_csv(csv_file)
print(f"\n\n💾 月度数据已保存至: {csv_file}")

# ==========================================
# 5. 关键发现
# ==========================================
print("\n\n【四、关键发现】")
print("="*120)

best_strategy = df_monthly.mean().idxmax()
worst_strategy = df_monthly.mean().idxmin()

print(f"\n🏆 年度最佳策略: {best_strategy.split('(')[0].strip()}  (平均月收益 {df_monthly[best_strategy].mean():.2f}%)")
print(f"💔 年度最差策略: {worst_strategy.split('(')[0].strip()}  (平均月收益 {df_monthly[worst_strategy].mean():.2f}%)")

# 找出V4表现特别好/差的月份
if v4_strategy:
    v4_best_month = df_monthly[v4_strategy].idxmax()
    v4_worst_month = df_monthly[v4_strategy].idxmin()
    
    print(f"\n🎯 V4 表现分析:")
    print(f"  最佳月份: {v4_best_month} ({df_monthly.loc[v4_best_month, v4_strategy]:.2f}%)")
    print(f"  最差月份: {v4_worst_month} ({df_monthly.loc[v4_worst_month, v4_strategy]:.2f}%)")
    
    # 看看V4是否在震荡期（1-9月）表现更好
    phase1_months = [str(m) for m in all_months if int(str(m).split('-')[1]) <= 9]
    phase2_months = [str(m) for m in all_months if int(str(m).split('-')[1]) >= 10]
    
    if phase1_months and phase2_months:
        v4_phase1 = df_monthly.loc[phase1_months, v4_strategy].mean()
        v4_phase2 = df_monthly.loc[phase2_months, v4_strategy].mean()
        
        v2_strategy = [s for s in strategies_sorted if 'V2' in s][0] if any('V2' in s for s in strategies_sorted) else None
        if v2_strategy:
            v2_phase1 = df_monthly.loc[phase1_months, v2_strategy].mean()
            v2_phase2 = df_monthly.loc[phase2_months, v2_strategy].mean()
            
            print(f"\n📊 分段表现 (V4 vs V2):")
            print(f"  震荡期 (1-9月):  V4={v4_phase1:>6.2f}%  |  V2={v2_phase1:>6.2f}%  →  {'V4胜' if v4_phase1 > v2_phase1 else 'V2胜'}")
            print(f"  牛市期 (10-12月): V4={v4_phase2:>6.2f}%  |  V2={v2_phase2:>6.2f}%  →  {'V4胜' if v4_phase2 > v2_phase1 else 'V2胜'}")

print("\n" + "="*120)
