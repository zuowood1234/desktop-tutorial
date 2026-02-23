import streamlit as st
import pandas as pd
import numpy as np
import os
import plotly.graph_objects as go
import datetime
from utils import get_db, inject_custom_css, check_authentication, render_sidebar

st.set_page_config(page_title="专业回测舱 - AI 智能投顾", layout="wide")
inject_custom_css()
check_authentication()
render_sidebar()

# 页面权限检查 (需要管理后台开启权限)
if st.session_state.get('user_role') != 'admin' and not st.session_state.get('can_backtest'):
    st.error("🚫 您的账户暂无专业回测权限。请联系管理员开启！")
    st.stop()

st.title("🔬 专业量化回测舱 (Pro)")
st.caption("基于 A 股 T+1 真实交易规则及双复权价格体系的高精度单票回测系统。")

# --- 布局 ---
col_sidebar, col_main = st.columns([1, 3])

with col_sidebar:
    st.markdown("### 1. 基础环境设置")
    stock_code = st.text_input("回测标的 (股票代码)", value="600519", placeholder="例如: 600519")
    initial_cash = st.number_input("初始资金 (元)", min_value=10000, value=200000, step=10000)
    
    st.markdown("---")
    st.markdown("### 1.5 回测时间窗口")
    start_date = st.date_input("起算日期 (Start Date)", value=datetime.date(2005, 1, 1), min_value=datetime.date(1990, 1, 1), max_value=datetime.date.today())
    end_date = st.date_input("截止日期 (End Date)", value=datetime.date.today(), min_value=datetime.date(1990, 1, 1), max_value=datetime.date.today())
    
    st.markdown("---")
    st.markdown("### 2. 摩擦成本与规则")
    slippage = st.number_input("滑点补偿 (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.05) / 100.0
    commission = st.number_input("双向佣金 (万分之几)", min_value=0.0, max_value=30.0, value=1.5, step=0.5) / 10000.0
    stamp_duty = st.number_input("双向印花税 (万分之几)", min_value=0.0, max_value=50.0, value=5.0, step=0.5) / 10000.0
    
    st.markdown("---")
    st.markdown("### 3. 风控刹车配置")
    stop_loss = st.number_input("触发止损 (-%)", min_value=0.0, max_value=50.0, value=8.0, step=1.0)
    take_profit = st.number_input("触发止盈 (+%)", min_value=0.0, max_value=200.0, value=0.0, help="0表示不止盈, 大于0生效")
    max_days = st.number_input("最大持股天数", min_value=0, max_value=500, value=20, help="0表示无时间限制")

with col_main:
    st.markdown("### 4. 策略构建器 (第一轨)")
    st.info("💡 提示：您可以随时切换所有条件是 AND (同时满足) 还是 OR (满足其一) 的关系。不勾选代表不限制。")
    
    st.write("**买入过滤网 (Buy Screen)**")
    with st.expander("📈 配置买入条件 (技术面 & 基本面)", expanded=True):
        buy_logic_type = st.radio("买入网条件组合逻辑：", ["AND (必须同时满足所有勾选条件, 推荐)", "OR (只要满足其中任意一个条件即可开仓)"], horizontal=True)
        st.markdown("---")
        buy_tabs = st.tabs(["👈 左侧交易 (逆势深水区抄底)", "👉 右侧交易 (追击主升浪/顺势)", "🏢 基本面与风控 (压舱石防雷)"])
        
        with buy_tabs[0]: # 左侧交易
            bc1, bc2 = st.columns(2)
            with bc1:
                buy_bias12 = st.checkbox("🚩 两周黄金坑(BIAS_12超跌)", value=False)
                if buy_bias12:
                    buy_bias12_val = st.slider("12日乖离率小于(%)", -30, 0, -10, 1)
                    
                buy_kdj = st.checkbox("🚩 KDJ 超卖与金叉", value=False)
                if buy_kdj:
                    buy_kdj_j = st.slider("J值小于极度超卖线", -20, 100, 20, 5)
                    buy_kdj_k = st.slider("同步要求 K值小于", 0, 100, 30, 5)
                    buy_kdj_d = st.slider("同步要求 D值小于", 0, 100, 30, 5)
                    
                buy_rsi = st.checkbox("🚩 RSI极度超卖", value=False)
                if buy_rsi:
                    buy_rsi_val = st.slider("RSI弱于", 0, 100, 30, 5)
            with bc2:
                buy_boll_lower = st.checkbox("🚩 触及布林下轨", value=False)
                
                buy_vol_shrink = st.checkbox("🚩 百日地量见地价", value=False)
                if buy_vol_shrink:
                    st.caption("要求: 当前成交量严重萎缩至过去20日均量的一半以下")
                    
                buy_limit_down = st.checkbox("🚩 抄底避险防火墙", value=False)
                if buy_limit_down:
                    st.caption("要求: 近5日内无跌停，防止接飞刀")
                    
        with buy_tabs[1]: # 右侧交易
            bc3, bc4 = st.columns(2)
            with bc3:
                buy_ma = st.checkbox("🚩 收盘价站上均线", value=True)
                if buy_ma:
                    buy_ma_col = st.selectbox("收盘价需大于", ["MA_5", "MA_10", "MA_20", "MA_60", "MA_120", "MA_250"], index=2)
                    
                buy_ma_bull = st.checkbox("🚩 经典多头排列", value=False)
                if buy_ma_bull:
                    st.caption("要求: 短期到长期均线依次发散 (MA5>10>20>60)")
                    
                buy_macd = st.checkbox("🚩 MACD上升动能", value=True)
                if buy_macd:
                    buy_macd_val = st.number_input("MACD 柱子大于", value=0.0)
                    
                buy_macd_gc = st.checkbox("🚩 MACD 金叉 (预埋)", value=False)
            with bc4:
                buy_turnover = st.checkbox("🚩 换手率爆发", value=False)
                if buy_turnover:
                    buy_turn_z = st.slider("换手Z-Score高于", 0.0, 5.0, 1.5, 0.1)
                    
                buy_vol_ratio = st.checkbox("🚩 右侧放量进攻", value=False)
                if buy_vol_ratio:
                    buy_vol_ratio_val = st.slider("5日量比大于", 1.0, 10.0, 2.0, 0.5)

        with buy_tabs[2]: # 基本面
            bc5, bc6 = st.columns(2)
            with bc5:
                buy_mv = st.checkbox("🚩 市值偏好", value=False)
                if buy_mv:
                    buy_mv_val = st.slider("总市值区间(亿元)", 0, 20000, (0, 500), 10)
                    
                buy_pe = st.checkbox("🚩 历史PE分位", value=False)
                if buy_pe:
                    buy_pe_val = st.slider("近三年PE分位低于(%)", 0, 100, 30, 5)
                    
                buy_pb = st.checkbox("🚩 PB市净率", value=False)
                if buy_pb:
                    buy_pb_val = st.slider("PB低于", 0.0, 10.0, 3.0, 0.5)
                    
                buy_roe = st.checkbox("🚩 高ROE要求", value=False)
                if buy_roe:
                    buy_roe_val = st.slider("ROE大于(%)", 0.0, 30.0, 15.0, 1.0)
            with bc6:
                buy_yoy = st.checkbox("🚩 净利润高质", value=False)
                if buy_yoy:
                    buy_yoy_val = st.slider("净利润YOY大于(%)", 0.0, 100.0, 20.0, 5.0)
                    
                buy_deducted_yoy = st.checkbox("🚩 扣非净利润(严苛核查质量)", value=False)
                if buy_deducted_yoy:
                    buy_deducted_yoy_val = st.slider("扣非净利润YOY大于(%)", 0.0, 100.0, 20.0, 5.0)
                    
                buy_rev_yoy = st.checkbox("🚩 营业收入暴力增长", value=False)
                if buy_rev_yoy:
                    buy_rev_yoy_val = st.slider("营收YOY大于(%)", 0.0, 100.0, 20.0, 5.0)
    st.write("")
    st.write("**卖出逃顶网 (Sell Screen)**")
    with st.expander("🏃 配置卖出条件", expanded=True):
        sell_logic_type = st.radio("卖出网条件组合逻辑：", ["AND (必须同时满足所有勾选条件)", "OR (只要满足其中任意一个条件即可平仓, 逃顶推荐)"], horizontal=True, index=1)
        st.markdown("---")
        sell_tabs = st.tabs(["👈 左侧卖出 (逆势遇阻逃顶)", "👉 右侧卖出 (均线破位止损止盈)"])
        
        with sell_tabs[0]: # 左侧卖出
            sc1, sc2 = st.columns(2)
            with sc1:
                sell_bias6 = st.checkbox("🏃 战术刺刀(BIAS_6连板警报)", value=False)
                if sell_bias6:
                    sell_bias6_val = st.slider("6日乖离率大于(%) - 谨防高位接盘", 0, 50, 15, 1)
                    
                sell_rsi = st.checkbox("🏃 RSI极度超买 (高压警报)", value=False)
                if sell_rsi:
                    sell_rsi_val = st.slider("RSI强势超过(需警惕)", 0, 100, 80, 5)
            with sc2:
                sell_kdj = st.checkbox("🏃 KDJ超买天花板警报", value=False)
                if sell_kdj:
                    sell_kdj_j = st.slider("逃顶: J值大于", 0, 120, 80, 5)
                    sell_kdj_k = st.slider("同步要求 K值大于", 0, 100, 70, 5)
                    sell_kdj_d = st.slider("同步要求 D值大于", 0, 100, 70, 5)
                    
                sell_boll = st.checkbox("🏃 触碰布林上轨", value=False)
                if sell_boll:
                    st.caption("提示: 最新价突破或触及 BOLL_Upper (股价短线过热抛压点)")

        with sell_tabs[1]: # 右侧卖出
            sc3, sc4 = st.columns(2)
            with sc3:
                sell_ma = st.checkbox("🏃 收盘价跌破生命线", value=True)
                if sell_ma:
                    sell_ma_col = st.selectbox("收盘价小于", ["MA_5", "MA_10", "MA_20", "MA_60", "MA_120", "MA_250"], index=1)
                    
                sell_ma_bear = st.checkbox("🏃 经典空头排列压制", value=False)
                if sell_ma_bear:
                    st.caption("极度危险提示: 均线被压制 (MA5<10<20<60)，大势已去")
            with sc4:
                sell_macd = st.checkbox("🏃 MACD 动能衰竭", value=False)
                if sell_macd:
                    sell_macd_val = st.number_input("MACD 柱子跌破", value=0.0)
                    
                sell_macd_dc = st.checkbox("🏃 MACD 死叉 (后知后觉信号)", value=False)
        
    st.markdown("---")
    st.markdown("### 5. 高阶自定义代码引擎 (第二轨 · DeepSeek 特权赋能)")
    st.caption("这里是留给硬核玩家的绝对自由之地。更棒的是，您现在可以直接让 AI 为您写代码！如果填写，将与第一轨取**交集 (AND)**。")
    
    col_ai_1, col_ai_2 = st.columns([5, 1])
    with col_ai_1:
        ai_prompt = st.text_input("💬 AI 策略翻译助手 (让 DeepSeek 帮你写表达式)", placeholder="例如：找那些刚放完天量（换手ZScore>2），且最近三年PE分位在20以下的超跌股。")
    with col_ai_2:
        st.write("")
        st.write("")
        if st.button("✨ 一键魔法生成", use_container_width=True):
            if ai_prompt:
                with st.spinner("🤖 DeepSeek 大脑全速运转中，为您编写量化逻辑..."):
                    from openai import OpenAI
                    try:
                        API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
                        BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
                        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
                        
                        sys_prompt = f"""
                        你是一位顶尖的量化工程师。用户正在使用 Pandas `df.eval()` 语法筛选 A 股数据。
                        可用特征字段 (严格遵守大小写和下划线)：
                        - 价格体系: Open_Qfq, High_Qfq, Low_Qfq, Close_Qfq
                        - 均线与乖离: MA_5 到 MA_250, BIAS_6, BIAS_12, BIAS_20, BIAS_60
                        - MACD: MACD, MACD_Signal, MACD_Hist, MACD_Golden_Cross (预先算好的Boolean), MACD_Dead_Cross
                        - 通道震荡: RSI_14, KDJ_K, KDJ_D, KDJ_J, BOLL_Upper, BOLL_Mid, BOLL_Lower
                        - 波动与异动: ATR_14, ATR_Ratio, Turnover_ZScore (今日换手偏离度), Vol_Ratio_5D (5日量比), Vol_Shrink_20D (是否极度缩量地量Boolean), Limit_Up_Count_5 (近5天涨停次数)
                        - 基本面护城河: PE_TTM, PB, PE_Percentile_3Y (近3年市盈率分位百分比0~100)
                        - 财报动能: ROE, NetProfit_YOY (净利润同比%), DeductedNetProfit_YOY (扣非净利润同比%), Revenue_YOY (营收同比%), Debt_Ratio (资产负债率)
                        - 长期动量: Price_Loc_250 (股价历史250天的振幅位置 0~1)
                        
                        请将用户的自然语言“翻译”成纯 Pandas Query 表达式。
                        规则：
                        1. 只输出合法且可以直接跑在 df.eval() 的 Pandas 代码。
                        2. 绝不要输出任何解释，不要包含 Markdown 格式 (如 ```python)。
                        3. 不允许换行。
                        4. 如果用户说了“买入条件”和“卖出条件”，请严格使用 `|||` 作为分隔符。如果没区分，统一当作买入条件，不加 `|||`。
                        
                        用户描述：{ai_prompt}
                        """
                        response = client.chat.completions.create(
                            model="deepseek-chat",
                            messages=[{"role": "user", "content": sys_prompt}],
                            temperature=0.1
                        )
                        res_text = response.choices[0].message.content.strip().replace("`", "")
                        
                        if '|||' in res_text:
                            b, s = res_text.split('|||', 1)
                            st.session_state.custom_buy_key = b.strip()
                            st.session_state.custom_sell_key = s.strip()
                        else:
                            st.session_state.custom_buy_key = res_text.strip()
                        st.rerun()
                    except Exception as e:
                        st.error(f"AI 生成失败，请检查 API 配置: {e}")
            else:
                st.warning("请先在左侧输入您的策略思路！")
                
    # 使用 session_state 来绑定输入框
    custom_buy = st.text_input("注入自定义买入逻辑 (Pandas Expression)", placeholder="例如: RSI_14 < 30 and ATR_Ratio > 0.05", key="custom_buy_key")
    custom_sell = st.text_input("注入自定义卖出逻辑 (Pandas Expression)", placeholder="例如: MACD_Hist < 0", key="custom_sell_key")

    st.markdown("---")
    if st.button("🚀 组合参数，开始专业级回测大炮", type="primary", use_container_width=True):
        st.toast("正在组装策略大循环...", icon="⚡")
        
        # 1. 检查数据文件是否存在
        data_path = f"backtest_data/final_vault/{stock_code}.parquet"
        if not os.path.exists(data_path):
            st.error(f"抱歉，未找到 {stock_code} 的超级数据库缓存。请先在后台运行数据采集脚本。")
            st.stop()
            
        # 2. 从 UI 的 Checkbox 中拼接出 Pandas query 字符串
        buy_conditions = []
        if buy_ma: buy_conditions.append(f"(Close_Qfq > {buy_ma_col})")
        if buy_ma_bull: buy_conditions.append("(MA_5 > MA_10 and MA_10 > MA_20 and MA_20 > MA_60)")
        if buy_bias12: buy_conditions.append(f"(BIAS_12 < {buy_bias12_val})")
        if buy_macd: buy_conditions.append(f"(MACD_Hist > {buy_macd_val})")
        if buy_macd_gc: buy_conditions.append("(MACD_Golden_Cross == True)")
        if buy_kdj: buy_conditions.append(f"(KDJ_J < {buy_kdj_j} and KDJ_K < {buy_kdj_k} and KDJ_D < {buy_kdj_d})")
        if buy_pb: buy_conditions.append(f"(PB < {buy_pb_val})")
        if buy_boll_lower: buy_conditions.append("(Close_Qfq <= BOLL_Lower)")
        if buy_turnover: buy_conditions.append(f"(Turnover_ZScore > {buy_turn_z})")
        if buy_vol_ratio: buy_conditions.append(f"(Vol_Ratio_5D > {buy_vol_ratio_val})")
        if buy_vol_shrink: buy_conditions.append("(Vol_Shrink_20D == True)")
        if buy_limit_down: buy_conditions.append("(Limit_Up_Count_5 == 0)")
        if buy_roe: buy_conditions.append(f"(ROE > {buy_roe_val})")
        if buy_mv: buy_conditions.append(f"(Total_MV >= {buy_mv_val[0] * 100000000} and Total_MV <= {buy_mv_val[1] * 100000000})") # 转换为元
        if buy_pe: buy_conditions.append(f"(PE_Percentile_3Y < {buy_pe_val})")
        if buy_rsi: buy_conditions.append(f"(RSI_14 < {buy_rsi_val})")
        if buy_yoy: buy_conditions.append(f"(NetProfit_YOY > {buy_yoy_val})")
        if buy_deducted_yoy: buy_conditions.append(f"(DeductedNetProfit_YOY > {buy_deducted_yoy_val})")
        if buy_rev_yoy: buy_conditions.append(f"(Revenue_YOY > {buy_rev_yoy_val})")
        if custom_buy.strip(): buy_conditions.append(f"({custom_buy.strip()})")
        
        sell_conditions = []
        if sell_ma: sell_conditions.append(f"(Close_Qfq < {sell_ma_col})")
        if sell_ma_bear: sell_conditions.append("(MA_5 < MA_10 and MA_10 < MA_20 and MA_20 < MA_60)")
        if sell_bias6: sell_conditions.append(f"(BIAS_6 > {sell_bias6_val})")
        if sell_macd: sell_conditions.append(f"(MACD_Hist < {sell_macd_val})")
        if sell_macd_dc: sell_conditions.append("(MACD_Dead_Cross == True)")
        if sell_kdj: sell_conditions.append(f"(KDJ_J > {sell_kdj_j} and KDJ_K > {sell_kdj_k} and KDJ_D > {sell_kdj_d})")
        if sell_rsi: sell_conditions.append(f"(RSI_14 > {sell_rsi_val})")
        if sell_boll: sell_conditions.append("(Close_Qfq >= BOLL_Upper)")
        if custom_sell.strip(): sell_conditions.append(f"({custom_sell.strip()})")
        
        # 3. 生成最终的 eval 语句
        buy_joiner = " and " if "AND" in buy_logic_type else " or "
        sell_joiner = " and " if "AND" in sell_logic_type else " or "
        
        final_buy_logic = buy_joiner.join(buy_conditions) if buy_conditions else "False"
        final_sell_logic = sell_joiner.join(sell_conditions) if sell_conditions else "False"
        
        # 处理可选的刹车参数
        v_sl = stop_loss / 100.0 if stop_loss > 0 else None
        v_tp = take_profit / 100.0 if take_profit > 0 else None
        v_md = int(max_days) if max_days > 0 else None
        
        st.info(f"⚙️ 后台编译的最终买点逻辑: `{final_buy_logic}`")
        st.info(f"⚙️ 后台编译的最终卖点逻辑: `{final_sell_logic}`")
        
        # 跑核心引擎!
        with st.spinner(f"正在驱动十万次级别的逐日矩阵模拟倒推，请耐心等待..."):
            from strategy_runner import StrategyRunner
            
            try:
                runner = StrategyRunner(
                    data_path=data_path,
                    initial_cash=initial_cash,
                    commission=commission,
                    stamp_duty=stamp_duty,
                    slippage=slippage,
                    buy_logic=final_buy_logic,
                    sell_logic=final_sell_logic,
                    stop_loss_pct=v_sl,
                    take_profit_pct=v_tp,
                    max_hold_days=v_md,
                    start_date=start_date,
                    end_date=end_date
                )
                curve_df, trades = runner.run()
                report = runner.generate_report(curve_df)
                
                # 将结果保存到 Session State 中，确保 UI 操作不会导致数据丢失
                st.session_state.backtest_results = {
                    "curve_df": curve_df,
                    "trades": trades,
                    "report": report,
                    "stock_code": stock_code
                }
            except Exception as outer_err:
                st.error(f"引擎执行错误: {outer_err}")

    # ------ 绘制极其华丽的图表与报表区 (独立于按钮状态) ------
    if 'backtest_results' in st.session_state:
        res = st.session_state.backtest_results
        curve_df = res["curve_df"]
        trades = res["trades"]
        report = res["report"]
        bk_stock_code = res["stock_code"]
        
        st.markdown("### 📊 终极战报：复盘全景图")
                
        # 指标墙：拆分为 2 行，每行 3 个格子，给予极其充足的展示空间
        c_row1_1, c_row1_2, c_row1_3 = st.columns(3)
        c_row1_1.metric("初始总资金", f"¥ {report['Initial_Cash']:,.0f}")
        c_row1_2.metric("最终净资产", f"¥ {report['Final_Equity']:,.0f}")
        
        ret_color = "normal" if report['Total_Return'] > 0 else "inverse"
        c_row1_3.metric("策略净收益率", f"{report['Total_Return']*100:.2f}%", delta_color=ret_color)
        
        st.write("") # 行间距
        
        c_row2_1, c_row2_2, c_row2_3 = st.columns(3)
        bench_color = "normal" if report['Benchmark_Return'] > 0 else "inverse"
        c_row2_1.metric("基准收益率 (死拿跑赢大盘)", f"{report['Benchmark_Return']*100:.2f}%", delta_color=bench_color)
        
        c_row2_2.metric("专业胜率", f"{report['Win_Rate']*100:.1f}%", f"{report['Total_Trades_Pairs']} 次交易")
        
        dd_color = "inverse" if report['Max_Drawdown'] < -0.2 else "normal"
        c_row2_3.metric("最大回撤 (极限抗压熔断能力)", f"{report['Max_Drawdown']*100:.2f}%", delta_color=dd_color)
        
        st.markdown("---")
        # 收益明细图表
        st.subheader(f"{bk_stock_code} 资金时序追踪 (2005 - 至今)")
        
        # 计算持仓状态用于背景涂色
        fig = go.Figure()

        # 画资金曲线
        fig.add_trace(go.Scatter(
            x=curve_df['Date'], y=curve_df['Equity'],
            mode='lines',
            name='总净值 (Equity)',
            line=dict(color='orange', width=2)
        ))
        
        # 画现金底座
        fig.add_trace(go.Scatter(
            x=curve_df['Date'], y=curve_df['Cash'],
            mode='none',
            fill='tozeroy',
            fillcolor='rgba(0, 200, 255, 0.1)',
            name='账面现金'
        ))
        
        # 添加买卖点标识
        if trades:
            buy_x = [t['Date'] for t in trades if t['Type']=='BUY']
            buy_y = [curve_df[curve_df['Date']==x]['Equity'].values[0] for x in buy_x]
            
            sell_x = [t['Date'] for t in trades if t['Type']=='SELL']
            sell_y = [curve_df[curve_df['Date']==x]['Equity'].values[0] for x in sell_x]
            
            fig.add_trace(go.Scatter(
                x=buy_x, y=buy_y,
                mode='markers', name='开仓点 (买入)',
                marker=dict(symbol='triangle-up', size=10, color='red')
            ))
            
            fig.add_trace(go.Scatter(
                x=sell_x, y=sell_y,
                mode='markers', name='逃顶/止损点',
                marker=dict(symbol='triangle-down', size=10, color='green')
            ))
        
        fig.update_layout(
            template="plotly_dark",
            hovermode='x unified',
            margin=dict(l=0, r=0, t=30, b=0),
            height=500,
            xaxis=dict(
                rangeselector=dict(
                    buttons=list([
                        dict(count=1, label="1个月", step="month", stepmode="backward"),
                        dict(count=6, label="6个月", step="month", stepmode="backward"),
                        dict(count=1, label="今年以来", step="year", stepmode="todate"),
                        dict(count=1, label="1年", step="year", stepmode="backward"),
                        dict(count=3, label="3年", step="year", stepmode="backward"),
                        dict(step="all", label="全部")
                    ]),
                    bgcolor="#333",
                    activecolor="#f39c12",
                    font=dict(color="white")
                ),
                rangeslider=dict(visible=True),
                type="date"
            )
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # 年度/月度战绩表 (Tear Sheet)
        st.markdown("### 🏆 机构级战报：绝对收益 vs 超额收益")
        use_monthly = st.toggle("🔍 细化到「月度」显示", value=False)
        
        df_tear = report.get("Tear_Sheet_Monthly") if use_monthly else report.get("Tear_Sheet_Yearly")
        
        if df_tear is not None and not df_tear.empty:
            # 将正数标红，负数标绿 (A股习惯)
            st.dataframe(
                df_tear.style.format({
                    "策略净收益": "{:.2%}",
                    "基准天然涨幅": "{:.2%}",
                    "🔥 超额收益 (Alpha)": "{:.2%}",
                    "期间最大回撤": "{:.2%}"
                }).map(lambda val: 'color: #ff4b4b; font-weight: bold' if val > 0 else 'color: #00fa9a' if val < 0 else '', subset=["🔥 超额收益 (Alpha)"]),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("该阶段无有效的对比数据。")
        
        # 流水单
        with st.expander("📝 详细交易履历表 (Trading Logs)", expanded=False):
            if trades:
                trades_df = pd.DataFrame(trades)
                trades_df['Date'] = trades_df['Date'].dt.date
                st.dataframe(trades_df, use_container_width=True)
            else:
                st.caption("回测周期内没有发生任何交易。")
