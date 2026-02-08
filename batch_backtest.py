from main import get_stock_data, API_KEY
from openai import OpenAI
import pandas as pd
import datetime
import os
import time
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import sys 

# 配置日志
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("batch_backtest.log", mode='w'),
        logging.StreamHandler(sys.stdout)
    ]
)

API_KEY = os.getenv("DEEPSEEK_API_KEY")

# ============ 市场情绪数据获取 ============
def get_market_context(symbol, date_str, df_stock):
    """
    获取市场情绪数据：大盘走势、板块表现、成交量对比
    :param symbol: 股票代码
    :param date_str: 日期字符串 YYYY-MM-DD
    :param df_stock: 该股票的历史数据DataFrame
    :return: dict with market_change, sector_change, volume_ratio
    """
    try:
        import akshare as ak
        
        # 1. 获取大盘数据（上证指数 000001）
        market_change = 0.0
        try:
            # 获取大盘最近几天的数据
            end_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y%m%d")
            start_date = (datetime.datetime.strptime(date_str, "%Y-%m-%d") - datetime.timedelta(days=5)).strftime("%Y%m%d")
            df_market = ak.stock_zh_index_daily(symbol="sh000001")  # 上证指数
            df_market['日期'] = pd.to_datetime(df_market['日期']).dt.strftime('%Y-%m-%d')
            market_row = df_market[df_market['日期'] == date_str]
            if not market_row.empty:
                market_change = market_row.iloc[0]['涨跌幅']
        except:
            market_change = 0.0  # 如果获取失败，默认0
        
        # 2. 板块表现（简化版：暂时用大盘代替，后续可以优化）
        # 真实场景需要先查询股票所属板块，再查板块涨跌
        # 这里为了速度，先用大盘作为板块的代理
        sector_change = market_change  
        
        # 3. 成交量对比
        volume_ratio = 1.0
        try:
            # 找到这一天在df_stock中的位置
            df_stock['日期_str'] = df_stock['日期'].astype(str)
            target_row = df_stock[df_stock['日期_str'] == date_str]
            if not target_row.empty:
                idx = target_row.index[0]
                if idx >= 5:  # 确保有足够的历史数据
                    recent_5_vol = df_stock.iloc[idx-5:idx]['成交量'].mean()
                    today_vol = df_stock.iloc[idx]['成交量']
                    volume_ratio = today_vol / recent_5_vol if recent_5_vol > 0 else 1.0
        except:
            volume_ratio = 1.0
        
        return {
            "market_change": market_change,
            "sector_change": sector_change,
            "volume_ratio": volume_ratio
        }
    except Exception as e:
        # 如果任何环节出错，返回中性值
        return {
            "market_change": 0.0,
            "sector_change": 0.0,
            "volume_ratio": 1.0
        }

# ============ 双AI策略 ============
def get_ai_advice_pure_technical(client, symbol, dates, batch_text):
    """
    策略C：纯技术面分析（原版prompt）
    只使用 MACD/RSI/KDJ 等技术指标
    """
    prompt = f"""
你是 A 股短线交易员。根据以下股票的技术数据，预测每日的操作：

股票代码: {symbol}
数据:
{batch_text}

要求:
1. 对每一天，给出【买入】、【卖出】、【持有】或【观望】。
2. 给出简短理由（10字内）。
3. 输出格式严格为：日期|操作|理由

示例:
2024-11-01|买入|超跌反弹
2024-11-02|持有|震荡整理
"""
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的技术分析师。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            stream=False
        )
        
        content = response.choices[0].message.content
        result = []
        for line in content.strip().split('\n'):
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
        logging.error(f"AI调用失败(纯技术): {e}")
        return []

def get_ai_advice_with_sentiment(client, symbol, dates, batch_text, market_contexts):
    """
    策略D：情绪增强分析（新版prompt）
    技术指标 + 大盘走势 + 板块表现 + 量能变化
    """
    # 在batch_text中嵌入市场情绪数据
    enhanced_text = ""
    for date in dates:
        ctx = market_contexts.get(date, {"market_change": 0, "sector_change": 0, "volume_ratio": 1})
        # 找到对应日期的原始数据行
        for line in batch_text.split('\n'):
            if date in line:
                enhanced_text += f"{line} | 大盘:{ctx['market_change']:.2f}% | 量比:{ctx['volume_ratio']:.2f}\n"
                break
    
    prompt = f"""
你是 A 股短线交易员。根据以下股票的技术数据和市场情绪，预测每日的操作：

股票代码: {symbol}
数据（包含大盘走势和量能对比）:
{enhanced_text}

要求:
1. 综合考虑技术面、大盘情绪、成交量变化。
2. 对每一天，给出【买入】、【卖出】、【持有】或【观望】。
3. 给出简短理由（10字内）。
4. 输出格式严格为：日期|操作|理由

示例:
2024-11-01|买入|大盘企稳+量能放大
2024-11-02|观望|市场观望
"""
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个综合市场情绪和技术面的专业交易员。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            stream=False
        )
        
        content = response.choices[0].message.content
        result = []
        for line in content.strip().split('\n'):
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
        logging.error(f"AI调用失败(情绪增强): {e}")
        return []

def get_ai_advice_batch_safe(client, symbol, date_list, data_rows_text):
    """
    【并发安全请求】带自动重试和指数退避
    """
    prompt = f"""
    角色：A股短线交易员
    目标：根据以下 {len(date_list)} 天的行情数据，分别为每一天给出次日操作建议。
    
    股票：{symbol}
    
    行情数据列表：
    {data_rows_text}
    
    请严格按以下格式逐行输出建议（每行一条）：
    YYYY-MM-DD | 建议操作 | 简短理由
    
    操作只能是：买入、卖出、持有、空仓。
    纯文本输出，不要markdown。
    """
    
    retry_count = 5 
    base_delay = 2 
    
    for attempt in range(retry_count):
        try:
            response = client.chat.completions.create(
                model="deepseek-chat", 
                messages=[
                    {"role": "system", "content": "你是一个严格的量化交易助手。请按指定格式输出纯文本。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                timeout=60
            )
            content = response.choices[0].message.content.strip()
            
            lines = content.split('\n')
            results = []
            
            for line in lines:
                line = line.strip()
                if not line: continue
                date_match = re.search(r'202\d-\d{2}-\d{2}', line)
                if not date_match: continue
                date_str = date_match.group(0)
                action_match = re.search(r'(买入|卖出|持有|空仓|观望)', line)
                action = action_match.group(0) if action_match else "观望"
                reason = line.replace(date_str, "").replace(action, "").replace("|", "").replace(":", "").strip()
                results.append({"date": date_str, "action": action, "reason": reason})
            
            if len(results) == 0:
                 raise ValueError("解析为空")
                 
            return results
            
        except Exception as e:
            error_str = str(e)
            delay = base_delay * (2 ** attempt)
            
            if "429" in error_str:
                logging.warning(f"⚠️ [429限流] {symbol} {date_list[0]} 休息 {delay}秒后重试...")
                time.sleep(delay)
            else:
                logging.warning(f"❌ [API错误] {symbol} {date_list[0]} 尝试{attempt+1}失败: {error_str}")
                time.sleep(2)

    return []

def get_stock_name(symbol):
    """
    获取股票中文名称，如果失败则返回代码本身
    """
    try:
        import akshare as ak
        # 获取实时行情快照，查找该代码
        # 注意：这个接口比较重，如果股票多可能会慢。但为了体验，值得。
        # 优化：只取单只股票的实时信息比较难，AkShare通常是全量推。
        # 替代方案：利用 stock_zh_a_hist 的返回值里通常只有数据，没有名字。
        # 我们用一个轻量级的 trick：利用 stock_individual_info_em
        df = ak.stock_individual_info_em(symbol=symbol)
        # df 只有 2 列：item, value
        # value 里的 '股票名称'
        name_row = df[df['item'] == '股票简称']
        if not name_row.empty:
            return name_row.iloc[0]['value']
        
        return symbol 
    except:
        return symbol

def run_single_stock_backtest(symbol, days=90):
    """
    跑一只股票的回测逻辑
    """
    # 1. 先查名字
    stock_name = get_stock_name(symbol)
    logging.info(f"🚀 [{symbol} {stock_name}] 开始回测 ({days}天)...")
    
    end_date = datetime.datetime.now().strftime("%Y%m%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days + 120)).strftime("%Y%m%d")
    
    try:
        import akshare as ak
        df_all = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
    except Exception as e:
        logging.error(f"❌ [{symbol}] 数据获取失败: {e}")
        return None

    if df_all is None or df_all.empty:
        logging.error(f"❌ [{symbol}] 数据为空")
        return None

    total_len = len(df_all)
    if total_len < days:
        start_index = 0
    else:
        start_index = total_len - days

    # --- 计算指标 ---
    df_all['EMA12'] = df_all['收盘'].ewm(span=12, adjust=False).mean()
    df_all['EMA26'] = df_all['收盘'].ewm(span=26, adjust=False).mean()
    df_all['DIF'] = df_all['EMA12'] - df_all['EMA26']
    df_all['DEA'] = df_all['DIF'].ewm(span=9, adjust=False).mean()
    df_all['MACD'] = 2 * (df_all['DIF'] - df_all['DEA'])
    
    BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    BATCH_SIZE = 5
    batch_tasks = []
    
    current_batch_dates = []
    current_batch_text = ""
    
    # 强制日期转字符串
    df_all['日期'] = df_all['日期'].astype(str)

    for i in range(start_index, total_len - 1):
        today_row = df_all.iloc[i]
        today_date_str = str(today_row['日期'])

        line = f"{today_date_str} | 收:{today_row['收盘']} | 涨:{today_row['涨跌幅']}%"
        
        current_batch_dates.append(today_date_str)
        current_batch_text += line + "\n"
        
        if len(current_batch_dates) == BATCH_SIZE or i == total_len - 2:
            batch_tasks.append((list(current_batch_dates), str(current_batch_text)))
            current_batch_dates = []
            current_batch_text = ""

    advice_map = {} 
    
    with ThreadPoolExecutor(max_workers=3) as executor: 
        future_to_task = {
            executor.submit(get_ai_advice_batch_safe, client, symbol, task[0], task[1]): task[0]
            for task in batch_tasks
        }
        
        for future in as_completed(future_to_task):
            try:
                result_list = future.result()
                if result_list:
                    for item in result_list:
                        d = str(item.get("date")).strip()
                        if d:
                            advice_map[d] = (item.get("action", "观望"), item.get("reason", ""))
            except Exception as e:
                pass

    print(f"🔎 [{symbol} {stock_name}] AI建议数量: {len(advice_map)}")

    # --- 结算 (双策略) ---
    initial_cash = 1000000.0
    
    # 策略A (次日开盘)
    cash_a = initial_cash
    pos_a = 0
    prev_asset_a = initial_cash 
    pending_signal_a = "无"  
    
    # 策略B (当日尾盘)
    cash_b = initial_cash
    pos_b = 0
    prev_asset_b = initial_cash 
    
    history = []

    for i in range(start_index, total_len - 1):
        today_row = df_all.iloc[i]
        next_day_row = df_all.iloc[i+1] # 依然需要 next_day 来算 A 的盘后持仓市值吗？不，A是今天开盘就操作了
        
        # 修正：next_day_row 其实在 loop 里是用不到的，除了算 A 的 T日收盘市值
        # 但既然我们现在严谨了，A 在 T 日开盘就操作了，所以 A 的 T 日市值就是 [T日收盘价 * 持仓]
        
        date = str(today_row['日期']).strip()
        
        # 1. 策略A：处理【昨天】遗留的信号 (在今天开盘执行)
        price_open_today = today_row['开盘']
        executed_action_a = "无"
        executed_price_a = ""
        
        if pending_signal_a == "买入":
            if pos_a == 0 and cash_a > price_open_today * 100:
                pos_a = int(cash_a // price_open_today / 100) * 100
                cash_a -= pos_a * price_open_today
                executed_action_a = "执行买入"
                executed_price_a = price_open_today
        elif pending_signal_a in ["卖出", "空仓"]:
            if pos_a > 0:
                cash_a += pos_a * price_open_today
                pos_a = 0
                executed_action_a = "执行卖出"
                executed_price_a = price_open_today
        
        # A 在 T 日收盘时的资产 (今天开盘操作完了，持有到收盘)
        asset_a = cash_a + (pos_a * today_row['收盘'])
        daily_pnl_a = asset_a - prev_asset_a
        prev_asset_a = asset_a

        # 2. 获取【今天】的 AI 建议 (用于 策略B 今天执行，或 策略A 明天执行)
        advice_action, reason = advice_map.get(date, ("观望", "无数据"))
        
        # 记录给 A 明天用
        pending_signal_a = advice_action

        # 3. 策略B：当场执行【今天】的信号 (在今天尾盘)
        price_close_today = today_row['收盘']
        action_b = "无"
        trade_price_b = ""
        
        if advice_action == "买入":
            if pos_b == 0 and cash_b > price_close_today * 100:
                pos_b = int(cash_b // price_close_today / 100) * 100 
                cash_b -= pos_b * price_close_today
                action_b = "买入"
                trade_price_b = price_close_today
        elif advice_action in ["卖出", "空仓"] and pos_b > 0:
            cash_b += pos_b * price_close_today
            pos_b = 0
            action_b = "卖出"
            trade_price_b = price_close_today
            
        # B 在 T 日收盘时的资产 (尾盘刚操作完)
        asset_b = cash_b + (pos_b * today_row['收盘'])
        daily_pnl_b = asset_b - prev_asset_b
        prev_asset_b = asset_b

        # 生成执行说明（策略A - 基于昨天的信号）
        exec_note_a = ""
        prev_signal = advice_map.get(df_all.iloc[i-1]['日期'] if i > start_index else "", ("", ""))[0] if i > start_index else ""
        prev_pos_a = 0  # 我们需要记录昨天的仓位，但为了简化，我们用逻辑推断
        
        if executed_action_a == "执行买入":
            exec_note_a = "✅ 执行买入（依据昨日信号）"
        elif executed_action_a == "执行卖出":
            exec_note_a = "✅ 执行卖出（依据昨日信号）"
        elif prev_signal == "买入" and executed_action_a == "无":
            exec_note_a = "⚠️ 买入信号但已有仓位或资金不足"
        elif prev_signal == "持有":
            if pos_a > 0:
                exec_note_a = "📊 继续持有（有仓位）"
            else:
                exec_note_a = "💤 空仓观望（无仓位）"
        elif prev_signal in ["卖出", "空仓"] and executed_action_a == "无":
            exec_note_a = "⚠️ 卖出信号但已空仓"
        else:
            exec_note_a = "无操作"

        # 生成执行说明（策略B - 基于今天的信号）
        exec_note_b = ""
        if advice_action == "买入":
            if action_b == "买入":
                exec_note_b = "✅ 执行买入"
            else:
                exec_note_b = "⚠️ 买入信号但已有仓位或资金不足"
        elif advice_action in ["卖出", "空仓"]:
            if action_b == "卖出":
                exec_note_b = "✅ 执行卖出"
            else:
                exec_note_b = "⚠️ 卖出信号但已空仓"
        elif advice_action == "持有":
            if pos_b > 0:
                exec_note_b = "📊 继续持有（有仓位）"
            else:
                exec_note_b = "💤 空仓观望（无仓位）"
        elif advice_action == "观望":
            exec_note_b = "💤 观望"
        else:
            exec_note_b = "无操作"

        history.append({
            "日期": date,
            "收盘": today_row['收盘'], # 记录当天的收盘价
            "AI建议": advice_action, # 这是今天的建议
            "理由": reason,
            
            # 策略A：显示今天发生了什么 (对应昨天的建议)
            "操作(开盘买)": executed_action_a,
            "执行说明(开盘买)": exec_note_a,
            "成交价(开盘买)": executed_price_a,
            "持仓股数(开盘买)": pos_a,
            "当日盈亏(开盘买)": round(daily_pnl_a, 2),
            "总资产(开盘买)": round(asset_a, 2),
            
            # 策略B：显示今天发生了什么 (对应今天的建议)
            "操作(尾盘买)": action_b,
            "执行说明(尾盘买)": exec_note_b,
            "成交价(尾盘买)": trade_price_b,
            "持仓股数(尾盘买)": pos_b,
            "当日盈亏(尾盘买)": round(daily_pnl_b, 2),
            "总资产(尾盘买)": round(asset_b, 2)
        })
    
    if not history:
        print(f"⚠️ [{symbol}] History is empty!") 
        return None
    
    # --- 计算基准收益率（买入持有策略） ---
    # 90天基准
    first_price_90 = df_all.iloc[start_index]['收盘']
    last_price = df_all.iloc[-1]['收盘']
    benchmark_roi_90 = (last_price - first_price_90) / first_price_90 * 100
    
    # 60天基准
    days_available = len(df_all) - start_index
    if days_available >= 60:
        price_60_days_ago = df_all.iloc[-60]['收盘']
        benchmark_roi_60 = (last_price - price_60_days_ago) / price_60_days_ago * 100
    else:
        benchmark_roi_60 = None
    
    # 30天基准
    if days_available >= 30:
        price_30_days_ago = df_all.iloc[-30]['收盘']
        benchmark_roi_30 = (last_price - price_30_days_ago) / price_30_days_ago * 100
    else:
        benchmark_roi_30 = None
    
    # --- 结算指标 ---
    final_a = history[-1]['总资产(开盘买)']
    roi_a = (final_a - initial_cash) / initial_cash * 100
    
    final_b = history[-1]['总资产(尾盘买)']
    roi_b = (final_b - initial_cash) / initial_cash * 100
    
    # 计算胜率 (策略A)
    win_days = 0
    hold_days = 0
    trade_count = 0
    metrics_max_dd = 0.0
    metrics_peak = initial_cash
    
    prev_asset = initial_cash
    for day in history:
        # 修复：匹配新的"执行买入"文本
        if '买入' in str(day['操作(开盘买)']):
            trade_count += 1
        
        curr = day['总资产(开盘买)']
        if curr != prev_asset:
            hold_days += 1
            if curr > prev_asset:
                win_days += 1
        
        if curr > metrics_peak:
            metrics_peak = curr
        if metrics_peak > 0:
            dd = (metrics_peak - curr) / metrics_peak
            if dd > metrics_max_dd:
                metrics_max_dd = dd
        prev_asset = curr
            
    win_rate = (win_days / hold_days * 100) if hold_days > 0 else 0.0
    
    return {
        "symbol": symbol, 
        "stock_name": stock_name,
        "roi_open": roi_a, "final_asset_open": final_a,
        "roi_close": roi_b, "final_asset_close": final_b,
        "benchmark_90d": benchmark_roi_90,
        "benchmark_60d": benchmark_roi_60,
        "benchmark_30d": benchmark_roi_30,
        "win_rate": win_rate,
        "trade_count": trade_count,
        "max_drawdown": metrics_max_dd * 100,
        "details": history
    }

def run_batch_backtest(stock_list):
    print(f"🔥 启动并发回测引擎 (Ultra版)，目标股票: {stock_list}")
    start_total = time.time()
    results = []
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_stock = {
            executor.submit(run_single_stock_backtest, stock): stock
            for stock in stock_list
        }
        
        for future in as_completed(future_to_stock):
            stock = future_to_stock[future]
            try:
                res = future.result()
                if res:
                    stock_name = res.get('stock_name', '')
                    print(f"✅ [{stock} {stock_name}] 完成! 开盘买: {res['roi_open']:.2f}% | 胜率: {res['win_rate']:.1f}%")
                    results.append(res)
                else:
                    print(f"⚠️ [{stock}] 返回None")
            except Exception as e:
                print(f"❌ [{stock}] 异常: {e}")

    print(f"\n✨ 全部完成! 总耗时: {time.time() - start_total:.1f}秒")
    return results

if __name__ == "__main__":
    stocks_input = input("请输入股票代码(逗号分隔): ")
    stocks = [s.strip() for s in stocks_input.split(",") if s.strip()]
    if not stocks:
        stocks = ["600519", "000858"]
        
    final_results = run_batch_backtest(stocks)
    
    if final_results:
        summary_rows = []
        for r in final_results:
            # 格式化基准收益率（可能为None）
            bench_90 = f"{r['benchmark_90d']:.2f}%" if r['benchmark_90d'] is not None else "N/A"
            bench_60 = f"{r['benchmark_60d']:.2f}%" if r['benchmark_60d'] is not None else "N/A"
            bench_30 = f"{r['benchmark_30d']:.2f}%" if r['benchmark_30d'] is not None else "N/A"
            
            summary_rows.append({
                "代码": r['symbol'], 
                "名称": r['stock_name'],
                "AI策略(开盘买)": f"{r['roi_open']:.2f}%", 
                "AI策略(尾盘买)": f"{r['roi_close']:.2f}%",
                "基准(90天)": bench_90,
                "基准(60天)": bench_60,
                "基准(30天)": bench_30,
                "策略优势(开vs基准)": f"{r['roi_open'] - r['benchmark_90d']:.2f}%",
                "胜率": f"{r['win_rate']:.1f}%",
                "交易次数": r['trade_count'],
                "最大回撤": f"{r['max_drawdown']:.2f}%",
                "最终资产(开盘买)": f"{r['final_asset_open']:.0f}",
                "最终资产(尾盘买)": f"{r['final_asset_close']:.0f}"
            })
        
        summary_df = pd.DataFrame(summary_rows)
        print("\n🏆 最终成绩单:")
        print(summary_df)
        summary_df.to_csv("backtest_result.csv", index=False)
        print("✅ backtest_result.csv 已保存")
        
        all_details = []
        for r in final_results:
            d_df = pd.DataFrame(r['details'])
            d_df.insert(0, '代码', r['symbol'])
            d_df.insert(1, '名称', r['stock_name'])
            all_details.append(d_df)
            
        if all_details:
            master_df = pd.concat(all_details, ignore_index=True)
            master_df.to_csv("all_details.csv", index=False)
            print(f"✅ all_details.csv 已保存 (共 {len(master_df)} 条)")
    else:
        print("❌ 没有任何结果生成！")
