
import os
import re
import datetime
import pandas as pd
import akshare as ak
from openai import OpenAI
import time

# 简单配置
from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

if not API_KEY:
    print("❌ 未找到 DEEPSEEK_API_KEY，请检查 .env")
    exit()

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

def run_debug_backtest(symbol="601881", days=7):
    """
    白盒测试：打印每一次 AI 思考过程
    """
    print(f"🔬 开始【白盒验证】回测，股票代码: {symbol}，回测天数: {days}")
    
    # 1. 获取数据
    end_date = datetime.datetime.now().strftime("%Y%m%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days + 60)).strftime("%Y%m%d")
    
    try:
        print(f"📡 正在从 AkShare 获取数据 ({start_date} - {end_date})...")
        df_all = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        return

    # 计算指标
    df_all['EMA12'] = df_all['收盘'].ewm(span=12, adjust=False).mean()
    df_all['EMA26'] = df_all['收盘'].ewm(span=26, adjust=False).mean()
    df_all['DIF'] = df_all['EMA12'] - df_all['EMA26']
    df_all['DEA'] = df_all['DIF'].ewm(span=9, adjust=False).mean()
    
    # 截取最后 N 天进行逐天模拟
    target_data = df_all.tail(days).reset_index(drop=True)
    
    print("\n" + "="*50)
    print("🧠 AI 思考过程全记录")
    print("="*50)

    history = []

    for i in range(len(target_data)):
        # 今天的行情数据 (代表 T 日收盘后)
        # 注意：这里我们模拟的是“站在 T 日晚上，看 T 日及之前的数据，预测 T+1 日”
        # 所以我们需要把 T 日及之前的 N 天数据发给 AI
        
        current_date = target_data.iloc[i]['日期']
        
        # 找到原始 df 中这一天对应的索引，往前取5天作为上下文
        idx_in_full = df_all[df_all['日期'] == current_date].index[0]
        context_df = df_all.iloc[idx_in_full-4 : idx_in_full+1]
        
        # 构造 Prompt 数据段
        data_text = ""
        for _, row in context_df.iterrows():
            macd_val = 2 * (row['DIF'] - row['DEA'])
            data_text += f"{row['日期']} | 收盘:{row['收盘']:.2f} | 涨幅:{row['涨跌幅']:.2f}% | MACD:{macd_val:.3f}\n"
            
        print(f"\n📅 [模拟 T日: {current_date}] 向 AI 发送数据:")
        print("-" * 30)
        print(data_text.strip())
        print("-" * 30)
        
        prompt = f"""
        你是一名经验丰富的A股短线交易员。请根据过去5天的行情数据，预测【次日】({current_date}之后的一天) 的股价走势并给出操作建议。
        
        行情数据：
        {data_text}
        
        请严格按以下格式输出：
        分析逻辑：[一句话概括技术面，如MACD走势、放量缩量等]
        操作建议：[买入/卖出/持有/观望]
        """
        
        # 调用 AI
        start_t = time.time()
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        duration = time.time() - start_t
        ai_msg = response.choices[0].message.content.strip()
        
        print(f"🤖 AI 回复 (耗时 {duration:.2f}s):")
        print(f"\033[96m{ai_msg}\033[0m") # 青色显示 AI 回复
        
        # 验证结果 (T+1)
        # 即使是最后一天，如果没有明天的数据则无法验证
        actual_next_day = None
        if idx_in_full + 1 < len(df_all):
            next_row = df_all.iloc[idx_in_full+1]
            actual_ret = next_row['涨跌幅']
            actual_next_day = f"{next_row['日期']} (涨跌: {actual_ret}%)"
            print(f"📉 真实历史验证 (T+1): {actual_next_day}")
        else:
            print(f"🔮 未来 (T+1): 尚无数据")

if __name__ == "__main__":
    # 默认跑 中国银河 (601881) 最近 5 天
    run_debug_backtest("601881", days=5)
