import streamlit as st
import pandas as pd
import numpy as np
import os
import plotly.express as px
import datetime
from utils import get_db, inject_custom_css, check_authentication, render_sidebar, get_cached_stock_name

st.set_page_config(page_title="全景阅兵场 - 批斗组合策略", layout="wide")
inject_custom_css()
check_authentication()
render_sidebar()

# 页面权限检查 (需要管理后台开启权限)
if st.session_state.get('user_role') != 'admin' and not st.session_state.get('can_backtest'):
    st.error("🚫 您的账户暂无专业回测权限。请联系管理员开启！")
    st.stop()

st.title("🌐 策略全景阅兵场")
st.caption("把一个策略应用到所有的A股核心标库上，看看到底是你的策略厉害，还是当初大盘本身就在暴涨。")

vault_dir = "backtest_data/final_vault"
available_stocks = []
if os.path.exists(vault_dir):
    available_stocks = [f.replace('.parquet', '') for f in os.listdir(vault_dir) if f.endswith('.parquet')]

if not available_stocks:
    st.warning("⚠️ 底层数据库为空，请先运行数据采集抓取脚本！")
    st.stop()
    
# --- 并排控制面板 ---
col_param1, col_param2 = st.columns(2)
with col_param1:
    st.markdown("### 1. 虚拟本金与摩擦成本环境")
    initial_cash = st.number_input("单只股票分配的初始资金 (元)", min_value=10000, value=200000, step=10000)
    
    col_f1, col_f2, col_f3 = st.columns(3)
    slippage = col_f1.number_input("双向滑点 (%)", min_value=0.0, max_value=5.0, value=0.1, step=0.05) / 100.0
    commission = col_f2.number_input("双向佣金 (万分之X)", min_value=0.0, max_value=30.0, value=1.5, step=0.5) / 10000.0
    stamp_duty = col_f3.number_input("印花税 (万分之X)", min_value=0.0, max_value=50.0, value=5.0, step=0.5) / 10000.0

with col_param2:
    st.markdown("### 2. 底层纪律/风控阀门")
    col_sl, col_tp, col_md = st.columns(3)
    stop_loss = col_sl.number_input("触发强制止损 (-%)", min_value=0.0, max_value=50.0, value=8.0, step=1.0)
    take_profit = col_tp.number_input("触发强制止盈 (+%)", min_value=0.0, max_value=200.0, value=0.0)
    max_days = col_md.number_input("最大容忍熬单天数", min_value=0, max_value=500, value=20)

st.markdown("---")
st.markdown("### 2.5 历史时间过滤网 (Time Window)")
col_time1, col_time2 = st.columns(2)
start_date = col_time1.date_input("首战起算日期 (Start Date)", value=datetime.date(2005, 1, 1), min_value=datetime.date(1990, 1, 1), max_value=datetime.date.today())
end_date = col_time2.date_input("终战截止日期 (End Date)", value=datetime.date.today(), min_value=datetime.date(1990, 1, 1), max_value=datetime.date.today())

st.markdown("---")
st.markdown("### 3. 克隆核心策略代码 (Core Engine)")
st.info("💡 请将你在【专业回测舱】中拼接好的最终 Pandas Code 复制到下方执行。如果代码写错引擎将自动熔断跳过。")

col_logic1, col_logic2 = st.columns(2)
with col_logic1:
    buy_logic = st.text_area("🛒 第一轨：买入引擎代码 (支持 eval)", value="Close_Qfq > MA_20", height=120)
with col_logic2:
    sell_logic = st.text_area("🏃 第二轨：逃顶引擎代码 (支持 eval)", value="Close_Qfq < MA_10 or MACD_Dead_Cross == True", height=120)

if st.button("🚀 三军听令 —— 启动十一国联军超算回测！", type="primary", use_container_width=True):
    from strategy_runner import StrategyRunner
    
    v_sl = stop_loss / 100.0 if stop_loss > 0 else None
    v_tp = take_profit / 100.0 if take_profit > 0 else None
    v_md = int(max_days) if max_days > 0 else None
    
    results = []
    
    # 构建酷炫进度条
    progress_bar = st.progress(0, text="正在装药填装引擎矩阵...")
    total_stocks = len(available_stocks)
    
    for i, code in enumerate(available_stocks):
        progress_bar.progress((i) / total_stocks, text=f"量化引擎狂飙中: 正在高频推演主力代码 {code} (进度: {i+1}/{total_stocks}) ...")
        
        data_path = os.path.join(vault_dir, f"{code}.parquet")
        runner = StrategyRunner(
            data_path=data_path,
            initial_cash=initial_cash,
            commission=commission,
            stamp_duty=stamp_duty,
            slippage=slippage,
            buy_logic=buy_logic,
            sell_logic=sell_logic,
            stop_loss_pct=v_sl,
            take_profit_pct=v_tp,
            max_hold_days=v_md,
            start_date=start_date,
            end_date=end_date
        )
        
        try:
            curve_df, trades = runner.run()
            report = runner.generate_report(curve_df)
            
            # 计算对比差值
            ret = report['Total_Return']
            bench = report['Benchmark_Return']
            alpha = ret - bench
            
            results.append({
                "标的代码": code,
                "股票名称": get_cached_stock_name(code),
                "策略绝对收益": ret,
                "被动死拿收益": bench,
                "🔥 超额 Alpha": alpha,
                "战斗胜率": report['Win_Rate'],
                "深渊回撤 (MaxDD)": report['Max_Drawdown'],
                "交易拔枪次数": report['Total_Trades_Pairs'],
                "Tear_Sheet_Monthly": report.get('Tear_Sheet_Monthly'),
                "trades": trades
            })
        except Exception as e:
            st.error(f"⚠️ {code} 回测报错 (可能是因为数据缺陷或该票无可算周期): {e}")
            
    progress_bar.progress(1.0, text="全线轰炸清算完毕！请检阅超级大盘看板。")
    st.balloons()
    
    st.session_state.batch_results = results
    st.session_state.batch_total_stocks = total_stocks

# --- 渲染区 (利用 Session State 防止按钮刷新消失) ---
if 'batch_results' in st.session_state and st.session_state.batch_results:
    results = st.session_state.batch_results
    total_stocks = st.session_state.batch_total_stocks
    
    res_df = pd.DataFrame(results)
    # 根据超额收益排序
    res_df = res_df.sort_values("🔥 超额 Alpha", ascending=False).reset_index(drop=True)
    
    st.markdown(f"### 🚩 终极战报：联军表现及阿尔法榜单")
    
    # DataFrame 展示层格式化
    display_df = res_df.copy()
    if "Tear_Sheet_Monthly" in display_df.columns:
        display_df = display_df.drop(columns=["Tear_Sheet_Monthly"])
    if "trades" in display_df.columns:
        display_df = display_df.drop(columns=["trades"])
        
    for col in ["策略绝对收益", "被动死拿收益", "🔥 超额 Alpha", "战斗胜率", "深渊回撤 (MaxDD)"]:
        display_df[col] = display_df[col].apply(lambda x: f"{x * 100:.2f}%")
        
    def color_profit(val):
        if isinstance(val, str) and "%" in val:
            num = float(val.strip('%'))
            if num > 0:
                return 'color: #ff4b4b; font-weight: bold'
            elif num < 0:
                return 'color: #00fa9a'
        return ''

    st.dataframe(
        display_df.style.map(color_profit, subset=["🔥 超额 Alpha", "策略绝对收益"]),
        use_container_width=True,
        hide_index=True
    )
    
    # 数据可视化
    st.markdown("### 📊 超额收益 (Alpha) 表现雷达扫描图")
    st.caption("高于横穿线心代表策略在个股上跑赢了死拿，低于代表你不仅多交了手续费，还由于乱动倒亏给了这只股票原始收益。")
    
    fig = px.bar(
        res_df, 
        x='股票名称', 
        y='🔥 超额 Alpha',
        color='🔥 超额 Alpha',
        color_continuous_scale=px.colors.diverging.RdYlGn[::-1],
        text=res_df['🔥 超额 Alpha'].apply(lambda x: f"{x*100:.1f}%")
    )
    
    fig.update_layout(
        template="plotly_dark",
        xaxis_title="受阅股票池",
        yaxis_title="超越市场的溢价 (%)",
        coloraxis_showscale=False,
        height=450
    )
    fig.update_traces(textposition='outside')
    st.plotly_chart(fig, use_container_width=True)
    
    # 综合评分卡
    st.markdown("---")
    st.markdown("### 🏆 联盟军团总结评分与系统诊断")
    col_c1, col_c2, col_c3 = st.columns(3)
    win_count = len(res_df[res_df["🔥 超额 Alpha"] > 0])
    win_ratio = win_count / total_stocks if total_stocks > 0 else 0
    median_alpha = res_df["🔥 超额 Alpha"].median()
    
    col_c1.metric("策略全系有效率 (跑赢标的数量)", f"{win_count} / {total_stocks}", f"{win_ratio*100:.1f}% 被征服", delta_color="normal" if win_ratio>0.5 else "inverse")
    col_c3.metric("舰队总执行开火次数", f"{res_df['交易拔枪次数'].sum()} 枪", "过多会加剧双向印花税和滑点的黑洞抽血")
    
    st.markdown("---")
    st.markdown("### 📊 策略时效性：军团月度平均超额收益分布 (Alpha Timing)")
    st.caption("透视策略的宏观适应期与失效期。红柱越高代表您的策略当月在全军中迎来了系统性红利，大爆赚；绿柱向下代表遭遇了全线的集体闷杀。")
    
    heatmap_records = []
    for r in results:
        code = r["标的代码"]
        name = r.get("股票名称", "")
        df_m = r["Tear_Sheet_Monthly"]
        if df_m is not None and not df_m.empty:
            for _, row_m in df_m.iterrows():
                heatmap_records.append({
                    "股票代码": f"{name}({code})",
                    "周期": str(row_m["周期"]),
                    "Alpha": row_m["🔥 超额收益 (Alpha)"]
                })
    
    if heatmap_records:
        hm_df = pd.DataFrame(heatmap_records)
        
        # 方案二：大盘归因法 - 计算每个月的平均超额收益
        mean_alpha_df = hm_df.groupby("周期")['Alpha'].mean().reset_index()
        # 由于 '周期' 格式类似 2015-01，是可以基于字符串排序的
        mean_alpha_df = mean_alpha_df.sort_values("周期").reset_index(drop=True)
        mean_alpha_df['风格'] = mean_alpha_df['Alpha'].apply(lambda x: '群体大爆发 (Alpha>0)' if x > 0 else '群体惨败 (Alpha<0)')
        
        fig_bar = px.bar(
            mean_alpha_df,
            x='周期',
            y='Alpha',
            color='风格',
            color_discrete_map={'群体大爆发 (Alpha>0)': '#ff4b4b', '群体惨败 (Alpha<0)': '#00fa9a'},
            text=mean_alpha_df['Alpha'].apply(lambda x: f"{x*100:.1f}%")
        )
        fig_bar.update_layout(
            template="plotly_dark",
            height=450,
            xaxis_title="时空周期 (年月)",
            yaxis_title="联军平均超额收益率",
            xaxis=dict(type='category', tickangle=-45)
        )
        fig_bar.update_traces(textposition='outside')
        st.plotly_chart(fig_bar, use_container_width=True)
        
        # 为了传给 DeepSeek 做精细化个股诊断，保留完整的时空矩阵
        pivot_df = hm_df.pivot(index="股票代码", columns="周期", values="Alpha").fillna(0)
        sorted_cols = sorted(pivot_df.columns.tolist())
        pivot_df = pivot_df[sorted_cols]
        
        # --- DeepSeek AI 分析师 ---
        st.markdown("### 🤖 DeepSeek 首席量化策略诊断官")
        st.caption("由大模型在后台推演上述全部矩阵的月度回报，通过深层量化归因，为您揭穿策略的伪装周期和真正的宏观胜负手。")
        
        if st.button("✨ 召唤 DeepSeek 撰写宏观归因及终极阅兵报告", type="primary", use_container_width=True):
            with st.spinner("🤖 DeepSeek 首席量化大脑正在分析您的时空矩阵，这需要极高的算力消耗思考，请屏息凝神..."):
                from openai import OpenAI
                try:
                    API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
                    BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
                    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
                    
                    analysis_df = pivot_df.copy()
                    for col in analysis_df.columns:
                        analysis_df[col] = analysis_df[col].apply(lambda x: f"{x*100:.1f}%")
                        
                    csv_data = analysis_df.to_csv()
                    
                    sys_prompt = f"""
                    你是一位顶尖的华尔街量化策略总监。
                    我跑出了一个针对A股11只核心蓝筹/科技股的回测策略。
                    下面是这个策略在个股层面按月度划分的**【超额收益率(Alpha)】**报表。
                    正数表示该月策略战胜了死拿这只股票本身的收益；负数代表策略反而亏给了市场自身的贝塔（乱动被割）。
                    
                    请求：
                    1. 请帮我一眼看穿这个策略的灵魂：它是一个牛市发威的回踩跟风策略？还是一个注定在震荡市来回被绞杀的失败残次品？它的本质特点是什么？
                    2. 请找出至少2个明显的【策略全军出击大爆发的同步时间段】和【全线溃退集大灾难片段】。最好能结合当月的A股历史宏观事件(如果不确定就基于时间猜测可能发生了什么流动性危机或抱团)，给出专业、一针见血的诊断。
                    3. 请你挑出这套组合在这个历史长河里“天生就八字不合”和“完美匹配”的标的，也就是哪些票在矩阵里红绿波浪最好看，哪些被摩擦最严重。大胆假设为什么会有这种差异？是盘子大小？还是庄股属性？
                    4. 语气极其专业，直接给出冷血结论，带点高手的毒舌或冷酷感。排版清晰美观，使用 Markdown。
                    
                    策略月度Alpha表现时空矩阵 (CSV):
                    {csv_data}
                    """
                    response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": sys_prompt}],
                        temperature=0.7
                    )
                    st.session_state.ds_report = response.choices[0].message.content.strip()
                except Exception as e:
                    st.error(f"AI 引擎调用坠毁，请检查环境变量(API_KEY/URL)是否连通: {e}")
                    
        if st.session_state.get('ds_report'):
            st.info("🎯 DeepSeek AI 归因报告输出完成：")
            st.markdown(st.session_state.ds_report)
    
    st.markdown("---")
    st.markdown("### 🔬 单票作战履历下钻 (Drill-down)")
    drilldown_options = [f'{r["股票名称"]}({r["标的代码"]})' for r in results]
    selected_label = st.selectbox("🎯 选择要下钻审视的战车", drilldown_options)
    
    # Extract code from label like "贵州茅台(600519)"
    selected_code = selected_label.split('(')[-1].strip(')')
    selected_detail = next(r for r in results if r['标的代码'] == selected_code)
    selected_name = selected_detail.get('股票名称', selected_code)
    
    tab_m, tab_t = st.tabs([f"📅 {selected_name} 月度收益表 (Monthly Tear Sheet)", f"📝 {selected_name} 详细交易履历表 (Trading Logs)"])
    with tab_m:
        df_m = selected_detail["Tear_Sheet_Monthly"]
        if df_m is not None and not df_m.empty:
            st.dataframe(
                df_m.style.format({
                    "策略净收益": "{:.2%}",
                    "基准天然涨幅": "{:.2%}",
                    "🔥 超额收益 (Alpha)": "{:.2%}",
                    "期间最大回撤": "{:.2%}"
                }).map(lambda val: 'color: #ff4b4b; font-weight: bold' if val > 0 else 'color: #00fa9a' if val < 0 else '', subset=["🔥 超额收益 (Alpha)"]),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("该阶段无有效的月度对比数据。")
    
    with tab_t:
        trades_data = selected_detail["trades"]
        if trades_data:
            trades_df = pd.DataFrame(trades_data)
            trades_df['Date'] = pd.to_datetime(trades_df['Date']).dt.date
            st.dataframe(trades_df, use_container_width=True)
        else:
            st.info("当前时间窗口和选定策略下，回测周期内没有发生任何交易。")
