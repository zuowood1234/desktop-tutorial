import streamlit as st
import pandas as pd
import os
from utils import inject_custom_css, check_authentication, render_sidebar

st.set_page_config(page_title="条件雷达选股 - AI 智能投顾", layout="wide")
inject_custom_css()
check_authentication()
render_sidebar()

st.title("🎯 雷达条件选股引擎")
st.caption("从全市场截面数据中，瞬间筛选出符合您量价、形态及基本面逻辑的个股。")

SCANNER_FILE = "backtest_data/today_scanner.parquet"

if not os.path.exists(SCANNER_FILE):
    st.warning("⚠️ 尚未生成今日的全市场快照数据。请在后台运行 `python build_scanner_data.py`。\n (当前可能正在后台火速生成中，请耐心等待数十秒后刷新...)")
    st.stop()

# 载入数据并放入 Cache
@st.cache_data(ttl=600)  # 10分钟刷新一次缓存
def load_scanner_data():
    return pd.read_parquet(SCANNER_FILE)

df = load_scanner_data()
data_date = str(df['Date'].max()) if 'Date' in df.columns else '最新'
st.success(f"✅ 成功加载横截面数据快照！当前标的池总量: **{len(df)}** 只股票 (最新数据日期: {data_date})")

# --------- UI 过滤条件 (移植回测舱买入逻辑) ---------
st.markdown("### 1. 扫描条件配置")

buy_logic_type = st.radio("条件组合逻辑：", ["AND (必须同时满足所有勾选条件, 推荐)", "OR (只要满足其中任意一个条件即可)"], horizontal=True)
st.markdown("---")

buy_tabs = st.tabs(["👈 左侧深水区 (超跌/背离)", "👉 右侧主升浪 (动能/突破)", "🏢 基本面验证 (估值护城河)"])

with buy_tabs[0]: 
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
            st.caption("提示: 当前成交量严重萎缩至过去20日均量的一半以下")
            
        buy_limit_down = st.checkbox("🚩 抄底避险防火墙", value=False)
        if buy_limit_down:
            st.caption("提示: 近5日内无跌停，防止接飞刀")

with buy_tabs[1]: 
    bc3, bc4 = st.columns(2)
    with bc3:
        buy_ma = st.checkbox("🚩 收盘价站上均线", value=False)
        if buy_ma:
            buy_ma_col = st.selectbox("当前价需大于", ["MA_5", "MA_10", "MA_20", "MA_60", "MA_120", "MA_250"], index=2)
            
        buy_ma_bull = st.checkbox("🚩 经典多头排列", value=False)
        if buy_ma_bull:
            st.caption("提示: 短期到长期均线依次发散 (MA5>10>20>60)")
            
        buy_macd = st.checkbox("🚩 MACD上升动能", value=False)
        if buy_macd:
            buy_macd_val = st.number_input("MACD 柱子大于", value=0.0)
            
        buy_macd_gc = st.checkbox("🚩 MACD 今日底背离金叉", value=False)
    with bc4:
        buy_turnover = st.checkbox("🚩 换手率爆发", value=False)
        if buy_turnover:
            buy_turn_z = st.slider("换手Z-Score高于均值倍数", 0.0, 5.0, 1.5, 0.1)
            
        buy_vol_ratio = st.checkbox("🚩 右侧放量进攻", value=False)
        if buy_vol_ratio:
            buy_vol_ratio_val = st.slider("5日量比大于", 1.0, 10.0, 2.0, 0.5)

        buy_limit_up_count = st.checkbox("🚩 资金拉板做活(连板基因)", value=False)
        if buy_limit_up_count:
            limit_up_period = st.radio("拉板统计周期", ["5日内", "10日内"], horizontal=True)
            limit_up_min = st.slider("至少包含涨停次数", 1, 5, 2, 1)
            
        buy_seal_ratio = st.checkbox("🚩 封单动能强度(要求硬板)", value=False)
        if buy_seal_ratio:
            seal_ratio_min = st.slider("虚拟封成估值不低于", 0.0, 5.0, 1.0, 0.5)

with buy_tabs[2]: 
    bc5, bc6 = st.columns(2)
    with bc5:
        buy_mv = st.checkbox("🚩 市值偏好", value=False)
        if buy_mv:
            buy_mv_val = st.slider("总市值区间(亿元)", 0, 20000, (0, 500), 10)
            
        buy_pe = st.checkbox("🚩 实时市盈率 (PE TTM)", value=False)
        if buy_pe:
            buy_pe_val = st.slider("PE_TTM 低于", 0.0, 300.0, 30.0, 5.0)
            
        buy_pb = st.checkbox("🚩 市净率 (PB)", value=False)
        if buy_pb:
            buy_pb_val = st.slider("PB 低于", 0.0, 10.0, 3.0, 0.5)

st.markdown("---")
st.markdown("### 2. 高阶 AI 代码注入引擎")
st.caption("与上述所选条件求 **交集 (AND)**")

col_ai_1, col_ai_2 = st.columns([5, 1])
with col_ai_1:
    ai_prompt = st.text_input("💬 让 DeepSeek 帮你写额外的筛选 Pandas 表达式:", placeholder="例如：找MACD红柱，且股价站在60日均线上的股票。")
with col_ai_2:
    st.write("")
    st.write("")
    if st.button("✨ AI 魔法生成", use_container_width=True):
        if ai_prompt:
            with st.spinner("🤖 DeepSeek 大脑全速运转中，为您编写量化逻辑..."):
                from openai import OpenAI
                try:
                    API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
                    BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
                    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
                    
                    sys_prompt = f"""
                    你是一位顶尖的量化工程师。用户正在针对 5000 只 A股的横截面快表 df 进行选股过滤。
                    需要你输出 `df.eval(或 df.query)` 兼容的 Pandas 查询字符串。
                    字段：
                    Close_Qfq, Open_Qfq, High_Qfq, Low_Qfq, Volume, Turnover, Turnover_Rate
                    MA_5, MA_10, MA_20, MA_60, MA_120, MA_250
                    BIAS_6, BIAS_12, BIAS_20, BIAS_60
                    MACD, MACD_Signal, MACD_Hist, MACD_Golden_Cross (Boolean)
                    RSI_14, KDJ_K, KDJ_D, KDJ_J, BOLL_Upper, BOLL_Mid, BOLL_Lower, ATR_14, ATR_Ratio
                    Turnover_ZScore, Vol_Ratio_5D, Vol_Shrink_20D (Boolean)
                    Limit_Up_Count_5, Limit_Up_Count_10, Limit_Down_Count_5, Limit_Up_Seal_Ratio
                    PE_TTM, PB, Total_MV (单位：元)
                    
                    规则: 
                    1. 仅输出最终代码字符串，不需要任何Markdown。
                    用户需求: {ai_prompt}
                    """
                    response = client.chat.completions.create(
                        model="deepseek-chat",
                        messages=[{"role": "user", "content": sys_prompt}],
                        temperature=0.1
                    )
                    res_text = response.choices[0].message.content.strip().replace("`", "")
                    st.session_state.custom_scanner_key = res_text.strip()
                    st.rerun()
                except Exception as e:
                    st.error(f"AI 生成失败: {e}")

custom_query = st.text_input("自定义 Pandas Query 逻辑", key="custom_scanner_key")

st.markdown("---")
# ================= 构建 Query ==================
if st.button("🚀 启动全市场雷达扫描 (毫秒级)", type="primary", use_container_width=True):
    conditions = []
    
    if buy_ma: conditions.append(f"(Close_Qfq > {buy_ma_col})")
    if buy_ma_bull: conditions.append("(MA_5 > MA_10 and MA_10 > MA_20 and MA_20 > MA_60)")
    if buy_bias12: conditions.append(f"(BIAS_12 < {buy_bias12_val})")
    if buy_macd: conditions.append(f"(MACD_Hist > {buy_macd_val})")
    if buy_macd_gc: conditions.append("(MACD_Golden_Cross == True)")
    if buy_kdj: conditions.append(f"(KDJ_J < {buy_kdj_j} and KDJ_K < {buy_kdj_k} and KDJ_D < {buy_kdj_d})")
    if buy_pb: conditions.append(f"(PB < {buy_pb_val})")
    if buy_boll_lower: conditions.append("(Close_Qfq <= BOLL_Lower)")
    if buy_turnover: conditions.append(f"(Turnover_ZScore > {buy_turn_z})")
    if buy_vol_ratio: conditions.append(f"(Vol_Ratio_5D > {buy_vol_ratio_val})")
    if buy_vol_shrink: conditions.append("(Vol_Shrink_20D == True)")
    if buy_limit_down: conditions.append("(Limit_Down_Count_5 == 0)")
    if buy_limit_up_count: 
        col_lk = "Limit_Up_Count_5" if limit_up_period == "5日内" else "Limit_Up_Count_10"
        conditions.append(f"({col_lk} >= {limit_up_min})")
    if buy_seal_ratio: conditions.append(f"(Limit_Up_Seal_Ratio >= {seal_ratio_min})")
    
    if buy_mv: 
        conditions.append(f"(Total_MV >= {buy_mv_val[0] * 100000000} and Total_MV <= {buy_mv_val[1] * 100000000})")
    if buy_pe: 
        conditions.append(f"(PE_TTM > 0 and PE_TTM < {buy_pe_val})")
    if buy_rsi: 
        conditions.append(f"(RSI_14 < {buy_rsi_val})")
        
    joiner = " and " if "AND" in buy_logic_type else " or "
    final_query_str = joiner.join(conditions) if conditions else ""
    
    if custom_query.strip():
        if final_query_str:
            final_query_str = f"({final_query_str}) and ({custom_query.strip()})"
        else:
            final_query_str = custom_query.strip()
            
    st.info(f"⚙️ 最终执行的引擎逻辑: `{final_query_str if final_query_str else '无条件过滤 (全盘)'}`")
    
    with st.spinner("⚡ 正在内存中急速碰撞运算..."):
        try:
            res_df = df.copy()
            if final_query_str:
                res_df = res_df.query(final_query_str)
            
            st.session_state.scanner_results = res_df
            st.toast(f"扫描完毕！找到 {len(res_df)} 只匹配标的", icon="🎯")
        except Exception as e:
            st.error(f"⚠️ 解析引擎语法错误，请检查您的组合逻辑: {str(e)}")


# 结果展示
if 'scanner_results' in st.session_state:
    res_df = st.session_state.scanner_results
    st.markdown("### 🏆 猎手寻源结果榜单")
    
    if res_df.empty:
        st.warning("😭 当前设定要求太高了，全市场没有一只股票符合条件！请放宽筛选力度试一试。")
    else:
        st.metric("筛选命中数量", f"{len(res_df)}只", f"占全池比例 {(len(res_df)/len(df))*100:.1f}%", delta_color="off")
        
        # 挑选人们最关注的字段做前端展示
        display_cols = ['Code', 'Stock_Name', 'Close_Raw', 'Pct_Chg_Raw', 'Turnover_Rate', 'Limit_Up_Count_5', 'MACD_Hist', 'PE_TTM', 'Total_MV']
        # 容错提取
        d_cols = [c for c in display_cols if c in res_df.columns]
        
        show_df = res_df[d_cols].copy()
        show_df = show_df.rename(columns={
            'Code': '股票代码', 'Stock_Name': '名称', 'Close_Raw': '现价', 'Pct_Chg_Raw': '今日涨幅(%)',
            'Turnover_Rate': '换手率(%)', 'Limit_Up_Count_5': '近5日涨停数', 'MACD_Hist': 'MACD柱', 
            'PE_TTM': '动态市盈率', 'Total_MV': '总市值'
        })
        
        if '总市值' in show_df.columns:
            show_df['总市值'] = (show_df['总市值'] / 100000000).apply(lambda x: f"{x:.2f}亿" if pd.notna(x) else "未知")
            
        def color_rule(val):
            if isinstance(val, (int, float)):
                if val > 0: return 'color: #ff4b4b; font-weight: bold'
                if val < 0: return 'color: #00fa9a'
            return ''
            
        if '今日涨幅(%)' in show_df.columns:
            st.dataframe(
                show_df.style.map(color_rule, subset=['今日涨幅(%)', 'MACD柱']).format({'今日涨幅(%)': '{:.2f}', '现价': '{:.2f}'}),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.dataframe(show_df, use_container_width=True, hide_index=True)
            
        # Add to watchlist feature could be implemented here...
        csv = res_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 导出完整指标宽表 (CSV)",
            data=csv,
            file_name=f"screener_hits_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
