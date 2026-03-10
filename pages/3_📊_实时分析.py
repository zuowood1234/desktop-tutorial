import streamlit as st
import pandas as pd
import time
import re
import os
from utils import get_db, get_cached_stock_name, inject_custom_css, check_authentication, render_sidebar
from main import get_market_status, get_stock_data
from backtest_engine import BacktestEngine

st.set_page_config(page_title="实时分析 - AI 智能投顾", layout="wide")
inject_custom_css()
check_authentication()
render_sidebar()

db = get_db()

st.title("📊 AI 实时分析 (V1-V4 全策略扫描)")

# 市场状态卡片
status_text, is_trading = get_market_status()
st.sidebar.markdown("---")
st.sidebar.markdown(f"**当前行情状态:**")
st.sidebar.info(status_text)

# 在主界面也显示状态，增加仪式感
col_s1, col_s2 = st.columns([2, 1])
with col_s1:
    if is_trading:
        st.success(f"🌐 系统已接入实时数据流 (新浪/东财) | 状态: {status_text}")
    else:
        st.warning(f"🕒 当前非交易时段 ({status_text}) | 使用最近交易日数据")
        
# 获取用户自选作为快捷选项
watchlist_df = db.get_user_watchlist(st.session_state.user_id)
tags = db.get_tags(st.session_state.user_id)

# 1. 选择来源
analysis_mode = st.radio("数据来源", ["从我的自选加载", "手动输入代码"], horizontal=True, key="realtime_source")

selected_stocks = []

if analysis_mode == "从我的自选加载":
    if not watchlist_df.empty:
        col_filter, col_all = st.columns([3, 1])
        with col_filter:
            selected_tags = st.multiselect("按标签筛选 (不选则分析全部)", tags)
        
        if selected_tags:
            selected_stocks = watchlist_df[watchlist_df['tag'].isin(selected_tags)]['stock_code'].tolist()
        else:
            selected_stocks = watchlist_df['stock_code'].tolist()
        
        st.info(f"已选中 {len(selected_stocks)} 只自选股: {', '.join(selected_stocks)}")
    else:
        st.warning("自选列表为空，请先前往 [⭐ 我的自选] 添加。")
else:
    # 股票手动输入
    stocks_input = st.text_area(
        "手动输入代码（逗号或换行分隔）", 
        placeholder="例如：600519\n或：600519, 601318, 000001",
        height=100
    )
    if stocks_input:
        selected_stocks = [s.strip() for s in re.split(r'[,，\n]', stocks_input) if s.strip()]

# 分析流程逻辑
col1, col2 = st.columns(2)
with col1:
    btn_quick = st.button("⚡ 快速扫描 (仅 V1-V3)", use_container_width=True, help="仅计算数学模型，速度快，无API消耗")
with col2:
    btn_full = st.button("🧠 全策略分析 (含 AI)", use_container_width=True, type="primary")

if btn_quick or btn_full:
    if not selected_stocks:
        st.error("⚠️ 请先选中要分析的股票（来自自选或手动输入）")
    else:
        mode_text = "全策略 (含AI)" if btn_full else "快速扫描 (V1-V3)"
        st.markdown("---")
        st.subheader(f"📋 正在对 {len(selected_stocks)} 只股票进行 {mode_text}...")
        progress_bar = st.progress(0)
        
        new_results = []
        for i, stock in enumerate(selected_stocks):
            with st.spinner(f"正在分析 {stock} ..."):
                try:
                    # 获取数据
                    df, error = get_stock_data(stock)
                    
                    if df is not None and not df.empty:
                        stock_name = get_cached_stock_name(stock)
                        
                        # === 数据列名适配 (中文 -> 英文) ===
                        # BacktestEngine 需要英文列名来计算指标
                        # 注意：get_stock_data 返回的可能是中文列名
                        rename_map = {
                            '日期': 'date', '收盘': 'close', '开盘': 'open',
                            '最高': 'high', '最低': 'low', '成交量': 'volume',
                            '涨跌幅': 'pctChg', '换手率': 'turn'
                        }
                        # 仅重命名存在的列
                        df = df.rename(columns=rename_map)
                        
                        # 容错：如果还是没有 close，尝试查找 Close
                        if 'close' not in df.columns:
                            # 尝试查找大小写不敏感匹配
                            for col in df.columns:
                                if col.lower() == 'close':
                                    df = df.rename(columns={col: 'close'})
                                elif col.lower() == 'volume':
                                    df = df.rename(columns={col: 'volume'})
                        
                        # 终极检查
                        if 'close' not in df.columns:
                            raise ValueError(f"数据缺少 'close' 列，当前列名: {df.columns.tolist()}")

                        # 确保 volume 是数值型
                        if 'volume' in df.columns:
                            df['volume'] = pd.to_numeric(df['volume'], errors='coerce').fillna(0)
                        if 'close' in df.columns:
                            df['close'] = pd.to_numeric(df['close'], errors='coerce')
                            
                        # === 核心调用 ===
                        engine = BacktestEngine(stock)
                        engine.df = df # 注入清洗后的数据
                        engine._calculate_indicators() 
                        
                        latest_row = df.iloc[-1]
                        prev_row = df.iloc[-2] if len(df) > 1 else None
                        
                        # 一次性获取所有策略结果
                        v1_act, v1_rsn, v1_scr = engine.make_decision(latest_row, prev_row, 'Score_V1')
                        v2_act, v2_rsn, v2_scr = engine.make_decision(latest_row, prev_row, 'Trend_V2')
                        v3_act, v3_rsn, v3_scr = engine.make_decision(latest_row, prev_row, 'Oscillation_V3')
                        
                        # V4: 根据按钮决定
                        if btn_full:
                            v4_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
                            v4_act, v4_rsn, v4_scr = engine.make_decision(latest_row, prev_row, 'AI_Agent_V4', api_key=v4_key)
                        else:
                            v4_act = "未启用"
                            v4_rsn = "快速扫描模式跳过 AI 分析"
                            v4_scr = 0
                        
                        # --- 以下是修正：获取绝对实时的涨跌幅和价格 ---
                        try:
                            # 单取该票的最新高频快照
                            df_spot = ak.stock_zh_a_spot_em()
                            spot_data = df_spot[df_spot['代码'] == stock].iloc[0]
                            latest_price = float(spot_data['最新价'])
                            pct_chg = float(spot_data['涨跌幅'])
                            real_time_tag = " (实时)"
                        except Exception as e:
                            # 降级：如果高频接口卡壳，依然用刚才日线拿到的最新价
                            latest_price = latest_row['close']
                            pct_chg = latest_row['pctChg'] if 'pctChg' in latest_row else 0
                            real_time_tag = ""
                        
                        new_results.append({
                            "代码": stock,
                            "名称": stock_name,
                            "价格": f"¥{latest_price:.2f}",
                            "涨跌": f"{pct_chg:.2f}%{real_time_tag}",
                            "时间": str(latest_row['date']),
                            
                            # V1 综合记分
                            "V1建议": v1_act, "V1评分": v1_scr, "V1理由": v1_rsn,
                            # V2 趋势猎手
                            "V2建议": v2_act, "V2评分": v2_scr, "V2理由": v2_rsn,
                            # V3 波段防御
                            "V3建议": v3_act, "V3评分": v3_scr, "V3理由": v3_rsn,
                            # V4 AI智能体
                            "V4建议": v4_act, "V4评分": v4_scr, "V4理由": v4_rsn,
                        })
                    else:
                        st.error(f"无法获取股票 {stock} 的行情数据 (df is empty or None)。Error info: {error}")
                except Exception as e:
                    import traceback
                    err_msg = traceback.format_exc()
                    st.error(f"分析股票 {stock} 遭遇严重错误:\n\n{err_msg}")
                    if 'df' in locals() and df is not None:
                        with st.expander("点击查看出错时的数据快照"):
                            st.write("Columns:", df.columns.tolist())
                            st.dataframe(df.head())
            progress_bar.progress((i + 1) / len(selected_stocks))
        
        # 只有当成功获取到结果时才刷新
        if new_results:
            st.session_state.last_analysis_results = new_results
            st.success(f"🎉 分析完成！共 {len(new_results)} 只股票成功。")
            time.sleep(1) # 给用户一点时间看成功提示
            st.rerun() 
        else:
            st.error("❌ 所有股票分析均失败，请检查上方报错信息。")
            # 不执行 rerun，保留报错信息在屏幕上

# --- 渲染分析结果 (如果存在) ---
if st.session_state.get('last_analysis_results'):
    results = st.session_state.last_analysis_results
    
    col_title, col_clear = st.columns([5, 1])
    col_title.markdown("### 📊 分析结果汇总")
    if col_clear.button("🗑️ 清除结果"):
        st.session_state.last_analysis_results = None
        st.rerun()

    if results:
        res_df = pd.DataFrame(results)
        
        # 简单表格展示 (只展示建议，表头中文化)
        display_cols = ['代码', '名称', '价格', '涨跌', 'V1建议', 'V2建议', 'V3建议', 'V4建议']
        display_df = res_df[display_cols].copy()
        display_df.columns = ['代码', '名称', '价格', '涨跌', 'V1综合记分', 'V2趋势猎手', 'V3波段防御', 'V4智能体']
        
        st.dataframe(
            display_df,
            use_container_width=True
        )
        
        st.markdown("---")
        st.subheader("🔍 深度拆解 (点击展开详情)")
        
        for res in results:
            # 标题颜色：如果任一策略建议买入，标题高亮
            is_buy = any("买" in str(res[k]) for k in ['V1建议', 'V2建议', 'V3建议', 'V4建议'])
            icon = "🔥" if is_buy else "📄"
            
            stock_label = f"{icon} **{res['名称']} ({res['代码']})** | {res['价格']} ({res['涨跌']})"
            
            # 默认全部折叠 (expanded=False)，保持界面清爽
            with st.expander(stock_label, expanded=False):
                
                # 使用 Tabs 展示四个策略
                t1, t2, t3, t4 = st.tabs(["🤖 V1 综合记分", "🏹 V2 趋势猎手", "🛡️ V3 波段防御", "🧠 V4 AI智能体"])
                
                with t1:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.metric("V1 建议", res['V1建议'])
                        st.progress(res['V1评分']/100, text=f"评分: {res['V1评分']}")
                    with c2:
                        st.info(f"**分析逻辑**: {res['V1理由']}")
                        
                with t2:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.metric("V2 建议", res['V2建议'])
                        st.progress(res['V2评分']/100, text=f"评分: {res['V2评分']}")
                    with c2:
                        st.info(f"**分析逻辑**: {res['V2理由']}")
                        
                with t3:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        st.metric("V3 建议", res['V3建议'])
                        st.progress(res['V3评分']/100, text=f"评分: {res['V3评分']}")
                    with c2:
                        st.info(f"**分析逻辑**: {res['V3理由']}")
                        
                with t4:
                    c1, c2 = st.columns([1, 2])
                    with c1:
                        if "API" in str(res['V4建议']):
                            st.warning(f"⚠️ {res['V4建议']}")
                        else:
                            st.metric("V4 建议", res['V4建议'])
                    with c2:
                        st.markdown("### 🧠 AI 分析逻辑")
                        st.markdown(res['V4理由'])

        # 下载按钮
        csv = res_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 下载分析报告 (CSV)",
            data=csv,
            file_name=f"strategy_analysis_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    else:
        st.info("暂无结果")
