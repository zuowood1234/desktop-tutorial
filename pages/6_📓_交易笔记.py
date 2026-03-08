import streamlit as st
import pandas as pd
import json
from datetime import datetime
import plotly.express as px
from utils import get_db, inject_custom_css

# 初始化数据库
db = get_db()

# 页面配置
st.set_page_config(page_title="交易笔记", page_icon="📓", layout="wide")
inject_custom_css()

# 检查权限
if 'user_id' not in st.session_state or st.session_state.user_id is None:
    st.warning("请先登录后查看交易笔记。")
    st.stop()

uid = st.session_state.user_id

# 定义常用标签
preset_tags = ["打板", "低吸", "追高", "割肉", "止盈", "情绪退潮", "主升浪", "错杀", "龙头", "试错", "反包", "模式内"]


# ====== 页面布局拆分 ======
col_left, col_right = st.columns([2.5, 7.5], gap="large")

with col_left:
    st.subheader("🗓️ 交易日历")
    
    st.markdown("""
    <style>
    /* 强制缩小分栏中按钮的内边距并禁止文本换行，防止两位数日期变成两行 */
    div[data-testid="column"] button, div[data-testid="stHorizontalBlock"] button {
        padding-left: 0px !important;
        padding-right: 0px !important;
    }
    div[data-testid="column"] button p, div[data-testid="stHorizontalBlock"] button p {
        font-size: 13px !important;
        white-space: nowrap !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    import calendar
    
    heatmap_df = db.get_notes_heatmap_data(uid)
    
    # 选择日期的状态管理
    if 'note_selected_date' not in st.session_state:
        st.session_state.note_selected_date = None
    
    note_counts = {}
    if not heatmap_df.empty:
        for _, row in heatmap_df.iterrows():
            note_counts[row['date']] = row['count']
    
    if 'cal_month' not in st.session_state:
        from datetime import datetime
        today = datetime.now()
        # 默认起始月份
        st.session_state.cal_month = pd.Timestamp(today.year, today.month, 1)

    if 'show_month_picker' not in st.session_state:
        st.session_state.show_month_picker = False
    
    col_m1, col_m2, col_m3 = st.columns([1, 3, 1])
    with col_m1:
        if st.button("⬅️", use_container_width=True, help="上个月"):
            st.session_state.cal_month -= pd.DateOffset(months=1)
            st.rerun()
    with col_m2:
        if st.button(f"{st.session_state.cal_month.year}年 {st.session_state.cal_month.month}月", use_container_width=True, help="点击切换年月"):
            st.session_state.show_month_picker = not st.session_state.show_month_picker
            st.rerun()
    with col_m3:
        if st.button("➡️", use_container_width=True, help="下个月"):
            st.session_state.cal_month += pd.DateOffset(months=1)
            st.rerun()

    if st.session_state.show_month_picker:
        with st.container(border=True):
            st.markdown("<div style='font-size:14px; color:#555;'>快速跳转</div>", unsafe_allow_html=True)
            pick_col1, pick_col2 = st.columns(2)
            with pick_col1:
                sel_year = st.selectbox("年份", range(2024, 2035), index=range(2024, 2035).index(st.session_state.cal_month.year), label_visibility="collapsed")
            with pick_col2:
                sel_month = st.selectbox("月份", range(1, 13), index=st.session_state.cal_month.month - 1, label_visibility="collapsed")
            if st.button("确定跳至该月", use_container_width=True, type="primary"):
                st.session_state.cal_month = pd.Timestamp(sel_year, sel_month, 1)
                st.session_state.show_month_picker = False
                st.rerun()
    
    weekdays = ["一", "二", "三", "四", "五", "六", "日"]
    cols = st.columns(7)
    for i, wd in enumerate(weekdays):
        cols[i].markdown(f"<div style='text-align:center; color:#666; margin-bottom: 5px; font-size:13px;'><b>{wd}</b></div>", unsafe_allow_html=True)
    
    year = st.session_state.cal_month.year
    month = st.session_state.cal_month.month
    cal = calendar.monthcalendar(year, month)
    
    for week in cal:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].write("")
            else:
                date_str = f"{year}-{month:02d}-{day:02d}"
                count = note_counts.get(date_str, 0)
                
                # 若空间较小，有笔记的时直接显示带有修饰的数字
                btn_label = f"{day}"
                if count > 0:
                    btn_label = f"📝"
                
                is_selected = (st.session_state.note_selected_date == date_str)
                btn_type = "primary" if is_selected else "secondary"
                    
                if cols[i].button(btn_label, key=f"cal_{date_str}", type=btn_type, use_container_width=True, help=f"{date_str} ({count}条记录)" if count>0 else date_str):
                    if st.session_state.note_selected_date == date_str:
                        st.session_state.note_selected_date = None 
                    else:
                        st.session_state.note_selected_date = date_str
                    st.rerun()
    
    st.write("")
    if st.session_state.note_selected_date:
        st.info(f"📅 已选: **{st.session_state.note_selected_date}**")
        if st.button("❌ 取消按日筛选", use_container_width=True):
            st.session_state.note_selected_date = None
            st.rerun()
    elif not note_counts:
        st.info("💡 暂无笔记，在右侧记录您的交易心得吧！")

with col_right:
    # ====== 中部：发布与搜索 ======
    tab1, tab2 = st.tabs(["✍️ 发布笔记", "🔍 发现与搜索"])

    with tab1:
        with st.container(border=True):
            st.markdown("**发布新笔记**")
            note_content = st.text_area("发生了什么？记录你的思考、逻辑与情绪...", height=150, help="支持 Markdown，统一排版字体。")

            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                selected_tags = st.multiselect("选择常用标签", preset_tags)
            with col2:
                custom_tags_str = st.text_input("自定义标签 (多个用逗号分隔)", placeholder="例如：缩量, 超跌")
            with col3:
                st.write("")
                st.write("")
                is_public = st.toggle("🌍 公开可见", value=False, help="若公开，平台其他用户在'发现'中也能看到您的洞察。")

            if st.button("🚀 立即发布", type="primary"):
                if not note_content.strip():
                    st.error("笔记内容不能为空哦！")
                else:
                    final_tags = list(selected_tags)
                    if custom_tags_str.strip():
                        # 处理中英文逗号
                        custom_tags_str = custom_tags_str.replace("，", ",")
                        custom_tags = [t.strip() for t in custom_tags_str.split(',') if t.strip()]
                        final_tags.extend(custom_tags)

                    final_tags = list(set(final_tags))
                    tags_json = json.dumps(final_tags, ensure_ascii=False)

                    date_str = datetime.now().strftime("%Y-%m-%d")

                    success, msg = db.add_trading_note(uid, note_content, tags_json, is_public, date_str)
                    if success:
                        st.success("发布成功！")
                        st.session_state.note_selected_date = None # 清除日期筛选以便看到最新笔记
                        st.rerun()
                    else:
                        st.error(msg)

    with tab2:
        search_col1, search_col2, search_col3 = st.columns([1, 2, 1])
        with search_col1:
            view_mode = st.radio("查看范围", ["📓 我的笔记", "🌍 全站公开"], horizontal=False)
        with search_col2:
            search_kw = st.text_input("搜索关键字...")
        with search_col3:
            filter_tags = st.multiselect("按标签筛选", preset_tags)

    st.markdown("---")

    # ====== 底部：信息流展示 ======

    if view_mode == "🌍 全站公开":
        df_notes = db.get_trading_notes(is_public=True)
    else:
        df_notes = db.get_trading_notes(uid=uid, date_str=st.session_state.note_selected_date)

    if df_notes.empty:
        if st.session_state.note_selected_date:
            st.info("所选日期没有笔记。")
        else:
            st.info("这里空空如也，什么也没有找到。")
    else:
        # 前端搜索与过滤
        if search_kw:
            df_notes = df_notes[df_notes['content'].str.contains(search_kw, case=False, na=False)]

        if filter_tags:
            def match_tags(tags_str):
                if not tags_str: return False
                try:
                    tags_list = json.loads(tags_str)
                    # 只要包一个所选标签即可 (OR逻辑)
                    return any(t in tags_list for t in filter_tags)
                except:
                    return False
            df_notes = df_notes[df_notes['tags'].apply(match_tags)]

        st.subheader(f"共找到 {len(df_notes)} 条笔记")

        for idx, row in df_notes.iterrows():
            with st.container(border=True):
                header_col1, header_col2, header_col3 = st.columns([6, 3, 1])
                with header_col1:
                    # 统一显示用户名、时间和隐私状态
                    privacy_icon = "🌍 公开" if row['is_public'] else "🔒 私密"
                    author_name = row['username'] if row['username'] else "未知用户"
                    st.caption(f"**{author_name}** · 发布于 {row['created_at'].strftime('%Y-%m-%d %H:%M')} · {privacy_icon}")

                with header_col2:
                    # 渲染标签
                    if row['tags']:
                        try:
                            tags_list = json.loads(row['tags'])
                            if tags_list:
                                tag_html = "".join([f"<span style='background-color:#E3F2FD; color:#1565C0; padding:4px 10px; border-radius:12px; margin-right:6px; font-size:12px; font-weight:500;'>{t}</span>" for t in tags_list])
                                st.markdown(f"<div style='text-align: right; margin-top: -5px;'>{tag_html}</div>", unsafe_allow_html=True)
                        except:
                            pass

                with header_col3:
                    if row['uid'] == uid:
                        if st.button("🗑️", key=f"del_{row['id']}", help="删除该笔记", use_container_width=True):
                            if db.delete_trading_note(row['id'], uid):
                                st.rerun()

                # 正文内容：强制应用系统统一字体，不随 markdown 改变基础字体
                st.markdown(f"<div style='font-family: inherit; font-size: 15px; line-height: 1.6; padding: 10px 0;'>\n\n{row['content']}\n\n</div>", unsafe_allow_html=True)

                # --- 评论区 ---
                if row['is_public']:
                    with st.expander("💬 评论交流", expanded=False):
                        comments_df = db.get_note_comments(row['id'])

                        if not comments_df.empty:
                            for _, c_row in comments_df.iterrows():
                                c_author = c_row['username'] if c_row['username'] else "未知用户"
                                col_c1, col_c2 = st.columns([9, 1])
                                with col_c1:
                                    st.markdown(f"<div style='font-size:13px; color:#666;'><b>{c_author}</b> · {c_row['created_at'].strftime('%Y-%m-%d %H:%M')}</div>", unsafe_allow_html=True)
                                    st.markdown(f"<div style='background-color:#f8f9fa; padding:8px 12px; border-radius:8px; margin-bottom:10px; font-size:14px; color:#333;'>{c_row['content']}</div>", unsafe_allow_html=True)
                                with col_c2:
                                    if c_row['uid'] == uid:
                                        if st.button("🗑️", key=f"del_c_{c_row['id']}", help="删除评论"):
                                            if db.delete_note_comment(c_row['id'], uid):
                                                st.rerun()
                        else:
                            st.markdown(f"<div style='font-size:14px; color:#888; margin-bottom:10px;'>暂无评论，来抢沙发吧！</div>", unsafe_allow_html=True)

                        # 评论输入框
                        col_in1, col_in2 = st.columns([5, 1])
                        with col_in1:
                            new_comment = st.text_input("写下你的想法...", key=f"comment_input_{row['id']}", label_visibility="collapsed")
                        with col_in2:
                            if st.button("发送", key=f"comment_btn_{row['id']}", use_container_width=True):
                                if new_comment.strip():
                                    success, msg = db.add_note_comment(row['id'], uid, new_comment)
                                    if success:
                                        st.rerun()
                                    else:
                                        st.error(msg)
                                else:
                                    st.warning("内容不能为空")
