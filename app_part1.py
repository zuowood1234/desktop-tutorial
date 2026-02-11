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

        has_run = db.check_if_daily_analysis_run(today_str)
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
                
                # --- 1. 汇总表格视图 (仿实时分析) ---
                # 构造符合展示的 DataFrame
                display_rows = []
                for _, row in recs_df.iterrows():
                    s_code = row['stock_code']
                    # 尝试获取名称
                    s_name = get_stock_name_offline(s_code)
                    
                    display_rows.append({
                        "代码": s_code,
                        "名称": s_name,
                        "收盘价": f"¥{row['price']:.2f}",
                        "技术派建议": row['tech_action'],
                        "情绪派建议": row['sent_action'],
                        # 简单判断一致性
                        "共振信号": "✅" if row['tech_action'] == row['sent_action'] else "⚠️ 分歧"
                    })
                
                st.dataframe(pd.DataFrame(display_rows), use_container_width=True, hide_index=True)
                
                st.divider()
                st.subheader("🔍 深度拆解 (点击展开详情)")
                
                # --- 2. 详细卡片视图 (仿实时分析) ---
                for _, row in recs_df.iterrows():
                    s_code = row['stock_code']
                    stock_name = get_stock_name_offline(s_code)
                    
                    # 使用 expander 保持页面整洁，和实时分析保持一致体验
                    with st.expander(f"📊 {stock_name} ({s_code}) | 收盘: ¥{row['price']:.2f} | 建议: {row['tech_action']} / {row['sent_action']}", expanded=False):
                        
                        col_t, col_s = st.columns(2)
                        
                        # 技术派卡片
                        with col_t:
                            st.markdown("#### 🍏 V1 纯技术派")
                            if "买" in row['tech_action']:
                                st.success(f"**{row['tech_action']}**")
                            elif "卖" in row['tech_action']:
                                st.error(f"**{row['tech_action']}**")
                            else:
                                st.info(f"**{row['tech_action']}**")
                            
                            st.markdown(f"> **理由**: {row['tech_reason']}")

                        # 情绪派卡片
                        with col_s:
                            st.markdown("#### 🍊 V2 情绪增强派")
                            if "买" in row['sent_action']:
                                st.success(f"**{row['sent_action']}**")
                            elif "卖" in row['sent_action']:
                                st.error(f"**{row['sent_action']}**")
                            else:
                                st.info(f"**{row['sent_action']}**")
                            
                            st.markdown(f"> **理由**: {row['sent_reason']}")
                        
                        # 底部共振提示
                        st.markdown("---")
                        if row['tech_action'] == row['sent_action']:
                            st.caption("✨ **信号共振**：双AI达成一致，信号可信度高。")
                        else:
                            st.caption("⚡ **信号分歧**：技术面与情绪面存在冲突，建议控制仓位，参考 V2 稳健派意见。")

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
