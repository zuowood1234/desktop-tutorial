"""
双AI策略对比回测 - 深度年度版 (365天) - 增强稳定性
"""
import os
import time
import datetime
import logging
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
from stock_names import STOCK_NAMES

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest_compare_fast.log'),
        logging.StreamHandler()
    ]
)

API_KEY = os.getenv("DEEPSEEK_API_KEY")

# ============ 全局配置 ============
BACKTEST_DAYS = 365
BATCH_SIZE = 10
MARKET_DATA_CACHE = None

# 配置输出文件名
SUMMARY_FILE = "backtest_summary_advanced.csv"
DETAILS_FILE = "backtest_details_advanced.csv"

def get_cached_market_data():
    global MARKET_DATA_CACHE
    if MARKET_DATA_CACHE is not None: return MARKET_DATA_CACHE
    try:
        import akshare as ak
        print("📊 正在同步大盘基准数据...")
        df = ak.stock_zh_index_daily(symbol="sh000001")
        if df is not None and not df.empty:
            if 'date' in df.columns: df = df.rename(columns={'date': '日期', 'close': '收盘'})
            df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')
            df = df.sort_values('日期')
            df['涨跌幅'] = df['收盘'].pct_change() * 100
            MARKET_DATA_CACHE = df.fillna(0)
            return MARKET_DATA_CACHE
    except Exception as e:
        print(f"⚠️ 大盘同步失败: {e}")
    return pd.DataFrame()

def get_stock_name(symbol):
    return STOCK_NAMES.get(symbol, symbol)

def get_market_context(date_str, df_stock, df_market):
    try:
        market_change = 0.0
        if not df_market.empty:
            row = df_market[df_market['日期'] == date_str]
            if not row.empty: market_change = row.iloc[0]['涨跌幅']
        
        vol_ratio = 1.0
        df_stock['日期_str'] = df_stock['日期'].astype(str)
        target = df_stock[df_stock['日期_str'] == date_str]
        if not target.empty:
            idx = target.index[0]
            if idx >= 5:
                v5 = df_stock.iloc[idx-5:idx]['成交量'].mean()
                v0 = df_stock.iloc[idx]['成交量']
                vol_ratio = v0 / v5 if v5 > 0 else 1.0
        return {"market_change": market_change, "volume_ratio": vol_ratio}
    except: return {"market_change": 0.0, "volume_ratio": 1.0}

def get_ai_advice_pure_technical(client, symbol, dates, batch_text):
    prompt = f"股票:{symbol}\n{batch_text}\n要求:日期|操作(买入/卖出/持有/观望)|理由(简短)"
    try:
        res = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": "你是技术分析师。只输出格式:日期|操作|理由"}, {"role": "user", "content": prompt}],
            temperature=0.1
        )
        lines = res.choices[0].message.content.strip().split('\n')
        return [{"date": l.split('|')[0].strip(), "action": l.split('|')[1].strip(), "reason": l.split('|')[2].strip()} 
                for l in lines if '|' in l and len(l.split('|')) >= 3]
    except: return []

def get_ai_advice_with_sentiment(client, symbol, dates, batch_text, market_contexts):
    enhanced = ""
    for d in dates:
        ctx = market_contexts.get(d, {"market_change": 0, "volume_ratio": 1})
        for line in batch_text.split('\n'):
            if d in line: enhanced += f"{line}|大盘:{ctx['market_change']:.2f}%|量比:{ctx['volume_ratio']:.2f}\n"
    prompt = f"股票:{symbol}\n{enhanced}\n要求:日期|操作(买入/卖出/持有/观望)|理由(简短)"
    try:
        res = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": "你综合情绪和技术。只输出格式:日期|操作|理由"}, {"role": "user", "content": prompt}],
            temperature=0.1
        )
        lines = res.choices[0].message.content.strip().split('\n')
        return [{"date": l.split('|')[0].strip(), "action": l.split('|')[1].strip(), "reason": l.split('|')[2].strip()} 
                for l in lines if '|' in l and len(l.split('|')) >= 3]
    except: return []

def run_compare_backtest(symbol):
    name = get_stock_name(symbol)
    logging.info(f"🚀 [{symbol} {name}] 启动 365 天回测...")
    
    import akshare as ak
    df = None
    full_symbol = "sh" + symbol if symbol.startswith('6') else "sz" + symbol
    
    for attempt in range(3):
        try:
            df = ak.stock_zh_a_daily(symbol=full_symbol, adjust="qfq")
            if df is not None and not df.empty:
                df = df.rename(columns={'date': '日期', 'open': '开盘', 'high': '最高', 'low': '最低', 'close': '收盘', 'volume': '成交量'})
                df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')
                df = df.sort_values('日期')
                df['涨跌幅'] = df['收盘'].pct_change() * 100
                df = df.tail(BACKTEST_DAYS + 100).reset_index(drop=True)
                # 补全指标计算
                df['EMA12'] = df['收盘'].ewm(span=12, adjust=False).mean()
                df['EMA26'] = df['收盘'].ewm(span=26, adjust=False).mean()
                df['DIF'] = df['EMA12'] - df['EMA26']
                df['DEA'] = df['DIF'].ewm(span=9, adjust=False).mean()
                df['MACD'] = 2 * (df['DIF'] - df['DEA'])
                # RSI
                delta = df['收盘'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df['RSI'] = 100 - (100 / (1 + rs))
                # KDJ
                low_9 = df['最低'].rolling(window=9).min()
                high_9 = df['最高'].rolling(window=9).max()
                rsv = (df['收盘'] - low_9) / (high_9 - low_9) * 100
                df['K'] = rsv.ewm(com=2).mean()
                break
        except: time.sleep(2)

    if df is None or df.empty: return None
    
    try:
        idx_start = max(1, len(df) - BACKTEST_DAYS)
        df_market = get_cached_market_data()
        client = OpenAI(
            api_key=API_KEY, 
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        )
        
        advice_t, advice_s, contexts = {}, {}, {}
        batches = []
        for i in range(idx_start, len(df)):
            date = df.iloc[i]['日期']
            row = df.iloc[i]
            contexts[date] = get_market_context(date, df, df_market)
            # 补齐技术特征文本
            batches.append(f"{date}|收:{row['收盘']:.2f}|跌:{row['涨跌幅']:.2f}%|MACD:{row['MACD']:.2f}|RSI:{row['RSI']:.1f}|K:{row['K']:.1f}")
        
        for i in range(0, len(batches), BATCH_SIZE):
            sub = batches[i:i+BATCH_SIZE]
            text = "\n".join(sub)
            dates = [l.split('|')[0] for l in sub]
            for item in get_ai_advice_pure_technical(client, symbol, dates, text): advice_t[item['date']] = (item['action'], item['reason'])
            for item in get_ai_advice_with_sentiment(client, symbol, dates, text, contexts): advice_s[item['date']] = (item['action'], item['reason'])
            time.sleep(0.1)

        cash_t, pos_t, cash_s, pos_s = 1000000.0, 0, 1000000.0, 0
        history = []
        for i in range(idx_start, len(df)):
            date, price = df.iloc[i]['日期'], df.iloc[i]['收盘']
            act_t, _ = advice_t.get(date, ("观望", ""))
            if act_t == "买入" and pos_t == 0: pos_t = int(cash_t // price / 100) * 100; cash_t -= pos_t * price
            elif act_t == "卖出" and pos_t > 0: cash_t += pos_t * price; pos_t = 0
            
            act_s, _ = advice_s.get(date, ("观望", ""))
            if act_s == "买入" and pos_s == 0: pos_s = int(cash_s // price / 100) * 100; cash_s -= pos_s * price
            elif act_s == "卖出" and pos_s > 0: cash_s += pos_s * price; pos_s = 0
            
            history.append({
                "代码": symbol,
                "名称": name,
                "日期": date, 
                "技术派操作": act_t,
                "情绪派操作": act_s,
                "资产(T)": round(cash_t+pos_t*price, 2), 
                "资产(S)": round(cash_s+pos_s*price, 2)
            })
            
        # 保存详细过程到 CSV (增量追加)
        df_details = pd.DataFrame(history)
        df_details.to_csv(DETAILS_FILE, mode='a', header=not os.path.exists(DETAILS_FILE), index=False, encoding='utf-8-sig')

        roi_t = (history[-1]['资产(T)'] - 1000000) / 10000
        roi_s = (history[-1]['资产(S)'] - 1000000) / 10000
        roi_b = (df.iloc[-1]['收盘'] - df.iloc[idx_start]['收盘']) / df.iloc[idx_start]['收盘'] * 100
        
        # 增加数值字段用于排序
        return {
            "代码": symbol, "名称": name, 
            "纯技术派(1年)": f"{roi_t:.1f}%", "纯技术派(1年)_val": roi_t,
            "情绪增强派(1年)": f"{roi_s:.1f}%", "情绪增强派(1年)_val": roi_s, 
            "基准(1年)": f"{roi_b:.1f}%", "基准(1年)_val": roi_b
        }
    except Exception as e:
        logging.error(f"失败 {symbol}: {e}")
        return None

if __name__ == "__main__":
    inp = "002910, 601698, 600703, 300620, 600745, 002920, 002304, 601288, 601126, 600879, 002905, 603598, 601881, 603983, 605136, 600362, 688141, 002284, 300115, 600276, 002717, 002973, 001337, 601212, 002456, 601138, 002050, 688207, 688041, 688676"
    stocks = [s.strip() for s in inp.split(",") if s.strip()]
    get_cached_market_data()
    
    if os.path.exists(SUMMARY_FILE): os.remove(SUMMARY_FILE)
    if os.path.exists(DETAILS_FILE): os.remove(DETAILS_FILE)
    
    print(f"🔥 开始对 {len(stocks)} 只股票进行 1 年期【进阶版】长跑测试...")
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(run_compare_backtest, s): s for s in stocks}
        for f in as_completed(futures):
            res = f.result()
            if res:
                df_temp = pd.DataFrame([res])
                # 增量保存，哪怕中途挂了，数据也在
                df_temp.to_csv(SUMMARY_FILE, mode='a', header=not os.path.exists(SUMMARY_FILE), index=False, encoding='utf-8-sig')
                print(f"✅ {res['名称']} 完成! 收益: {res['纯技术派(1年)']} VS {res['情绪增强派(1年)']}")
