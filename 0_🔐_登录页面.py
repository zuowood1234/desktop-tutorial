import streamlit as st
import re
from utils import get_db, inject_custom_css, check_and_run_auto_analysis

# 初始化数据库
db = get_db()

# 设置网页
st.set_page_config(page_title="AI 智能投顾 - 登录页面", layout="wide", initial_sidebar_state="expanded")

# --- 认证逻辑 ---
if 'last_analysis_results' not in st.session_state:
    st.session_state.last_analysis_results = None
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
    st.session_state.user_role = 'user'

inject_custom_css()

# 如果未登录，展示登录/注册界面
if st.session_state.user_id is None:
    st.title("🔐 AI 智能投顾")
    st.markdown("欢迎使用 AI 智能投顾系统。请登录以继续。")

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
                    role = 'admin' if r_user.lower() == 'admin' else 'user'
                    success, msg = db.register_user(r_user, r_email, r_pw, role)
                    if success:
                        st.success("注册成功！请切换到登录页。")
                    else:
                        st.error(msg)
    st.stop()

# ==================== 首页 (登录后导航大盘) ====================
st.title(f"👋 欢迎回来，{st.session_state.username}！")
st.markdown("这里是您的 AI 智能投顾控制台。")

# 侧边栏
st.sidebar.title(f"👤 {st.session_state.username}")
if st.session_state.user_role == 'admin':
    st.sidebar.info("🔱 管理员模式")

if st.sidebar.button("🚪 退出登录"):
    st.session_state.user_id = None
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("💡 Powered by DeepSeek AI")

st.markdown("---")
st.subheader("🚀 快速导航")

# 第一行：交易笔记、我的自选、实时分析
col1, col2, col3 = st.columns(3)

with col1:
    st.info("📓 **交易笔记**\n\n记录复盘感悟，标注重要事件，沉淀交易体系和灵感。")
    if st.button("进入交易笔记", use_container_width=True):
        st.switch_page("pages/1_📓_交易笔记.py")

with col2:
    st.info("⭐ **我的自选**\n\n管理您的自选股，批量导入、添加标签。")
    if st.button("前往自选股", use_container_width=True):
        st.switch_page("pages/2_⭐_我的自选.py")

with col3:
    st.success("📊 **实时分析**\n\n一键扫描自选股，AI 实时生成多维度操作建议。")
    if st.button("开始实时分析", use_container_width=True):
        st.switch_page("pages/3_📊_实时分析.py")

st.markdown("---")
# 第二行：历史复盘、策略说明、雷达选股器
col4, col5, col6 = st.columns(3)

with col4:
    st.warning("📅 **历史复盘**\n\n查看每日收盘后系统自动生成的历史策略建议存档。")
    if st.button("查看历史复盘", use_container_width=True):
        st.switch_page("pages/4_📅_历史复盘.py")

with col5:
    st.info("📖 **策略说明**\n\n了解 V1-V4 四大核心策略的设计原理。")
    if st.button("查看策略说明", use_container_width=True):
        st.switch_page("pages/5_📖_策略说明.py")

with col6:
    st.success("🎯 **雷达选股器**\n\n全市场秒级扫描，找出符合形态和基本面逻辑的个股。")
    if st.button("进入雷达选股", use_container_width=True):
        st.switch_page("pages/6_🎯_雷达选股器.py")

# 第三行：专业回测舱、全景阅兵场、管理后台（按权限显示）
if st.session_state.user_role == 'admin' or st.session_state.get('can_backtest'):
    st.markdown("---")
    col7, col8, col9 = st.columns(3)
    with col7:
        st.info("🔬 **专业回测舱**\n\n开启第二轨代码引擎，验证一切量化假说。")
        if st.button("进入专业回测", use_container_width=True):
            st.switch_page("pages/7_🔬_专业回测舱.py")
    with col8:
        st.success("🌐 **策略全景阅兵场**\n\n批量测试策略在全市场的实际表现。")
        if st.button("进入全景阅兵场", use_container_width=True):
            st.switch_page("pages/8_🌐_策略全景阅兵场.py")
    if st.session_state.user_role == 'admin':
        with col9:
            st.error("👑 **管理后台**\n\n管理员专属，查看用户数据、一键触发跑批。")
            if st.button("进入管理后台", use_container_width=True):
                st.switch_page("pages/9_👑_管理后台.py")
elif st.session_state.user_role == 'admin':
    st.markdown("---")
    col_a, _, __ = st.columns(3)
    with col_a:
        st.error("👑 **管理后台**\n\n管理员专属，查看用户数据、一键触发跑批。")
        if st.button("进入管理后台", use_container_width=True):
            st.switch_page("pages/9_👑_管理后台.py")

st.markdown("---")
st.info("🚧 更多功能 (如今日大盘指数、深度市场分析) 敬请期待！系统架构已升级完毕，即将提速开发。")

# ==================== 🚀 自动化引擎：盘后自动检查 ====================
try:
    check_and_run_auto_analysis()
except Exception as e:
    print(f"Auto-run skipped: {e}")
