import pandas as pd
import numpy as np
import os
import time
import requests
import json
from dotenv import load_dotenv

load_dotenv()

class BacktestEngine:
    def __init__(self, stock_code, days=30, start_date=None, end_date=None):
        self.stock_code = stock_code
        self.days = days
        self.start_date = start_date
        self.end_date = end_date
        self.df = None
        self.stock_name = stock_code # 默认
        self.cache_dir = "stock_data_cache"
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def get_stock_data(self):
        """
        获取股票数据，计算所有策略所需的技术指标
        """
        # 这里简化处理，直接复用之前的 baostock 逻辑
        # 在实际代码中，这里应该包含完整的数据获取和指标计算
        # 为了节省篇幅，假设数据已经包含：
        # date, open, high, low, close, volume
        # MA5, MA10, MA20, MA60
        # MACD, MACD_signal, MACD_hist
        # K, D, J
        # RSI
        # upper, middle, lower (Bollinger Bands)
        # ATR
        
        # 临时：尝试从缓存读取或重新下载（完整逻辑在之前的版本中，这里做适配）
        # 为确保策略能跑，我们假设数据已经准备好。
        # 如果是第一次运行，需确保包含所有指标计算逻辑。
        
        # ... (此处省略重复的 baostock 下载代码，重点在策略逻辑) ...
        # 如果需要完整的数据获取代码，请告诉我，我可以补全。
        # 这里我们假设外部已经调用了 data_fetcher 或者在此处实现。
        
        import baostock as bs
        
        # 尝试读取缓存
        cache_file = os.path.join(self.cache_dir, f"{self.stock_code}_{self.start_date}_{self.end_date}.csv")
        if os.path.exists(cache_file):
            self.df = pd.read_csv(cache_file)
            self.df['date'] = pd.to_datetime(self.df['date'])
            # 重新计算指标以防万一
            self._calculate_indicators()
            return self.df

        # 下载数据
        lg = bs.login()
        
        # 获取名称
        rs_name = bs.query_stock_basic(code=self.stock_code)
        if rs_name.error_code == '0':
            while (rs_name.next()):
                self.stock_name = rs_name.get_row_data()[1]

        # 获取K线
        rs = bs.query_history_k_data_plus(
            self.stock_code,
            "date,open,high,low,close,preclose,volume,amount,adjustflag,turn,pctChg",
            start_date=self.start_date, end_date=self.end_date,
            frequency="d", adjustflag="3"
        )
        
        data_list = []
        while (rs.next()):
            data_list.append(rs.get_row_data())
            
        bs.logout()
        
        if not data_list:
            return pd.DataFrame()
            
        self.df = pd.DataFrame(data_list, columns=rs.fields)
        self.df = self.df.apply(pd.to_numeric, errors='ignore')
        self.df['date'] = pd.to_datetime(self.df['date'])
        
        self._calculate_indicators()
        
        # 保存缓存
        self.df.to_csv(cache_file, index=False)
        return self.df

    def _calculate_indicators(self):
        """统一计算所有策略需要的技术指标"""
        df = self.df
        if df is None or df.empty: return

        # 1. 均线
        df['MA5'] = df['close'].rolling(window=5).mean()
        df['MA10'] = df['close'].rolling(window=10).mean()
        df['MA20'] = df['close'].rolling(window=20).mean()
        df['MA30'] = df['close'].rolling(window=30).mean()
        df['MA60'] = df['close'].rolling(window=60).mean()

        # 2. MACD
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp12 - exp26
        df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_hist'] = (df['MACD'] - df['MACD_signal']) * 2

        # 3. KDJ
        low_list = df['low'].rolling(window=9, min_periods=9).min()
        high_list = df['high'].rolling(window=9, min_periods=9).max()
        rsv = (df['close'] - low_list) / (high_list - low_list) * 100
        df['K'] = rsv.ewm(com=2).mean()
        df['D'] = df['K'].ewm(com=2).mean()
        df['J'] = 3 * df['K'] - 2 * df['D']

        # 4. RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # 5. Bollinger Bands
        df['middle'] = df['close'].rolling(window=20).mean()
        df['std'] = df['close'].rolling(window=20).std()
        df['upper'] = df['middle'] + 2 * df['std']
        df['lower'] = df['middle'] - 2 * df['std']
        
        # 6. ATR
        df['H-L'] = df['high'] - df['low']
        df['H-PC'] = abs(df['high'] - df['close'].shift(1))
        df['L-PC'] = abs(df['low'] - df['close'].shift(1))
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        df['ATR'] = df['TR'].rolling(window=14).mean()

    def run_backtest(self, strategy_type='Score_V1'):
        """运行回测主流程"""
        if self.df is None:
            self.get_stock_data()
            
        if self.df is None or self.df.empty:
            return {
                "total_return": 0,
                "trades": [],
                "win_rate": 0,
                "max_drawdown": 0
            }

        position = 0
        balance = 100000
        initial_balance = 100000
        trades = []
        logs = []
        
        df_test = self.df.copy()
        
        for i in range(1, len(df_test)):
            row = df_test.iloc[i]
            prev_row = df_test.iloc[i-1]
            date = row['date']
            price = row['close']
            
            # 获取策略决策
            action, reason, score = self.make_decision(row, prev_row, strategy_type)
            
            # 执行交易
            if action == "买入" and position == 0:
                position = balance / price
                balance = 0
                trades.append({
                    "date": date,
                    "action": "买入",
                    "price": price,
                    "reason": reason,
                    "score": score
                })
                logs.append([date, price, "AI建议买入", "全仓买入", position, position * price, date, strategy_type, self.stock_code])
                
            elif action == "卖出" and position > 0:
                balance = position * price
                position = 0
                trades.append({
                    "date": date,
                    "action": "卖出",
                    "price": price,
                    "reason": reason,
                    "score": score
                })
                logs.append([date, price, "AI建议卖出", "清仓卖出", 0, balance, date, strategy_type, self.stock_code])
            
            else:
                current_asset = balance + position * price
                logs.append([date, price, "持仓/观望", "无操作", position if position > 0 else 0, current_asset, date, strategy_type, self.stock_code])

        #虽然最后可能持仓，但按当前价格计算总资产
        final_asset = balance + position * df_test.iloc[-1]['close']
        total_return = (final_asset - initial_balance) / initial_balance * 100
        
        # 保存CSV日志
        log_df = pd.DataFrame(logs, columns=['日期', '收盘', 'AI建议', '操作', '持仓', '总资产', 'date', '策略', '股票'])
        log_df['股票名称'] = self.stock_name
        log_df.to_csv(f"backtest_{strategy_type}_{self.stock_code}.csv", index=False)
        
        return {
            "total_return": total_return,
            "trades": trades,
            "final_asset": final_asset
        }

    def make_decision(self, row, prev_row, strategy_type='Score_V1', api_key=None):
        return self._make_decision(row, prev_row, strategy_type, api_key)

    def _make_decision(self, row, prev_row, strategy_name='Score_V1', api_key=None):
        """
        统一决策入口
        """
        if strategy_name == 'Score_V1' or strategy_name == 'V1':
            return self._strategy_v1_composite_score(row, prev_row)
        elif strategy_name == 'Trend_V2' or strategy_name == 'V2':
            return self._strategy_v2_trend_hunter(row, prev_row)
        elif strategy_name == 'Oscillation_V3' or strategy_name == 'V3':
            return self._strategy_v3_band_defender(row, prev_row)
        elif strategy_name == 'AI_Agent_V4' or strategy_name == 'V4':
            return self._strategy_v4_ai_agent(row, prev_row, api_key)
        else:
            return "观望", "未知策略", 0

    # ==========================================
    # 策略 1: 综合记分 (Composite Score - V1)
    # ==========================================
    def _strategy_v1_composite_score(self, row, prev_row):
        score = 0
        reasons = []

        # 1. 趋势 Trend (20分)
        if row['MA5'] > row['MA10']:
            score += 20
            reasons.append("MA5>MA10趋势向上")

        # 2. 均线结构 MA Structure (20分)
        if row['MA5'] > row['MA10'] and row['MA10'] > row['MA20']:
            score += 20
            reasons.append("均线多头排列")
        elif row['MA5'] > row['MA20']: # 次级状态
            score += 10

        # 3. 动能 MACD (15分)
        if row['MACD'] > 0 and row['MACD'] > row['MACD_signal']:
            score += 15
            reasons.append("MACD金叉增强")

        # 4. 量能 Volume (25分) - 权重提升！
        # 逻辑：成交量大于5日均量 或 比昨日放量
        # 简化处理：如果比昨日放量20%以上
        vol_increase = False
        if prev_row is not None and prev_row['volume'] > 0:
            if row['volume'] > prev_row['volume'] * 1.05: # 稍微放量即可
                vol_increase = True
        
        if vol_increase and row['close'] > row['open']: # 放量阳线
            score += 25
            reasons.append("放量上涨资金流入")
        elif vol_increase:
            score += 15 # 放量但非阳线
        
        # 5. 超买超卖 KDJ (10分) - 权重降低
        if row['K'] > row['D'] and row['K'] < 80:
            score += 10
            reasons.append("KDJ金叉")

        # 6. 相对强弱 RSI (10分) - 权重降低
        if 50 < row['RSI'] < 80:
            score += 10
            reasons.append("RSI强势区")

        # 决策
        details = ";".join(reasons[:2])
        if score > 60:
            return "买入", f"综合记分{score}分: {details}", score
        elif score < 40:
            return "卖出", f"综合记分低至{score}分", score
        else:
            return "观望", f"综合记分{score}分，趋势未明", score

    # ==========================================
    # 策略 2: 趋势猎手 (Trend Hunter - V2)
    # ==========================================
    def _strategy_v2_trend_hunter(self, row, prev_row):
        price = row['close']
        ma5 = row['MA5']
        ma10 = row['MA10']
        score = 80 if price > ma10 else 20
        
        # 买入：站上 MA5 且 MA5 > MA10
        if price > ma5 and ma5 > ma10:
            return "买入", "股价站上MA5且均线多头", score
        # 卖出：跌破 MA10
        elif price < ma10:
            return "卖出", f"跌破MA10生命线({ma10:.2f})", score
        else:
            return "观望", "MA10之上持仓/观望", score

    # ==========================================
    # 策略 3: 波段防御者 (Band Defender - V3)
    # ==========================================
    def _strategy_v3_band_defender(self, row, prev_row):
        price = row['close']
        lower = row['lower']
        upper = row['upper']
        middle = row['middle']
        score = 50
        
        if price < lower: score = 90
        elif price > upper: score = 10
        
        # 买入：跌破下轨
        if price <= lower:
            return "买入", "触及布林下轨，超跌反弹", score
        # 卖出：突破上轨
        elif price >= upper:
            return "卖出", "触及布林上轨，超买止盈", score
        # 卖出：跌破中轨 (趋势坏了也得跑)
        elif price < middle and prev_row is not None and prev_row['close'] > prev_row['middle']:
            return "卖出", "有效跌破中轨，反弹结束", score
        else:
            return "观望", "通道内震荡", score

    # ==========================================
    # 策略 4: AI Agent (V4)
    # ==========================================
    def _strategy_v4_ai_agent(self, row, prev_row, api_key=None):
        """
        构建 Prompt 并尝试调用 LLM API
        """
        # ... (略去 Prompt 构建) ...
        # 1. Prompt 构建逻辑太长，我只替换头部和中间的关键调用逻辑
        prompt = f"""
你是一个资深的股票分析师，现在的行情数据是：
- 股票代码: {self.stock_code}
- 日期: {row['date']}
- 收盘价: {row['close']:.2f}
- 涨跌幅: {((row['close'] - prev_row['close'])/prev_row['close']*100) if prev_row is not None else 0:.2f}%
- MA5: {row['MA5']:.2f}
- MA10: {row['MA10']:.2f}
- MA20: {row['MA20']:.2f}
- 成交量: {row['volume']}
- KDJ: K={row['K']:.1f}, D={row['D']:.1f}
- RSI: {row['RSI']:.1f}

请根据这些数据，结合市场情绪与资金，板块热点判断未来走势，并给出操作建议（买入/卖出/观望）。
返回格式要求：必须包含“操作建议：买入”或“操作建议：卖出”或“操作建议：观望”这几个字。
"""
        
        # 2. 尝试调用 API
        action = "API未配置"
        reason = "未检测到 OPENAI_API_KEY，无法进行AI分析"
        score = 0
        
        try:
            # 优先使用传入的 api_key
            final_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
            
            if final_key:
                # 简易版：直接用 requests 调用 DeepSeek (兼容 OpenAI 格式)
                # 默认 Base URL
                base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {final_key}"
                }
                
                payload = {
                    "model": "deepseek-chat", # 默认尝试 deepseek-chat
                    "messages": [
                        {"role": "system", "content": "你是一个专业的股票交易员。请根据行情直接给出操作建议（买入/卖出/观望）并简述理由。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 100
                }
                
                # 发起请求 (设置超时防止卡死)
                try:
                    response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=8)
                    
                    if response.status_code == 200:
                        res_json = response.json()
                        content = res_json['choices'][0]['message']['content']
                        
                        # 解析结果
                        if "买入" in content:
                            action = "买入"
                            score = 80
                        elif "卖出" in content:
                            action = "卖出"
                            score = 20
                        else:
                            action = "观望"
                            score = 50
                            
                        # 截取理由
                        reason = content.replace('\n', ' ')[:50] + "..."
                    else:
                        action = "API错误"
                        reason = f"HTTP {response.status_code}: {response.text[:50]}"
                        
                except requests.exceptions.Timeout:
                    action = "超时"
                    reason = "AI响应超时(>8s)，建议重试"
                except Exception as req_err:
                    action = "请求失败"
                    reason = str(req_err)
                    
            else:
                pass # Unconfigured
                    
        except Exception as e:
            action = "API错误"
            reason = f"AI调用异常: {str(e)}"
            score = 0

        return action, reason, score

# 兼容旧代码的 Run 接口，作为单独脚本运行时
if __name__ == "__main__":
    import sys
    stock_code = "600519"
    if len(sys.argv) > 1:
        stock_code = sys.argv[1]
    
    engine = BacktestEngine(stock_code, start_date="2025-01-01", end_date="2025-12-31")
    engine.get_stock_data()
    
    # 默认跑 V1
    print(f"Testing {stock_code} with Score_V1...")
    result = engine.run_backtest('Score_V1')
    print(f"Return: {result['total_return']:.2f}%")
