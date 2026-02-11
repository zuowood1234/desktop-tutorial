import pandas as pd
import numpy as np
import os

# ==========================================
# 📊 V4 策略深度分析报告生成器
# ==========================================

EXCEL_FILE = "2025_Strategy_Battle_V4.xlsx"

if not os.path.exists(EXCEL_FILE):
    print("❌ 找不到回测文件！")
    exit(1)

# 读取数据
df_summary = pd.read_excel(EXCEL_FILE, sheet_name="策略收益对比总表")
df_logs = pd.read_excel(EXCEL_FILE, sheet_name="全部交易流水")

print("="*80)
print("🏆 策略深度对比分析报告")
print("="*80)

# ==========================================
# 1. 整体表现对比
# ==========================================
print("\n【一、整体表现对比】")
print("-"*80)

# 提取收益率数据（去掉%符号并转为float）
def parse_percentage(col):
    return df_summary[col].str.rstrip('%').astype(float)

strategies = ['基准', 'V1', 'V2', 'V3', 'V4']
periods = ['2025全年', '1-9月', '10-12月']

results = {}
for period in periods:
    print(f"\n📅 时间段：{period}")
    print(f"{'策略':<12} {'平均收益%':<12} {'中位数%':<12} {'最大值%':<12} {'最小值%':<12} {'胜率%':<12}")
    print("-"*80)
    
    for strategy in strategies:
        col_name_map = {
            '2025全年': f"{strategy}_2025全年" if strategy != '基准' else "基准_2025全年",
            '1-9月': f"{strategy}_1-9月" if strategy != '基准' else "基准_1-9月(震荡)",
            '10-12月': f"{strategy}_10-12月" if strategy != '基准' else "基准_10-12月(牛市)"
        }
        
        col_name = col_name_map[period]
        if col_name in df_summary.columns:
            data = parse_percentage(col_name)
            avg = data.mean()
            median = data.median()
            max_val = data.max()
            min_val = data.min()
            win_rate = (data > 0).sum() / len(data) * 100
            
            results[f"{strategy}_{period}"] = {
                'avg': avg,
                'median': median,
                'max': max_val,
                'min': min_val,
                'win_rate': win_rate
            }
            
            print(f"{strategy:<12} {avg:>11.2f} {median:>11.2f} {max_val:>11.2f} {min_val:>11.2f} {win_rate:>11.1f}")

# ==========================================
# 2. V4 相对优势分析
# ==========================================
print("\n\n【二、V4 策略相对优势】")
print("-"*80)

for period in periods:
    print(f"\n📅 {period}：")
    
    col_v4 = f"V4_{period.split('(')[0]}" if period == '2025全年' else f"V4_{period.replace('(震荡)', '').replace('(牛市)', '').strip()}"
    col_base = f"基准_{period}"
    col_v1 = f"V1_{period.split('(')[0]}"
    col_v2 = f"V2_{period.split('(')[0]}"
    col_v3 = f"V3_{period.split('(')[0]}"
    
    # 简化列名匹配
    v4_cols = [c for c in df_summary.columns if 'V4' in c and period.split('(')[0] in c]
    v1_cols = [c for c in df_summary.columns if 'V1' in c and period.split('(')[0] in c]
    v2_cols = [c for c in df_summary.columns if 'V2' in c and period.split('(')[0] in c]
    v3_cols = [c for c in df_summary.columns if 'V3' in c and period.split('(')[0] in c]
    base_cols = [c for c in df_summary.columns if '基准' in c and period.split('(')[0] in c]
    
    if v4_cols and v1_cols and v2_cols and v3_cols and base_cols:
        v4_data = parse_percentage(v4_cols[0])
        v1_data = parse_percentage(v1_cols[0])
        v2_data = parse_percentage(v2_cols[0])
        v3_data = parse_percentage(v3_cols[0])
        base_data = parse_percentage(base_cols[0])
        
        # 胜率统计
        v4_vs_base = (v4_data > base_data).sum()
        v4_vs_v1 = (v4_data > v1_data).sum()
        v4_vs_v2 = (v4_data > v2_data).sum()
        v4_vs_v3 = (v4_data > v3_data).sum()
        total = len(v4_data)
        
        print(f"  V4 跑赢基准: {v4_vs_base}/{total} ({v4_vs_base/total*100:.1f}%)")
        print(f"  V4 跑赢 V1:  {v4_vs_v1}/{total} ({v4_vs_v1/total*100:.1f}%)")
        print(f"  V4 跑赢 V2:  {v4_vs_v2}/{total} ({v4_vs_v2/total*100:.1f}%)")
        print(f"  V4 跑赢 V3:  {v4_vs_v3}/{total} ({v4_vs_v3/total*100:.1f}%)")
        
        # 平均超额收益
        print(f"  平均超额收益 (vs 基准): {(v4_data - base_data).mean():.2f}%")

# ==========================================
# 3. V4 最佳/最差案例
# ==========================================
print("\n\n【三、V4 表现极值案例】")
print("-"*80)

v4_full = parse_percentage([c for c in df_summary.columns if 'V4' in c and '2025全年' in c][0])
df_summary['V4_全年收益'] = v4_full

# Top 5
print("\n🏆 V4 表现最佳（Top 5）：")
top5 = df_summary.nlargest(5, 'V4_全年收益')[['代码', '名称', 'V4_全年收益']]
for idx, row in top5.iterrows():
    print(f"  {row['名称']:<12} ({row['代码']})  {row['V4_全年收益']:>8.2f}%")

# Bottom 5
print("\n📉 V4 表现最差（Bottom 5）：")
bottom5 = df_summary.nsmallest(5, 'V4_全年收益')[['代码', '名称', 'V4_全年收益']]
for idx, row in bottom5.iterrows():
    print(f"  {row['名称']:<12} ({row['代码']})  {row['V4_全年收益']:>8.2f}%")

# ==========================================
# 4. 交易行为分析（基于流水）
# ==========================================
print("\n\n【四、交易行为分析】")
print("-"*80)

for strategy in ['V1 (MA5激进)', 'V2 (MA10稳健)', 'V3 (布林震荡)', 'V4 (增强趋势)']:
    if '策略类型' in df_logs.columns:
        strategy_logs = df_logs[df_logs['策略类型'] == strategy]
    elif '策略' in df_logs.columns:
        strategy_logs = df_logs[df_logs['策略'] == strategy]
    else:
        continue
    
    if strategy_logs.empty:
        continue
    
    # 计算交易次数
    buy_count = (strategy_logs['操作'] == '全仓买入').sum()
    sell_count = (strategy_logs['操作'] == '清仓卖出').sum()
    
    # 计算平均持仓天数（简化版：总交易日/交易次数）
    total_days = len(strategy_logs)
    avg_holding = total_days / max(buy_count, 1)
    
    print(f"\n{strategy}:")
    print(f"  总交易次数: {buy_count + sell_count}")
    print(f"  买入次数: {buy_count}")
    print(f"  卖出次数: {sell_count}")
    print(f"  平均持仓周期: ~{avg_holding:.1f} 天")

# ==========================================
# 5. 风险指标对比
# ==========================================
print("\n\n【五、风险指标对比】")
print("-"*80)

print(f"\n{'策略':<12} {'最大亏损%':<12} {'亏损股票数':<15} {'平均亏损%':<12}")
print("-"*80)

for strategy in strategies:
    if strategy == '基准':
        col = '基准_2025全年'
    else:
        col = f"{strategy}_2025全年"
    
    if col in df_summary.columns:
        data = parse_percentage(col)
        max_loss = data.min()
        loss_count = (data < 0).sum()
        avg_loss = data[data < 0].mean() if loss_count > 0 else 0
        
        print(f"{strategy:<12} {max_loss:>11.2f} {loss_count:>14} {avg_loss:>11.2f}")

# ==========================================
# 6. 结论与建议
# ==========================================
print("\n\n【六、总结与建议】")
print("="*80)

v4_avg = results.get('V4_2025全年', {}).get('avg', 0)
v2_avg = results.get('V2_2025全年', {}).get('avg', 0)
v1_avg = results.get('V1_2025全年', {}).get('avg', 0)
base_avg = results.get('基准_2025全年', {}).get('avg', 0)

print(f"\n✅ V4 策略年化收益: {v4_avg:.2f}%")
print(f"   相比基准 ({base_avg:.2f}%)：{'✅ 超额' + str(v4_avg - base_avg) + '%' if v4_avg > base_avg else '❌ 落后' + str(base_avg - v4_avg) + '%'}")
print(f"   相比 V2  ({v2_avg:.2f}%)：{'✅ 更优' if v4_avg > v2_avg else '❌ 不如'}")
print(f"   相比 V1  ({v1_avg:.2f}%)：{'✅ 更优' if v4_avg > v1_avg else '❌ 不如'}")

# 震荡期表现
v4_p1 = results.get('V4_1-9月', {}).get('avg', 0)
v2_p1 = results.get('V2_1-9月', {}).get('avg', 0)
print(f"\n📊 震荡期（1-9月）表现:")
print(f"   V4: {v4_p1:.2f}%  |  V2: {v2_p1:.2f}%  →  V4 {'胜出' if v4_p1 > v2_p1 else '落后'} {abs(v4_p1 - v2_p1):.2f}%")

# 牛市期表现
v4_p2 = results.get('V4_10-12月', {}).get('avg', 0)
v2_p2 = results.get('V2_10-12月', {}).get('avg', 0)
print(f"\n📈 牛市期（10-12月）表现:")
print(f"   V4: {v4_p2:.2f}%  |  V2: {v2_p2:.2f}%  →  V4 {'胜出' if v4_p2 > v2_p2 else '落后'} {abs(v4_p2 - v2_p2):.2f}%")

print("\n🎯 核心发现:")
if v4_avg > base_avg:
    print(f"   1. V4 成功跑赢基准，Alpha = +{v4_avg - base_avg:.2f}%")
else:
    print(f"   1. V4 未能跑赢基准，需要进一步优化")

if v4_p1 > v2_p1:
    print(f"   2. 震荡期 V4 优于 V2，MA60过滤器起作用 ✅")
else:
    print(f"   2. 震荡期 V4 不如 V2，过滤器可能过于保守")

if v4_p2 > v2_p2:
    print(f"   3. 牛市期 V4 优于 V2，ATR止损保护利润 ✅")
else:
    print(f"   3. 牛市期 V4 不如 V2，可能提前止盈")

print("\n💡 下一步优化方向:")
print("   - 如果 V4 整体不如 V2：考虑放松 MA60 条件，或改为 MA30")
print("   - 如果震荡期亏损严重：增加 ADX 趋势强度过滤")
print("   - 如果牛市期跑输：调整 ATR 倍数从 2 倍改为 2.5~3 倍")
print("   - 考虑引入仓位管理：分批建仓/金字塔加仓")

print("\n" + "="*80)
print("分析完成！如需可视化图表或更多细节，请告知。")
