import streamlit as st
import time
from utils import get_db, inject_custom_css, check_authentication, render_sidebar

st.set_page_config(page_title="管理后台 - AI 智能投顾", layout="wide")
inject_custom_css()
check_authentication()
render_sidebar()

# 仅允许管理员访问
if st.session_state.get('user_role') != 'admin':
    st.error("🚫 您没有权限访问此页面。")
    st.stop()

db = get_db()
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
