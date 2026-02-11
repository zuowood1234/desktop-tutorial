import pandas as pd
import numpy as np

# ==========================================
# 📊 新股票池月度策略详细对比
# ==========================================

print("🔍 正在生成新股票池的超详细月度对比数据...")

df_logs = pd.read_excel('2025_新股票池回测报告.xlsx', sheet_name='全部交易流水')

# 日期处理
df_logs['date'] = pd.to_datetime(df_logs['日期'] if '日期' in df_logs.columns else df_logs['date'])
df_logs['year_month'] = df_logs['date'].dt.to_period('M')

# 获取所有月份
all_months = sorted(df_logs['year_month'].unique())

# 智能选择股票列
stock_col = '股票' if '股票' in df_logs.columns and df_logs['股票'].notna().sum() > 0 else '股票代码'
all_stocks = sorted(df_logs[stock_col].dropna().unique())

print(f"\n发现 {len(all_stocks)} 只股票，{len(all_months)} 个月")
print(f"使用列名: {stock_col}")
print("="*100)

# 结果存储
detailed_results = []

# 对每只股票进行分析
for idx, stock in enumerate(all_stocks):
    print(f"[{idx+1}/{len(all_stocks)}] 处理股票: {stock}...")
    
    # 获取股票名称
    stock_name = str(stock)
    stock_data_sample = df_logs[df_logs[stock_col] == stock]
    if '股票名称' in stock_data_sample.columns and not stock_data_sample.empty:
        name_val = stock_data_sample.iloc[0]['股票名称']
        if pd.notna(name_val):
            stock_name = str(name_val)
    
    # 对每个月份进行分析
    for month in all_months:
        month_str = str(month)
        
        row_data = {
            '股票代码': str(stock),
            '股票名称': stock_name,
            '月份': month_str
        }
        
        # 基准收益率
        month_price_data = df_logs[(df_logs[stock_col] == stock) & (df_logs['year_month'] == month)]
        
        if not month_price_data.empty:
            start_price = month_price_data.iloc[0]['收盘']
            end_price = month_price_data.iloc[-1]['收盘']
            benchmark_ret = (end_price - start_price) / start_price * 100
            row_data['基准收益率(%)'] = round(benchmark_ret, 2)
        else:
            row_data['基准收益率(%)'] = 0.0
        
        # 各策略收益率
        for strategy_name in ['V1 (MA5激进)', 'V2 (MA10稳健)', 'V3 (布林震荡)', 'V4 (增强趋势)']:
            strategy_data = df_logs[(df_logs['策略'] == strategy_name) & 
                                   (df_logs[stock_col] == stock) & 
                                   (df_logs['year_month'] == month)]
            
            if not strategy_data.empty:
                start_asset = strategy_data.iloc[0]['总资产']
                end_asset = strategy_data.iloc[-1]['总资产']
                
                if start_asset > 0:
                    strategy_ret = (end_asset - start_asset) / start_asset * 100
                else:
                    strategy_ret = 0.0
            else:
                strategy_ret = 0.0
            
            short_name = strategy_name.split(' ')[0]
            row_data[f'{short_name}收益率(%)'] = round(strategy_ret, 2)
        
        # 计算Alpha
        benchmark = row_data['基准收益率(%)']
        for prefix in ['V1', 'V2', 'V3', 'V4']:
            strategy_ret = row_data[f'{prefix}收益率(%)']
            alpha = strategy_ret - benchmark
            row_data[f'{prefix}_Alpha(%)'] = round(alpha, 2)
        
        # 找出最佳策略
        strategy_rets = {
            'V1': row_data['V1收益率(%)'],
            'V2': row_data['V2收益率(%)'],
            'V3': row_data['V3收益率(%)'],
            'V4': row_data['V4收益率(%)']
        }
        best_strategy = max(strategy_rets, key=strategy_rets.get)
        row_data['最佳策略'] = best_strategy
        row_data['最佳收益率(%)'] = round(strategy_rets[best_strategy], 2)
        
        detailed_results.append(row_data)

# 生成详细报表
df_detailed = pd.DataFrame(detailed_results)

cols_order = [
    '股票代码', '股票名称', '月份',
    '基准收益率(%)',
    'V1收益率(%)', 'V1_Alpha(%)',
    'V2收益率(%)', 'V2_Alpha(%)',
    'V3收益率(%)', 'V3_Alpha(%)',
    'V4收益率(%)', 'V4_Alpha(%)',
    '最佳策略', '最佳收益率(%)'
]

df_detailed = df_detailed[cols_order]

excel_file = "2025_新股票池月度详细对比.xlsx"

with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df_detailed.to_excel(writer, sheet_name='完整明细表', index=False)
    
    # 策略统计汇总
    summary_data = []
    for strategy in ['V1', 'V2', 'V3', 'V4']:
        total_count = len(df_detailed)
        beat_benchmark = (df_detailed[f'{strategy}_Alpha(%)'] > 0).sum()
        is_best = (df_detailed['最佳策略'] == strategy).sum()
        avg_ret = df_detailed[f'{strategy}收益率(%)'].mean()
        avg_alpha = df_detailed[f'{strategy}_Alpha(%)'].mean()
        
        summary_data.append({
            '策略': strategy,
            '样本数': total_count,
            '跑赢基准次数': beat_benchmark,
            '跑赢基准率(%)': round(beat_benchmark / total_count * 100, 1),
            '最佳策略次数': is_best,
            '最佳策略率(%)': round(is_best / total_count * 100, 1),
            '平均收益率(%)': round(avg_ret, 2),
            '平均Alpha(%)': round(avg_alpha, 2)
        })
    
    df_summary = pd.DataFrame(summary_data)
    df_summary.to_excel(writer, sheet_name='策略统计汇总', index=False)
    
    # 按月份汇总
    month_summary = []
    for month in all_months:
        month_str = str(month)
        month_data = df_detailed[df_detailed['月份'] == month_str]
        
        # 各策略平均表现
        v1_avg = month_data['V1收益率(%)'].mean()
        v2_avg = month_data['V2收益率(%)'].mean()
        v3_avg = month_data['V3收益率(%)'].mean()
        v4_avg = month_data['V4收益率(%)'].mean()
        benchmark_avg = month_data['基准收益率(%)'].mean()
        
        strategies = {'V1': v1_avg, 'V2': v2_avg, 'V3': v3_avg, 'V4': v4_avg}
        best_strategy = max(strategies, key=strategies.get)
        best_return = strategies[best_strategy]
        alpha = best_return - benchmark_avg
        
        row = {
            '月份': month_str,
            '基准平均(%)': round(benchmark_avg, 2),
            'V1平均(%)': round(v1_avg, 2),
            'V2平均(%)': round(v2_avg, 2),
            'V3平均(%)': round(v3_avg, 2),
            'V4平均(%)': round(v4_avg, 2),
            '最佳策略': best_strategy,
            '最佳收益(%)': round(best_return, 2),
            'Alpha(%)': round(alpha, 2),
            'V1胜出次数': (month_data['最佳策略'] == 'V1').sum(),
            'V2胜出次数': (month_data['最佳策略'] == 'V2').sum(),
            'V3胜出次数': (month_data['最佳策略'] == 'V3').sum(),
            'V4胜出次数': (month_data['最佳策略'] == 'V4').sum()
        }
        
        month_summary.append(row)
    
    df_month_summary = pd.DataFrame(month_summary)
    df_month_summary.to_excel(writer, sheet_name='按月份汇总', index=False)

print(f"\n✅ 超详细报表已生成: {excel_file}")
print(f"📊 数据规模: {len(df_detailed)} 行 ({len(all_stocks)}股票 × {len(all_months)}月)")

# 验证数据完整性
print("\n🔍 数据完整性检查:")
for strategy in ['V1', 'V2', 'V3', 'V4']:
    non_zero = (df_detailed[f'{strategy}收益率(%)'] != 0).sum()
    print(f"  {strategy}: {non_zero}/{len(df_detailed)} 行有非零收益 ({non_zero/len(df_detailed)*100:.1f}%)")

# 打印月度分析
print("\n" + "="*100)
print("📅 新股票池月度最佳策略分析")
print("="*100)
print(df_month_summary[['月份', '基准平均(%)', 'V1平均(%)', 'V2平均(%)', 'V3平均(%)', 'V4平均(%)', '最佳策略', 'Alpha(%)']].to_string(index=False))

print("\n策略月度冠军统计:")
print(df_month_summary['最佳策略'].value_counts().to_string())

print(f"\n平均Alpha: {df_month_summary['Alpha(%)'].mean():.2f}%")
print(f"跑赢基准月份: {(df_month_summary['Alpha(%)'] > 0).sum()}/12")

print("\n" + "="*100)
print("📁 请打开 Excel 文件查看完整数据！")
