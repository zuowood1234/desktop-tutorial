import pandas as pd
import akshare as ak
import os
import time
from datetime import datetime, timedelta
import openai
from dotenv import load_dotenv
import json
import argparse
import sys

# 加载环境变量
load_dotenv()

# 初始化 DeepSeek 客户端
client = openai.OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://openrouter.fans/v1",
)

CACHE_DIR = "stock_data_cache"
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

class BacktestEngine:
    def __init__(self, stock_code, days=30, start_date=None, end_date=None):
        self.symbol = stock_code
        self.days = days
        self.start_date_str = start_date
        self.end_date_str = end_date
        self.df = None
        self.stock_name = stock_code # default

    def get_stock_data(self):
        """获取并缓存日线数据"""
        today_str = datetime.now().strftime("%Y%m%d")
        cache_file = os.path.join(CACHE_DIR, f"{self.symbol}_{today_str}.csv")
        
        if os.path.exists(cache_file):
            print(f"📦 加载缓存: {cache_file}")
            self.df = pd.read_csv(cache_file)
            # 获取名字
            if 'stock_name' in self.df.columns:
                 self.stock_name = self.df.iloc[0]['stock_name']
        else:
            print(f"🌐 下载数据: {self.symbol}...")
            try:
                # 尝试获取名称
                try:
                    stock_info = ak.stock_individual_info_em(symbol=self.symbol)
                    self.stock_name = stock_info.iloc[5]['value'] # 通常是股票简称
                except:
                    self.stock_name = self.symbol

                # 获取日线
                start_date_fetch = "20200101" # 多拉一点保证有MA
                end_date_fetch = today_str
                
                df = ak.stock_zh_a_hist(symbol=self.symbol, period="daily", start_date=start_date_fetch, end_date=end_date_fetch, adjust="qfq")
                df.rename(columns={
                    "日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low", 
                    "成交量": "volume", "成交额": "amount", "换手率": "turnover"
                }, inplace=True)
                
                df['stock_name'] = self.stock_name
                df.to_csv(cache_file, index=False)
                self.df = df
            except Exception as e:
                print(f"❌ 数据下载失败: {e}")
                return False
        
        # 计算指标
        self.df['MA5'] = self.df['close'].rolling(5).mean()
        self.df['MA10'] = self.df['close'].rolling(10).mean()
        self.df['MA20'] = self.df['close'].rolling(20).mean()
        self.df['VR'] = self.df['volume'] / self.df['volume'].rolling(5).mean()  # 量比
        self.df['Bias'] = (self.df['close'] - self.df['MA10']) / self.df['MA10'] # 乖离率(相对MA10)
        
        # 处理日期索引
        self.df['date'] = pd.to_datetime(self.df['date'])
        
        return True

    def _get_market_context(self, date_str):
        """简化的市场环境模拟 (V2: 关注上证)"""
        # 在真实回测中，这里应该读取上证指数当日涨跌幅
        return "震荡"

    def _ask_ai_decision(self, row, market_status="震荡"):
        """调用 AI 进行决策 (V2: 稳健派 + MA10防守 + 缩量无视)"""
        
        prompt = f"""
        你是交易员。当前股票 {self.stock_name} ({self.symbol})，日期 {row['date'].strftime('%Y-%m-%d')}。
        
        【技术数据】
        - 收盘价: {row['close']:.2f}
        - MA5: {row['MA5']:.2f}
        - MA10: {row['MA10']:.2f} (V2 生命线)
        - MA20: {row['MA20']:.2f}
        - 成交量: {row['volume'] / 10000:.0f} 万手
        - 量比 (VR): {row['VR']:.2f} (VR<1.0 缩量, VR>1.5 放量)
        
        【策略规则 - V2 稳健派 (宽幅防守)】
        1. 买入: 站上 MA5 (初期仍看MA5突破)，且 MA5>MA20 趋势确立，量比 > 1.0 (需要量能)。
        2. 卖出 (止损): 
           - 有效跌破 MA10 (生命线)，必须离场。
           - 或 跌破 MA5 但且放量 (VR>1.5) ，视为出货。
        3. 持有 (死扛): 
           - 跌破 MA5 但缩量 (VR<0.8) -> 视为洗盘，死扛直到破 MA10。
           - 股价在 MA5 和 MA10 之间波动 -> 忽略噪音。
        
        请输出决策 (买入/卖出/持有/空仓) 和简短理由。
        格式：决策|理由
        """
        
        for attempt in range(3):
            try:
                response = client.chat.completions.create(
                    model="liquid/lfm-40b:free",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                    max_tokens=100
                )
                content = response.choices[0].message.content.strip()
                if "|" in content:
                    choice, reason = content.split("|", 1)
                    return choice.strip(), reason.strip()
                return "观望", content
            except Exception as e:
                print(f"⚠️ AI 连接失败 ({attempt+1}/3): {e}")
                time.sleep(2) # 等待2秒重试
        
        print("❌ 3次尝试均失败，终止回测。")
        sys.exit(1) # 直接退出程序

    def run_backtest(self):
        """执行回测"""
        if self.df is None and not self.get_stock_data():
            return None

        # 确定回测时间段
        if self.start_date_str and self.end_date_str:
            start_dt = pd.to_datetime(self.start_date_str)
            end_dt = pd.to_datetime(self.end_date_str)
            mask = (self.df['date'] >= start_dt) & (self.df['date'] <= end_dt)
            test_df = self.df.loc[mask].copy()
            if test_df.empty:
                print("❌ 指定时间段无数据")
                return None
        else:
            # 默认最近 N 天
            test_df = self.df.iloc[-self.days:].copy()

        test_data = test_df.reset_index(drop=True)
        history = []
        
        # 初始资金
        cash = 100000
        position = 0
        initial_asset = 100000
        
        print(f"🧠 开始逐日回测 ({len(test_data)} 天)...")
        
        for i, row in test_data.iterrows():
            date_str = row['date'].strftime('%Y-%m-%d')
            price = row['close']
            
            # AI 决策
            action, reason = self._ask_ai_decision(row)
            print(f"📅 {date_str} [{action}] Close:{price} | Reason:{reason[:20]}...")
            
            # 执行模拟
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
                "日期": date_str,
                "收盘": price,
                "AI建议": action,
                "操作": executed,
                "持仓": position,
                "总资产": current_asset
            })
            
        return history

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='AI Backtest Engine V2 (Sentiment Enhanced)')
    parser.add_argument('stock_code', type=str, help='Stock Code')
    parser.add_argument('--days', type=int, default=30, help='Days')
    parser.add_argument('--start', type=str, help='Start Date YYYY-MM-DD')
    parser.add_argument('--end', type=str, help='End Date YYYY-MM-DD')
    
    args = parser.parse_args()

    # 处理日期逻辑
    start_str = args.start
    end_str = args.end
    
    if not start_str and not end_str:
        # 如果没传，就用默认天数倒推
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=args.days)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")
    
    print(f"\n🚀 [V2] 回测范围: {start_str} 至 {end_str}")

    engine = BacktestEngine(
        args.stock_code, 
        start_date=start_str, 
        end_date=end_str
    )
    result = engine.run_backtest()
    
    if result:
        df = pd.DataFrame(result)
        initial = 100000
        final = df.iloc[-1]['总资产']
        roi = (final - initial) / initial * 100
        
        print("\n" + "="*40)
        print(f"💰 V2 回测结果 ({args.stock_code})")
        print(f"最终资产: {final:.2f}")
        print(f"收益率: {roi:.2f}%")
        print("="*40)
        
        filename = f"backtest_v2_{args.stock_code}.csv"
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"✅ 结果已保存: {filename}")
