#!/usr/bin/env python3
"""
改进版严格逐日回测 - 明确区分买入/持有/观望
根据持仓状态调整Prompt
"""

import os
import time
import akshare as ak
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

def get_market_data():
    """获取上证指数2026年1月数据"""
    print("📊 正在获取上证指数数据...")
    
    try:
        df = ak.stock_zh_index_daily(symbol="sh000001")
        df = df.rename(columns={'date': '日期', 'close': '收盘'})
        df['日期'] = pd.to_datetime(df['日期'])
        df['涨跌幅'] = df['收盘'].pct_change() * 100
        
        mask = (df['日期'] >= '2026-01-01') & (df['日期'] <= '2026-01-31')
        df_market = df.loc[mask].copy()
        
        print(f"✅ 获取到{len(df_market)}天上证指数数据")
        return df_market
    except Exception as e:
        print(f"⚠️ 大盘数据获取失败: {e}")
        return None

def get_stock_data(symbol, name):
    """获取股票2026年1月数据"""
    print(f"📊 正在获取{name}({symbol})数据...")
    
    try:
        if symbol.startswith('6'):
            symbol_with_prefix = f'sh{symbol}'
        else:
            symbol_with_prefix = f'sz{symbol}'
        
        df = ak.stock_zh_a_daily(symbol=symbol_with_prefix, adjust="qfq")
        df = df.rename(columns={
            'date': '日期', 'open': '开盘', 'high': '最高',
            'low': '最低', 'close': '收盘', 'volume': '成交量'
        })
        df['日期'] = pd.to_datetime(df['日期'])
        df['涨跌幅'] = df['收盘'].pct_change() * 100
        
        mask = (df['日期'] >= '2026-01-01') & (df['日期'] <= '2026-01-31')
        df_stock = df.loc[mask].copy()
        
        df_stock['VOL5'] = df['成交量'].rolling(window=5).mean()
        df_stock['量比'] = df_stock.apply(
            lambda row: row['成交量'] / row['VOL5'] if pd.notna(row['VOL5']) and row['VOL5'] > 0 else 1.0,
            axis=1
        )
        
        print(f"✅ 获取到{len(df_stock)}天数据")
        return df_stock
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        return None

def get_ai_decision(client, symbol, name, historical_data, sentiment_data, current_date, holding):
    """
    获取AI决策 - 根据持仓状态调整Prompt
    
    Args:
        holding: True=有持仓, False=空仓
    """
    
    # ============================================================================
    # 技术派
    # ============================================================================
    if not holding:
        # 空仓时：问是否买入
        prompt_tech = f"""你是 A 股短线交易员。根据技术数据预测操作：

股票: {symbol} {name}
{historical_data}

今天是: {current_date}
当前状态: 空仓（现金100万）

要求：判断今天应该【买入】还是【观望】
- 买入：使用全部现金开仓
- 观望：继续空仓等待

请只回复：操作|理由
例如：买入|放量突破，趋势转强"""

    else:
        # 有仓位时：问是否持有或卖出
        prompt_tech = f"""你是 A 股短线交易员。根据技术数据预测操作：

股票: {symbol} {name}
{historical_data}

今天是: {current_date}
当前状态: 持仓中

要求：判断今天应该【持有】还是【卖出】
- 持有：继续持有现有仓位
- 卖出：清仓离场

请只回复：操作|理由
例如：卖出|跌破支撑，趋势转弱"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是技术分析师。"},
                {"role": "user", "content": prompt_tech},
            ],
            temperature=0.3,
        )
        
        tech_reply = response.choices[0].message.content.strip()
        tech_parts = tech_reply.split('|')
        tech_action = tech_parts[0].strip() if len(tech_parts) > 0 else ("观望" if not holding else "持有")
        tech_reason = tech_parts[1].strip() if len(tech_parts) > 1 else ""
        
    except Exception as e:
        tech_action = "观望" if not holding else "持有"
        tech_reason = f"API失败:{e}"
    
    time.sleep(0.5)
    
    # ============================================================================
    # 情绪派
    # ============================================================================
    if not holding:
        # 空仓时
        prompt_sent = f"""你是 A 股短线交易员。综合技术面和市场情绪预测操作：

股票: {symbol} {name}
{sentiment_data}

今天是: {current_date}
当前状态: 空仓（现金100万）

要求：综合考虑技术、大盘、量能，判断今天应该【买入】还是【观望】
- 买入：使用全部现金开仓
- 观望：继续空仓等待

请只回复：操作|理由
例如：买入|大盘企稳+量能放大+技术突破"""

    else:
        # 有仓位时
        prompt_sent = f"""你是 A 股短线交易员。综合技术面和市场情绪预测操作：

股票: {symbol} {name}
{sentiment_data}

今天是: {current_date}
当前状态: 持仓中

要求：综合考虑技术、大盘、量能，判断今天应该【持有】还是【卖出】
- 持有：继续持有现有仓位
- 卖出：清仓离场

请只回复：操作|理由
例如：卖出|大盘转弱+量能萎缩+技术破位"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你综合市场情绪和技术面。"},
                {"role": "user", "content": prompt_sent},
            ],
            temperature=0.3,
        )
        
        sent_reply = response.choices[0].message.content.strip()
        sent_parts = sent_reply.split('|')
        sent_action = sent_parts[0].strip() if len(sent_parts) > 0 else ("观望" if not holding else "持有")
        sent_reason = sent_parts[1].strip() if len(sent_parts) > 1 else ""
        
    except Exception as e:
        sent_action = "观望" if not holding else "持有"
        sent_reason = f"API失败:{e}"
    
    time.sleep(0.5)
    
    return tech_action, tech_reason, sent_action, sent_reason

def daily_backtest(symbol, name, df_stock, df_market):
    """逐日回测单只股票"""
    
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    print(f"\n{'='*80}")
    print(f"开始逐日回测: {name}({symbol})")
    print(f"{'='*80}")
    
    results = []
    
    # 跟踪持仓状态
    tech_holding = False
    sent_holding = False
    
    for idx in range(len(df_stock)):
        current_date = df_stock.iloc[idx]['日期']
        current_date_str = current_date.strftime('%Y-%m-%d')
        
        # 历史数据
        historical_stock = df_stock.iloc[:idx+1].copy()
        
        # 构建K线文本
        k_line_text = ""
        for _, row in historical_stock.iterrows():
            k_line_text += f"{row['日期'].strftime('%Y-%m-%d')} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}%\n"
        
        # 构建情绪文本
        sentiment_text = ""
        for _, row in historical_stock.iterrows():
            row_date_str = row['日期'].strftime('%Y-%m-%d')
            
            if df_market is not None:
                market_row = df_market[df_market['日期'] == row['日期']]
                market_change = market_row.iloc[0]['涨跌幅'] if len(market_row) > 0 and pd.notna(market_row.iloc[0]['涨跌幅']) else 0.0
            else:
                market_change = 0.0
            
            sentiment_text += f"{row_date_str} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}% | 大盘:{market_change:+.2f}% | 量比:{row['量比']:.2f}\n"
        
        print(f"📅 {current_date_str} (第{idx+1}/{len(df_stock)}天) ", end="")
        print(f"价:{historical_stock.iloc[-1]['收盘']:.2f} ", end="")
        print(f"涨:{historical_stock.iloc[-1]['涨跌幅']:+.2f}% ", end="")
        print(f"技术:{'持仓' if tech_holding else '空仓'} 情绪:{'持仓' if sent_holding else '空仓'} ", end="")
        
        # 获取AI决策（传入持仓状态）
        tech_action, tech_reason, sent_action, sent_reason = get_ai_decision(
            client, symbol, name, k_line_text, sentiment_text, 
            current_date_str, tech_holding  # 技术派用自己的持仓状态
        )
        
        # 分别获取情绪派（使用情绪派的持仓状态）
        _, _, sent_action, sent_reason = get_ai_decision(
            client, symbol, name, k_line_text, sentiment_text,
            current_date_str, sent_holding  # 情绪派用自己的持仓状态
        )
        
        print(f"→ 技术:{tech_action} 情绪:{sent_action}")
        
        # 更新持仓状态
        if tech_action == '买入':
            tech_holding = True
        elif tech_action == '卖出':
            tech_holding = False
        
        if sent_action == '买入':
            sent_holding = True
        elif sent_action == '卖出':
            sent_holding = False
        
        results.append({
            '日期': current_date_str,
            '收盘': historical_stock.iloc[-1]['收盘'],
            '涨跌幅': historical_stock.iloc[-1]['涨跌幅'],
            '技术派操作': tech_action,
            '技术派理由': tech_reason,
            '技术派持仓': '是' if tech_holding else '否',
            '情绪派操作': sent_action,
            '情绪派理由': sent_reason,
            '情绪派持仓': '是' if sent_holding else '否',
        })
    
    return pd.DataFrame(results)

def simulate_trading(results_df, stock_name):
    """模拟交易"""
    
    tech_cash = 1000000.0
    tech_position = 0
    tech_trades = []
    
    sent_cash = 1000000.0
    sent_position = 0
    sent_trades = []
    
    for _, row in results_df.iterrows():
        price = row['收盘']
        
        # 技术派
        if row['技术派操作'] == '买入' and tech_position == 0:
            tech_position = tech_cash / price
            tech_trades.append(f"{row['日期']} 买入 @{price:.2f}")
        elif row['技术派操作'] == '卖出' and tech_position > 0:
            tech_cash = tech_position * price
            tech_trades.append(f"{row['日期']} 卖出 @{price:.2f}")
            tech_position = 0
        
        # 情绪派
        if row['情绪派操作'] == '买入' and sent_position == 0:
            sent_position = sent_cash / price
            sent_trades.append(f"{row['日期']} 买入 @{price:.2f}")
        elif row['情绪派操作'] == '卖出' and sent_position > 0:
            sent_cash = sent_position * price
            sent_trades.append(f"{row['日期']} 卖出 @{price:.2f}")
            sent_position = 0
    
    # 月末结算
    final_price = results_df.iloc[-1]['收盘']
    
    tech_final = (tech_position * final_price) if tech_position > 0 else tech_cash
    sent_final = (sent_position * final_price) if sent_position > 0 else sent_cash
    
    tech_return = (tech_final / 1000000 - 1) * 100
    sent_return = (sent_final / 1000000 - 1) * 100
    hold_return = (final_price / results_df.iloc[0]['收盘'] - 1) * 100
    
    print(f"\n{stock_name} 收益汇总:")
    print(f"  技术派: {tech_return:+.2f}% (交易{len(tech_trades)}次)")
    print(f"  情绪派: {sent_return:+.2f}% (交易{len(sent_trades)}次)")
    print(f"  持有:   {hold_return:+.2f}%")
    
    if tech_trades:
        print(f"\n  技术派交易:")
        for t in tech_trades:
            print(f"    {t}")
    
    if sent_trades:
        print(f"\n  情绪派交易:")
        for t in sent_trades:
            print(f"    {t}")
    
    return tech_return, sent_return, hold_return

if __name__ == "__main__":
    print("\n" + "🚀" * 40)
    print("改进版严格逐日回测 - 2026年1月白银有色")
    print("特点：明确区分 买入/持有/观望，根据持仓状态调整Prompt")
    print("🚀" * 40)
    
    # 获取数据
    df_market = get_market_data()
    df_stock = get_stock_data('601212', '白银有色')
    
    if df_stock is None:
        print("\n❌ 无法获取股票数据，测试终止")
        exit(1)
    
    # 逐日回测
    results_df = daily_backtest('601212', '白银有色', df_stock, df_market)
    
    # 保存结果
    results_df.to_csv('improved_backtest_results.csv', index=False, encoding='utf-8-sig')
    print(f"\n✅ 详细结果已保存: improved_backtest_results.csv")
    
    # 计算收益
    tech_return, sent_return, hold_return = simulate_trading(results_df, '白银有色')
    
    print("\n" + "="*80)
    print("📊 最终收益对比")
    print("="*80)
    print(f"技术派: {tech_return:+.2f}%")
    print(f"情绪派: {sent_return:+.2f}%")
    print(f"持有:   {hold_return:+.2f}%")
    print("="*80)
    
    print(f"\n💡 这是改进后的结果（明确区分买入/持有/观望）！")
