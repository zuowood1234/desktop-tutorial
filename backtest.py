from main import get_stock_data, API_KEY
from openai import OpenAI
import pandas as pd
import datetime
import os
import time
import json
import logging
import re
import sys 

# 关键：我们不再让日志悄悄溜走，而是想把它们抓出来，虽然这在单进程下很难直接传给 Streamlit。
# 妥协方案：我们只在出错时把异常抛出去，而不是吞掉。

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_ai_advice_batch(client, symbol, date_list, data_rows_text):
    """
    【AI请求核心函数：单次串行，报错必抛】
    不再使用复杂的重试吞掉异常，而是直接暴露错误。
    """
    prompt = f"""
    角色：A股短线交易员
    目标：根据以下 {len(date_list)} 天的行情数据，分别为每一天给出次日操作建议。
    
    股票：{symbol}
    
    行情数据列表：
    {data_rows_text}
    
    请严格按以下格式逐行输出建议（每行一条）：
    YYYY-MM-DD | 建议操作 | 简短理由
    
    例如：
    2023-01-01 | 买入 | 均线支撑强
    2023-01-02 | 卖出 | 放量滞涨
    
    注意：
    1. 日期必须与输入对应。
    2. 操作只能是：买入、卖出、持有、空仓。
    3. 不要输出 JSON，不要 Markdown，直接纯文本。
    """
    
    # 我们只试一次，如果错了直接抛异常，让外层捕获并显示
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", 
            messages=[
                {"role": "system", "content": "你是一个严格的量化交易助手。请按指定格式输出纯文本。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            timeout=60
        )
        content = response.choices[0].message.content.strip()
        
        # --- 解析逻辑 ---
        lines = content.split('\n')
        results = []
        
        for line in lines:
            line = line.strip()
            if not line: continue
            date_match = re.search(r'\d{4}-\d{2}-\d{2}', line)
            if not date_match: continue
            date_str = date_match.group(0)
            action_match = re.search(r'(买入|卖出|持有|空仓|观望)', line)
            action = action_match.group(0) if action_match else "观望"
            reason = line.replace(date_str, "").replace(action, "").replace("|", "").replace(":", "").strip()
            results.append({"date": date_str, "action": action, "reason": reason})
        
        if len(results) == 0:
             # 如果解析失败，抛出 ValueError，并带上原文内容以便调试
             raise ValueError(f"AI返回内容格式无法解析: {content[:100]}...")
             
        return results
        
    except Exception as e:
        # 这里不要吞掉异常，不要返回默认值！直接往上抛！
        raise e 

def backtest_strategy(symbol, days=30):
    """
    回测 DeepSeek 策略 (最终稳定回退版)
    回归初心：串行处理，一次5天，但加上了极其严格的报错提示。
    """
    # 1. 获取数据
    print(f"📡 获取 {symbol} 过去 {days} 天的历史数据...")
    end_date = datetime.datetime.now().strftime("%Y%m%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days + 90)).strftime("%Y%m%d")
    
    try:
        import akshare as ak
        df_all = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
    except Exception as e:
        print(f"❌ 数据获取失败: {e}")
        return None

    if df_all is None or df_all.empty:
        return None

    # 2. 截取时间段
    total_len = len(df_all)
    if total_len < days:
        start_index = 0
    else:
        start_index = total_len - days

    # --- 2.5 计算技术指标 (向量化计算，飞快) ---
    # MACD
    # EMA12
    df_all['EMA12'] = df_all['收盘'].ewm(span=12, adjust=False).mean()
    # EMA26
    df_all['EMA26'] = df_all['收盘'].ewm(span=26, adjust=False).mean()
    # DIF
    df_all['DIF'] = df_all['EMA12'] - df_all['EMA26']
    # DEA
    df_all['DEA'] = df_all['DIF'].ewm(span=9, adjust=False).mean()
    # MACD柱
    df_all['MACD'] = 2 * (df_all['DIF'] - df_all['DEA'])
    
    # RSI (相对强弱指标, 14日)
    delta = df_all['收盘'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df_all['RSI'] = 100 - (100 / (1 + rs))
    
    # KDJ (随机指标, 9,3,3)
    low_list = df_all['最低'].rolling(window=9, min_periods=9).min()
    high_list = df_all['最高'].rolling(window=9, min_periods=9).max()
    rsv = (df_all['收盘'] - low_list) / (high_list - low_list) * 100
    df_all['K'] = rsv.ewm(com=2).mean()
    df_all['D'] = df_all['K'].ewm(com=2).mean()
    df_all['J'] = 3 * df_all['K'] - 2 * df_all['D']

    print(f"🚀 开始 AI 回测: {df_all.iloc[start_index]['日期']} ~ {df_all.iloc[-1]['日期']}")
    
    BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # 3. 准备任务 (退回到 5天一组，这是最稳的平衡点)
    BATCH_SIZE = 5
    batch_tasks = []
    
    current_batch_dates = []
    current_batch_text = ""
    
    for i in range(start_index, total_len - 1):
        today_row = df_all.iloc[i]
        
        # 强制日期转字符串
        today_date_str = str(today_row['日期'])

        # 获取预先算好的指标
        macd = today_row['MACD']
        rsi = today_row['RSI']
        k = today_row['K']
        d = today_row['D']
        
        # 简单的形态描述
        macd_signal = "金叉" if today_row['DIF'] > today_row['DEA'] else "死叉"
        rsi_signal = "超买" if rsi > 80 else ("超卖" if rsi < 20 else "正常")
        
        line = f"{today_date_str} | 收:{today_row['收盘']} | 涨:{today_row['涨跌幅']}% | MACD:{macd_signal}({macd:.2f}) | RSI:{rsi:.1f}({rsi_signal}) | KDJ_K:{k:.1f}"
        
        current_batch_dates.append(today_date_str)
        current_batch_text += line + "\n"
        
        if len(current_batch_dates) == BATCH_SIZE or i == total_len - 2:
            batch_tasks.append((list(current_batch_dates), str(current_batch_text)))
            current_batch_dates = []
            current_batch_text = ""

    advice_map = {} 
    
    # 串行执行，一旦出错，直接把具体错误存进 map，不再掩饰
    for idx, task in enumerate(batch_tasks):
        dates = task[0]
        text = task[1]
        
        try:
            result_list = get_ai_advice_batch(client, symbol, dates, text)
            for item in result_list:
                d = str(item.get("date")).strip() # 强制转字符串并去空格
                if d:
                    advice_map[d] = (item.get("action", "观望"), item.get("reason", ""))
        except Exception as e:
            # 关键修改：如果报错，把报错信息作为“理由”写进去！
            error_msg = str(e)
            for d in dates:
                advice_map[str(d)] = ("观望", f"ERROR: {error_msg}")
        
        # 稍微停顿一下
        time.sleep(0.5)

    # 4. 模拟交易结算
    initial_cash = 1000000.0
    cash = initial_cash
    position = 0
    cnt_win = 0
    cnt_loss = 0
    history = []

    for i in range(start_index, total_len - 1):
        today_row = df_all.iloc[i]
        next_day_row = df_all.iloc[i+1]
        date = str(today_row['日期']).strip() # 强制转字符串
        
        # 获取建议
        # 如果这里取出是 ERROR，那么理由里就会带有具体的报错信息
        advice_action, reason = advice_map.get(date, ("观望", "无数据(KeysNotFound)"))
        
        price = next_day_row['开盘']
        trade_action = "无"
        
        if advice_action == "买入":
            if position == 0:
                if cash > price * 100:
                    position = int(cash // price / 100) * 100 
                    cost_trade = position * price
                    cash -= cost_trade
                    trade_action = "买入"
                else:
                    trade_action = "资金不足"
                    
        elif advice_action in ["卖出", "空仓", "观望"]:
            if position > 0:
                revenue = position * price
                cash += revenue
                position = 0
                trade_action = "卖出"
            
        current_asset = cash + (position * next_day_row['收盘'])
        
        daily_return = next_day_row['涨跌幅']
        if position > 0:
            if daily_return > 0:
                cnt_win += 1
            elif daily_return < 0:
                cnt_loss += 1

        # 修正显示逻辑：如果空仓，AI说"持有"其实就是"观望"
        display_advice = advice_action
        if position == 0 and advice_action in ["持有", "卖出"]:
            display_advice = "观望 (空仓)"

        history.append({
            "日期": date,
            "收盘": next_day_row['收盘'], # 新增：用于计算基准收益
            "AI建议": display_advice,
            "理由": reason, 
            "实际操作": trade_action,
            "当日盈亏": daily_return if position > 0 else 0,
            "总资产": current_asset,
            "持仓股数": position,
            "现金": cash
        })

    if not history:
        return pd.DataFrame()

    return pd.DataFrame(history)

if __name__ == "__main__":
    backtest_strategy("600519", days=30)
