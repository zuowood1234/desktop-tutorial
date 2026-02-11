import pandas as pd
import akshare as ak
import os
import argparse
from datetime import datetime, timedelta

# ==========================================
# 🍋 V3 引擎：布林带震荡策略 (Bollinger Mean Reversion)
# 核心逻辑：跌破下轨买入，回归中轨卖出
# ==========================================

class BacktestEngineV3:
    def __init__(self, stock_code, start_date=None, end_date=None, initial_capital=100000):
        self.stock_code = stock_code
        self.symbol = stock_code
        self.start_date_str = start_date
        self.end_date_str = end_date
        self.initial_capital = initial_capital
        
        # 缓存目录
        self.cache_dir = "stock_data_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
        
        self.df = None
        self.stock_name = "未知"

    def get_stock_data(self):
        """获取数据(Baostock)"""
        import baostock as bs
        
        cache_file = os.path.join(self.cache_dir, f"{self.stock_code}_{datetime.now().strftime('%Y%m%d')}.csv")
        
        if os.path.exists(cache_file):
            self.df = pd.read_csv(cache_file)
            self.df['date'] = pd.to_datetime(self.df['date'])
        else:
            print(f"🌐 下载数据(Baostock-V3): {self.stock_code}...")
            lg = bs.login()
            
            # Format Code
            bs_code = f"sh.{self.stock_code}" if self.stock_code.startswith('6') else f"sz.{self.stock_code}"
            if self.stock_code.startswith('688'): bs_code = f"sh.{self.stock_code}" 
            if self.stock_code.startswith('30'): bs_code = f"sz.{self.stock_code}"
            
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount,turn,pctChg",
                start_date="2020-01-01", 
                end_date=datetime.now().strftime('%Y-%m-%d'),
                frequency="d", 
                adjustflag="2"
            )
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                bs.logout()
                return False
                
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']:
                df[col] = pd.to_numeric(df[col])
            
            df.rename(columns={'turn': 'turnover', 'pctChg': '涨跌幅'}, inplace=True)
            self.stock_name = self.stock_code 
            df['stock_name'] = self.stock_name
            
            df.to_csv(cache_file, index=False)
            self.df = df
            bs.logout()
            
        if self.df is None or self.df.empty: return False

        # ==========================================
        # 📊 计算布林带指标 (Bollinger Bands)
        # ==========================================
        # 中轨 (Mid) = MA20
        self.df['Mid'] = self.df['close'].rolling(window=20).mean()
        # 标准差 (Std)
        self.df['Std'] = self.df['close'].rolling(window=20).std()
        # 上轨 (Upper) = Mid + 2*Std
        self.df['Upper'] = self.df['Mid'] + 2 * self.df['Std']
        # 下轨 (Lower) = Mid - 2*Std
        self.df['Lower'] = self.df['Mid'] - 2 * self.df['Std']
        
        return True

    def run_backtest(self):
        if self.df is None and not self.get_stock_data():
            return None

        # 过滤日期
        if self.start_date_str and self.end_date_str:
            start_dt = pd.to_datetime(self.start_date_str)
            end_dt = pd.to_datetime(self.end_date_str)
            mask = (self.df['date'] >= start_dt) & (self.df['date'] <= end_dt)
            test_data = self.df.loc[mask].copy()
        else:
            test_data = self.df.copy()

        if test_data.empty:
            return []

        # 初始化账户
        cash = self.initial_capital
        position = 0
        history = []
        
        # 遍历每一天
        for i, row in test_data.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')
            price = row['close']
            
            # 指标
            upper = row['Upper']
            mid = row['Mid']
            lower = row['Lower']
            
            # 跳过没有指标的前20天
            if pd.isna(upper):
                continue

            action = "观望"
            reason = ""
            
            # ==========================================
            # 🍋 V3 策略逻辑 (Python 规则)
            # ==========================================
            
            # 1. 买入信号：股价跌破下轨 (超卖)
            # 逻辑：跌出箱体下沿，概率回调
            if price < lower and position == 0:
                action = "买入"
                reason = f"股价({price:.2f})跌破布林下轨({lower:.2f})，超卖反弹预期。"
            
            # 2. 卖出信号：股价回归中轨 (均值回归)
            # 逻辑：或者是突破上轨 (超买)
            elif (price > mid or price > upper) and position > 0:
                action = "卖出"
                reason = f"股价({price:.2f})回归中轨({mid:.2f})或突破上轨，止盈离场。"
            
            # 3. 持有/观望
            else:
                if position > 0:
                    action = "持有"
                    reason = f"持仓中，等待回归中轨({mid:.2f})."
                else:
                    action = "观望"
                    reason = f"股价在通道内({lower:.2f}~{upper:.2f})震荡。"

            # 执行交易
            executed = "无"
            if action == "买入" and position == 0:
                position = int(cash / price / 100) * 100
                if position > 0:
                    cash -= position * price
                    executed = "全仓买入"
            elif action == "卖出" and position > 0:
                cash += position * price
                position = 0
                executed = "清仓卖出"
            
            # 结算
            current_asset = cash + (position * price)
            
            history.append({
                "股票代码": self.stock_code,
                "策略类型": "V3 (布林震荡)",
                "日期": date_str,
                "收盘": price,
                "上轨": upper,
                "中轨": mid,
                "下轨": lower,
                "AI建议": action,
                "操作": executed,
                "持仓": position,
                "总资产": current_asset
            })
            
        return history

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('stock_code', type=str)
    parser.add_argument('--start', type=str)
    parser.add_argument('--end', type=str)
    args = parser.parse_args()
    
    engine = BacktestEngineV3(args.stock_code, args.start, args.end)
    res = engine.run_backtest()
    
    if res:
        df = pd.DataFrame(res)
        df.to_csv(f"backtest_v3_{args.stock_code}.csv", index=False, encoding='utf-8-sig')
        print(f"✅ V3 Done: {args.stock_code}")
