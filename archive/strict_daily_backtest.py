#!/usr/bin/env python3
"""
严格逐日回测 + 真实大盘数据
2026年1月白银有色(601212)
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
        df = ak.stock_zh_index_daily(symbol="sh000001")  # 上证指数
        df = df.rename(columns={'date': '日期', 'close': '收盘'})
        df['日期'] = pd.to_datetime(df['日期'])
        df['涨跌幅'] = df['收盘'].pct_change() * 100
        
        # 筛选2026年1月
        mask = (df['日期'] >= '2026-01-01') & (df['日期'] <= '2026-01-31')
        df_market = df.loc[mask].copy()
        
        print(f"✅ 获取到{len(df_market)}天上证指数数据")
        return df_market
    except Exception as e:
        print(f"⚠️ 大盘数据获取失败: {e}，将使用0作为默认值")
        return None

def get_stock_data():
    """获取白银有色2026年1月数据"""
    print("📊 正在获取白银有色(601212)数据...")
    
    try:
        df = ak.stock_zh_a_daily(symbol="sh601212", adjust="qfq")
        df = df.rename(columns={
            'date': '日期', 'open': '开盘', 'high': '最高',
            'low': '最低', 'close': '收盘', 'volume': '成交量'
        })
        df['日期'] = pd.to_datetime(df['日期'])
        df['涨跌幅'] = df['收盘'].pct_change() * 100
        
        # 筛选2026年1月
        mask = (df['日期'] >= '2026-01-01') & (df['日期'] <= '2026-01-31')
        df_stock = df.loc[mask].copy()
        
        # 计算5日均量和量比
        df_stock['VOL5'] = df['成交量'].rolling(window=5).mean()
        df_stock['量比'] = df_stock.apply(
            lambda row: row['成交量'] / row['VOL5'] if pd.notna(row['VOL5']) and row['VOL5'] > 0 else 1.0,
            axis=1
        )
        
        print(f"✅ 获取到{len(df_stock)}天股票数据")
        return df_stock
    except Exception as e:
        print(f"❌ 股票数据获取失败: {e}")
        return None

def daily_backtest(df_stock, df_market):
    """逐日回测，严格遵守时间顺序"""
    
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    results = []
    
    print("\n" + "="*80)
    print("开始逐日回测 - 每天独立调用AI判断")
    print("="*80)
    
    for idx in range(len(df_stock)):
        current_date = df_stock.iloc[idx]['日期']
        current_date_str = current_date.strftime('%Y-%m-%d')
        
        # 只使用当天及之前的数据
        historical_stock = df_stock.iloc[:idx+1].copy()
        
        # 构建历史K线文本（纯技术派）
        k_line_text = ""
        for _, row in historical_stock.iterrows():
            k_line_text += f"{row['日期'].strftime('%Y-%m-%d')} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}%\n"
        
        # 构建带大盘和量比的文本（情绪派）
        sentiment_text = ""
        for _, row in historical_stock.iterrows():
            row_date_str = row['日期'].strftime('%Y-%m-%d')
            
            # 获取当天大盘涨跌幅
            if df_market is not None:
                market_row = df_market[df_market['日期'] == row['日期']]
                market_change = market_row.iloc[0]['涨跌幅'] if len(market_row) > 0 and pd.notna(market_row.iloc[0]['涨跌幅']) else 0.0
            else:
                market_change = 0.0
            
            sentiment_text += f"{row_date_str} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}% | 大盘:{market_change:+.2f}% | 量比:{row['量比']:.2f}\n"
        
        print(f"\n{'='*80}")
        print(f"📅 {current_date_str} (第{idx+1}/{len(df_stock)}天)")
        print(f"{'='*80}")
        print(f"当前价格: {historical_stock.iloc[-1]['收盘']:.2f}")
        print(f"涨跌幅: {historical_stock.iloc[-1]['涨跌幅']:.2f}%")
        
        # 调用AI - 纯技术派
        print(f"\n🤖 调用AI判断（纯技术派）...")
        
        prompt_tech = f"""你是 A 股短线交易员。根据技术数据预测操作：

股票: 601212 白银有色
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
            
            print(f"  ✅ 技术派: {tech_action} | {tech_reason}")
            
        except Exception as e:
            print(f"  ❌ 技术派失败: {e}")
            tech_action = "观望"
            tech_reason = "API失败"
        
        time.sleep(1)  # 避免请求过快
        
        # 调用AI - 情绪增强派
        print(f"🤖 调用AI判断（情绪增强派）...")
        
        prompt_sent = f"""你是 A 股短线交易员。综合技术面和市场情绪预测操作：

股票: 601212 白银有色
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
            
            print(f"  ✅ 情绪派: {sent_action} | {sent_reason}")
            
        except Exception as e:
            print(f"  ❌ 情绪派失败: {e}")
            sent_action = "观望"
            sent_reason = "API失败"
        
        time.sleep(1)
        
        # 记录结果
        results.append({
            '日期': current_date_str,
            '收盘': historical_stock.iloc[-1]['收盘'],
            '涨跌幅': historical_stock.iloc[-1]['涨跌幅'],
            '量比': historical_stock.iloc[-1]['量比'],
            '大盘涨跌': market_change if df_market is not None else 0.0,
            '技术派操作': tech_action,
            '技术派理由': tech_reason,
            '情绪派操作': sent_action,
            '情绪派理由': sent_reason,
        })
    
    return pd.DataFrame(results)

def simulate_trading(results_df):
    """模拟交易，计算收益"""
    
    print("\n" + "="*80)
    print("模拟交易 - 计算收益率")
    print("="*80)
    
    # 技术派交易
    tech_cash = 1000000.0
    tech_position = 0
    tech_holding = False
    
    # 情绪派交易
    sent_cash = 1000000.0
    sent_position = 0
    sent_holding = False
    
    for _, row in results_df.iterrows():
        price = row['收盘']
        
        # 技术派
        if row['技术派操作'] in ['买入'] and not tech_holding and tech_cash > 0:
            tech_position = tech_cash / price
            tech_holding = True
            print(f"{row['日期']} 技术派买入 @{price:.2f}")
        elif row['技术派操作'] in ['卖出'] and tech_holding:
            tech_cash = tech_position * price
            tech_position = 0
            tech_holding = False
            print(f"{row['日期']} 技术派卖出 @{price:.2f} 资产:{tech_cash:.2f}")
        
        # 情绪派
        if row['情绪派操作'] in ['买入'] and not sent_holding and sent_cash > 0:
            sent_position = sent_cash / price
            sent_holding = True
            print(f"{row['日期']} 情绪派买入 @{price:.2f}")
        elif row['情绪派操作'] in ['卖出'] and sent_holding:
            sent_cash = sent_position * price
            sent_position = 0
            sent_holding = False
            print(f"{row['日期']} 情绪派卖出 @{price:.2f} 资产:{sent_cash:.2f}")
    
    # 月末结算
    final_price = results_df.iloc[-1]['收盘']
    
    if tech_holding:
        tech_final = tech_position * final_price
    else:
        tech_final = tech_cash
    
    if sent_holding:
        sent_final = sent_position * final_price
    else:
        sent_final = sent_cash
    
    tech_return = (tech_final / 1000000 - 1) * 100
    sent_return = (sent_final / 1000000 - 1) * 100
    
    # 持有不动
    hold_return = (final_price / results_df.iloc[0]['收盘'] - 1) * 100
    
    print("\n" + "="*80)
    print("📊 最终收益统计")
    print("="*80)
    print(f"纯技术派: {tech_return:+.2f}%")
    print(f"情绪增强派: {sent_return:+.2f}%")
    print(f"持有不动: {hold_return:+.2f}%")
    print("="*80)
    
    return tech_return, sent_return, hold_return

if __name__ == "__main__":
    print("\n" + "🚀" * 40)
    print("严格逐日回测 - 2026年1月白银有色")
    print("特点：1. 逐日调用AI  2. 真实大盘数据  3. 无数据泄露")
    print("🚀" * 40)
    
    # 获取数据
    df_market = get_market_data()
    df_stock = get_stock_data()
    
    if df_stock is None:
        print("\n❌ 无法获取股票数据，测试终止")
        exit(1)
    
    # 逐日回测
    results_df = daily_backtest(df_stock, df_market)
    
    # 保存详细结果
    results_df.to_csv('strict_daily_backtest_results.csv', index=False, encoding='utf-8-sig')
    print(f"\n✅ 详细结果已保存到: strict_daily_backtest_results.csv")
    
    # 计算收益
    tech_return, sent_return, hold_return = simulate_trading(results_df)
    
    print(f"\n💡 这是真实可信的回测结果（无数据泄露）！")
