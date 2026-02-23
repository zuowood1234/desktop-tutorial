import streamlit as st
from utils import inject_custom_css, check_authentication, render_sidebar

st.set_page_config(page_title="策略说明 - AI 智能投顾", layout="wide")
inject_custom_css()
check_authentication()
render_sidebar()

st.title("📖 核心策略体系说明")
st.markdown("本系统集成四大核心策略，分别应对不同的市场环境。您可以根据当前行情风格灵活切换。")

tab_v1, tab_v2, tab_v3, tab_v4 = st.tabs([
    "🤖 V1 综合记分", 
    "🏹 V2 趋势猎手", 
    "🛡️ V3 波段防御者", 
    "🧠 V4 AI 智能体"
])

with tab_v1:
    st.header("🤖 V1: 综合记分 (Composite Score)")
    st.caption("适用场景：全天候 / 震荡偏强 / 需要综合判断")
    st.info("💡 核心逻辑：基于多因子量化模型，通过六大维度对市场进行 0-100 分打分。")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 📊 评分细则 (总分 100)")
        st.write("**1. 趋势 Trend (20分)**：`MA5 > MA10`，短期趋势向上。")
        st.write("**2. 结构 Structure (20分)**：`MA5 > MA10 > MA20`，均线多头排列。")
        st.write("**3. 动能 MACD (15分)**：`MACD > Signal`，动能增强。")
        st.write("**4. 量能 Volume (25分)**：`放量上涨`，量价齐升 (权重最高🔥)。")
        st.write("**5. 情绪 KDJ (10分)**：`K > D`，处于强势区。")
        st.write("**6. 强弱 RSI (10分)**：`50 < RSI < 80`，处于强势区间。")
    
    with c2:
        st.markdown("#### 🚦 交易信号")
        st.success("**买入信号**：总分 **> 60 分** (市场进入强势区，且大概率伴随放量)")
        st.error("**卖出信号**：总分 **< 40 分** (市场转弱，防守为主)")
        st.warning("**观望**：40-60 分 (趋势不明朗)")

with tab_v2:
    st.header("🏹 V2: 趋势猎手 (Trend Hunter)")
    st.caption("适用场景：大牛市 / 主升浪 / 单边趋势 (2025年回测冠军🏆)")
    st.info("💡 核心逻辑：抓大放小，以 MA10 为生命线，不吃鱼头鱼尾，只吃最肥的中段。")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 📥 买入规则 (趋势确立)")
        st.markdown("""
        必须同时满足：
        1. **股价站上 MA5** (`Close > MA5`)：代表短期强势。
        2. **均线金叉向上** (`MA5 > MA10`)：代表中期趋势向上。
        """)
        st.success("信号：**买入**")

    with c2:
        st.markdown("#### 📤 卖出规则 (趋势破坏)")
        st.markdown("""
        满足其中之一即卖出：
        1. **股价跌破 MA10** (`Close < MA10`)：有效跌破生命线，无条件止损/止盈。
        """)
        st.error("信号：**卖出**")
        
    st.markdown("#### 👁️ 观望状态")
    st.write("当股价在 MA5 和 MA10 之间震荡，或均线纠缠不清时，保持 **观望**。")

with tab_v3:
    st.header("🛡️ V3: 波段防御者 (Band Defender)")
    st.caption("适用场景：熊市 / 震荡市 / 暴跌抄底 (胜率之王🎯)")
    st.info("💡 核心逻辑：利用布林带 (Bollinger Bands, N=20, P=2) 的均值回归特性，由恐慌和贪婪驱动交易。")

    st.markdown("#### 📐 指标定义")
    st.latex(r"Middle = MA_{20}")
    st.latex(r"Upper = Middle + 2 \times \sigma")
    st.latex(r"Lower = Middle - 2 \times \sigma")

    col_b1, col_b2 = st.columns(2)
    with col_b1:
        st.markdown("#### 📥 买入逻辑 (贪婪抄底)")
        st.markdown("**条件**：股价触及或跌破下轨 (`Close <= Lower`)")
        st.caption("解读：市场进入非理性恐慌区，价格被低估，预期将回归中轨。")
        st.success("信号：**买入**")
        
    with col_b2:
        st.markdown("#### 📤 卖出逻辑 (恐惧/止损)")
        st.markdown("**条件 1 (止盈)**：股价触及上轨 (`Close >= Upper`)")
        st.caption("解读：市场进入狂热区，预期回调。")
        st.markdown("**条件 2 (防守)**：股价跌破中轨 (`Close < Middle`)")
        st.caption("解读：上升趋势结束，转为下跌趋势。")
        st.error("信号：**卖出**")
        
    st.markdown("#### 👁️ 观望状态")
    st.write("当股价在 **布林通道内部** (Lower < Close < Upper) 运行时，视为正常波动，**观望** 不操作。")

with tab_v4:
    st.header("🧠 V4: AI 智能体 (AI Agent)")
    st.caption("适用场景：复杂博弈 / 需要通过自然语言分析 / 捕捉非线性逻辑")
    st.info("💡 核心逻辑：利用大语言模型 (LLM) 的推理能力，将量化数据转化为自然语言 Prompt，模拟人类交易员的思考过程。")

    st.markdown("#### 🧬 真实 Prompt 模板")
    st.write("系统将每一日的行情数据填入以下模板，发送给 DeepSeek/GPT 进行推演：")
    
    st.code("""
你是一个资深的股票分析师，现在的行情数据是：
- 股票代码: {stock_code}
- 日期: {date}
- 开盘价: {open}
- 最高价: {high}
- 最低价: {low}
- 收盘价: {close} (涨幅 {pct_chg}%)
- 均线数据: MA5={ma5}, MA10={ma10}, MA20={ma20}
- 成交量: {volume}
- 技术指标: KDJ(K={k}, D={d}), RSI={rsi}

请根据这些数据，结合市场情绪与资金，板块热点判断未来走势，并给出操作建议（买入/卖出/观望）。
返回格式要求：必须包含“操作建议：买入”或“操作建议：卖出”或“操作建议：观望”这几个字。
    """, language="markdown")
    
    col_ai1, col_ai2 = st.columns(2)
    with col_ai1:
        st.markdown("#### ✅ 优势")
        st.write("- 能综合多个矛盾指标得出结论。")
        st.write("- 能理解“放量滞涨”、“缩量回调”等复杂形态。")
    
    with col_ai2:
        st.markdown("#### ⚠️ 注意")
        st.write("- 依赖 API 稳定性。")
        st.write("- 不同的 AI 模型 (DeepSeek vs GPT) 风格不同。")
