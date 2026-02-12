
import streamlit as st
import pandas as pd
import akshare as ak
import datetime
import time
from backtest_engine import BacktestEngine
from stock_names import get_stock_name_offline
import plotly.express as px

# 设置页面
st.set_page_config(page_title="🔬 量化策略研究室", layout="wide")

st.title("🔬 量化策略研究室 (Research Lab)")
st.markdown("在这里，我们可以对 **大样本股票池** 进行历史回测，验证策略的 **胜率** 和 **收益能力**。")

# ==================== 1. 侧边栏配置 ====================
st.sidebar.header("🛠️ 实验参数配置")

# A. 股票池选择
pool_type = st.sidebar.selectbox(
    "1. 选择股票池 (样本)",
    ["⭐ 我的自选股", "🏆 沪深300成分股 (大盘蓝筹)", "🚀 创业板50 (成长龙头)", "🎲 随机抽样 (50只)"]
)

# B. 回测时间范围
date_range = st.sidebar.date_input(
    "2. 回测时间范围",
    [datetime.date(2025, 1, 1), datetime.date(2025, 12, 31)]
)

# C. 策略选择
strategy_type = st.sidebar.selectbox(
    "3. 待测策略",
    ["Score_V1 (综合记分)", "Trend_V2 (趋势猎手)", "Oscillation_V3 (波段防御)"]
)

# D. 资金设置
initial_capital = st.sidebar.number_input("初始资金 (每只)", value=100000)

# ==================== 2. 获取股票列表 ====================
@st.cache_data
def get_stock_pool(pool_type):
    """获取股票池列表"""
    stocks = []
    
    if "我的自选" in pool_type:
        from database import DBManager
        db = DBManager()
        # 获取所有用户的去重自选股，或者指定用户的
        # 这里简单起见，获取数据库里所有的 distinct stock_code
        # 实际使用中可能需要根据当前登录用户或其他逻辑
        # 既然是 Lab，我们拿数据库里存的所有关注过的票来跑
        try:
            with db._get_connection() as conn:
                df = pd.read_sql("SELECT DISTINCT stock_code FROM watchlist", conn)
            stocks = df['stock_code'].tolist()
        except Exception as e:
            st.error(f"读取自选股失败: {e}")
            
    elif "沪深300" in pool_type:
        with st.spinner("正在拉取沪深300成分股名单..."):
            try:
                df = ak.index_stock_cons(symbol="000300")
                stocks = df['品种代码'].tolist()
            except:
                st.error("获取沪深300失败，请检查网络")

    elif "创业板50" in pool_type:
        with st.spinner("正在拉取创业板50名单..."):
            try:
                df = ak.index_stock_cons(symbol="399673")
                stocks = df['品种代码'].tolist()
            except:
                pass
                
    elif "随机" in pool_type:
        # 获取 A 股所有股票，随机抽 50 个
        pass # 暂未实现，为了演示简单，先保留前两个
        
    return stocks

# ==================== 3. 核心回测逻辑 (重写 loop) ====================
def run_single_stock_backtest(stock_code, start_date, end_date, strategy):
    """跑一只股票的回测"""
    from main import get_stock_data
    
    # 1. 获取数据 (使用 main.py 的 ak.stock_zh_a_hist)
    # 这里的 start_date 需要是字符串 "YYYYMMDD"
    s_str = start_date.strftime("%Y%m%d")
    e_str = end_date.strftime("%Y%m%d")
    
    try:
        df_hist = ak.stock_zh_a_hist(symbol=stock_code, period="daily", start_date=s_str, end_date=e_str, adjust="qfq")
    except:
        return None
        
    if df_hist is None or df_hist.empty:
        return None

    # 列名适配
    rename_map = {'日期':'date', '开盘':'open', '收盘':'close', '最高':'high', '最低':'low', '成交量':'volume', '涨跌幅':'pctChg'}
    cols = df_hist.columns.tolist()
    final_map = {k:v for k,v in rename_map.items() if k in cols}
    df = df_hist.rename(columns=final_map)
    df['date'] = pd.to_datetime(df['date'])
    
    # 初始化引擎
    engine = BacktestEngine(stock_code)
    engine.df = df
    engine._calculate_indicators()
    
    if engine.df is None or engine.df.empty: return None
    
    # 模拟交易循环
    balance = initial_capital
    position = 0
    trades = []
    
    df_run = engine.df
    
    # 至少要有数据才跑
    if len(df_run) < 20: return None # 数据太少不够算均线
    
    for i in range(20, len(df_run)):
        row = df_run.iloc[i]
        prev_row = df_run.iloc[i-1]
        date = row['date']
        price = float(row['close'])
        
        # 调用策略
        # 注意: make_decision 内部也是用的 row/prev_row
        action, reason, score = engine.make_decision(row, prev_row, strategy)
        
        # 执行交易 (全仓买卖模式 - 简单验证)
        if action == "买入" and position == 0:
            position = balance / price
            balance = 0
            trades.append({'date': date, 'action': 'buy', 'price': price, 'reason': reason})
            
        elif action == "卖出" and position > 0:
            balance = position * price
            position = 0
            trades.append({'date': date, 'action': 'sell', 'price': price, 'reason': reason})
            
    # 结算
    final_val = balance + (position * df_run.iloc[-1]['close'])
    ret = (final_val - initial_capital) / initial_capital * 100
    
    # 统计胜率
    win_count = 0
    total_trades = 0
    # 简单的胜率统计：卖出价格 > 上一次买入价格
    last_buy_price = 0
    for t in trades:
        if t['action'] == 'buy':
            last_buy_price = t['price']
        elif t['action'] == 'sell':
            if last_buy_price > 0:
                total_trades += 1
                if t['price'] > last_buy_price:
                    win_count += 1
            last_buy_price = 0
            
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
    
    return {
        "stock": stock_code,
        "return": ret,
        "win_rate": win_rate,
        "trades": total_trades,
        "final_val": final_val
    }

# ==================== 4. 主界面逻辑 ====================

if st.button("🔥 开始大样本回测", type="primary"):
    start_date, end_date = date_range
    stocks = get_stock_pool(pool_type)
    
    if not stocks:
        st.error("股票池为空！")
        st.stop()
        
    st.info(f"选定股票池: {len(stocks)} 只。正在全力回测中，请稍候...")
    
    progress = st.progress(0)
    results = []
    
    # 为了演示速度，如果是 HS300，我们只跑前 50 只 (User可自行修改)
    # 或者全跑但需要时间
    # 这里我们设置一个上限，防止卡死
    limit = 50 
    target_stocks = stocks[:limit]
    
    st.caption(f"⚠️ 为节省时间，本次仅演示前 {limit} 只股票 ({len(stocks)} -> {limit})。")
    
    start_time = time.time()
    
    for i, stock in enumerate(target_stocks):
        res = run_single_stock_backtest(stock, start_date, end_date, strategy_type)
        if res:
            res['name'] = get_stock_name_offline(stock)
            results.append(res)
            
        progress.progress((i + 1) / len(target_stocks))
    
    end_time = time.time()
    duration = end_time - start_time
    
    # ==================== 5. 展示结果 ====================
    if results:
        df_res = pd.DataFrame(results)
        
        st.divider()
        st.subheader("📊 实验报告")
        st.write(f"耗时: {duration:.2f} 秒 | 成功分析: {len(df_res)} 只")
        
        # 核心指标
        avg_ret = df_res['return'].mean()
        avg_win = df_res['win_rate'].mean()
        pos_ret = len(df_res[df_res['return'] > 0])
        pos_ratio = pos_ret / len(df_res) * 100
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("平均收益率", f"{avg_ret:.2f}%", help="所有股票收益率的平均值")
        c2.metric("平均胜率", f"{avg_win:.2f}%", help="每只股票交易胜率的平均值")
        c3.metric("正收益占比", f"{pos_ratio:.1f}%", help="最终赚钱的股票数量占比")
        c4.metric("最牛股票", f"{df_res.iloc[df_res['return'].idxmax()]['name']}")
        
        # 图表：收益率分布
        fig = px.histogram(df_res, x="return", nbins=20, title="收益率分布图 (横轴:收益%, 纵轴:股票数量)")
        fig.add_vline(x=0, line_dash="dash", line_color="red")
        st.plotly_chart(fig, use_container_width=True)
        
        # 详细表格
        st.subheader("📋 详细榜单")
        
        # 格式化
        df_display = df_res[['stock', 'name', 'return', 'win_rate', 'trades', 'final_val']].copy()
        df_display['return'] = df_display['return'].map(lambda x: f"{x:.2f}%")
        df_display['win_rate'] = df_display['win_rate'].map(lambda x: f"{x:.1f}%")
        df_display['final_val'] = df_display['final_val'].map(lambda x: f"¥{x:,.0f}")
        
        st.dataframe(
            df_display.sort_values('return', ascending=False),
            column_config={
                "stock": "代码",
                "name": "名称",
                "return": "总收益率",
                "win_rate": "交易胜率",
                "trades": "交易次数",
                "final_val": "期末资产"
            },
            use_container_width=True
        )
        
    else:
        st.warning("本次回测未产生有效结果 (可能数据获取失败或无交易)。")

