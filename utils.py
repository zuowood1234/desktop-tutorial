import streamlit as st
import os
from dotenv import load_dotenv
from database import DBManager
from stock_names import get_stock_name_offline
from datetime import datetime

# 强制加载 .env (使用绝对路径)
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(current_dir, '.env')
load_dotenv(dotenv_path=env_path, override=True)

@st.cache_resource
def get_db():
    # Force cache invalidation to load new DBManager methods V2
    return DBManager()

@st.cache_data(ttl=3600*24) # 股票名称缓存 24小时
def get_cached_stock_name(code):
    return get_stock_name_offline(code)

@st.cache_data(ttl=60) # 每日任务状态缓存 1分钟
def get_cached_daily_run_status(date_str):
    db = get_db()
    return db.check_if_daily_analysis_run(date_str)

def check_and_run_auto_analysis():
    # Only run scheduled background tasks if someone is actually logged in,
    # otherwise it blocks the login page screen.
    if 'user_id' not in st.session_state or st.session_state.user_id is None:
        return
        
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
            status_text = st.empty()
            status_text.text(f"正在后台生成 {today_str} 收盘数据...")
            with st.spinner(f"🤖 下午好！系统正在自动执行【今日收盘复盘】，请稍候..."):
                # 动态导入防止循环引用
                from auto_daily_analysis import run_auto_daily_analysis
                run_auto_daily_analysis()
                st.toast(f"✅ 今日收盘数据已自动生成！", icon="🎉")
                time.sleep(1) # 给用户一点反应时间
            status_text.empty()
        
        # 标记本次会话已检查
        st.session_state.daily_check_done = today_str
            
    except Exception as e:
        print(f"⚠️ [AutoScheduler] 自动任务异常: {e}")

def inject_custom_css():
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

def check_authentication():
    if 'user_id' not in st.session_state or st.session_state.user_id is None:
        st.warning("⚠️ 请先在首页进行登录操作。")
        if st.button("👉 点击此处返回首页登录"):
            st.switch_page("app.py")
        st.stop()

def render_sidebar():
    if st.session_state.get('user_id'):
        st.sidebar.title(f"👤 {st.session_state.get('username', '')}")
        if st.session_state.get('user_role') == 'admin':
            st.sidebar.info("🔱 管理员模式")
            
        if st.sidebar.button("🚪 退出登录"):
            st.session_state.user_id = None
            st.rerun()
            
        st.sidebar.markdown("---")
        st.sidebar.caption("💡 Powered by DeepSeek AI")
