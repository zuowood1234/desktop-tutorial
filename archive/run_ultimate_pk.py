
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
    # 自动补齐前缀
    symbol = fix_stock_code(symbol)
    full_symbol = "sh" + symbol if symbol.startswith('6') else "sz" + symbol
    
    try:
        # 使用不复权数据排查问题，通常后复权更准
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
        
        # 筛选时间
        mask = (df['日期'] >= start_date) & (df['日期'] <= end_date)
        res = df.loc[mask].reset_index(drop=True)
        if res.empty:
            return None
        return res
    except Exception as e:
        return None

# ----------------- 策略 A (旧版) -----------------
# 1. A-技术: 纯均线
def strategy_a_tech(row, prev_row):
    if row['MA5'] > row['MA10'] > row['MA20']: return "买入"
    if row['MA5'] < row['MA10']: return "卖出"
    return "观望"

# 2. A-情绪: 均线 + 简单放量
def strategy_a_sent(row, prev_row):
    base_signal = strategy_a_tech(row, prev_row)
    vol_ratio = row['成交量'] / row['VOL5'] if row['VOL5'] > 0 else 1.0
    
    if base_signal == "买入" and vol_ratio > 1.2: return "买入"
    if base_signal == "卖出": return "卖出"
    # 情绪特有：缩量阴跌坚决卖
    if vol_ratio < 0.6 and row['涨跌幅'] < 0: return "卖出"
    return "观望"

# ----------------- 策略 B (新版) -----------------
# 3. B-技术: MACD + RSI
def strategy_b_tech(row, prev_row):
    # MACD金叉
    is_gold = row['MACD_DIFF'] > row['MACD_DEA'] and prev_row['MACD_DIFF'] <= prev_row['MACD_DEA']
    is_dead = row['MACD_DIFF'] < row['MACD_DEA']
    
    if is_gold and 30 < row['RSI_6'] < 75: return "买入"
    if is_dead or row['RSI_6'] > 80: return "卖出"
    if row['MACD_DIFF'] > row['MACD_DEA'] and row['RSI_6'] < 80: return "持有"
    return "观望"

# 4. B-情绪: 量比战法 (Hard Rules from yesterday)
def strategy_b_sent(row, prev_row):
    vol_ratio = row['成交量'] / row['VOL5'] if row['VOL5'] > 0 else 1.0
    change = row['涨跌幅']
    rsi = row['RSI_6']
    
    # 抢筹
    if vol_ratio > 1.8 and change > 2.0: return "买入"
    # 洗盘低吸
    if vol_ratio < 0.6 and -3.0 < change < -0.5 and rsi > 40: return "买入"
    # 出货
    if vol_ratio > 2.0 and change < -1.0: return "卖出"
    # 阴跌
    if vol_ratio < 0.8 and change < 0 and rsi < 40: return "卖出"
    
    return "观望"

# ----------------- 回测核心逻辑 (统一账户算法) -----------------
def run_simulation(df, signal_source, is_reference_data=False):
    capital = 1000000 # 初始一百万
    position = 0
    balance = capital
    cost_price = 0
    final_val = capital
    
    # 如果是参考数据(策略C)，signal_source 是一个 Series (日期->操作)
    # 如果是实时算(AB)，signal_source 是函数
    
    for i in range(1, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        date_str = curr['日期'].strftime('%Y-%m-%d')
        price = curr['收盘']
        
        action = "观望"
        
        if is_reference_data:
            # 策略 C: 查表
            # 注意: 参考数据的日期可能缺漏，或者格式不一致
            # 我们做个模糊匹配
            try:
                # 昨天文件里的日期是 string，这里转过 datetime了，需要转回去匹配
                match_row = signal_source[signal_source['日期'] == date_str]
                if not match_row.empty:
                    action = match_row.iloc[0]
            except:
                pass
        else:
            # 策略 AB: 实时算
            action = signal_source(curr, prev)
            
        # 状态机交易 (全仓进出，简单粗暴测收益能力)
        if "买入" in str(action) and position == 0:
            position = balance // price
            balance -= position * price
            cost_price = price
        elif "卖出" in str(action) and position > 0:
            balance += position * price
            position = 0
            cost_price = 0
            
    # 期末结算
    if position > 0:
        balance += position * df.iloc[-1]['收盘']
        
    return (balance - capital) / capital * 100

def load_reference_data():
    file_path = "backtest_details_advanced.csv"
    if not os.path.exists(file_path): 
        return None
    
    # 读入所有列
    df = pd.read_csv(file_path)
    # 对代码补位
    df['代码'] = df['代码'].apply(fix_stock_code)
    return df

if __name__ == "__main__":
    ref_df = load_reference_data()
    if ref_df is None:
        print("未找到昨天的参考文件 backtest_details_advanced.csv")
        exit()
        
    # 获取唯一的股票列表 (全量 30 只)
    unique_stocks = ref_df['代码'].unique()
    print(f"检测到 {len(unique_stocks)} 只目标股票，开始全量严谨回测...")
    
    results = []
    
    for code in unique_stocks:
        # 获取行情
        df = get_data(code)
        if df is None or len(df) < 100: # 没数据的跳过
            print(f"Skipping {code} (No Data)")
            continue
            
        print(f"Processing {code}...")
        
        # 1. 跑 A (技术/情绪)
        roi_a_tech = run_simulation(df, strategy_a_tech)
        roi_a_sent = run_simulation(df, strategy_a_sent)
        
        # 2. 跑 B (技术/情绪)
        roi_b_tech = run_simulation(df, strategy_b_tech)
        roi_b_sent = run_simulation(df, strategy_b_sent)
        
        # 3. 提取 C (技术/情绪) 来自参考文件
        # 提取该股票的历史记录
        stock_ref = ref_df[ref_df['代码'] == code]
        
        # 策略C-技术派 (提取 '技术派操作' 列)
        c_tech_signals = stock_ref[['日期', '技术派操作']].copy()
        c_tech_signals.columns = ['日期', '操作']
        roi_c_tech = run_simulation(df, c_tech_signals['操作'], is_reference_data=True) # 这里传入 Series 稍微改下逻辑，传入 DF 查表
        
        # 策略C-情绪派 (提取 '情绪派操作' 列)
        c_sent_signals = stock_ref[['日期', '情绪派操作']].copy()
        c_sent_signals.columns = ['日期', '操作']
        roi_c_sent = run_simulation(df, c_sent_signals['操作'], is_reference_data=True)
        
        # 修正: 上面的 run_simulation 逻辑里查表有点问题，重写内部
        # 为了不改动主函数太复杂，我们在这里特化处理 C:
        # (其实在 loop 里传入 stock_ref 配合 is_reference_data=True 以及一个 col_name 会更好)
        # 这里临时打补丁修正上面的逻辑 BUG
        def run_c_correct(df, ref_sub_df, col_name):
            cap = 1000000; pos = 0; bal = cap
            # 转为字典加速
            lookup = ref_sub_df.set_index('日期')[col_name].to_dict()
            
            for i in range(len(df)):
                d = df.iloc[i]['日期'].strftime('%Y-%m-%d')
                act = lookup.get(d, "观望")
                p = df.iloc[i]['收盘']
                
                if "买入" in str(act) and pos == 0:
                    pos = bal // p; bal -= pos * p
                elif "卖出" in str(act) and pos > 0:
                    bal += pos * p; pos = 0
            if pos > 0: bal += pos * df.iloc[-1]['收盘']
            return (bal - cap)/cap * 100
            
        roi_c_tech = run_c_correct(df, stock_ref, '技术派操作')
        roi_c_sent = run_c_correct(df, stock_ref, '情绪派操作')

        results.append({
            "股票": code,
            "A-技术": roi_a_tech, "A-情绪": roi_a_sent,
            "B-技术": roi_b_tech, "B-情绪": roi_b_sent,
            "C-技术(AI)": roi_c_tech, "C-情绪(AI)": roi_c_sent
        })
        
    final_df = pd.DataFrame(results)
    
    # 格式化百分比
    fmt_cols = ["A-技术", "A-情绪", "B-技术", "B-情绪", "C-技术(AI)", "C-情绪(AI)"]
    for c in fmt_cols:
        final_df[c] = final_df[c].apply(lambda x: f"{x:.2f}%")
        
    final_df.to_excel("Ultimate_Strategy_Comparison_6Cols.xlsx", index=False)
    print(final_df)
