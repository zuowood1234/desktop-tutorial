#!/usr/bin/env python3
"""
批量严格逐日回测 - 2026年1月
测试4只正常股票（非妖股）
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

# 测试股票列表
STOCKS = {
    '002050': '三花智控',
    '002284': '亚太股份',
    '601126': '四方股份',
    '000021': '深科技',
}

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
        # 根据市场选择前缀
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
        
        # 计算量比
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

def daily_backtest_single_stock(symbol, name, df_stock, df_market, client):
    """单只股票的逐日回测"""
    
    print(f"\n{'='*80}")
    print(f"开始回测: {name}({symbol})")
    print(f"{'='*80}")
    
    results = []
    
    for idx in range(len(df_stock)):
        current_date = df_stock.iloc[idx]['日期']
        current_date_str = current_date.strftime('%Y-%m-%d')
        
        # 只使用历史数据
        historical_stock = df_stock.iloc[:idx+1].copy()
        
        # 构建历史K线文本
        k_line_text = ""
        for _, row in historical_stock.iterrows():
            k_line_text += f"{row['日期'].strftime('%Y-%m-%d')} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}%\n"
        
        # 构建情绪派文本
        sentiment_text = ""
        for _, row in historical_stock.iterrows():
            row_date_str = row['日期'].strftime('%Y-%m-%d')
            
            if df_market is not None:
                market_row = df_market[df_market['日期'] == row['日期']]
                market_change = market_row.iloc[0]['涨跌幅'] if len(market_row) > 0 and pd.notna(market_row.iloc[0]['涨跌幅']) else 0.0
            else:
                market_change = 0.0
            
            sentiment_text += f"{row_date_str} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}% | 大盘:{market_change:+.2f}% | 量比:{row['量比']:.2f}\n"
        
        print(f"📅 {current_date_str} (第{idx+1}/{len(df_stock)}天) 价格:{historical_stock.iloc[-1]['收盘']:.2f} 涨跌:{historical_stock.iloc[-1]['涨跌幅']:.2f}%", end=" ")
        
        # 技术派
        prompt_tech = f"""你是 A 股短线交易员。根据技术数据预测操作：

股票: {symbol} {name}
{k_line_text}
今天是: {current_date_str}

要求：根据以上历史数据，判断今天应该【买入】/【卖出】/【持有】/【观望】

请只回复：操作|理由
例如：买入|超跌反弹"""

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
            tech_action = tech_parts[0].strip() if len(tech_parts) > 0 else "观望"
            tech_reason = tech_parts[1].strip() if len(tech_parts) > 1 else ""
            
        except Exception as e:
            tech_action = "观望"
            tech_reason = f"API失败:{e}"
        
        time.sleep(0.5)
        
        # 情绪派
        prompt_sent = f"""你是 A 股短线交易员。综合技术面和市场情绪预测操作：

股票: {symbol} {name}
{sentiment_text}
今天是: {current_date_str}

要求：综合考虑技术、大盘、量能，判断今天应该【买入】/【卖出】/【持有】/【观望】

请只回复：操作|理由
例如：买入|大盘企稳+量能放大"""

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
            sent_action = sent_parts[0].strip() if len(sent_parts) > 0 else "观望"
            sent_reason = sent_parts[1].strip() if len(sent_parts) > 1 else ""
            
        except Exception as e:
            sent_action = "观望"
            sent_reason = f"API失败:{e}"
        
        print(f"技术:{tech_action} 情绪:{sent_action}")
        
        time.sleep(0.5)
        
        results.append({
            '日期': current_date_str,
            '收盘': historical_stock.iloc[-1]['收盘'],
            '涨跌幅': historical_stock.iloc[-1]['涨跌幅'],
            '技术派操作': tech_action,
            '技术派理由': tech_reason,
            '情绪派操作': sent_action,
            '情绪派理由': sent_reason,
        })
    
    return pd.DataFrame(results)

def simulate_trading(results_df, stock_name):
    """模拟交易"""
    
    # 技术派
    tech_cash = 1000000.0
    tech_position = 0
    tech_holding = False
    tech_trades = []
    
    # 情绪派
    sent_cash = 1000000.0
    sent_position = 0
    sent_holding = False
    sent_trades = []
    
    for _, row in results_df.iterrows():
        price = row['收盘']
        
        # 技术派
        if row['技术派操作'] in ['买入'] and not tech_holding and tech_cash > 0:
            tech_position = tech_cash / price
            tech_holding = True
            tech_trades.append(f"{row['日期']} 买入 @{price:.2f}")
        elif row['技术派操作'] in ['卖出'] and tech_holding:
            tech_cash = tech_position * price
            tech_position = 0
            tech_holding = False
            tech_trades.append(f"{row['日期']} 卖出 @{price:.2f}")
        
        # 情绪派
        if row['情绪派操作'] in ['买入'] and not sent_holding and sent_cash > 0:
            sent_position = sent_cash / price
            sent_holding = True
            sent_trades.append(f"{row['日期']} 买入 @{price:.2f}")
        elif row['情绪派操作'] in ['卖出'] and sent_holding:
            sent_cash = sent_position * price
            sent_position = 0
            sent_holding = False
            sent_trades.append(f"{row['日期']} 卖出 @{price:.2f}")
    
    # 月末结算
    final_price = results_df.iloc[-1]['收盘']
    
    tech_final = (tech_position * final_price) if tech_holding else tech_cash
    sent_final = (sent_position * final_price) if sent_holding else sent_cash
    
    tech_return = (tech_final / 1000000 - 1) * 100
    sent_return = (sent_final / 1000000 - 1) * 100
    hold_return = (final_price / results_df.iloc[0]['收盘'] - 1) * 100
    
    return {
        'stock_name': stock_name,
        'tech_return': tech_return,
        'sent_return': sent_return,
        'hold_return': hold_return,
        'tech_trades': tech_trades,
        'sent_trades': sent_trades,
    }

if __name__ == "__main__":
    print("\n" + "🚀" * 40)
    print("批量严格逐日回测 - 2026年1月")
    print("测试4只正常股票（非妖股）")
    print("🚀" * 40)
    
    # 获取大盘数据
    df_market = get_market_data()
    
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    all_results = {}
    summary_data = []
    
    for symbol, name in STOCKS.items():
        print(f"\n{'#'*80}")
        print(f"# {name}({symbol})")
        print(f"{'#'*80}")
        
        # 获取数据
        df_stock = get_stock_data(symbol, name)
        
        if df_stock is None or len(df_stock) == 0:
            print(f"❌ {name} 数据获取失败，跳过")
            continue
        
        # 回测
        results_df = daily_backtest_single_stock(symbol, name, df_stock, df_market, client)
        
        # 保存详细结果
        csv_filename = f'backtest_{symbol}_{name}.csv'
        results_df.to_csv(csv_filename, index=False, encoding='utf-8-sig')
        print(f"✅ 详细结果已保存: {csv_filename}")
        
        # 模拟交易
        perf = simulate_trading(results_df, name)
        all_results[symbol] = perf
        
        summary_data.append({
            '代码': symbol,
            '名称': name,
            '技术派收益': f"{perf['tech_return']:+.2f}%",
            '情绪派收益': f"{perf['sent_return']:+.2f}%",
            '持有收益': f"{perf['hold_return']:+.2f}%",
        })
        
        print(f"\n{name} 收益汇总:")
        print(f"  技术派: {perf['tech_return']:+.2f}%")
        print(f"  情绪派: {perf['sent_return']:+.2f}%")
        print(f"  持有:   {perf['hold_return']:+.2f}%")
    
    # 生成汇总报告
    print("\n" + "="*80)
    print("📊 总体收益汇总")
    print("="*80)
    
    summary_df = pd.DataFrame(summary_data)
    print(summary_df.to_string(index=False))
    
    summary_df.to_csv('batch_backtest_summary.csv', index=False, encoding='utf-8-sig')
    print(f"\n✅ 汇总结果已保存: batch_backtest_summary.csv")
    
    print("\n" + "="*80)
    print("🎯 批量回测完成！")
    print("="*80)
