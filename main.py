import os
import akshare as ak
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
import datetime

# 加载环境变量
load_dotenv()

# 获取 API Key
API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

from stock_names import get_stock_name_offline

def get_stock_name(symbol):
    """
    获取股票中文名称 (转发至更健壮的 offline/cloud 模块)
    """
    return get_stock_name_offline(symbol)

def get_market_index_change():
    """获取上证指数当前的涨跌幅，作为市场情绪参考"""
    try:
        df = ak.stock_zh_index_spot_em(symbol="上证指数")
        if not df.empty:
            change_pct = df.iloc[0]['涨跌幅']
            return float(change_pct)
    except:
        pass
    return 0.0

def get_market_status():
    """判定当前 A 股市场交易状态 (强制使用 UTC+8 时间)"""
    from datetime import datetime, timezone, timedelta
    
    # 强制转换为北京时间 (UTC+8)
    tz_cn = timezone(timedelta(hours=8))
    now = datetime.now(tz_cn)
    
    current_time = now.time()
    
    # 定义时间节点
    t_930 = datetime.strptime("09:30:00", "%H:%M:%S").time()
    t_1130 = datetime.strptime("11:30:00", "%H:%M:%S").time()
    t_1300 = datetime.strptime("13:00:00", "%H:%M:%S").time()
    t_1500 = datetime.strptime("15:00:00", "%H:%M:%S").time()
    
    if now.weekday() >= 5: # 周六周日
        return "🔴 休市中 (周末)", False
    
    if t_930 <= current_time <= t_1130:
        return "🟢 交易中 (上午盘)", True
    elif t_1130 < current_time < t_1300:
        return "💤 盘间休息 (午休)", False
    elif t_1300 <= current_time <= t_1500:
        return "🟢 交易中 (下午盘)", True
    elif current_time > t_1500:
        return "🔴 已收盘 (盘后数据)", False
    else:
        return "🕙 等待开盘", False

def get_stock_data(symbol):
    """获取 A 股历史行情数据"""
    import time
    full_symbol = "sh" + symbol if symbol.startswith('6') else "sz" + symbol
    max_retries = 3
    for attempt in range(max_retries):
        try:
            df = ak.stock_zh_a_daily(symbol=full_symbol, adjust="qfq")
            if df is None or df.empty:
                return None, f"获取到的数据为空，可能股票代码 {symbol} 不存在"
            df = df.rename(columns={'date': '日期', 'open': '开盘', 'high': '最高', 'low': '最低', 'close': '收盘', 'volume': '成交量'})
            df = df.sort_values('日期')
            df['涨跌幅'] = df['收盘'].pct_change() * 100
            df['涨跌幅'] = df['涨跌幅'].fillna(0).round(2)
            df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')
            return df.tail(90), None
        except:
            time.sleep(1)
    return None, "获取数据失败"

def analyze_with_deepseek(symbol, df, cost=None, strategy_type="technical"):
    """
    通过 DeepSeek 分析股票
    strategy_type: "technical" (纯技术派) 或 "sentiment" (情绪增强派)
    """
    df['MA5'] = df['收盘'].rolling(window=5).mean()
    df['MA10'] = df['收盘'].rolling(window=10).mean()
    df['MA20'] = df['收盘'].rolling(window=20).mean()
    
    recent_data = df.tail(3).to_dict('records')
    latest = recent_data[-1]
    
    profit_info = f"- 浮动盈亏: {(latest['收盘'] - cost) / cost * 100:.2f}%" if cost else ""
    
    market_context = ""
    role_desc = "你是一位经验丰富的 A 股短线交易专家，擅长技术分析和趋势跟踪。"
    if strategy_type == "sentiment":
        m_change = get_market_index_change()
        v5_avg = df['成交量'].tail(5).mean()
        vol_ratio = latest['成交量'] / v5_avg if v5_avg > 0 else 1.0
        market_context = f"\n- **大盘背景**: 上证指数目前涨跌幅 {m_change}%\n- **量比 (5日均量)**: {vol_ratio:.2f}"
        role_desc = "你是一位对 A 股情绪博弈有极深造诣的顶级操盘手，擅长综合技术面和大盘情绪、资金动向进行多维研判。"

    prompt = f"""
# Role
{role_desc}
# Task
请分析 {symbol} 的短线走势，给出操作建议。视角：【{ "纯技术" if strategy_type=="technical" else "情绪+技术增强"}】。

# Output Format (JSON ONLY)
```json
{{
    "action": "✅ 买入 / 📊 持有 / 💤 观望 / ❌ 卖出",
    "confidence": 85,
    "scores": {{ "technical": 80, "sentiment": 70, "risk": 60 }},
    "reason": "简短分析依据"
}}
```

# 数据
- 代码: {symbol}{market_context}
- 收盘: {latest['收盘']}, 涨跌: {latest['涨跌幅']}%
- MA5={latest['MA5']:.2f}, MA10={latest['MA10']:.2f}, MA20={latest['MA20']:.2f}
{profit_info}

**只输出JSON，不要任何额外文字！**
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的股票分析师，总是输出严格的JSON格式。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1
        )
        import json, re
        res_content = response.choices[0].message.content
        match = re.search(r'\{.*\}', res_content, re.DOTALL)
        return {
            **json.loads(match.group(0)),
            "usage": response.usage if hasattr(response, 'usage') else None
        } if match else {"error": "解析失败"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    print("AI 智能分析引擎启动...")
