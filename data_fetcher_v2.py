import os
import pandas as pd
import numpy as np
import akshare as ak
import datetime
from tqdm import tqdm
import time

# 定义存储路径
DATA_DIR = "backtest_data"
VAULT_DIR = os.path.join(DATA_DIR, "vault")
BUFFER_DIR = os.path.join(DATA_DIR, "buffer")

# 创建目录
os.makedirs(VAULT_DIR, exist_ok=True)
os.makedirs(BUFFER_DIR, exist_ok=True)

def get_trading_calendar(start_date="20050101"):
    """
    获取真实的交易日历作为绝对的对齐基准 (Master Calendar)
    """
    print("正在获取 A股 交易日历...")
    calendar_df = ak.tool_trade_date_hist_sina()
    calendar_df['trade_date'] = pd.to_datetime(calendar_df['trade_date']).dt.date
    
    # 过滤出给定时间之后的数据
    start_dt = pd.to_datetime(start_date).date()
    calendar_obj = calendar_df[calendar_df['trade_date'] >= start_dt].copy()
    calendar_obj['Date'] = pd.to_datetime(calendar_obj['trade_date'])
    calendar_obj = calendar_obj[['Date']].sort_values('Date').reset_index(drop=True)
    return calendar_obj

def fetch_stock_history_dual(code, start_date="20050101", end_date=None):
    """
    针对单只股票，分别获取【不复权(Raw)】和【前复权(Qfq)】的数据，并进行横向拼接拼接入库。
    """
    if end_date is None:
        end_date = datetime.datetime.now().strftime("%Y%m%d")
        
    try:
        # 1. 获取不复权数据 (用于算真实成交额，盈亏，市值，涨跌停计算)
        df_raw = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="")
        if df_raw.empty:
            return None
            
        df_raw['日期'] = pd.to_datetime(df_raw['日期'])
        df_raw = df_raw.rename(columns={
            '日期': 'Date',
            '开盘': 'Open_Raw',
            '最高': 'High_Raw',
            '最低': 'Low_Raw',
            '收盘': 'Close_Raw',
            '成交量': 'Volume',
            '成交额': 'Turnover',
            '换手率': 'Turnover_Rate',
            '涨跌幅': 'Pct_Chg_Raw'
        })
        # 取出需要的 Raw 列
        raw_cols = ['Date', 'Open_Raw', 'High_Raw', 'Low_Raw', 'Close_Raw', 'Volume', 'Turnover', 'Turnover_Rate', 'Pct_Chg_Raw']
        df_raw = df_raw[raw_cols].copy()

        # 2. 获取前复权数据 (用于算技术指标，无跳空缺口)
        df_qfq = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        if df_qfq.empty:
            return None
            
        df_qfq['日期'] = pd.to_datetime(df_qfq['日期'])
        df_qfq = df_qfq.rename(columns={
            '日期': 'Date',
            '开盘': 'Open_Qfq',
            '最高': 'High_Qfq',
            '最低': 'Low_Qfq',
            '收盘': 'Close_Qfq'
        })
        qfq_cols = ['Date', 'Open_Qfq', 'High_Qfq', 'Low_Qfq', 'Close_Qfq']
        df_qfq = df_qfq[qfq_cols].copy()

        # 3. 将两者基于 Date 进行精准合并 (Inner Join)
        df_merged = pd.merge(df_raw, df_qfq, on='Date', how='inner')
        if df_merged.empty:
            return None
            
        df_merged['Code'] = code
        return df_merged
        
    except Exception as e:
        print(f"获取 {code} 数据时发生错误: {e}")
        return None

def calc_daily_limits_and_flags(df):
    """
    基于合并后的单票 DataFrame，计算 `limit_up` / `limit_down` / `is_trading` / `is_st`
    （基于每日的价格判断）
    """
    # 按照日期排序确保逻辑正确
    df = df.sort_values("Date").reset_index(drop=True)
    
    # 获取前一日的不复权收盘价用于计算今日涨跌停
    df['Prev_Close_Raw'] = df['Close_Raw'].shift(1)
    
    # 动态确定板块的涨跌幅限制
    # - 创业板(300)、科创板(688) 为 20% (注：创业板虽然2020年后才实行20%，此处我们可用简化逻辑：若涨跌幅超过10%，或属于新规日之后，先统一以板块目前属性近似)
    # - 主板 为 10%
    # - ST 为 5%
    
    # 为了防止大量历史涨跌停幅度规则（上市首日等）的逻辑错误，
    # 更好的实战算法是：根据昨日收盘价和代码前缀计算今日理论涨跌停价
    def get_limit_pct(code, date):
        # 简化版涨跌停限制
        if code.startswith('688'):
            return 0.20
        elif code.startswith('300'):
            # 创业板改革日期 2020-08-24
            if date >= pd.to_datetime('2020-08-24'):
                return 0.20
            else:
                return 0.10
        elif code.startswith('8') or code.startswith('4') or code.startswith('8') or code.startswith('9'):
            return 0.30  # 北交所
        else:
            return 0.10 # 主板 10%
            
    # 计算涨跌停价（采用标准的 A股 四舍五入到 2 位小数计算规则）
    limits_up = []
    limits_down = []
    for i, row in df.iterrows():
        if pd.isna(row['Prev_Close_Raw']):
            # 缺失前收盘的情况（如上市第一天），当日通常不设涨停或由发行价决定，这里可以近似将最高最低设为涨停跌停
            limits_up.append(row['High_Raw']) 
            limits_down.append(row['Low_Raw'])
            continue
            
        pct = get_limit_pct(row['Code'], row['Date'])
        # 真实的 ST 属性历史追踪非常难（需要专业数据源），这里先假定当前涨跌幅如果是 5% 级别，很有可能是ST
        # 这是一个 Trick，能在无昂贵数据源的情况下抓到大多历史 ST 状态
        is_suspected_st = abs(row['Pct_Chg_Raw']) < 5.5 and abs(row['Pct_Chg_Raw']) > 4.5 and (row['High_Raw'] == row['Low_Raw'] or row['Close_Raw'] == row['High_Raw'] or row['Close_Raw'] == row['Low_Raw'])
        if is_suspected_st and abs(round(row['Prev_Close_Raw'] * 1.05, 2) - row['High_Raw']) < 0.02:
            pct = 0.05
            
        limit_up_price = round(row['Prev_Close_Raw'] * (1 + pct), 2)
        limit_down_price = round(row['Prev_Close_Raw'] * (1 - pct), 2)
        limits_up.append(limit_up_price)
        limits_down.append(limit_down_price)
        
    df['limit_up'] = limits_up
    df['limit_down'] = limits_down
    
    return df

def align_with_master_calendar(df, master_calendar_df):
    """
    将股票数据与 Master Calendar对齐，填补缺失日，增加 is_trading 标志
    """
    code = df['Code'].iloc[0] if not df.empty else "UNKNOWN"
    
    # Left join with master calendar
    aligned_df = pd.merge(master_calendar_df, df, on='Date', how='left')
    
    # is_trading 标记
    # 如果 Volume > 0 且 Close_Raw 不为空，则判定为交易日
    aligned_df['is_trading'] = aligned_df['Close_Raw'].notna() & (aligned_df['Volume'] > 0)
    
    # 填充非交易日的 Code
    aligned_df['Code'] = code
    aligned_df['Volume'] = aligned_df['Volume'].fillna(0)
    aligned_df['Turnover'] = aligned_df['Turnover'].fillna(0)
    
    return aligned_df

def build_single_stock_vault(code, master_calendar_df, start_date="20050101"):
    """
    构建存入 Vault 的单票 Parquet 数据文件
    """
    print(f"正在构建 {code} 的历史数据池...")
    # 1. 下载双轨道数据
    df = fetch_stock_history_dual(code, start_date=start_date)
    if df is None or df.empty:
        print(f"未能获取到 {code} 的历史数据。")
        return False
        
    # 2. 计算涨跌停等标志性属性
    df = calc_daily_limits_and_flags(df)
    
    # 3. 与主日历对齐 (插入停牌的 NaN 数据)
    # 我们只对齐这只股票上市之日到当前的数据，上市前的部分留空即可
    first_trade_date = df['Date'].min()
    current_stock_calendar = master_calendar_df[master_calendar_df['Date'] >= first_trade_date].copy()
    
    final_df = align_with_master_calendar(df, current_stock_calendar)
    
    # 4. 追加保存入 Vault 目录
    out_path = os.path.join(VAULT_DIR, f"{code}.parquet")
    final_df.to_parquet(out_path, engine="pyarrow", index=False)
    print(f" ---> {code} 数据已经成功入库 (包含 {len(final_df)} 个历史交易日，包含停牌)，路径：{out_path}")
    return True

if __name__ == "__main__":
    print("=== A股量化回测系统 - 数据冷库(Vault)构建脚本 ===")
    
    # 获取上帝日历
    master_cal = get_trading_calendar(start_date="20050101")
    
    # 测试获取热门指数及大白马（我们可以先小规模测试）
    # 600519(茅台), 000001(平安银行), 300750(宁德时代), 688981(中芯国际), 002050(三花智控)
    # 新增: 002460(赣锋锂业), 601012(隆基绿能), 002456(欧菲光), 002920(德赛西威), 000333(美的集团), 300999(金龙鱼)
    test_codes = [
        "600519", "000001", "300750", "688981", "002050",
        "002460", "601012", "002456", "002920", "000333", "300999"
    ]
    
    for code in test_codes:
        build_single_stock_vault(code, master_cal, start_date="20050101")
        time.sleep(1) # 防止请求过快被 AkShare API 封禁
        
    print("\n测试股票数据已经抓取完毕并构建好了 Super_Parquet 结构！")
