
import pandas as pd
import numpy as np
import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

class BacktestEngine:
    """
    策略决策引擎 (Strategy Engine)
    负责计算技术指标并根据 V1-V4 策略生成交易信号。
    """
    def __init__(self, stock_code, days=30, start_date=None, end_date=None):
        self.stock_code = stock_code
        self.df = None
        self.stock_name = stock_code 

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

        # 4. 量能 Volume (25分)
        vol_increase = False
        if prev_row is not None and prev_row['volume'] > 0:
            if row['volume'] > prev_row['volume'] * 1.05:
                vol_increase = True
        
        if vol_increase and row['close'] > row['open']: 
            score += 25
            reasons.append("放量上涨资金流入")
        elif vol_increase:
            score += 15 
        
        # 5. 超买超卖 KDJ (10分)
        if row['K'] > row['D'] and row['K'] < 80:
            score += 10
            reasons.append("KDJ金叉")

        # 6. 相对强弱 RSI (10分)
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
        # 卖出：跌破中轨
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
        # 1. Prompt 构建
        prompt = f"""
你是一个资深的股票分析师，现在的行情数据是：
- 股票代码: {self.stock_code}
- 日期: {row['date']}
- 开盘价: {row['open']:.2f}
- 最高价: {row['high']:.2f}
- 最低价: {row['low']:.2f}
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
                    "max_tokens": 1000
                }
                
                # 发起请求 (设置超时防止卡死)
                try:
                    # 超时已调整为 45 秒
                    response = requests.post(f"{base_url}/chat/completions", headers=headers, json=payload, timeout=45)
                    
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
                            
                        reason = content
                    else:
                        action = "API错误"
                        reason = f"HTTP {response.status_code}: {response.text[:50]}"
                        
                except requests.exceptions.Timeout:
                    action = "超时"
                    reason = "AI响应超时(>45s)，建议重试"
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

