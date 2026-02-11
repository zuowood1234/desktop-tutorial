import pandas as pd
import numpy as np

# ==========================================
# 📊 交易胜率分析：每次买卖的盈亏统计
# ==========================================

print("🔍 正在分析各策略的交易胜率...")

# 读取新股票池的交易流水
df_logs = pd.read_excel('2025_新股票池回测报告.xlsx', sheet_name='全部交易流水')

print(f"\n总记录数: {len(df_logs)}")
print("="*100)

# 策略分析
strategies = ['V1 (MA5激进)', 'V2 (MA10稳健)', 'V3 (布林震荡)', 'V4 (增强趋势)']
stock_col = '股票' if '股票' in df_logs.columns else '股票代码'

all_results = []

for strategy in strategies:
    print(f"\n处理策略: {strategy}...")
    
    strategy_data = df_logs[df_logs['策略'] == strategy].copy()
    
    # 获取所有股票
    stocks = strategy_data[stock_col].unique()
    
    total_trades = 0
    profitable_trades = 0
    loss_trades = 0
    
    trade_details = []
    
    # 对每只股票分析交易
    for stock in stocks:
        stock_data = strategy_data[strategy_data[stock_col] == stock].copy()
        stock_data = stock_data.sort_values('日期' if '日期' in stock_data.columns else 'date')
        
        # 找出所有买入和卖出操作
        buy_records = stock_data[stock_data['操作'] == '全仓买入']
        sell_records = stock_data[stock_data['操作'] == '清仓卖出']
        
        # 配对买卖操作
        for i, buy_row in buy_records.iterrows():
            buy_date = buy_row['日期'] if '日期' in buy_row else buy_row['date']
            buy_price = buy_row['收盘']
            
            # 找到这次买入后的第一次卖出
            future_sells = sell_records[sell_records['日期' if '日期' in sell_records.columns else 'date'] > buy_date]
            
            if not future_sells.empty:
                sell_row = future_sells.iloc[0]
                sell_date = sell_row['日期'] if '日期' in sell_row else sell_row['date']
                sell_price = sell_row['收盘']
                
                # 计算收益率
                profit_pct = (sell_price - buy_price) / buy_price * 100
                
                total_trades += 1
                
                if profit_pct > 0:
                    profitable_trades += 1
                    trade_type = '盈利'
                else:
                    loss_trades += 1
                    trade_type = '亏损'
                
                trade_details.append({
                    '股票': stock,
                    '买入日期': buy_date,
                    '卖出日期': sell_date,
                    '买入价': buy_price,
                    '卖出价': sell_price,
                    '收益率(%)': round(profit_pct, 2),
                    '类型': trade_type
                })
    
    # 计算统计数据
    win_rate = profitable_trades / total_trades * 100 if total_trades > 0 else 0
    
    # 计算平均盈利和平均亏损
    if trade_details:
        df_trades = pd.DataFrame(trade_details)
        avg_profit = df_trades[df_trades['收益率(%)'] > 0]['收益率(%)'].mean() if profitable_trades > 0 else 0
        avg_loss = df_trades[df_trades['收益率(%)'] < 0]['收益率(%)'].mean() if loss_trades > 0 else 0
        max_profit = df_trades['收益率(%)'].max()
        max_loss = df_trades['收益率(%)'].min()
    else:
        avg_profit = 0
        avg_loss = 0
        max_profit = 0
        max_loss = 0
    
    all_results.append({
        '策略': strategy.split(' ')[0],
        '总交易次数': total_trades,
        '盈利次数': profitable_trades,
        '亏损次数': loss_trades,
        '胜率(%)': round(win_rate, 1),
        '平均单次盈利(%)': round(avg_profit, 2),
        '平均单次亏损(%)': round(avg_loss, 2),
        '最大单次盈利(%)': round(max_profit, 2),
        '最大单次亏损(%)': round(max_loss, 2),
        '盈亏比': round(abs(avg_profit / avg_loss), 2) if avg_loss != 0 else 0
    })

# 生成报表
df_results = pd.DataFrame(all_results)

print("\n\n" + "="*100)
print("📊 各策略交易胜率分析")
print("="*100)
print(df_results.to_string(index=False))

# 保存到Excel
excel_file = "策略交易胜率分析.xlsx"
with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
    df_results.to_excel(writer, sheet_name='交易胜率统计', index=False)

print(f"\n\n✅ 详细报告已保存: {excel_file}")

# 关键发现
print("\n\n" + "="*100)
print("🔍 关键发现")
print("="*100)

best_winrate = df_results.loc[df_results['胜率(%)'].idxmax()]
worst_winrate = df_results.loc[df_results['胜率(%)'].idxmin()]

print(f"\n🏆 最高胜率: {best_winrate['策略']} - {best_winrate['胜率(%)']}%")
print(f"   盈利次数: {best_winrate['盈利次数']}/{best_winrate['总交易次数']}")
print(f"   平均盈利: {best_winrate['平均单次盈利(%)']}%")
print(f"   平均亏损: {best_winrate['平均单次亏损(%)']}%")

print(f"\n💔 最低胜率: {worst_winrate['策略']} - {worst_winrate['胜率(%)']}%")
print(f"   盈利次数: {worst_winrate['盈利次数']}/{worst_winrate['总交易次数']}")
print(f"   平均盈利: {worst_winrate['平均单次盈利(%)']}%")
print(f"   平均亏损: {worst_winrate['平均单次亏损(%)']}%")

# 盈亏比分析
best_ratio = df_results.loc[df_results['盈亏比'].idxmax()]
print(f"\n💰 最佳盈亏比: {best_ratio['策略']} - {best_ratio['盈亏比']:.2f}")
print(f"   说明: 平均每次盈利是亏损的 {best_ratio['盈亏比']:.2f} 倍")

# 交易频率
print(f"\n📈 交易频率对比:")
for _, row in df_results.iterrows():
    trades_per_stock = row['总交易次数'] / 27  # 27只股票
    print(f"   {row['策略']}: 平均每只股票 {trades_per_stock:.1f} 次交易/年")

print("\n" + "="*100)
