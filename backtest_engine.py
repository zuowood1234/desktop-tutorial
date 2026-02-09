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



def run_compare_backtest(symbol, days=90):
    """
    核心对比回测逻辑
    """
    stock_name = get_stock_name(symbol)
    logging.info(f"🚀 [{symbol} {stock_name}] 开始双AI对比回测...")
    
    # 1. 获取数据 (尝试使用新浪财经作为备用源，因为 AkShare 东财源连接失败)
    end_date = datetime.datetime.now().strftime("%Y%m%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=days + 60)).strftime("%Y%m%d") # 多取一点缓冲
    
    df_all = None
    
    # 尝试方案 A: 新浪财经接口 (无需代理通常较稳)
    try:
        # 转换代码格式: 600519 -> sh600519, 000001 -> sz000001
        sina_symbol = f"sh{symbol}" if symbol.startswith('6') else f"sz{symbol}"
        url = f"https://q.stock.sohu.com/hisHq?code=cn_{symbol}&start={start_date}&end={end_date}"
        # 搜狐/新浪历史数据有时候不稳定，尝试使用更简单的网易财经或直接 requests
        
        # 这里为了稳妥，我们手动实现一个简单的新浪日线抓取，或者继续尝试 akshare 的其他接口
        import akshare as ak
        # 尝试使用 akshare 的 index_zh_a_hist (虽然是指数，但个股也有其他接口)
        # 改用: stock_zh_a_daily (新浪源)
        df_all = ak.stock_zh_a_daily(symbol=sina_symbol, start_date=start_date, end_date=end_date)
        
        # 调试: 打印返回的列
        logging.info(f"新浪源返回列名: {df_all.columns}")
        
        # 新浪源通常返回: date, open, high, low, close, volume, amount, turn...
        # 我们只需要前6个关键列
        rename_map = {
            'date': '日期', 
            'open': '开盘', 
            'high': '最高', 
            'low': '最低', 
            'close': '收盘', 
            'volume': '成交量'
        }
        df_all = df_all.rename(columns=rename_map)
        
        # 确保包含必要的列
        required_cols = ['日期', '开盘', '最高', '收盘', '最低', '成交量']
        for col in required_cols:
            if col not in df_all.columns:
                 # 如果是中文列名 (可能是不同版本的akshare)
                 pass 
        
        # 计算涨跌幅
        df_all['收盘'] = pd.to_numeric(df_all['收盘'])
        df_all['涨跌幅'] = df_all['收盘'].pct_change() * 100
        df_all['涨跌幅'] = df_all['涨跌幅'].fillna(0)
        
    except Exception as e_sina:
        logging.warning(f"新浪源失败: {e_sina}, 尝试回退到东财源...")
        try:
            import akshare as ak
            df_all = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        except Exception as e:
             logging.error(f"所有数据源均失败: {e}")
             return None

    if df_all is None or df_all.empty:
        return None

    # 统一日期格式
    df_all['日期'] = pd.to_datetime(df_all['日期']).dt.strftime('%Y-%m-%d')
    total_len = len(df_all)
    start_index = max(0, total_len - days)

    # 2. 准备市场情绪数据
    market_contexts = {}
    for i in range(start_index, total_len):
        date_str = df_all.iloc[i]['日期']
        market_contexts[date_str] = get_market_context(date_str, df_all)
        
    # 初始化 DeepSeek 客户端
    BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    # 4. 严格逐日回测 (防止未来函数/数据对齐作弊)
    # 4. 严格逐日回测 (防止未来函数/数据对齐作弊)
    advice_pure = {}
    advice_sentiment = {}
    
    # 初始化持仓状态 (False=空仓, True=持仓)
    # 简单的假设：每次买入满仓，卖出空仓
    pos_pure = False 
    pos_sent = False
    
    print(f"🧠 开始严格逐日回测 (共 {total_len} 个交易日) [含持仓感知]...")
    
    # 维护一个滚动的历史数据窗口
    history_window = []
    
    for i in range(start_index, total_len - 1):
        today_row = df_all.iloc[i]
        date_str = str(today_row['日期'])
        
        # 1. 构建截至今日的历史窗口
        # 为了节省 Token，只取最近 10 天的数据传给 AI
        history_window.append({
            "date": date_str,
            "close": today_row['收盘'],
            "pct": today_row['涨跌幅'],
            "vol": today_row['成交量']
        })
        
        recent_data = history_window[-10:] # 只看最近10天
        
        # 构建 Prompt 文本 (K线数据)
        k_lines_text = ""
        sent_enhanced_text = ""
        
        for item in recent_data:
            d = item['date']
            line = f"{d} | 收:{item['close']:.2f} | 涨:{item['pct']:.2f}%"
            k_lines_text += line + "\n"
            
            # 情绪数据
            ctx = market_contexts.get(d, {"market_change": 0, "volume_ratio": 1})
            sent_enhanced_text += f"{line} | 大盘:{ctx['market_change']:.2f}% | 量比:{ctx['volume_ratio']:.2f}\n"

        # === 动态 Prompt 构建函数 ===
        def build_prompt(strategy_name, data_text, is_holding):
            status_str = "【当前持仓：持有中】" if is_holding else "【当前持仓：空仓】"
            action_guide = ""
            if is_holding:
                action_guide = "你现在持有该股。请决策：是【持有】等待上涨，还是【卖出】止盈止损？(除非由于极大风险，否则不要轻易卖出)"
            else:
                action_guide = "你现在空仓。请决策：是继续【观望】，还是【买入】搏取收益？(只有出现明确买点才买入)"
            
            return f"""
你是 A 股短线交易员。{status_str}
基于以下最近 10 天的行情，判断【今天】({date_str}) 的操作：

{data_text}

交易指引：{action_guide}

要求：请严格按照格式输出：操作|理由
操作只能是【买入】/【卖出】/【持有】/【观望】中的一个。
理由请简短概括，不超过10个字。

示例：
买入|放量突破
卖出|高位滞涨
"""

        # 2. 调用 AI (纯技术)
        prompt_pure = build_prompt("纯技术", k_lines_text, pos_pure)
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt_pure}],
                temperature=0.1
            )
            content = resp.choices[0].message.content.strip()
            parts = content.split('|')
            action = parts[0].strip()
            reason = parts[1].strip() if len(parts) > 1 else "AI未提供理由"
            
            # 清洗动作
            valid_action = "观望"
            if "买" in action: valid_action = "买入"
            elif "卖" in action: valid_action = "卖出"
            elif "持" in action: valid_action = "持有"
            
            # 自动纠错：如果空仓却说持有 -> 视为观望；如果持仓却说买入 -> 视为持有
            if not pos_pure and valid_action == "持有": valid_action = "观望"
            if pos_pure and valid_action == "买入": valid_action = "持有"
            
            advice_pure[date_str] = (valid_action, reason)
            
            # 更新模拟持仓状态 (用于下一天的 Prompt)
            if valid_action == "买入": pos_pure = True
            elif valid_action == "卖出": pos_pure = False
            
        except Exception as e:
            logging.error(f"技术派逐日失败 {date_str}: {e}")
            advice_pure[date_str] = ("观望", "API错误")

        # 3. 调用 AI (情绪增强)
        prompt_sent = build_prompt("情绪增强", sent_enhanced_text, pos_sent)
        try:
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt_sent}],
                temperature=0.1
            )
            content = resp.choices[0].message.content.strip()
            parts = content.split('|')
            action = parts[0].strip()
            reason = parts[1].strip() if len(parts) > 1 else "AI未提供理由"

            valid_action = "观望"
            if "买" in action: valid_action = "买入"
            elif "卖" in action: valid_action = "卖出"
            elif "持" in action: valid_action = "持有"
            
            # 自动纠错
            if not pos_sent and valid_action == "持有": valid_action = "观望"
            if pos_sent and valid_action == "买入": valid_action = "持有"
            
            advice_sentiment[date_str] = (valid_action, reason)
            
            # 更新模拟持仓状态
            if valid_action == "买入": pos_sent = True
            elif valid_action == "卖出": pos_sent = False

        except Exception as e:
            logging.error(f"情绪派逐日失败 {date_str}: {e}")
            advice_sentiment[date_str] = ("观望", "API错误")
            
        # 打印进度 (不换行)
        print(f"\r📅 进度: {date_str} 完成", end="", flush=True)
        # time.sleep(0.1) # 极速模式，不等待
        
    print(f"\n✅ 逐日回测完成！")

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
            
            "AI建議(情绪增强)": action_d,
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
    import sys
    
    # 支持命令行参数传参，方便 app.py 调用
    if len(sys.argv) > 1:
        # 假设参数格式如: python backtest_engine.py 600519,000001
        stocks_input = sys.argv[1]
    else:
        stocks_input = input("请输入股票代码(逗号分隔): ")
        
    stocks = [s.strip() for s in stocks_input.split(",") if s.strip()]
    if not stocks:
        stocks = ["600519"]
    
    # 默认仅回测最近 30 天 (约5-8分钟)，以免时间过长
    # 如果需要长周期，可改为 [30, 60, 90]
    periods = [30]
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
        
        # 详细日志 (保存所有生成周期的详情，这里优先保存30天的)
        all_details = []
        for stock, period_results in all_results.items():
            # 优先 90 > 60 > 30 
            target_p = 30
            if 90 in period_results: target_p = 90
            elif 60 in period_results: target_p = 60
            
            if target_p in period_results:
                r = period_results[target_p]
                d_df = pd.DataFrame(r['details'])
                d_df.insert(0, '代码', r['symbol'])
                d_df.insert(1, '名称', r['stock_name'])
                all_details.append(d_df)
        
        if all_details:
            master_df = pd.concat(all_details, ignore_index=True)
            master_df.to_csv("backtest_compare_details.csv", index=False, encoding='utf-8-sig')
            print(f"✅ backtest_compare_details.csv 已保存 (共 {len(master_df)} 条)")
    else:
        print("❌ 没有结果")

