
import os
import akshare as ak
import pandas as pd
import numpy as np
import warnings
from ta.trend import MACD
from ta.momentum import RSIIndicator, StochasticOscillator

warnings.filterwarnings('ignore')

# 修复股票代码补0问题
def fix_stock_code(code):
    code_str = str(code).split('.')[0]
    return code_str.zfill(6)

# ----------------- 数据加载 (带重试和补0) -----------------
def get_data(symbol, start_date="2024-02-01", end_date="2025-02-09"):
    symbol = fix_stock_code(symbol)
    full_symbol = "sh" + symbol if symbol.startswith('6') else "sz" + symbol
    
    try:
        df = ak.stock_zh_a_daily(symbol=full_symbol, adjust="qfq")
        if df is None or df.empty:
            return None
            
        df = df.rename(columns={
            'date': '日期', 'open': '开盘', 'high': '最高', 
            'low': '最低', 'close': '收盘', 'volume': '成交量'
        })
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.sort_values('日期')
        
        # 指标计算
        macd = MACD(close=df['收盘'])
        df['MACD_DIFF'] = macd.macd()
        df['MACD_DEA'] = macd.macd_signal()
        df['RSI_6'] = RSIIndicator(close=df['收盘'], window=6).rsi()
        df['MA5'] = df['收盘'].rolling(window=5).mean()
        df['MA10'] = df['收盘'].rolling(window=10).mean()
        df['MA20'] = df['收盘'].rolling(window=20).mean()
        df['VOL5'] = df['成交量'].rolling(window=5).mean()
        df['涨跌幅'] = df['收盘'].pct_change() * 100
        
        mask = (df['日期'] >= start_date) & (df['日期'] <= end_date)
        res = df.loc[mask].reset_index(drop=True)
        if res.empty:
            return None
        return res
    except Exception as e:
        return None

# ----------------- 策略 AB 逻辑 -----------------
def strategy_a_tech(row, prev_row):
    if row['MA5'] > row['MA10'] > row['MA20']: return "买入"
    if row['MA5'] < row['MA10']: return "卖出"
    return "观望"

def strategy_a_sent(row, prev_row):
    base_signal = strategy_a_tech(row, prev_row)
    vol_ratio = row['成交量'] / row['VOL5'] if row['VOL5'] > 0 else 1.0
    if base_signal == "买入" and vol_ratio > 1.2: return "买入"
    if base_signal == "卖出": return "卖出"
    if vol_ratio < 0.6 and row['涨跌幅'] < 0: return "卖出"
    return "观望"

def strategy_b_tech(row, prev_row):
    is_gold = row['MACD_DIFF'] > row['MACD_DEA'] and prev_row['MACD_DIFF'] <= prev_row['MACD_DEA']
    is_dead = row['MACD_DIFF'] < row['MACD_DEA']
    if is_gold and 30 < row['RSI_6'] < 75: return "买入"
    if is_dead or row['RSI_6'] > 80: return "卖出"
    if row['MACD_DIFF'] > row['MACD_DEA'] and row['RSI_6'] < 80: return "持有"
    return "观望"

def strategy_b_sent(row, prev_row):
    vol_ratio = row['成交量'] / row['VOL5'] if row['VOL5'] > 0 else 1.0
    change = row['涨跌幅']
    rsi = row['RSI_6']
    if vol_ratio > 1.8 and change > 2.0: return "买入"
    if vol_ratio < 0.6 and -3.0 < change < -0.5 and rsi > 40: return "买入"
    if vol_ratio > 2.0 and change < -1.0: return "卖出"
    if vol_ratio < 0.8 and change < 0 and rsi < 40: return "卖出"
    return "观望"

# ----------------- 回测 (只算AB) -----------------
def run_simulation(df, signal_source):
    capital = 1000000
    position = 0
    balance = capital
    
    for i in range(1, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        price = curr['收盘']
        
        action = signal_source(curr, prev)
            
        if "买入" in str(action) and position == 0:
            position = balance // price
            balance -= position * price
        elif "卖出" in str(action) and position > 0:
            balance += position * price
            position = 0
            
    if position > 0:
        balance += position * df.iloc[-1]['收盘']
        
    return (balance - capital) / capital * 100

# ----------------- 加载策略 C 官方总结 -----------------
def load_c_summary():
    file_path = "backtest_summary_advanced.csv"
    if not os.path.exists(file_path):
        print(f"Error: Summary file {file_path} not found!")
        return None
    
    df = pd.read_csv(file_path)
    # df 应该包含 '代码', '技术派总收益(%)', '情绪派总收益(%)' 等列
    df['代码'] = df['代码'].apply(fix_stock_code)
    return df

if __name__ == "__main__":
    # 1. 加载 C 的官方总结
    c_summary_df = load_c_summary()
    if c_summary_df is None:
        exit()
        
    # 获取目标股票列表 (从 C 的总结里直接拿)
    unique_stocks = c_summary_df['代码'].unique()
    print(f"检测到 {len(unique_stocks)} 只目标股票，开始混合对比...")
    
    results = []
    
    for code in unique_stocks:
        # 2. 查 C 的现成数据 (精确)
        # 假设总结文件里的列名如下 (如果不匹配可能需要调整)
        try:
            row_c = c_summary_df[c_summary_df['代码'] == code].iloc[0]
            # 正确的列名是 '纯技术派(1年)' 和 '情绪增强派(1年)'
            roi_c_tech = row_c.get('纯技术派(1年)', '0%') 
            roi_c_sent = row_c.get('情绪增强派(1年)', '0%')
            
            # 去掉 % 符号并转为浮点数
            if isinstance(roi_c_tech, str): roi_c_tech = float(roi_c_tech.replace('%', ''))
            if isinstance(roi_c_sent, str): roi_c_sent = float(roi_c_sent.replace('%', ''))
        except Exception as e:
            print(f"Error parsing C summary for {code}: {e}")
            roi_c_tech = 0.0
            roi_c_sent = 0.0
            
        # 3. 算 A/B 的新数据
        df = get_data(code)
        if df is None or len(df) < 100:
            print(f"Skipping {code} (No Market Data)")
            continue
            
        #print(f"Calculating AB for {code}...")
        
        roi_a_tech = run_simulation(df, strategy_a_tech)
        roi_a_sent = run_simulation(df, strategy_a_sent)
        roi_b_tech = run_simulation(df, strategy_b_tech)
        roi_b_sent = run_simulation(df, strategy_b_sent)
        
        results.append({
            "股票": code,
            "A-技术(均线)": roi_a_tech, "A-情绪(放量)": roi_a_sent,
            "B-技术(指标)": roi_b_tech, "B-情绪(量法)": roi_b_sent,
            "C-技术(AI官方)": roi_c_tech, "C-情绪(AI官方)": roi_c_sent
        })
        
    final_df = pd.DataFrame(results)
    
    # 格式化
    fmt_cols = ["A-技术(均线)", "A-情绪(放量)", "B-技术(指标)", "B-情绪(量法)", "C-技术(AI官方)", "C-情绪(AI官方)"]
    for c in fmt_cols:
        final_df[c] = final_df[c].apply(lambda x: f"{x:.2f}%")
        
    final_df.to_excel("Final_Strategy_Comparison_Directly_Extracted.xlsx", index=False)
    print(final_df)
