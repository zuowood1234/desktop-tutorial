import streamlit as st
import time
import pandas as pd
import plotly.graph_objects as go
from dotenv import load_dotenv
import os

# 强制加载 .env (使用绝对路径)
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(dotenv_path=env_path, override=True)

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

# --- 缓存优化层 ---
@st.cache_data(ttl=3600*24) # 股票名称缓存 24小时
def get_cached_stock_name(code):
    return get_stock_name_offline(code)

@st.cache_data(ttl=60) # 每日任务状态缓存 1分钟
def get_cached_daily_run_status(date_str):
    # 使用全局 db 实例
    return db.check_if_daily_analysis_run(date_str)

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

# ==================== 🚀 自动化引擎：盘后自动检查 ====================
# 逻辑：每次有人访问页面时，检查当前是否为盘后 (15:15后)，且今日是否已运行过任务。
# 如果是盘后且未运行，则自动触发。
def check_and_run_auto_analysis():
    # 简单的防抖动机制，避免同一分钟内多人触发
    now = datetime.now()
    
    # 1. 必须是工作日 (周一到周五: 0-4)
    if now.weekday() > 4:
        return

    # 2. 必须是 A 股收盘后 (为了保险，定在 15:15)
    market_close_time = now.replace(hour=15, minute=15, second=0, microsecond=0)
    if now < market_close_time:
        return

    # 3. 检查数据库中最新的记录日期
    try:
        today_str = now.strftime("%Y-%m-%d")
        
        # 检查标记位 (使用 session_state 避免单次访问重复查库，虽然跨会话无效)
        if 'daily_check_done' in st.session_state and st.session_state.daily_check_done == today_str:
            return

        has_run = get_cached_daily_run_status(today_str)
        if not has_run:
            status_text.text(f"正在后台生成 {today_str} 收盘数据...")
            with st.spinner(f"🤖 下午好！系统正在自动执行【今日收盘复盘】，请稍候..."):
                # 动态导入防止循环引用
                from auto_daily_analysis import run_auto_daily_analysis
                run_auto_daily_analysis()
                st.toast(f"✅ 今日收盘数据已自动生成！", icon="🎉")
                time.sleep(1) # 给用户一点反应时间
        
        # 标记本次会话已检查
        st.session_state.daily_check_done = today_str
            
    except Exception as e:
        print(f"⚠️ [AutoScheduler] 自动任务异常: {e}")

# 在渲染主界面样式前尝试运行
status_text = st.empty() # 占位符
try:
    check_and_run_auto_analysis()
    status_text.empty() # 清除占位符
except Exception as e:
    status_text.empty()
    print(f"Auto-run skipped: {e}")

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

nav_options = ["📊 实时分析", "📅 每日建议", "⭐ 我的自选", "📖 策略说明"]
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
    
    # --- 新增：手动补录功能 ---
    with st.expander("🛠️ 没看到今日数据？点此手动生成", expanded=False):
        st.warning("如果系统未自动运行，您可以手动触发。请仅在收盘后（15:00 后）使用。")
        if st.button("🔄 立即生成今日复盘 (补录)", use_container_width=True):
            with st.spinner("正在后台执行全量自选股分析，请勿离开..."):
                try:
                    # 尝试导入并运行自动化脚本
                    from auto_daily_analysis import run_auto_daily_analysis
                    run_auto_daily_analysis()
                    st.success("✅ 补录成功！请刷新页面查看。")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"执行失败: {str(e)}")

    # 1. 获取有记录的所有日期
    dates_df = db.get_daily_recommendations(st.session_state.user_id)
    
    if dates_df.empty:
        st.info("📭 暂无历史记录。请确保您的 [⭐ 我的自选] 中有股票，且系统已执行过每日任务。")
    else:
        # 日期选择器
        dates_list = dates_df['date'].tolist()
        selected_date = st.selectbox("📅 选择日期查看存档", dates_list, index=0) # 默认选最新的
        
        if selected_date:
            recs_df = db.get_recommendations_by_date(st.session_state.user_id, selected_date)
            
            if recs_df.empty:
                st.warning(f"未找到 {selected_date} 的详细建议。")
            else:
                st.markdown(f"### 📋 {selected_date} 复盘报告")
                
                # --- 汇总表格视图 (只展示 V1-V3) ---
                display_rows = []
                for _, row in recs_df.iterrows():
                    s_code = row['stock_code']
                    # 尝试获取名称
                    s_name = get_cached_stock_name(s_code)
                    
                    # 涨跌幅处理
                    pct = row.get('pct_chg')
                    if pct is None:
                        pct_str = "--"
                    else:
                        pct_val = float(pct)
                        pct_str = f"{pct_val:.2f}%"
                    
                    # 获取策略结果
                    v1 = row.get('tech_action') or '未生成'
                    v2 = row.get('sent_action') or '未生成'
                    v3 = row.get('v3_action') or '未生成'
                    
                    display_rows.append({
                        "代码": s_code,
                        "名称": s_name,
                        "涨跌幅": pct_str,
                        "V1 综合记分": v1,
                        "V2 趋势猎手": v2,
                        "V3 波段防御": v3
                    })
                
                # 展示简洁的大表格
                st.dataframe(
                    pd.DataFrame(display_rows), 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "代码": st.column_config.TextColumn("代码", width="small"),
                        "名称": st.column_config.TextColumn("名称", width="small"),
                        "涨跌幅": st.column_config.TextColumn("今日涨幅", width="small"),
                        "V1 综合记分": st.column_config.TextColumn("V1 综合记分", width="medium"),
                        "V2 趋势猎手": st.column_config.TextColumn("V2 趋势猎手", width="medium"),
                        "V3 波段防御": st.column_config.TextColumn("V3 波段防御", width="medium"),
                    }
                )
                
                if not display_rows:
                    st.info("数据生成中或为空...")

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
                st.session_state.stock_names_cache[code] = get_cached_stock_name(code)
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
            # 引入新引擎
            from backtest_engine import BacktestEngine
            
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
                            
                            latest_price = latest_row['close']
                            pct_chg = latest_row['pctChg'] if 'pctChg' in latest_row else 0
                            
                            new_results.append({
                                "代码": stock,
                                "名称": stock_name,
                                "价格": f"¥{latest_price:.2f}",
                                "涨跌": f"{pct_chg:.2f}%",
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
    if st.session_state.last_analysis_results:
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

# ==================== 页面2：策略说明 ====================
elif page == "📖 策略说明":
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



