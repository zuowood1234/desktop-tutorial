#!/usr/bin/env python3
"""
使用白银有色(601212)真实数据测试AI决策逻辑
时间段: 2024-11-01 到 2024-11-07
"""

import os
import sys
import time
import akshare as ak
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

def get_real_data():
    """获取白银有色2026年1月的真实行情数据"""
    print("📊 正在获取白银有色(601212) 2026年1月真实行情数据...")
    
    try:
        # 使用不同的API接口
        df = ak.stock_zh_a_daily(symbol="sh601212", adjust="qfq")
        
        if df is None or df.empty:
            print("❌ 数据获取失败")
            return None
        
        # 重命名列
        df = df.rename(columns={
            'date': '日期', 'open': '开盘', 'high': '最高',
            'low': '最低', 'close': '收盘', 'volume': '成交量'
        })
        df['日期'] = pd.to_datetime(df['日期'])
        df['涨跌幅'] = df['收盘'].pct_change() * 100
        
        # 筛选时间范围 - 2026年1月所有交易日
        mask = (df['日期'] >= '2026-01-01') & (df['日期'] <= '2026-01-31')
        df = df.loc[mask].reset_index(drop=True)
        
        if df.empty:
            print("❌ 该时间段无数据")
            return None
            
        # 显示获取到的数据
        print(f"\n真实K线数据 (共{len(df)}天):")
        print("-" * 60)
        for _, row in df.iterrows():
            print(f"{row['日期'].strftime('%Y-%m-%d')} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}% | 成交量:{int(row['成交量'])}")
        print("-" * 60)
        
        # 构建给AI的文本
        k_line_text = ""
        for _, row in df.iterrows():
            k_line_text += f"{row['日期'].strftime('%Y-%m-%d')} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}%\n"
        
        # 带量比的版本
        df['VOL5'] = df['成交量'].rolling(window=5).mean()
        sentiment_text = ""
        for _, row in df.iterrows():
            vol_ratio = row['成交量'] / row['VOL5'] if pd.notna(row['VOL5']) and row['VOL5'] > 0 else 1.0
            sentiment_text += f"{row['日期'].strftime('%Y-%m-%d')} | 收:{row['收盘']:.2f} | 涨:{row['涨跌幅']:.2f}% | 大盘:0.00% | 量比:{vol_ratio:.2f}\n"
        
        return k_line_text, sentiment_text
        
    except Exception as e:
        print(f"❌ 获取数据失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_with_real_data(k_line_text, sentiment_text):
    """使用真实数据测试AI"""
    
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    # 测试1: 纯技术派
    print("\n" + "="*60)
    print("🧪 测试 1: 纯技术派（真实K线数据）")
    print("="*60)
    
    prompt_tech = f"""
你是 A 股短线交易员。根据技术数据预测操作：

股票: 601212 白银有色
{k_line_text}

要求：对每天给出【买入】/【卖出】/【持有】/【观望】，格式：日期|操作|理由

示例：
2024-11-01|买入|超跌反弹
"""
    
    print("\n📤 发送的Prompt:")
    print("-" * 60)
    print(prompt_tech)
    print("-" * 60)
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是技术分析师。"},
                {"role": "user", "content": prompt_tech},
            ],
            temperature=0.3,
        )
        
        ai_reply = response.choices[0].message.content.strip()
        print("\n📥 AI的完整回复:")
        print("-" * 60)
        print(ai_reply)
        print("-" * 60)
        
    except Exception as e:
        print(f"\n❌ API调用失败: {e}")
    
    time.sleep(2)
    
    # 测试2: 情绪增强派
    print("\n" + "="*60)
    print("🧪 测试 2: 情绪增强派（真实数据 + 量比）")
    print("="*60)
    
    prompt_sent = f"""
你是 A 股短线交易员。综合技术面和市场情绪预测操作：

股票: 601212 白银有色
{sentiment_text}

要求：综合考虑技术、大盘、量能，对每天给出【买入】/【卖出】/【持有】/【观望】，格式：日期|操作|理由

示例：
2024-11-01|买入|大盘企稳+量能放大
"""
    
    print("\n📤 发送的Prompt:")
    print("-" * 60)
    print(prompt_sent)
    print("-" * 60)
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你综合市场情绪和技术面。"},
                {"role": "user", "content": prompt_sent},
            ],
            temperature=0.3,
        )
        
        ai_reply = response.choices[0].message.content.strip()
        print("\n📥 AI的完整回复:")
        print("-" * 60)
        print(ai_reply)
        print("-" * 60)
        
    except Exception as e:
        print(f"\n❌ API调用失败: {e}")

if __name__ == "__main__":
    print("\n" + "🔬" * 30)
    print("AI决策验证 - 使用白银有色真实数据")
    print("时间段: 2026年1月全部交易日")
    print("🔬" * 30)
    
    result = get_real_data()
    if result:
        k_line_text, sentiment_text = result
        test_with_real_data(k_line_text, sentiment_text)
        
        print("\n" + "="*60)
        print("✅ 测试完成！")
        print("="*60)
    else:
        print("\n❌ 无法获取数据，测试终止")
