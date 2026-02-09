
import os
import akshare as ak
import pandas as pd
import numpy as np
import warnings
from ta.trend import MACD
from ta.momentum import RSIIndicator, StochasticOscillator

warnings.filterwarnings('ignore')

# ----------------- 数据加载 -----------------
def get_data(symbol, start_date="2024-02-01", end_date="2025-02-09"):
    full_symbol = "sh" + symbol if symbol.startswith('6') else "sz" + symbol
    print(f"Fetch data for {full_symbol}...")
    try:
        df = ak.stock_zh_a_daily(symbol=full_symbol, adjust="qfq")
        df = df.rename(columns={
            'date': '日期', 'open': '开盘', 'high': '最高', 
            'low': '最低', 'close': '收盘', 'volume': '成交量'
        })
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.sort_values('日期')
        df['涨跌幅'] = df['收盘'].pct_change() * 100
        
        # 指标计算
        macd = MACD(close=df['收盘'])
        df['MACD_DIFF'] = macd.macd()
        df['MACD_DEA'] = macd.macd_signal()
        df['RSI_6'] = RSIIndicator(close=df['收盘'], window=6).rsi()
        kdj = StochasticOscillator(high=df['最高'], low=df['最低'], close=df['收盘'])
        df['K'] = kdj.stoch()
        df['D'] = kdj.stoch_signal()
        df['MA5'] = df['收盘'].rolling(window=5).mean()
        df['MA10'] = df['收盘'].rolling(window=10).mean()
        df['MA20'] = df['收盘'].rolling(window=20).mean()
        df['VOL5'] = df['成交量'].rolling(window=5).mean()
        
        # 筛选时间
        mask = (df['日期'] >= start_date) & (df['日期'] <= end_date)
        return df.loc[mask].reset_index(drop=True)
    except Exception as e:
        print(f"Error: {e}")
        return None

# ----------------- 策略 A: 均线派 (MA) -----------------
def strategy_a(row, prev_row):
    """
    买入: MA5 > MA10 > MA20 (多头排列)
    卖出: MA5 < MA10 (死叉)
    """
    score = 50
    reasons = []
    
    # 简单的硬逻辑
    if row['MA5'] > row['MA10'] > row['MA20']:  score += 25; reasons.append("MA多头")
    elif row['MA5'] < row['MA10']:              score -= 25; reasons.append("MA死叉")
    
    # 动作映射
    action = "观望"
    if score >= 70: action = "买入"
    elif score <= 40: action = "卖出"
    elif 40 < score < 70: action = "持有"
    
    return action, reasons

# ----------------- 策略 B: 指标派 (MACD/RSI) -----------------
def strategy_b(row, prev_row):
    """
    买入: MACD金叉 + RSI健康(20-80)
    卖出: MACD死叉 或 RSI>80
    """
    score = 50
    reasons = []
    
    # MACD
    if row['MACD_DIFF'] > row['MACD_DEA']:
        score += 10
        if prev_row['MACD_DIFF'] <= prev_row['MACD_DEA']:
            score += 20; reasons.append("MACD金叉")
    elif row['MACD_DIFF'] < row['MACD_DEA']:
        score -= 20; reasons.append("MACD死叉")

    # RSI
    if row['RSI_6'] > 80: score -= 40; reasons.append("RSI超买")
    elif row['RSI_6'] < 20: score += 20; reasons.append("RSI超卖")
    
    action = "观望"
    if score >= 75: action = "买入"
    elif score <= 40: action = "卖出"
    elif 40 < score < 75: action = "持有"
    
    return action, reasons

# ----------------- 加载策略 C (AI派) 参考数据 -----------------
def load_strategy_c_reference():
    """读取昨天生成的 backtest_details_advanced.csv 作为 策略 C 的真值"""
    ref_file = "backtest_details_advanced.csv"
    if not os.path.exists(ref_file):
        print("Error: Reference file not found!")
        return pd.DataFrame()
    
    df = pd.read_csv(ref_file)
    # 假设 '情绪派操作' 列就是昨天的 AI 决策
    # 我们需要构建一个快速查找表: (code, date) -> (action, reason)
    # 注意：昨天的文件可能没有 '理由' 列，只有 '操作'。我们暂且只取操作。
    return df

# ----------------- 回测引擎 -----------------
def run_backtest(df, strat_func, strat_name, ref_ai_df=None, code=None):
    capital = 100000
    position = 0
    cost = 0
    logs = []
    
    # 如果是策略 C，需要预处理查找表
    ai_lookup = {}
    if strat_name == "策略C(AI)" and not ref_ai_df.empty:
        # 筛选该股票
        sub = ref_ai_df[ref_ai_df['代码'].astype(str) == code]
        for _, r in sub.iterrows():
            d_str = r['日期']
            act = r['情绪派操作'] # 复用昨天的情绪派结果
            ai_lookup[d_str] = act
            
    for i in range(1, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        date_str = curr['日期'].strftime('%Y-%m-%d')
        price = curr['收盘']
        
        # --- 决策 ---
        if strat_name == "策略C(AI)":
            # 查表
            action = ai_lookup.get(date_str, "观望")
            reason = ["AI历史记录"]
        else:
            # 实时算
            action, reason = strat_func(curr, prev)
        
        # --- 风控 (策略C 昨天可能已经含风控，这里只对 AB 强制风控) ---
        if strat_name != "策略C(AI)" and position > 0 and (price - cost)/cost < -0.10:
            action = "卖出"
            reason.append("硬止损")
            
        # --- 交易执行 ---
        if action == "买入" and position == 0:
            position = capital // price
            cost = price
            capital -= position * price
            logs.append([strat_name, date_str, "买入", price, position, "|".join(reason)])
            
        elif action == "卖出" and position > 0:
            capital += position * price
            profit = (price - cost) / cost * 100
            logs.append([strat_name, date_str, "卖出", price, position, f"{'|'.join(reason)} (盈亏:{profit:.1f}%)"])
            position = 0
            cost = 0
            
    final_val = capital + (position * df.iloc[-1]['收盘'])
    roi = (final_val - 100000) / 100000 * 100
    return roi, logs

if __name__ == "__main__":
    # 昨天的股票池 (必须和 CSV 里的一致，才能复用策略 C)
    # 根据用户刚才看到的文件内容，股票有: 600703, 002910, 601698 等
    # 我们这里只跑 CSV 里存在的股票，进行公平 PK
    
    ref_df = load_strategy_c_reference()
    if ref_df.empty:
        print("无法加载策略 C 参考数据")
        exit()
        
    # 从参考文件中提取股票列表 (去重)
    target_stocks = ref_df['代码'].unique().astype(str).tolist()
    print(f"将要对比的股票: {target_stocks}")
    
    all_summary = []
    
    writer = pd.ExcelWriter("PK_Strategy_ABC_Revived.xlsx", engine='xlsxwriter')
    
    for code in target_stocks:
        print(f"Running metrics for {code}...")
        df = get_data(code)
        if df is None or df.empty: continue
        
        # 1. 跑 A
        roi_a, logs_a = run_backtest(df, strategy_a, "策略A(均线)", code=code)
        # 2. 跑 B
        roi_b, logs_b = run_backtest(df, strategy_b, "策略B(指标)", code=code)
        # 3. 跑 C (复用)
        roi_c, logs_c = run_backtest(df, None, "策略C(AI)", ref_ai_df=ref_df, code=code)
        
        all_summary.append({
            "股票": code,
            "策略A(均线)": f"{roi_a:.2f}%",
            "策略B(指标)": f"{roi_b:.2f}%",
            "策略C(AI)": f"{roi_c:.2f}%",
            "胜者": max([("A", roi_a), ("B", roi_b), ("C", roi_c)], key=lambda x:x[1])[0]
        })
        
        # 保存明细
        full_logs = logs_a + logs_b + logs_c
        log_df = pd.DataFrame(full_logs, columns=["策略", "日期", "操作", "价格", "股数", "理由"])
        log_df = log_df.sort_values(['日期', '策略'])
        log_df.to_excel(writer, sheet_name=str(code), index=False)
        
    # 总表
    sum_df = pd.DataFrame(all_summary)
    sum_df.to_excel(writer, sheet_name="总成绩单", index=False)
    writer.close()
    
    print("\n========= 最终 PK 结果 =========")
    print(sum_df)
    print("\n详细交易单已保存至 PK_Strategy_ABC_Revived.xlsx")
