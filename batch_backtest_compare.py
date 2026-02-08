"""
双AI策略对比回测
对比"纯技术面"vs"情绪增强"两种AI策略的收益率
都使用尾盘买入执行
"""

import os
import time
import datetime
import re
import logging
import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('backtest_compare.log'),
        logging.StreamHandler()
    ]
)

API_KEY = os.getenv("DEEPSEEK_API_KEY")

def get_stock_name(symbol):
    """获取股票中文名称"""
    try:
        import akshare as ak
        df = ak.stock_individual_info_em(symbol=symbol)
        name_row = df[df['item'] == '股票简称']
        if not name_row.empty:
            return name_row.iloc[0]['value']
        return symbol 
    except:
        return symbol

def get_market_context(date_str, df_stock):
    """
    获取市场情绪数据
    """
    try:
        import akshare as ak
        
        # 1. 大盘数据
        market_change = 0.0
        try:
            df_market = ak.stock_zh_index_daily(symbol="sh000001")
            df_market['日期'] = pd.to_datetime(df_market['日期']).dt.strftime('%Y-%m-%d')
            market_row = df_market[df_market['日期'] == date_str]
            if not market_row.empty:
                market_change = market_row.iloc[0]['涨跌幅']
        except:
            pass
        
        # 2. 成交量对比
        volume_ratio = 1.0
        try:
            df_stock['日期_str'] = df_stock['日期'].astype(str)
            target_row = df_stock[df_stock['日期_str'] == date_str]
            if not target_row.empty:
                idx = target_row.index[0]
                if idx >= 5:
                    recent_5_vol = df_stock.iloc[idx-5:idx]['成交量'].mean()
                    today_vol = df_stock.iloc[idx]['成交量']
                    volume_ratio = today_vol / recent_5_vol if recent_5_vol > 0 else 1.0
        except:
            pass
        
        return {"market_change": market_change, "volume_ratio": volume_ratio}
    except:
        return {"market_change": 0.0, "volume_ratio": 1.0}

def get_ai_advice_pure_technical(client, symbol, dates, batch_text):
    """策略C：纯技术面"""
    prompt = f"""
你是 A 股短线交易员。根据技术数据预测操作：

股票: {symbol}
{batch_text}

要求：对每天给出【买入】/【卖出】/【持有】/【观望】，格式：日期|操作|理由

示例：
2024-11-01|买入|超跌反弹
"""
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是技术分析师。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        
        result = []
        for line in response.choices[0].message.content.strip().split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 3:
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', parts[0])
                    if date_match:
                        result.append({
                            "date": date_match.group(1),
                            "action": parts[1].strip(),
                            "reason": parts[2].strip()
                        })
        return result
    except Exception as e:
        logging.error(f"纯技术AI失败: {e}")
        return []

def get_ai_advice_with_sentiment(client, symbol, dates, batch_text, market_contexts):
    """策略D：情绪增强"""
    enhanced_text = ""
    for date in dates:
        ctx = market_contexts.get(date, {"market_change": 0, "volume_ratio": 1})
        for line in batch_text.split('\n'):
            if date in line:
                enhanced_text += f"{line} | 大盘:{ctx['market_change']:.2f}% | 量比:{ctx['volume_ratio']:.2f}\n"
                break
    
    prompt = f"""
你是 A 股短线交易员。综合技术面和市场情绪预测操作：

股票: {symbol}
{enhanced_text}

要求：综合考虑技术、大盘、量能，对每天给出【买入】/【卖出】/【持有】/【观望】，格式：日期|操作|理由

示例：
2024-11-01|买入|大盘企稳+量能放大
"""
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你综合市场情绪和技术面。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        
        result = []
        for line in response.choices[0].message.content.strip().split('\n'):
            if '|' in line:
                parts = line.split('|')
                if len(parts) >= 3:
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', parts[0])
                    if date_match:
                        result.append({
                            "date": date_match.group(1),
                            "action": parts[1].strip(),
                            "reason": parts[2].strip()
                        })
        return result
    except Exception as e:
        logging.error(f"情绪增强AI失败: {e}")
        return []

def run_compare_backtest(symbol, days=90):
    """
    核心对比回测逻辑
    """
    stock_name = get_stock_name(symbol)
    logging.info(f"🚀 [{symbol} {stock_name}] 开始双AI对比回测...")
    
    # 1. 获取数据
    end_date = datetime.datetime.now().strftime("%Y%m%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days + 30)).strftime("%Y%m%d")
    
    try:
        import akshare as ak
        df_all = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
    except Exception as e:
        logging.error(f"数据获取失败: {e}")
        return None

    if df_all is None or df_all.empty:
        return None

    df_all['日期'] = df_all['日期'].astype(str)
    total_len = len(df_all)
    start_index = max(0, total_len - days)

    # 2. 准备市场情绪数据
    market_contexts = {}
    for i in range(start_index, total_len):
        date_str = df_all.iloc[i]['日期']
        market_contexts[date_str] = get_market_context(date_str, df_all)
    
    # 3. 准备批次数据
    BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    BATCH_SIZE = 5
    batch_tasks = []
    current_batch_dates = []
    current_batch_text = ""
    
    for i in range(start_index, total_len - 1):
        today_row = df_all.iloc[i]
        date_str = str(today_row['日期'])
        line = f"{date_str} | 收:{today_row['收盘']:.2f} | 涨:{today_row['涨跌幅']:.2f}%"
        
        current_batch_dates.append(date_str)
        current_batch_text += line + "\n"
        
        if len(current_batch_dates) == BATCH_SIZE or i == total_len - 2:
            batch_tasks.append((list(current_batch_dates), str(current_batch_text)))
            current_batch_dates = []
            current_batch_text = ""

    # 4. 调用双AI获取建议
    advice_pure = {}  # 纯技术
    advice_sentiment = {}  # 情绪增强
    
    print(f"🧠 正在获取双AI建议（共{len(batch_tasks)}批）...")
    for dates, text in batch_tasks:
        # 纯技术
        result_pure = get_ai_advice_pure_technical(client, symbol, dates, text)
        for item in result_pure:
            d = str(item.get("date")).strip()
            if d:
                advice_pure[d] = (item.get("action", "观望"), item.get("reason", ""))
        
        # 情绪增强
        result_sent = get_ai_advice_with_sentiment(client, symbol, dates, text, market_contexts)
        for item in result_sent:
            d = str(item.get("date")).strip()
            if d:
                advice_sentiment[d] = (item.get("action", "观望"), item.get("reason", ""))
        
        time.sleep(0.5)  # 避免请求过快
    
    print(f"✅ 纯技术AI建议：{len(advice_pure)}条 | 情绪增强AI建议：{len(advice_sentiment)}条")

    # 5. 双策略回测（都用尾盘买入）
    initial_cash = 1000000.0
    
    # 策略C - 纯技术
    cash_c = initial_cash
    pos_c = 0
    prev_asset_c = initial_cash
    
    # 策略D - 情绪增强
    cash_d = initial_cash
    pos_d = 0
    prev_asset_d = initial_cash
    
    history = []

    for i in range(start_index, total_len - 1):
        today_row = df_all.iloc[i]
        date = str(today_row['日期']).strip()
        price = today_row['收盘']
        
        # 策略C执行
        action_c, reason_c = advice_pure.get(date, ("观望", ""))
        executed_c = "无"
        
        if action_c == "买入" and pos_c == 0 and cash_c > price * 100:
            pos_c = int(cash_c // price / 100) * 100
            cash_c -= pos_c * price
            executed_c = "买入"
        elif action_c in ["卖出", "空仓"] and pos_c > 0:
            cash_c += pos_c * price
            pos_c = 0
            executed_c = "卖出"
        
        asset_c = cash_c + (pos_c * price)
        pnl_c = asset_c - prev_asset_c
        prev_asset_c = asset_c
        
        # 策略D执行
        action_d, reason_d = advice_sentiment.get(date, ("观望", ""))
        executed_d = "无"
        
        if action_d == "买入" and pos_d == 0 and cash_d > price * 100:
            pos_d = int(cash_d // price / 100) * 100
            cash_d -= pos_d * price
            executed_d = "买入"
        elif action_d in ["卖出", "空仓"] and pos_d > 0:
            cash_d += pos_d * price
            pos_d = 0
            executed_d = "卖出"
        
        asset_d = cash_d + (pos_d * price)
        pnl_d = asset_d - prev_asset_d
        prev_asset_d = asset_d
        
        # 记录
        ctx = market_contexts.get(date, {"market_change": 0, "volume_ratio": 1})
        history.append({
            "日期": date,
            "收盘": price,
            "大盘涨跌": f"{ctx['market_change']:.2f}%",
            "量比": f"{ctx['volume_ratio']:.2f}",
            
            "AI建议(纯技术)": action_c,
            "理由(纯技术)": reason_c,
            "操作(纯技术)": executed_c,
            "持仓(纯技术)": pos_c,
            "当日盈亏(纯技术)": round(pnl_c, 2),
            "总资产(纯技术)": round(asset_c, 2),
            
            "AI建议(情绪增强)": action_d,
            "理由(情绪增强)": reason_d,
            "操作(情绪增强)": executed_d,
            "持仓(情绪增强)": pos_d,
            "当日盈亏(情绪增强)": round(pnl_d, 2),
            "总资产(情绪增强)": round(asset_d, 2),
            
            "策略优势(情绪-纯技术)": round(asset_d - asset_c, 2)
        })
    
    # 6. 计算指标
    final_c = history[-1]['总资产(纯技术)']
    roi_c = (final_c - initial_cash) / initial_cash * 100
    
    final_d = history[-1]['总资产(情绪增强)']
    roi_d = (final_d - initial_cash) / initial_cash * 100
    
    # 基准
    first_price = df_all.iloc[start_index]['收盘']
    last_price = df_all.iloc[-1]['收盘']
    benchmark_roi = (last_price - first_price) / first_price * 100
    
    return {
        "symbol": symbol,
        "stock_name": stock_name,
        "roi_pure": roi_c,
        "roi_sentiment": roi_d,
        "benchmark_roi": benchmark_roi,
        "advantage": roi_d - roi_c,
        "details": history
    }

if __name__ == "__main__":
    stocks_input = input("请输入股票代码(逗号分隔): ")
    stocks = [s.strip() for s in stocks_input.split(",") if s.strip()]
    if not stocks:
        stocks = ["600519"]
    
    # 多周期对比：30/60/90天
    periods = [30, 60, 90]
    all_results = {}  # {stock: {30: result, 60: result, 90: result}}
    
    for stock in stocks:
        print(f"\n{'='*60}")
        print(f"开始回测：{stock}")
        print(f"{'='*60}")
        
        all_results[stock] = {}
        
        for period in periods:
            print(f"\n⏰ 回测周期：{period}天")
            res = run_compare_backtest(stock, days=period)
            if res:
                all_results[stock][period] = res
                print(f"✅ {period}天完成 | 纯技术:{res['roi_pure']:.2f}% | 情绪增强:{res['roi_sentiment']:.2f}% | 基准:{res['benchmark_roi']:.2f}%")
            else:
                print(f"❌ {period}天失败")
    
    # 生成汇总表（横向对比）
    if all_results:
        summary_rows = []
        for stock, period_results in all_results.items():
            if not period_results:
                continue
            
            # 获取股票名称（从任一周期结果中）
            stock_name = next(iter(period_results.values()))['stock_name']
            
            row = {
                "代码": stock,
                "名称": stock_name,
            }
            
            # 添加各周期数据
            for period in periods:
                if period in period_results:
                    r = period_results[period]
                    row[f"纯技术({period}天)"] = f"{r['roi_pure']:.2f}%"
                    row[f"情绪增强({period}天)"] = f"{r['roi_sentiment']:.2f}%"
                    row[f"基准({period}天)"] = f"{r['benchmark_roi']:.2f}%"
                    row[f"情绪优势({period}天)"] = f"{r['advantage']:.2f}%"
                else:
                    row[f"纯技术({period}天)"] = "N/A"
                    row[f"情绪增强({period}天)"] = "N/A"
                    row[f"基准({period}天)"] = "N/A"
                    row[f"情绪优势({period}天)"] = "N/A"
            
            summary_rows.append(row)
        
        summary_df = pd.DataFrame(summary_rows)
        print("\n" + "="*80)
        print("🏆 多周期双AI对比成绩单")
        print("="*80)
        print(summary_df.to_string(index=False))
        summary_df.to_csv("backtest_compare_summary.csv", index=False, encoding='utf-8-sig')
        print("\n✅ backtest_compare_summary.csv 已保存")
        
        # 详细日志（只保存90天的，因为包含了最多信息）
        all_details = []
        for stock, period_results in all_results.items():
            if 90 in period_results:
                r = period_results[90]
                d_df = pd.DataFrame(r['details'])
                d_df.insert(0, '代码', r['symbol'])
                d_df.insert(1, '名称', r['stock_name'])
                all_details.append(d_df)
        
        if all_details:
            master_df = pd.concat(all_details, ignore_index=True)
            master_df.to_csv("backtest_compare_details.csv", index=False, encoding='utf-8-sig')
            print(f"✅ backtest_compare_details.csv 已保存 (90天详情，共 {len(master_df)} 条)")
    else:
        print("❌ 没有结果")

