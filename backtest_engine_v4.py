import pandas as pd
import os
import time
from datetime import datetime, timedelta
import argparse
import sys

# ==========================================
# 🚀 V4 引擎：增强趋势策略
# 集成：MA60 长期过滤 + ATR 动态止损
# ==========================================

CACHE_DIR = "stock_data_cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

class BacktestEngineV4:
    def __init__(self, stock_code, days=30, start_date=None, end_date=None):
        self.symbol = stock_code
        self.days = days
        self.start_date_str = start_date
        self.end_date_str = end_date
        self.df = None
        self.stock_name = stock_code # default

    def get_stock_data(self):
        """获取并缓存日线数据 (Baostock)"""
        import baostock as bs
        
        today_str = datetime.now().strftime("%Y%m%d")
        cache_file = os.path.join(CACHE_DIR, f"{self.symbol}_{today_str}.csv")
        
        if os.path.exists(cache_file):
            self.df = pd.read_csv(cache_file)
            if 'stock_name' in self.df.columns:
                 self.stock_name = str(self.df.iloc[0]['stock_name'])
        else:
            # print(f"🌐 下载数据(Baostock-V4): {self.symbol}...")
            # 1. Login
            lg = bs.login()
            if lg.error_code != '0':
                print(f"❌ Baostock login failed: {lg.error_msg}")
                return False

            # 2. Format Code
            bs_code = f"sh.{self.symbol}" if self.symbol.startswith('6') else f"sz.{self.symbol}"
            if self.symbol.startswith('688'): bs_code = f"sh.{self.symbol}" 
            if self.symbol.startswith('30'): bs_code = f"sz.{self.symbol}"
            
            # 3. Get Stock Name
            try:
                rs_basic = bs.query_stock_basic(code=bs_code)
                if rs_basic.error_code == '0':
                    basic_data = []
                    while rs_basic.next():
                        basic_data.append(rs_basic.get_row_data())
                    if basic_data:
                        self.stock_name = basic_data[0][2]  # code_name is 3rd field
            except:
                pass
            
            # 4. Query K-Line Data
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount,turn,pctChg",
                start_date="2020-01-01", 
                end_date=datetime.now().strftime('%Y-%m-%d'),
                frequency="d", 
                adjustflag="2" # qfq
            )
            
            data_list = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            
            if not data_list:
                print(f"⚠️ {self.symbol}: Baostock 返回空数据")
                bs.logout()
                return False
                
            df = pd.DataFrame(data_list, columns=rs.fields)
            
            # 5. Convert Types
            for col in ['open', 'high', 'low', 'close', 'volume', 'amount', 'turn', 'pctChg']:
                df[col] = pd.to_numeric(df[col])
            
            # 6. Rename Columns
            df.rename(columns={'turn': 'turnover', 'pctChg': '涨跌幅'}, inplace=True)
            df['stock_name'] = self.stock_name
            
            df.to_csv(cache_file, index=False)
            self.df = df
            bs.logout()

        if self.df is None or self.df.empty: return False

        # 计算技术指标
        self.df['MA5'] = self.df['close'].rolling(5).mean()
        self.df['MA10'] = self.df['close'].rolling(10).mean()
        self.df['MA20'] = self.df['close'].rolling(20).mean()
        self.df['MA60'] = self.df['close'].rolling(60).mean()  # 新增：季线
        
        # 计算 ATR (Average True Range)
        self.df['H-L'] = self.df['high'] - self.df['low']
        self.df['H-PC'] = abs(self.df['high'] - self.df['close'].shift(1))
        self.df['L-PC'] = abs(self.df['low'] - self.df['close'].shift(1))
        self.df['TR'] = self.df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        self.df['ATR'] = self.df['TR'].rolling(window=14).mean()
        
        # 清理中间列
        self.df.drop(['H-L', 'H-PC', 'L-PC', 'TR'], axis=1, inplace=True)
        
        # 处理日期索引
        self.df['date'] = pd.to_datetime(self.df['date'])
        
        return True

    def _make_decision(self, row, position_info):
        """
        V4 策略核心逻辑
        position_info: {'has_position': bool, 'entry_price': float, 'entry_atr': float}
        """
        price = row['close']
        ma5 = row['MA5']
        ma10 = row['MA10']
        ma60 = row['MA60']
        atr = row['ATR']
        
        # 跳过指标未就绪的前期数据
        if pd.isna(ma60) or pd.isna(atr):
            return "观望", "指标计算中"
        
        # ==========================================
        # 卖出/止损逻辑 (持仓时优先判断)
        # ==========================================
        if position_info['has_position']:
            entry_price = position_info['entry_price']
            entry_atr = position_info['entry_atr']
            
            # 动态止损：跌破 (买入价 - 2×ATR)
            stop_loss_price = entry_price - (2 * entry_atr)
            
            # 条件1：触发 ATR 止损
            if price < stop_loss_price:
                return "卖出", f"触发ATR止损({stop_loss_price:.2f})"
            
            # 条件2：跌破 MA10 生命线
            if price < ma10:
                return "卖出", f"跌破MA10生命线({ma10:.2f})"
            
            # 否则持有
            return "持有", f"持仓中，止损位{stop_loss_price:.2f}"
        
        # ==========================================
        # 买入逻辑 (空仓时)
        # ==========================================
        else:
            # 方案A：MA60 长期趋势过滤
            if price < ma60:
                return "观望", f"股价({price:.2f})低于季线MA60({ma60:.2f})，趋势不明"
            
            # 核心买入条件
            if price > ma5 and ma5 > ma10:
                return "买入", f"股价站上MA5且趋势向上，季线支撑良好"
            
            return "观望", f"等待MA5金叉MA10信号"

    def run_backtest(self):
        if self.df is None and not self.get_stock_data():
            return None

        # 确定回测时间段
        if self.start_date_str and self.end_date_str:
            start_dt = pd.to_datetime(self.start_date_str)
            end_dt = pd.to_datetime(self.end_date_str)
            mask = (self.df['date'] >= start_dt) & (self.df['date'] <= end_dt)
            test_data = self.df.loc[mask].copy()
        else:
            end_dt = pd.to_datetime(datetime.now())
            start_dt = end_dt - timedelta(days=self.days)
            mask = (self.df['date'] >= start_dt) & (self.df['date'] <= end_dt)
            test_data = self.df.loc[mask].copy()

        if test_data.empty:
            return []

        # 初始化账户
        cash = 100000
        position = 0
        history = []
        
        # 持仓信息
        position_info = {
            'has_position': False,
            'entry_price': 0,
            'entry_atr': 0
        }
        
        # print(f"🧠 开始逐日回测 ({len(test_data)} 天)...")
        
        for i, row in test_data.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')
            price = row['close']
            
            # 决策
            action, reason = self._make_decision(row, position_info)
            # print(f"📅 {date_str} [{action}] Close:{price} | {reason[:30]}...")
            
            # 执行模拟
            executed = "无"
            if action == "买入" and position == 0:
                position = int(cash / price / 100) * 100
                if position > 0:
                    cash -= position * price
                    executed = "全仓买入"
                    # 记录买入信息
                    position_info['has_position'] = True
                    position_info['entry_price'] = price
                    position_info['entry_atr'] = row['ATR']
                    
            elif action == "卖出" and position > 0:
                cash += position * price
                position = 0
                executed = "清仓卖出"
                # 清除持仓信息
                position_info['has_position'] = False
                position_info['entry_price'] = 0
                position_info['entry_atr'] = 0
            
            # 结算
            current_asset = cash + (position * price)
            
            history.append({
                "股票代码": self.symbol,
                "股票名称": self.stock_name,
                "策略类型": "V4 (增强趋势)",
                "日期": date_str,
                "收盘": price,
                "AI建议": action,
                "操作": executed,
                "持仓": position,
                "总资产": current_asset
            })
            
        return history

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AI Backtest Engine V4 (Enhanced Trend)')
    parser.add_argument('stock_code', type=str, help='Stock Code')
    parser.add_argument('--days', type=int, default=30, help='Days')
    parser.add_argument('--start', type=str, help='Start Date YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='End Date YYYY-MM-DD')
    
    args = parser.parse_args()

    # 处理日期逻辑
    start_str = args.start
    end_str = args.end
    
    if not start_str and not end_str:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=args.days)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")
    
    # print(f"\n🚀 [V4] 回测范围: {start_str} 至 {end_str}")

    engine = BacktestEngineV4(
        args.stock_code, 
        start_date=start_str, 
        end_date=end_str
    )
    result = engine.run_backtest()
    
    if result:
        df = pd.DataFrame(result)
        filename = f"backtest_v4_{args.stock_code}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        # print(f"✅ V4 结果已保存: {filename}")
