import os
import pandas as pd
import numpy as np
import ta
import warnings
warnings.filterwarnings('ignore')

VAULT_DIR = "backtest_data/vault"
SUPER_VAULT_DIR = "backtest_data/super_vault"
os.makedirs(SUPER_VAULT_DIR, exist_ok=True)

def calculate_super_features(df):
    """
    接收基础的行情数据表，计算所有的技术指标和特征因子
    必须强制使用 _Qfq (前复权) 数据来计算技术指标，以防跳空缺口导致指标失真
    """
    print(f"  -> 正在为 {df['Code'].iloc[-1] if not df['Code'].isna().all() else 'Unknown'} 计算全维特征矩阵...")
    
    # 临时过滤掉停牌日（NaN列）以保证指标计算顺滑，计算后再 merge 回去
    valid_df = df[df['is_trading'] == True].copy()
    if valid_df.empty:
        return df

    ta_df = pd.DataFrame(index=valid_df.index) 
    
    # 提取用于计算的前复权价格
    open_p = valid_df['Open_Qfq']
    high_p = valid_df['High_Qfq']
    low_p = valid_df['Low_Qfq']
    close_p = valid_df['Close_Qfq']
    volume_p = valid_df['Volume'] # 成交量用真实的

    # 1. 均线系统 (Moving Averages)
    ta_df['MA_5'] = valid_df['Close_Qfq'].rolling(window=5).mean()
    ta_df['MA_10'] = valid_df['Close_Qfq'].rolling(window=10).mean()
    ta_df['MA_20'] = valid_df['Close_Qfq'].rolling(window=20).mean()
    ta_df['MA_60'] = valid_df['Close_Qfq'].rolling(window=60).mean()
    ta_df['MA_120'] = valid_df['Close_Qfq'].rolling(window=120).mean()
    ta_df['MA_250'] = valid_df['Close_Qfq'].rolling(window=250).mean()

    ta_df['MA_6'] = valid_df['Close_Qfq'].rolling(window=6).mean()
    ta_df['MA_12'] = valid_df['Close_Qfq'].rolling(window=12).mean()
    
    # 动能因子：乖离率 (BIAS)
    ta_df['BIAS_6'] = (close_p - ta_df['MA_6']) / ta_df['MA_6'] * 100
    ta_df['BIAS_12'] = (close_p - ta_df['MA_12']) / ta_df['MA_12'] * 100
    ta_df['BIAS_20'] = (close_p - ta_df['MA_20']) / ta_df['MA_20'] * 100
    ta_df['BIAS_60'] = (close_p - ta_df['MA_60']) / ta_df['MA_60'] * 100

    # 动能因子：价格在250日内的分位值
    rolling_max_250 = close_p.rolling(window=250, min_periods=60).max()
    rolling_min_250 = close_p.rolling(window=250, min_periods=60).min()
    ta_df['Price_Loc_250'] = (close_p - rolling_min_250) / (rolling_max_250 - rolling_min_250)

    # 2. 震荡指标 (Oscillators)
    # MACD 
    macd_obj = ta.trend.MACD(close=close_p, window_slow=26, window_fast=12, window_sign=9)
    ta_df['MACD'] = macd_obj.macd()
    ta_df['MACD_Signal'] = macd_obj.macd_signal()
    ta_df['MACD_Hist'] = macd_obj.macd_diff()
    
    # 【高阶逻辑预计算】 MACD 交叉信号预埋
    # 金叉：今天红柱(>0)，且昨天是绿柱(<=0)
    ta_df['MACD_Golden_Cross'] = (ta_df['MACD_Hist'] > 0) & (ta_df['MACD_Hist'].shift(1) <= 0)
    # 死叉：今天绿柱(<0)，且昨天是红柱(>=0)
    ta_df['MACD_Dead_Cross'] = (ta_df['MACD_Hist'] < 0) & (ta_df['MACD_Hist'].shift(1) >= 0)

    # RSI
    ta_df['RSI_14'] = ta.momentum.RSIIndicator(close=close_p, window=14).rsi()

    # KDJ (Stochastic Oscillator)
    stoch = ta.momentum.StochasticOscillator(high=high_p, low=low_p, close=close_p, window=9, smooth_window=3)
    ta_df['KDJ_K'] = stoch.stoch()
    ta_df['KDJ_D'] = stoch.stoch_signal()
    # J = 3K - 2D
    ta_df['KDJ_J'] = 3 * ta_df['KDJ_K'] - 2 * ta_df['KDJ_D']

    # 3. 趋势与波动率指标
    # Bollinger Bands
    bbands = ta.volatility.BollingerBands(close=close_p, window=20, window_dev=2)
    ta_df['BOLL_Lower'] = bbands.bollinger_lband()
    ta_df['BOLL_Mid'] = bbands.bollinger_mavg()
    ta_df['BOLL_Upper'] = bbands.bollinger_hband()

    # ATR
    atr_obj = ta.volatility.AverageTrueRange(high=high_p, low=low_p, close=close_p, window=14)
    ta_df['ATR_14'] = atr_obj.average_true_range()
    ta_df['ATR_Ratio'] = ta_df['ATR_14'] / close_p

    # 将算好的 TA_df 横向拼接到 valid_df
    enriched_valid_df = pd.concat([valid_df, ta_df], axis=1)

    # 4. A股特色定制因子 
    # 换手率异动 Z-Score （判断突发天量）
    turnover = enriched_valid_df['Turnover_Rate']
    ma_turnover_20 = turnover.rolling(window=20, min_periods=5).mean()
    std_turnover_20 = turnover.rolling(window=20, min_periods=5).std()
    enriched_valid_df['Turnover_ZScore'] = (turnover - ma_turnover_20) / std_turnover_20
    
    # 量比因子与地量因子
    volume_series_p = enriched_valid_df['Volume']
    ma_volume_5 = volume_series_p.rolling(window=5, min_periods=2).mean()
    ma_volume_20 = volume_series_p.rolling(window=20, min_periods=5).mean()
    enriched_valid_df['Vol_Ratio_5D'] = volume_series_p / ma_volume_5.shift(1)  # 严格防未来，与过去5日均量对比
    # 地量标志：今天的量不到过去20天均量的一半
    enriched_valid_df['Vol_Shrink_20D'] = (volume_series_p < (ma_volume_20 * 0.5))

    # 连板基因挖掘: 近 5 日与 10 日涨停次数
    is_limit_up = (enriched_valid_df['Close_Raw'] >= enriched_valid_df['limit_up'])
    enriched_valid_df['Limit_Up_Count_5'] = is_limit_up.rolling(window=5, min_periods=1).sum()
    enriched_valid_df['Limit_Up_Count_10'] = is_limit_up.rolling(window=10, min_periods=1).sum()
    
    # 防止接飞刀：近 5 日跌停次数
    is_limit_down = (enriched_valid_df['Close_Raw'] <= enriched_valid_df['limit_down'])
    enriched_valid_df['Limit_Down_Count_5'] = is_limit_down.rolling(window=5, min_periods=1).sum()
    
    # [模拟因子] 封单成交比估算 (Limit_Up_Seal_Ratio)
    # 真实封成比需要 Level 2 快照数据。此处通过日线特征进行粗略估算：
    # 如果是无量一字板（全天最低价等于最高价且涨停），封成比极高（赋予虚拟值 5.0 代表 500%）
    # 如果是普通涨停，赋予基础强度 1.0；未涨停为 0
    is_one_line_board = (enriched_valid_df['Low_Raw'] == enriched_valid_df['High_Raw']) & is_limit_up
    limit_seal_proxy = np.where(is_one_line_board, 5.0, np.where(is_limit_up, 1.0, 0.0))
    enriched_valid_df['Limit_Up_Seal_Ratio'] = limit_seal_proxy

    # 把洗好的矩阵重新合并回大表
    final_df = pd.merge(df, enriched_valid_df.drop(columns=[col for col in df.columns if col != 'Date']), on='Date', how='left')
    
    return final_df

def process_all_vaults():
    """读取所有基础 Vault 数据，生成融合 100个特征列的 Super_Parquet"""
    files = [f for f in os.listdir(VAULT_DIR) if f.endswith('.parquet')]
    print(f"检测到 {len(files)} 个基础股票数据文件，开始特征工程...")

    for f in files:
        base_path = os.path.join(VAULT_DIR, f)
        super_path = os.path.join(SUPER_VAULT_DIR, f)
        
        # 1. 读取含有历史空隙的基础表
        df = pd.read_parquet(base_path)
        
        # 2. 核心特征工程处理
        super_df = calculate_super_features(df)
        
        # 3. 存储为强化的表
        super_df.to_parquet(super_path, engine="pyarrow", index=False)
        print(f"  [OK] {f} 指标注入完成！当前列数：{len(super_df.columns)}")

if __name__ == "__main__":
    print("\n=== Super Parquet 指标因子工厂引擎启动 ===")
    process_all_vaults()
    print("全部股票的 C表级超级宽表 已经构建完毕！")
