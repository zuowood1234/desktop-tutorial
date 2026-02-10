import streamlit as st
import time
import pandas as pd
import plotly.graph_objects as go
from main import get_stock_data, analyze_with_deepseek, get_stock_name

from stock_names import get_stock_name_offline
from database import DBManager
import os
import glob
import re

# 初始化数据库 (使用 cache_resource 缓存连接池，避免每次刷新重连)
@st.cache_resource
def get_db():
    return DBManager()

db = get_db()

# 设置网页
st.set_page_config(page_title="AI 智能投顾", layout="wide", initial_sidebar_state="expanded")

# --- 认证逻辑 ---
if 'last_analysis_results' not in st.session_state:
    st.session_state.last_analysis_results = None
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
    st.session_state.user_role = 'user'

# 如果未登录，展示登录/注册界面
if st.session_state.user_id is None:
    st.title("🔐 AI 智能投顾 - 请登录")
    
    auth_tab1, auth_tab2 = st.tabs(["用户登录", "新用户注册"])
    
    with auth_tab1:
        with st.form("login_form"):
            l_user = st.text_input("用户名")
            l_pw = st.text_input("密码", type="password")
            submitted = st.form_submit_button("立即登录")
            if submitted:
                user_data = db.login_user(l_user, l_pw)
                if user_data == "disabled":
                    st.error("🚫 您的账号已被管理员禁用，请联系管理员。")
                elif user_data:
                    st.session_state.user_id = user_data['uid']
                    st.session_state.username = user_data['username']
                    st.session_state.user_role = user_data['role']
                    st.session_state.can_backtest = user_data.get('can_backtest', False)
                    st.success(f"欢迎回来, {l_user}!")
                    st.rerun()
                else:
                    st.error("用户名或密码错误")
                    
    with auth_tab2:
        with st.form("reg_form"):
            r_user = st.text_input("设置用户名")
            r_email = st.text_input("电子邮箱")
            r_pw = st.text_input("设置密码", type="password")
            r_pw_conf = st.text_input("确认密码", type="password")
            st.info("💡 提示：用户名为 'admin' 将自动获得管理权限")
            reg_submitted = st.form_submit_button("注册账号")
            if reg_submitted:
                email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
                if not re.match(email_regex, r_email):
                    st.error("请输入有效的邮箱地址")
                elif r_pw != r_pw_conf:
                    st.error("两次密码输入不一致")
                elif len(r_pw) < 6:
                    st.error("密码长度至少6位")
                else:
                    # 如果用户名为admin，则设为管理员
                    role = 'admin' if r_user.lower() == 'admin' else 'user'
                    success, msg = db.register_user(r_user, r_email, r_pw, role)
                    if success:
                        st.success("注册成功！请切换到登录页。")
                    else:
                        st.error(msg)
    st.stop()

# 全局样式 - 统一字号
st.markdown("""
<style>
    /* 统一正文字号 */
    .stMarkdown, .stText, p, div, span, label {
        font-size: 16px !important;
    }
    
    /* 大标题 */
    h1 {
        font-size: 28px !important;
        font-weight: 600 !important;
    }
    
    /* 副标题 */
    h2, h3 {
        font-size: 20px !important;
        font-weight: 600 !important;
    }
    
    /* Metric标签 */
    [data-testid="stMetricLabel"] {
        font-size: 16px !important;
    }
    
    /* Metric数值 */
    [data-testid="stMetricValue"] {
        font-size: 20px !important;
    }
    
    /* 按钮文字 */
    button {
        font-size: 16px !important;
    }
    
    /* 输入框文字 */
    input, textarea {
        font-size: 16px !important;
    }
    
    /* 表格文字 */
    table {
        font-size: 16px !important;
    }
    
    /* 进度条文字 */
    .stProgress > div > div {
        font-size: 14px !important;
    }
    
    /* Expander标题 */
    .streamlit-expanderHeader {
        font-size: 16px !important;
    }
    
    /* 隐藏顶部工具栏和页脚 */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
    .stAppDeployButton {display:none;}
</style>
""", unsafe_allow_html=True)

# 侧边栏导航
st.sidebar.title(f"👤 {st.session_state.username}")
if st.session_state.user_role == 'admin':
    st.sidebar.info("🔱 管理员模式")

nav_options = ["📊 实时分析", "📅 每日建议", "⭐ 我的自选", "📈 历史回测", "📖 策略说明"]
if st.session_state.user_role == 'admin':
    nav_options.append("👑 管理后台")

page = st.sidebar.radio(
    "",
    nav_options,
    label_visibility="collapsed"
)

if st.sidebar.button("🚪 退出登录"):
    st.session_state.user_id = None
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("💡 Powered by DeepSeek AI")

# ==================== 页面5：管理后台 (管理员专用) ====================
if page == "👑 管理后台":
    st.title("👑 系统管理后台")
    st.markdown("您可以查看所有注册用户的信息及其权限状况。")
    
    users_df = db.get_all_users()
    if not users_df.empty:
        # 为了美观，使用列展示
        c_m1, c_m2 = st.columns([1, 1])
        c_m1.metric("👥 总注册用户", len(users_df))
        with c_m2:
            st.write("⚙️ 自动化任务")
            if st.button("🔄 立即运行每日自动分析 (全量)", use_container_width=True):
                with st.spinner("正在后台执行全量自选股分析，请勿离开..."):
                    from auto_daily_analysis import run_auto_daily_analysis
                    run_auto_daily_analysis()
                    st.success("✅ 每日任务执行成功！所有用户的自选股已更新建议。")
                    
        st.markdown("---")
        
        # 表头
        h1, h2, h3, h4, h5, h6, h7 = st.columns([0.8, 1.2, 1.8, 1, 1, 1, 1])
        h1.caption("UID")
        h2.caption("用户名")
        h3.caption("邮箱")
        h4.caption("状态")
        h5.caption("回测")
        h6.caption("Token")
        h7.caption("操作")
        st.divider()
        
        for idx, row in users_df.iterrows():
            with st.container():
                c1, c2, c3, c4, c5, c6, c7 = st.columns([0.8, 1.2, 1.8, 1, 1, 1, 1])
                
                c1.write(f"`{row['uid']}`")
                c2.write(f"**{row['username']}**")
                c3.write(row['email'])
                
                if row['status'] == 'active':
                    c4.markdown("🍏 :green[正常]")
                else:
                    c4.markdown("🍎 :red[禁用]")
                
                is_authed = row['can_backtest'] or row['role'] == 'admin'
                c5.markdown("🔓 :blue[已授权]" if is_authed else "🔒 :gray[未授权]")
                
                # Token 消耗显示
                tokens = row['total_tokens'] if row['total_tokens'] else 0
                c6.markdown(f"🪙 `{tokens:,}`")
                
                # 操作逻辑
                with c7.popover("⚙️"):
                    st.subheader(f"管理: {row['username']}")
                    
                    # 1. 查看自选与建议 (新增需求)
                    if st.button("🔍 查看该用户自选 & 建议", key=f"v_{row['uid']}", use_container_width=True):
                        st.session_state[f"view_user_info_{row['uid']}"] = True
                    
                    if st.session_state.get(f"view_user_info_{row['uid']}", False):
                        st.markdown("---")
                        u_watchlist = db.get_user_watchlist(row['uid'])
                        if u_watchlist.empty:
                            st.caption("该用户暂无自选股")
                        else:
                            st.write("**自选清单:**")
                            st.dataframe(u_watchlist[['stock_code', 'tag']], use_container_width=True)
                            
                        # 获取用户最近的有数据的日期
                        dates_df = db.get_daily_recommendations(row['uid'])
                        if not dates_df.empty:
                            latest_date = dates_df.iloc[0]['date']
                            st.write(f"**最新分析存档 ({latest_date}):**")
                            u_recs = db.get_recommendations_by_date(row['uid'], latest_date)
                            if not u_recs.empty:
                                # 展示详细建议，包含理由
                                display_df = u_recs[['stock_code', 'tech_action', 'tech_reason', 'sent_action', 'sent_reason', 'price']]
                                st.dataframe(display_df, use_container_width=True)
                            else:
                                st.caption("该日期暂无详细建议数据")
                        else:
                            st.caption("该用户暂无历史分析存档")
                        
                        if st.button("收起详情", key=f"c_v_{row['uid']}"):
                            st.session_state[f"view_user_info_{row['uid']}"] = False
                            st.rerun()

                    st.markdown("---")
                    if row['role'] == 'admin':
                        st.info("🔱 管理员账号")
                    else:
                        
                        # 权限切换
                        t_perm = not row['can_backtest']
                        p_label = "✅ 开启回测权限" if t_perm else "❌ 关闭回测权限"
                        if st.button(p_label, key=f"p_{row['uid']}", use_container_width=True):
                            db.update_user_backtest_permission(row['uid'], t_perm)
                            st.rerun()
                            
                        # 状态切换
                        if row['status'] == 'active':
                            if st.button("🚫 禁用该账号", key=f"d_{row['uid']}", use_container_width=True):
                                db.update_user_status(row['uid'], 'disabled')
                                st.rerun()
                        else:
                            if st.button("🟢 恢复账号正常", key=f"e_{row['uid']}", use_container_width=True):
                                db.update_user_status(row['uid'], 'active')
                                st.rerun()
            st.divider()
    else:
        st.info("暂无用户数据")

# ==================== 页面：📅 每日建议回顾 ====================
if page == "📅 每日建议":
    st.title("📅 每日收盘建议回顾")
    st.markdown("系统每天收盘后会自动分析您的自选股并存档，您可以在此翻看历史记录。")
    
    # 1. 获取有记录的所有日期
    dates_df = db.get_daily_recommendations(st.session_state.user_id)
    
    if dates_df.empty:
        st.info("📭 暂无历史记录。请确保您的 [⭐ 我的自选] 中有股票，且系统已执行过每日任务。")
    else:
        # 日期选择器
        dates_list = dates_df['date'].tolist()
        selected_date = st.selectbox("📅 选择日期查看存档", dates_list)
        
        if selected_date:
            recs_df = db.get_recommendations_by_date(st.session_state.user_id, selected_date)
            
            if recs_df.empty:
                st.warning(f"未找到 {selected_date} 的详细建议。")
            else:
                st.markdown(f"### 📋 {selected_date} 自动建议报告")
                
                # 汇总视图
                with st.expander("📍 快速概览", expanded=False):
                    st.table(recs_df[['stock_code', 'price', 'tech_action', 'sent_action']])
                
                st.divider()
                
                # 详细卡片视图
                for _, row in recs_df.iterrows():
                    s_code = row['stock_code']
                    stock_name = get_stock_name_offline(s_code)
                    
                    with st.container():
                        st.markdown(f"#### 🏷️ {stock_name} ({s_code}) | 收盘: ¥{row['price']:.2f}")
                        
                        col_t, col_s = st.columns(2)
                        with col_t:
                            st.markdown("🍏 **技术派**")
                            st.info(f"建议: **{row['tech_action']}**\n\n依据: {row['tech_reason']}")
                        
                        with col_s:
                            st.markdown("🍊 **情绪增强派**")
                            st.success(f"建议: **{row['sent_action']}**\n\n依据: {row['sent_reason']}")
                            
                        # 共振逻辑
                        if row['tech_action'] == row['sent_action']:
                            st.caption("✅ 信号共振：双派系意见一致")
                        else:
                            st.caption("⚠️ 信号背离：建议分步操作")
                        
                        st.divider()

# ==================== 页面2：我的自选 (新) ====================
if page == "⭐ 我的自选":
    st.title("⭐ 我的自选股管理")
    
    # 1. 批量添加 (优化：去重逻辑)
    with st.expander("➕ 批量添加股票", expanded=False):
        col_text, col_btn = st.columns([3, 1])
        with col_text:
            bulk_input = st.text_area("输入代码", placeholder="例如: 000001, 600519\n支持换行或逗号分隔", height=100)
            target_tag = st.text_input("初始标签 (可选)", placeholder="例如: 科技股", value="")
        
        with col_btn:
            st.write("") 
            st.write("")
            st.write("")
            if st.button("🚀 检查并导入", use_container_width=True):
                found_codes = re.findall(r'\d{6}', bulk_input)
                if found_codes:
                    # 先获取现有自选，用于去重
                    current_df = db.get_user_watchlist(st.session_state.user_id)
                    existing_codes = set(current_df['stock_code'].tolist()) if not current_df.empty else set()
                    
                    input_codes = set(found_codes)
                    new_codes = input_codes - existing_codes
                    skipped_codes = input_codes & existing_codes
                    
                    if not new_codes:
                        st.warning(f"所有输入代码 ({len(input_codes)}个) 均已存在，无需重复添加。")
                    else:
                        success_count = 0
                        # 如果没有输入标签，则设为空字符串，而不是"未分类"
                        tag_to_save = target_tag.strip()
                        for code in new_codes:
                            if db.add_to_watchlist(st.session_state.user_id, code, tag_to_save):
                                success_count += 1
                        
                        msg = f"✅ 成功导入 {success_count} 只新股票！"
                        if skipped_codes:
                            msg += f"\n(已跳过 {len(skipped_codes)} 只重复股票: {', '.join(list(skipped_codes)[:5])}...)"
                        st.success(msg)
                        time.sleep(1) # 给用户一点时间看提示
                        st.rerun()
                else:
                    st.error("未发现有效的6位股票代码")

    st.markdown("---")

    # 2. 列表展示与批量操作
    watchlist_df = db.get_user_watchlist(st.session_state.user_id)
    if not watchlist_df.empty:
        # 获取股票名称 (带缓存)
        if 'stock_names_cache' not in st.session_state:
            st.session_state.stock_names_cache = {}
            
        def get_name_cached(code):
            if code not in st.session_state.stock_names_cache:
                st.session_state.stock_names_cache[code] = get_stock_name_offline(code)
            return st.session_state.stock_names_cache[code]

        watchlist_df['股票名称'] = watchlist_df['stock_code'].apply(get_name_cached)
        
        # --- 批量操作栏 ---
        col_batch_tag, col_batch_del, col_refresh = st.columns([3, 1, 1])
        with col_batch_tag:
            new_batch_tag = st.text_input("批量修改标签为:", placeholder="输入新标签...", key="batch_tag_input")

        with col_refresh:
             st.write("")
             st.write("")
             if st.button("🔄 刷新名称", help="如果名称不显示，点此强制从网络获取"):
                # 清除通过 app.py 维护的缓存
                if 'stock_names_cache' in st.session_state:
                    del st.session_state['stock_names_cache']
                # 清除通过 stock_names.py 维护的缓存
                if 'stock_name_cache' in st.session_state:
                    del st.session_state['stock_name_cache']
                st.rerun()
        
        # 使用 Streamlit 的 data_editor (支持勾选)
        # 我们需要在 DataFrame 前面加一列 "选择" (bool)
        watchlist_df.insert(0, "选择", False)
        
        edited_df = st.data_editor(
            watchlist_df,
            column_config={
                "选择": st.column_config.CheckboxColumn(
                    "选中",
                    help="勾选以进行批量操作",
                    default=False,
                ),
                "stock_code": "代码",
                "股票名称": "名称",
                "tag": "当前标签"
            },
            disabled=["stock_code", "股票名称", "tag"], # 禁止直接编辑这几列，只允许勾选
            hide_index=True,
            use_container_width=True,
            key="watchlist_editor"
        )
        
        # 获取被勾选的行
        selected_rows = edited_df[edited_df["选择"] == True]
        selected_codes = selected_rows['stock_code'].tolist()
        
        if selected_codes:
            st.info(f"已选中 {len(selected_codes)} 只股票: {', '.join(selected_codes)}")
            
            # 操作按钮区
            c_op1, c_op2 = st.columns([1, 1])
            with c_op1:
                if st.button("🏷️ 批量更新标签", type="primary", use_container_width=True):
                    if new_batch_tag.strip():
                        count = 0
                        for code in selected_codes:
                            db.update_stock_tag(st.session_state.user_id, code, new_batch_tag.strip())
                            count += 1
                        st.success(f"已将 {count} 只股票的标签更新为 '{new_batch_tag}'！")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning("请输入要设置的新标签名称")
            
            with c_op2:
                if st.button("🗑️ 批量移出自选", type="secondary", use_container_width=True):
                    count = 0
                    for code in selected_codes:
                        db.remove_from_watchlist(st.session_state.user_id, code)
                        count += 1
                    st.success(f"已移除 {count} 只股票！")
                    time.sleep(1)
                    st.rerun()
        else:
            st.caption("👆 如需批量操作，请先在表格左侧勾选股票")

    else:
        st.info("自选股列表为空，请先添加股票。")

# ==================== 页面1：实时分析 ====================
if page == "📊 实时分析":
    from main import get_market_status
    
    st.title("📊 AI 实时分析")
    
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
            st.warning(f"🕒 当前非交易时段 ({status_text}) | 系统使用最近一个交易日的收盘数据进行分析")
            
    # 获取用户自选作为快捷选项
    watchlist_df = db.get_user_watchlist(st.session_state.user_id)
    tags = db.get_tags(st.session_state.user_id)
    
    # 1. 选择来源
    analysis_mode = st.radio("数据来源", ["从我的自选加载", "手动输入代码"], horizontal=True)
    
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

    # 分析流程逻辑...
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        analyze_btn = st.button("🚀 开始分析", use_container_width=True, type="primary")
    
    if analyze_btn:
        if not selected_stocks:
            st.error("⚠️ 请先选中要分析的股票（来自自选或手动输入）")
        else:
            stocks = selected_stocks
            st.markdown("---")
            st.subheader(f"📋 分析 {len(stocks)} 只股票")
            progress_bar = st.progress(0)
            
            new_results = []
            for i, stock in enumerate(stocks):
                with st.spinner(f"正在深度分析 {stock}..."):
                    try:
                        df, error = get_stock_data(stock)
                        if df is not None and not df.empty:
                            stock_name = get_stock_name_offline(stock)
                            res_tech = analyze_with_deepseek(stock, df, strategy_type="technical")
                            res_sent = analyze_with_deepseek(stock, df, strategy_type="sentiment")
                            
                            # 记录 Token 消耗
                            for res, s_type in [(res_tech, "technical"), (res_sent, "sentiment")]:
                                usage = res.get('usage')
                                if usage:
                                    db.log_token_usage(
                                        st.session_state.user_id, 
                                        f"realtime_{s_type}", 
                                        stock, 
                                        usage.prompt_tokens, 
                                        usage.completion_tokens
                                    )
                            latest = df.iloc[-1]
                            
                            new_results.append({
                                "代码": stock,
                                "名称": stock_name,
                                "价格": f"¥{latest['收盘']:.2f}",
                                "涨跌": f"{latest['涨跌幅']:.2f}%",
                                "技术建议": res_tech.get('action', '💤 观望'),
                                "情绪建议": res_sent.get('action', '💤 观望'),
                                "技术得分": res_tech.get('scores', {}).get('technical', 50),
                                "情绪得分": res_sent.get('scores', {}).get('sentiment', 50),
                                "技术理由": res_tech.get('reason', 'N/A'),
                                "情绪理由": res_sent.get('reason', 'N/A'),
                                "风险(T)": res_tech.get('scores', {}).get('risk', 50),
                                "风险(S)": res_sent.get('scores', {}).get('risk', 50),
                            })
                        else:
                            st.error(f"无法获取股票 {stock} 的行情数据。")
                    except Exception as e:
                        st.error(f"分析股票 {stock} 失败: {str(e)}")
                progress_bar.progress((i + 1) / len(stocks))
            
            # 保存到 session_state
            st.session_state.last_analysis_results = new_results
            st.rerun() # 刷新以显示结果

    # --- 渲染分析结果 (如果存在) ---
    if st.session_state.last_analysis_results:
        results = st.session_state.last_analysis_results
        
        col_title, col_clear = st.columns([5, 1])
        col_title.markdown("### 📊 上一次分析汇总")
        if col_clear.button("🗑️ 清除结果"):
            st.session_state.last_analysis_results = None
            st.rerun()

        res_df = pd.DataFrame(results)
        st.dataframe(
            res_df[['代码', '名称', '价格', '涨跌', '技术建议', '情绪建议']],
            use_container_width=True
        )
        
        st.markdown("---")
        st.subheader("🔍 策略深度拆解 (技术 vs 情绪)")
        for res in results:
            stock_label = f"**{res['名称']} ({res['代码']})** | 当前价: {res['价格']} ({res['涨跌']})"
            with st.expander(stock_label, expanded=True):
                col_t, col_s = st.columns(2)
                with col_t:
                    st.markdown("#### 🛠️ 纯技术派")
                    st.markdown(f"**建议：{res['技术建议']}**")
                    st.progress(res['技术得分']/100, text=f"技术评分: {res['技术得分']}")
                    st.info(f"**分析依据:**\n\n{res['技术理由']}")
                    st.caption(f"风控等级: {res['风险(T)']}/100")
                    
                with col_s:
                    st.markdown("#### 🎭 情绪增强派")
                    st.markdown(f"**建议：{res['情绪建议']}**")
                    st.progress(res['情绪得分']/100, text=f"情绪评分: {res['情绪得分']}")
                    st.info(f"**分析依据:**\n\n{res['情绪理由']}")
                    st.caption(f"风控等级: {res['风险(S)']}/100")
                
                if res['技术建议'] == res['情绪建议']:
                    st.success(f"🎯 **共振一致**：两套策略均建议【{res['技术建议']}】，确定性较高。")
                else:
                    st.warning(f"⚠️ **观点分歧**：技术建议{res['技术建议']}，而情绪倾向{res['情绪建议']}，建议分批或观望。")
                st.markdown("---")
    
        # 下载按钮
        csv = res_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 下载分析报告 (CSV)",
            data=csv,
            file_name=f"ai_analysis_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

# ==================== 页面2：策略说明 ====================
elif page == "📖 策略说明":
    st.title("📖 AI 策略深度白皮书")
    
    # 策略核心理念
    st.info("""
    **核心哲学 (Strategy Philosophy):** 
    本系统采用【势能交易 (Trend Following)】逻辑。核心理念是：**不预测顶底，只跟随趋势。** 在多头排列中敢于重仓，在趋势走弱时果断离场，利用均线作为决策支点，规避情绪化的追涨杀跌。
    """)
    
    # 使用标签页展示多维度细节
    tab_logic, tab_indicator, tab_prompt = st.tabs(["🎯 决策逻辑", "📊 指标公式", "🤖 AI 提示词公开"])

    with tab_logic:
        st.markdown("""
        ### 🧠 V4.0 势能决策引擎机制
        
        我们的决策引擎现在模拟了一个具备 10 年 A 股经验的“势能操盘手”行为模式：
        
        #### 1. 入场条件 (Buy Logic)
        - **趋势确认**：股价位居 $MA_5$ 和 $MA_{20}$ 之上，且均线呈现发散状态。
        - **动能释放**：量比 (Volume Ratio) 突破 1.2，意味着成交活跃，资金开始进场。
        - **AI 判定**：AI 在 10 日 K 线数据中识别到阳线实体增大、低点不断抬升的看涨势能。

        #### 2. 持仓守则 (Holding Logic)
        - **均线防守**：以 $MA_5$ 为短线防守，只要收盘不破均线且均线上翘，坚定持有。
        - **止盈机制**：在乖离率 (Bias) 过大或出现高位巨量阴线时，AI 会提示分步止盈。

        #### 3. 离场保护 (Sell Logic)
        - **破位止损**：一旦收盘价跌破 $MA_5$ (激进派) 或 $MA_{10}$ (稳健派)，立即无条件执行。
        - **情绪预警**：大盘暴跌期间，即便个股走势尚可，AI 也会降低风险评分建议避险。

        ---
        
        ### ⚔️ 流派对决：技术派 vs 情绪派
        
        系统同时运行两种 AI 代理，它们在以下方面有本质区别：

        | 维度 | 🥉 纯技术派 (Pure Tech) | 🚀 情绪增强派 (Sentiment+) |
        | :--- | :--- | :--- |
        | **信息量** | 仅看个股价量、指标数据 | **个股数据 + 大盘(上证)走势** |
        | **核心哲学** | 个股即一切，忽略大盘噪音 | 大盘是水，个股是船；水落船难行 |
        | **适用场景** | 妖股、逆势独立行情 | 普涨/普跌行情、波段决策 |
        | **典型表现** | 大盘大跌时仍可能买入强势股 | 大盘走弱时会自动收缩阵线避险 |
        """)

    with tab_indicator:
        st.markdown(r"""
        ### 📐 核心指标计算公式
        
        系统实时计算以下因子并喂给 AI 进行逻辑分析：
        
        #### I. 移动平均线 (Moving Average)
        $$MA_n = \frac{1}{n} \sum_{i=1}^n C_i$$
        *其中 $C_i$ 为第 $i$ 日的收盘价。我们主要参考 $MA_5$ (周线)、$MA_{10}$ (半月线) 和 $MA_{20}$ (月线)。*
        
        #### II. 量比 (Volume Ratio)
        $$VR = \frac{V_{today}}{\frac{1}{5} \sum_{k=1}^5 V_{k}}$$
        *衡量日成交量与过去 5 日均量的对比。$VR > 1.5$ 视为放量，$VR < 0.8$ 视为缩量。*
        
        #### III. 势能评分 (Energy Score)
        由 AI 结合 K 线斜率 $\Delta P / \Delta t$ 与量价配合程度综合得出。
        """)

    with tab_prompt:
        st.markdown("### 🧬 AI 系统级提示词 (System Prompts)")
        st.write("这是我们目前投喂给 DeepSeek 的真实指令片段，确保 AI 保持专业的交易人格。")
        
        st.code("""
# 身份设定
你是 A 股短线势能交易专家。

# 核心策略
1. 顺势而为：价在MA5、MA20之上且放量时，应积极做多，不要因位高而恐高。
2. 趋势防守：破MA5且量缩需警惕，跌破MA10视为趋势反转。
3. 信号第一：只输出基于当前均线和量价关系的果断决策。

# 输入数据流
- [日期 | 价量配比 | 均线位置 | 大盘环境]
        """, language="markdown")
        
        st.caption("注：V2.0 策略目前正在后台进行宽幅防守（MA10 止损）对比测试。")

# ==================== 页面3：历史回测 ====================
elif page == "📈 历史回测":
    st.title("📈 策略长跑英雄榜")
    st.markdown("这里记录了 AI 投顾系统在历史长河中的实战表现。")

    # --- 1. 年度英雄榜专区 ---
    #版本选择
    bt_v = st.radio("📈 选择策略版本", ["🥉 初级版 (纯技术/旧版)", "🚀 进阶版 (技术+情绪+量比)"], horizontal=True)
    
    if "进阶版" in bt_v:
        annual_file = "backtest_summary_advanced.csv"
        details_file_path = "backtest_details_advanced.csv"
        ver_tag = "进阶版"
    else:
        annual_file = "backtest_summary_primary.csv"
        details_file_path = "backtest_details_primary.csv"
        ver_tag = "初级版"

    if os.path.exists(annual_file):
        st.success(f"🏆 **【{ver_tag}】2025-2026 年度大长跑英雄榜 (365天)**")
        try:
            df_annual = pd.read_csv(annual_file)
            if not df_annual.empty:
                # 收益率转换并排序
                for col in ['纯技术派(1年)', '情绪增强派(1年)', '基准(1年)']:
                    if col in df_annual.columns:
                        if col + '_val' not in df_annual.columns:
                            df_annual[col + '_val'] = df_annual[col].str.replace('%', '').astype(float)
                
                # 计算超额收益 (Alpha)
                df_annual['技术派Alpha'] = df_annual['纯技术派(1年)_val'] - df_annual['基准(1年)_val']
                df_annual['情绪派Alpha'] = df_annual['情绪增强派(1年)_val'] - df_annual['基准(1年)_val']
                
                # 动态确定每只股票的最强收益和对应的 Alpha
                df_annual['最强收益_val'] = df_annual[['纯技术派(1年)_val', '情绪增强派(1年)_val']].max(axis=1)
                
                def get_best_info(row):
                    if row['纯技术派(1年)_val'] >= row['情绪增强派(1年)_val']:
                        return row['纯技术派(1年)'], row['技术派Alpha'], "技术派"
                    else:
                        return row['情绪增强派(1年)'], row['情绪派Alpha'], "情绪派"
                
                df_annual[['最强收益', '最强Alpha', '胜出策略']] = df_annual.apply(
                    lambda x: pd.Series(get_best_info(x)), axis=1
                )
                
                # 按照最强收益排序找出总冠军
                df_sorted = df_annual.sort_values('最强收益_val', ascending=False)
                winner = df_sorted.iloc[0]
                
                # 冠军展示牌
                w_col1, w_col2, w_col3 = st.columns([1, 1, 1])
                w_col1.metric("🥇 年度冠军", f"{winner['名称']}")
                w_col2.metric(f"最高收益 ({winner['胜出策略']})", winner['最强收益'])
                
                # 超额收益显示优化
                alpha_val = winner['最强Alpha']
                w_col3.metric("超额收益 (Alpha)", f"{'+' if alpha_val > 0 else ''}{alpha_val:.1f}%", delta=f"{alpha_val:.1f}%")

                # 表格展示 (增加对比列)
                display_df = df_annual[['代码', '名称', '纯技术派(1年)', '情绪增强派(1年)', '基准(1年)', '技术派Alpha', '情绪派Alpha']].copy()
                # 格式化 Alpha
                display_df['技术派Alpha'] = display_df['技术派Alpha'].apply(lambda x: f"{'+' if x>0 else ''}{x:.1f}%")
                display_df['情绪派Alpha'] = display_df['情绪派Alpha'].apply(lambda x: f"{'+' if x>0 else ''}{x:.1f}%")
                
                st.dataframe(display_df, use_container_width=True, height=400)
                
                # 下载按钮
                c_dl1, c_dl2 = st.columns(2)
                with c_dl1:
                    with open(annual_file, 'rb') as f:
                        st.download_button(f"📥 下载【{ver_tag}】汇总", data=f, file_name=annual_file, key=f"dl_s_{ver_tag}")
                
                if os.path.exists(details_file_path):
                    with c_dl2:
                        with open(details_file_path, 'rb') as f:
                            st.download_button(f"📥 下载【{ver_tag}】全明细", data=f, file_name=details_file_path, key=f"dl_d_{ver_tag}")
            else:
                st.warning(f"【{ver_tag}】报告文件已创建，但尚未有数据存入。请稍等片刻...")
        except Exception as e:
            st.error(f"读取年度报告失败: {e}")
    else:
        st.info(f"🕒 **【{ver_tag}】年度回测进行中/未生成...**")

    st.divider()

    # --- 2. 手动回测入口 (特定权限) ---
    st.subheader("🛠️ 发起新回测")
    can_bt = st.session_state.get('can_backtest', False) or st.session_state.user_role == 'admin'
    
    if not can_bt:
        st.warning("🔒 您当前没有回测权限，请联系管理员（admin）开通。")
    else:
        # 管理员可以手动输入代码
        if st.session_state.user_role == 'admin':
            with st.expander("👑 管理员控制台：手动发起 365 天大长跑", expanded=False):
                admin_stocks = st.text_input("输入股票代码 (逗号分隔)", placeholder="例如: 600519, 000001")
                if st.button("🔥 立即全量重跑（覆盖现有年度榜单）"):
                    if admin_stocks:
                        import subprocess
                        # 修改脚本中的 stocks 列表并重新运行 (这里简单处理，直接通过命令行传参，我们需要修改脚本支持参数)
                        st.info(f"正在调起后台引擎回测: {admin_stocks} ...")
                        
                        # 1. 尝试杀死旧进程 (防止重复运行占用资源)
                        subprocess.Popen(["pkill", "-f", "backtest_engine.py"])
                        
                        # 2. 启动新进程 (不阻塞 Streamlit)
                        import sys
                        cmd = [sys.executable, "backtest_engine.py", admin_stocks]
                        # 使用 nohup 或直接 Popen 剥离
                        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        
                        st.success("✅ 后台引擎已启动！请稍候刷新页面查看生成的 CSV 报告...")
                    else:
                        st.error("请输入代码")
        
        # 普通获授权用户可以看到普通回测逻辑（暂略，已有年度榜单展示）
        st.info("✅ 您已获得回测权限。当前年度榜单由系统自动维护。")

    st.divider()

    # --- 2. 其他历史记录 ---
    st.markdown("### 📜 历史回测存档")
    csv_files = glob.glob("backtest*.csv")
    csv_files = [f for f in csv_files if f != annual_file] # 排除已展示的年度文件
    
    if not csv_files:
        st.caption("暂无其他历史存档")
    else:
        selected_file = st.selectbox(
            "选择存档文件",
            csv_files,
            format_func=lambda x: f"{x} ({os.path.getsize(x) / 1024:.1f} KB)"
        )
        
        if selected_file:
            try:
                df = pd.read_csv(selected_file)
                st.dataframe(df.head(50), use_container_width=True)
                with open(selected_file, 'rb') as f:
                    st.download_button("📥 下载数据", data=f, file_name=selected_file)
                    
                # 如果是汇总文件，尝试展示关键指标
                if "summary" in selected_file.lower():
                    st.markdown("#### 📊 关键指标")
                    # 尝试识别收益率列
                    roi_cols = [col for col in df.columns if '收益' in col or 'roi' in col.lower() or '%' in col]
                    if roi_cols:
                        st.markdown("**收益率对比**")
                        for col in roi_cols:
                            st.write(f"- {col}: {df[col].tolist()}")
            except Exception as e:
                st.error(f"❌ 读取文件失败: {e}")

# 页脚
st.markdown("---")
st.caption("💡 AI 智能投顾系统 | v4.0.1 (SSL-READY) | 数据来源: AkShare | AI: DeepSeek")
