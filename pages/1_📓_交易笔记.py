import streamlit as st
import pandas as pd
import json
from datetime import datetime, date, timedelta
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

# 颜色映射
COLOR_MAP = {
    "blue":   {"bg": "#DBEAFE", "border": "#3B82F6", "text": "#1E40AF", "emoji": "🔵"},
    "red":    {"bg": "#FEE2E2", "border": "#EF4444", "text": "#991B1B", "emoji": "🔴"},
    "orange": {"bg": "#FEF3C7", "border": "#F59E0B", "text": "#92400E", "emoji": "🟠"},
    "green":  {"bg": "#D1FAE5", "border": "#10B981", "text": "#065F46", "emoji": "🟢"},
    "purple": {"bg": "#EDE9FE", "border": "#8B5CF6", "text": "#4C1D95", "emoji": "🟣"},
}

import calendar

# ---- Session State 初始化 ----
if 'note_selected_date' not in st.session_state:
    st.session_state.note_selected_date = None
if 'cal_month' not in st.session_state:
    today = datetime.now()
    st.session_state.cal_month = pd.Timestamp(today.year, today.month, 1)
if 'show_month_picker' not in st.session_state:
    st.session_state.show_month_picker = False

# ====== 数据加载 ======
# 日历热力图：显示自己所有笔记 + 他人公开笔记的计数
heatmap_df = db.get_all_visible_notes_heatmap(uid)
note_counts = {}
if not heatmap_df.empty:
    for _, row in heatmap_df.iterrows():
        note_counts[row['date']] = row['count']

events_df = db.get_calendar_events(uid)

# 构建 event_map: {date_str: [(title, color, is_mine), ...]}
event_map = {}
if not events_df.empty:
    for _, ev in events_df.iterrows():
        try:
            start = datetime.strptime(ev['start_date'], "%Y-%m-%d").date()
            end = datetime.strptime(ev['end_date'], "%Y-%m-%d").date()
            cur = start
            while cur <= end:
                d_str = cur.strftime("%Y-%m-%d")
                if d_str not in event_map:
                    event_map[d_str] = []
                event_map[d_str].append({
                    "title": ev['title'],
                    "color": ev['color'],
                    "is_mine": ev['uid'] == uid,
                    "is_public": ev['is_public'],
                    "username": ev['username'],
                    "event_id": ev['id'],
                })
                cur += timedelta(days=1)
        except:
            pass

# ====== 顶部：交易日历（全宽）======
st.subheader("🗓️ 交易日历")

st.markdown("""
<style>
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

# 月份导航
nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([1, 3, 3, 1])
with nav_col1:
    if st.button("⬅️", use_container_width=True, help="上个月"):
        st.session_state.cal_month -= pd.DateOffset(months=1)
        st.rerun()
with nav_col2:
    if st.button(f"{st.session_state.cal_month.year}年 {st.session_state.cal_month.month}月",
                 use_container_width=True, help="点击切换年月"):
        st.session_state.show_month_picker = not st.session_state.show_month_picker
        st.rerun()
with nav_col3:
    if st.session_state.note_selected_date:
        st.info(f"📅 已选: **{st.session_state.note_selected_date}**")
with nav_col4:
    if st.button("➡️", use_container_width=True, help="下个月"):
        st.session_state.cal_month += pd.DateOffset(months=1)
        st.rerun()

if st.session_state.show_month_picker:
    with st.container(border=True):
        pick_col1, pick_col2, pick_col3 = st.columns([2, 2, 1])
        with pick_col1:
            sel_year = st.selectbox("年份", range(2024, 2035),
                                    index=range(2024, 2035).index(st.session_state.cal_month.year),
                                    label_visibility="collapsed")
        with pick_col2:
            sel_month = st.selectbox("月份", range(1, 13),
                                     index=st.session_state.cal_month.month - 1,
                                     label_visibility="collapsed")
        with pick_col3:
            if st.button("跳转", use_container_width=True, type="primary"):
                st.session_state.cal_month = pd.Timestamp(sel_year, sel_month, 1)
                st.session_state.show_month_picker = False
                st.rerun()

# 星期头
weekdays = ["一", "二", "三", "四", "五", "六", "日"]
hdr_cols = st.columns(7)
for i, wd in enumerate(weekdays):
    hdr_cols[i].markdown(
        f"<div style='text-align:center; color:#888; font-size:13px; margin-bottom:4px'><b>{wd}</b></div>",
        unsafe_allow_html=True
    )

year = st.session_state.cal_month.year
month = st.session_state.cal_month.month
cal = calendar.monthcalendar(year, month)

for week in cal:
    week_cols = st.columns(7)
    for i, day in enumerate(week):
        if day == 0:
            week_cols[i].write("")
        else:
            date_str = f"{year}-{month:02d}-{day:02d}"
            count = note_counts.get(date_str, 0)
            events_today = event_map.get(date_str, [])
            is_selected = (st.session_state.note_selected_date == date_str)

            # 构建 label 和 tooltip
            label = f"{day}"
            if count > 0:
                label = "📝"

            if events_today:
                first_ev_color = events_today[0]["color"]
                ev_titles = " | ".join([e["title"] for e in events_today])
                tooltip = f"{date_str} · {ev_titles}" + (f" · {count}条笔记" if count > 0 else "")
                # 叠加颜色图标可见性
                color_dot = COLOR_MAP.get(first_ev_color, COLOR_MAP["blue"])["emoji"]
                label = f"{color_dot}{day}" if count == 0 else f"{color_dot}📝"
            else:
                tooltip = f"{date_str}" + (f" ({count}条记录)" if count > 0 else "")

            btn_type = "primary" if is_selected else "secondary"
            if week_cols[i].button(label, key=f"cal_{date_str}", type=btn_type,
                                   use_container_width=True, help=tooltip):
                if st.session_state.note_selected_date == date_str:
                    st.session_state.note_selected_date = None
                else:
                    st.session_state.note_selected_date = date_str
                st.rerun()

# 本月事件图例
month_events = [ev for ev in events_df.itertuples()
                if not events_df.empty and hasattr(ev, 'start_date')
                and ev.start_date[:7] == f"{year}-{month:02d}"
                or (hasattr(ev, 'end_date') and ev.end_date[:7] == f"{year}-{month:02d}")] \
    if not events_df.empty else []

if not events_df.empty:
    this_month_mask = (
        events_df['start_date'].str[:7] == f"{year}-{month:02d}"
    ) | (
        events_df['end_date'].str[:7] == f"{year}-{month:02d}"
    )
    month_events_df = events_df[this_month_mask]
    if not month_events_df.empty:
        legend_parts = []
        for _, mev in month_events_df.iterrows():
            c = COLOR_MAP.get(mev['color'], COLOR_MAP['blue'])
            priv = "🌍" if mev['is_public'] else "🔒"
            legend_parts.append(
                f"<span style='background:{c['bg']};border:1px solid {c['border']};color:{c['text']};"
                f"padding:3px 10px;border-radius:12px;margin-right:8px;font-size:12px;'>"
                f"{c['emoji']} {mev['title']} {mev['start_date'][5:]} ~ {mev['end_date'][5:]} {priv}</span>"
            )
        st.markdown("<div style='margin-top:8px;'>" + "".join(legend_parts) + "</div>", unsafe_allow_html=True)

st.markdown("---")

# ====== 中部：选中日期详情 ======
if st.session_state.note_selected_date:
    sel_date = st.session_state.note_selected_date
    date_events = event_map.get(sel_date, [])
    # 加载自己的笔记 + 他人公开的笔记
    date_notes_df = db.get_notes_for_date_visible(uid, sel_date)

    cols_mid = st.columns([1, 9])
    with cols_mid[0]:
        if st.button("❌", help="取消日期筛选"):
            st.session_state.note_selected_date = None
            st.rerun()
    with cols_mid[1]:
        st.markdown(f"**📅 {sel_date} 的事件与笔记**")

    if date_events:
        ev_cols = st.columns(min(len(date_events), 4))
        for i, ev in enumerate(date_events):
            c = COLOR_MAP.get(ev["color"], COLOR_MAP["blue"])
            priv_label = "🌍 公开" if ev["is_public"] else "🔒 私密"
            with ev_cols[i % 4]:
                st.markdown(
                    f"<div style='background:{c['bg']};border:1px solid {c['border']};border-radius:10px;"
                    f"padding:10px 14px;margin-bottom:10px;'>"
                    f"<b style='color:{c['text']};'>{c['emoji']} {ev['title']}</b><br>"
                    f"<span style='font-size:12px;color:#666;'>by {ev['username']} · {priv_label}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
    else:
        st.caption("该日没有特殊事件标注")

    if not date_notes_df.empty:
        for _, row in date_notes_df.iterrows():
            is_own = (row['uid'] == uid)
            # 自己的笔记：普通白色边框；他人公开笔记：蓝色调背景
            border_style = "border: 1px solid #e0e0e0;" if is_own else "border: 1px solid #93C5FD; background: #EFF6FF;"
            with st.container():
                st.markdown(f"<div style='border-radius:10px; padding:12px 16px; margin-bottom:10px; {border_style}'>", unsafe_allow_html=True)
                h1, h2, h3 = st.columns([6, 3, 1])
                with h1:
                    privacy_icon = "🌍 公开" if row['is_public'] else "🔒 私密"
                    other_label = "" if is_own else " · <span style='color:#1D4ED8;font-weight:600;'>他人笔记</span>"
                    st.markdown(
                        f"<div style='font-size:13px;color:#555;'><b>{row['username']}</b> · "
                        f"{row['created_at'].strftime('%H:%M')} · {privacy_icon}{other_label}</div>",
                        unsafe_allow_html=True
                    )
                with h2:
                    if row['tags']:
                        try:
                            tags_list = json.loads(row['tags'])
                            if tags_list:
                                tag_html = "".join([
                                    f"<span style='background:#E3F2FD;color:#1565C0;padding:3px 8px;"
                                    f"border-radius:10px;margin-right:5px;font-size:12px;'>{t}</span>"
                                    for t in tags_list
                                ])
                                st.markdown(tag_html, unsafe_allow_html=True)
                        except:
                            pass
                with h3:
                    if is_own:
                        if st.button("🗑️", key=f"sel_del_{row['id']}", help="删除该笔记"):
                            if db.delete_trading_note(row['id'], uid):
                                st.rerun()
                st.markdown(
                    f"<div style='font-size:15px;line-height:1.6;padding:8px 0;'>{row['content']}</div>",
                    unsafe_allow_html=True
                )

                # 评论区（公开笔记才有评论）
                if row['is_public']:
                    comments_df = db.get_note_comments(row['id'])
                    comment_count = len(comments_df) if not comments_df.empty else 0

                    with st.expander(f"💬 评论 ({comment_count})", expanded=(comment_count > 0)):
                        if not comments_df.empty:
                            for _, c_row in comments_df.iterrows():
                                c_author = c_row['username'] if c_row['username'] else "未知用户"
                                col_c1, col_c2 = st.columns([9, 1])
                                with col_c1:
                                    st.markdown(
                                        f"<div style='font-size:13px;color:#666;'>"
                                        f"<b>{c_author}</b> · {c_row['created_at'].strftime('%m-%d %H:%M')}</div>",
                                        unsafe_allow_html=True
                                    )
                                    st.markdown(
                                        f"<div style='background:#f8f9fa;padding:8px 12px;border-radius:8px;"
                                        f"margin-bottom:8px;font-size:14px;color:#333;'>{c_row['content']}</div>",
                                        unsafe_allow_html=True
                                    )
                                with col_c2:
                                    if c_row['uid'] == uid:
                                        if st.button("🗑️", key=f"dc_del_{c_row['id']}", help="删除评论"):
                                            if db.delete_note_comment(c_row['id'], uid):
                                                st.rerun()
                        else:
                            st.caption("暂无评论")

                        # 发评论
                        col_in1, col_in2 = st.columns([5, 1])
                        with col_in1:
                            new_comment = st.text_input(
                                "写下你的想法...",
                                key=f"dc_comment_input_{row['id']}",
                                label_visibility="collapsed"
                            )
                        with col_in2:
                            if st.button("发送", key=f"dc_comment_btn_{row['id']}", use_container_width=True):
                                if new_comment.strip():
                                    ok, msg = db.add_note_comment(row['id'], uid, new_comment)
                                    if ok:
                                        st.rerun()
                                    else:
                                        st.error(msg)
                                else:
                                    st.warning("内容不能为空")

                st.markdown("</div>", unsafe_allow_html=True)


    else:
        st.caption("该日暂无笔记")


    st.markdown("---")

# ====== 下部：功能 Tabs ======
tab1, tab2, tab3 = st.tabs(["✍️ 发布笔记", "🗓️ 管理事件", "🔍 发现与搜索"])

# ---- Tab 1: 发布笔记 ----
with tab1:
    with st.container(border=True):
        st.markdown("**发布新笔记**")
        note_content = st.text_area("发生了什么？记录你的思考、逻辑与情绪...", height=120,
                                    help="支持 Markdown，统一排版字体。")
        col1, col2, col3 = st.columns([3, 2, 1])
        with col1:
            selected_tags = st.multiselect("选择常用标签", preset_tags)
        with col2:
            custom_tags_str = st.text_input("自定义标签 (逗号分隔)", placeholder="例如：缩量, 超跌")
        with col3:
            st.write("")
            st.write("")
            note_is_public = st.toggle("🌍 公开", value=False, help="公开后平台其他用户可见")

        if st.button("🚀 立即发布", type="primary"):
            if not note_content.strip():
                st.error("笔记内容不能为空哦！")
            else:
                final_tags = list(selected_tags)
                if custom_tags_str.strip():
                    custom_tags_str = custom_tags_str.replace("，", ",")
                    final_tags.extend([t.strip() for t in custom_tags_str.split(',') if t.strip()])
                final_tags = list(set(final_tags))
                tags_json = json.dumps(final_tags, ensure_ascii=False)
                date_str = datetime.now().strftime("%Y-%m-%d")
                success, msg = db.add_trading_note(uid, note_content, tags_json, note_is_public, date_str)
                if success:
                    st.success("发布成功！")
                    st.session_state.note_selected_date = None
                    st.rerun()
                else:
                    st.error(msg)

# ---- Tab 2: 管理事件 ----
with tab2:
    col_form, col_list = st.columns([4, 6])

    with col_form:
        with st.container(border=True):
            st.markdown("**➕ 添加新事件**")
            ev_title = st.text_input("事件标题", placeholder="例如：英伟达 GTC 会议")
            ev_col1, ev_col2 = st.columns(2)
            with ev_col1:
                ev_start = st.date_input("开始日期", value=date.today())
            with ev_col2:
                ev_end = st.date_input("结束日期", value=date.today())

            color_options = {"🔵 蓝色": "blue", "🔴 红色": "red", "🟠 橙色": "orange",
                             "🟢 绿色": "green", "🟣 紫色": "purple"}
            ev_color_label = st.selectbox("颜色", list(color_options.keys()))
            ev_color = color_options[ev_color_label]
            ev_is_public = st.toggle("🌍 公开给所有用户", value=False,
                                     help="公开后其他用户登录后也能在日历上看到此事件")

            if st.button("✅ 添加事件", type="primary", use_container_width=True):
                if not ev_title.strip():
                    st.error("事件标题不能为空")
                elif ev_end < ev_start:
                    st.error("结束日期不能早于开始日期")
                else:
                    ok, msg = db.add_calendar_event(
                        uid, ev_title.strip(),
                        ev_start.strftime("%Y-%m-%d"),
                        ev_end.strftime("%Y-%m-%d"),
                        ev_color, ev_is_public
                    )
                    if ok:
                        st.success("事件添加成功！")
                        st.rerun()
                    else:
                        st.error(msg)

    with col_list:
        st.markdown("**📌 我的事件列表**")
        if events_df.empty:
            st.info("暂无事件，在左侧添加吧！")
        else:
            my_events = events_df[events_df['uid'] == uid]
            public_others = events_df[(events_df['uid'] != uid) & (events_df['is_public'] == True)]

            if not my_events.empty:
                st.caption("🏷️ 我创建的事件")
                for _, ev in my_events.iterrows():
                    c = COLOR_MAP.get(ev['color'], COLOR_MAP['blue'])
                    priv = "🌍 公开" if ev['is_public'] else "🔒 私密"
                    erow1, erow2 = st.columns([8, 1])
                    with erow1:
                        st.markdown(
                            f"<div style='background:{c['bg']};border-left:4px solid {c['border']};"
                            f"padding:8px 12px;border-radius:6px;margin-bottom:6px;'>"
                            f"<b style='color:{c['text']};'>{c['emoji']} {ev['title']}</b> "
                            f"<span style='color:#888;font-size:12px;'>"
                            f"{ev['start_date'][5:]} ~ {ev['end_date'][5:]} · {priv}</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                    with erow2:
                        if st.button("🗑️", key=f"del_ev_{ev['id']}", help="删除该事件"):
                            if db.delete_calendar_event(ev['id'], uid):
                                st.rerun()

            if not public_others.empty:
                st.caption("🌍 其他用户的公开事件")
                for _, ev in public_others.iterrows():
                    c = COLOR_MAP.get(ev['color'], COLOR_MAP['blue'])
                    st.markdown(
                        f"<div style='background:{c['bg']};border-left:4px solid {c['border']};"
                        f"padding:8px 12px;border-radius:6px;margin-bottom:6px;'>"
                        f"<b style='color:{c['text']};'>{c['emoji']} {ev['title']}</b> "
                        f"<span style='color:#888;font-size:12px;'>"
                        f"{ev['start_date'][5:]} ~ {ev['end_date'][5:]} · by {ev['username']}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )

# ---- Tab 3: 发现与搜索 ----
with tab3:
    search_col1, search_col2, search_col3 = st.columns([1, 2, 1])
    with search_col1:
        view_mode = st.radio("查看范围", ["📓 我的笔记", "🌍 全站公开"], horizontal=False)
    with search_col2:
        search_kw = st.text_input("搜索关键字...")
    with search_col3:
        filter_tags = st.multiselect("按标签筛选", preset_tags)

    st.markdown("---")

    if view_mode == "🌍 全站公开":
        df_notes = db.get_trading_notes(is_public=True)
    else:
        df_notes = db.get_trading_notes(uid=uid)

    if df_notes.empty:
        st.info("这里空空如也，什么也没有找到。")
    else:
        if search_kw:
            df_notes = df_notes[df_notes['content'].str.contains(search_kw, case=False, na=False)]
        if filter_tags:
            def match_tags(tags_str):
                if not tags_str: return False
                try:
                    tags_list = json.loads(tags_str)
                    return any(t in tags_list for t in filter_tags)
                except:
                    return False
            df_notes = df_notes[df_notes['tags'].apply(match_tags)]

        st.subheader(f"共找到 {len(df_notes)} 条笔记")

        for idx, row in df_notes.iterrows():
            with st.container(border=True):
                header_col1, header_col2, header_col3 = st.columns([6, 3, 1])
                with header_col1:
                    privacy_icon = "🌍 公开" if row['is_public'] else "🔒 私密"
                    author_name = row['username'] if row['username'] else "未知用户"
                    st.caption(f"**{author_name}** · {row['created_at'].strftime('%Y-%m-%d %H:%M')} · {privacy_icon}")
                with header_col2:
                    if row['tags']:
                        try:
                            tags_list = json.loads(row['tags'])
                            if tags_list:
                                tag_html = "".join([
                                    f"<span style='background:#E3F2FD;color:#1565C0;padding:4px 10px;"
                                    f"border-radius:12px;margin-right:6px;font-size:12px;font-weight:500;'>{t}</span>"
                                    for t in tags_list
                                ])
                                st.markdown(
                                    f"<div style='text-align:right;margin-top:-5px;'>{tag_html}</div>",
                                    unsafe_allow_html=True
                                )
                        except:
                            pass
                with header_col3:
                    if row['uid'] == uid:
                        if st.button("🗑️", key=f"del_{row['id']}", help="删除该笔记", use_container_width=True):
                            if db.delete_trading_note(row['id'], uid):
                                st.rerun()

                st.markdown(
                    f"<div style='font-family:inherit;font-size:15px;line-height:1.6;padding:10px 0;'>"
                    f"\n\n{row['content']}\n\n</div>",
                    unsafe_allow_html=True
                )

                if row['is_public']:
                    with st.expander("💬 评论交流", expanded=False):
                        comments_df = db.get_note_comments(row['id'])
                        if not comments_df.empty:
                            for _, c_row in comments_df.iterrows():
                                c_author = c_row['username'] if c_row['username'] else "未知用户"
                                col_c1, col_c2 = st.columns([9, 1])
                                with col_c1:
                                    st.markdown(
                                        f"<div style='font-size:13px;color:#666;'>"
                                        f"<b>{c_author}</b> · {c_row['created_at'].strftime('%Y-%m-%d %H:%M')}</div>",
                                        unsafe_allow_html=True
                                    )
                                    st.markdown(
                                        f"<div style='background:#f8f9fa;padding:8px 12px;border-radius:8px;"
                                        f"margin-bottom:10px;font-size:14px;color:#333;'>{c_row['content']}</div>",
                                        unsafe_allow_html=True
                                    )
                                with col_c2:
                                    if c_row['uid'] == uid:
                                        if st.button("🗑️", key=f"del_c_{c_row['id']}", help="删除评论"):
                                            if db.delete_note_comment(c_row['id'], uid):
                                                st.rerun()
                        else:
                            st.markdown(
                                "<div style='font-size:14px;color:#888;margin-bottom:10px;'>暂无评论，来抢沙发吧！</div>",
                                unsafe_allow_html=True
                            )
                        col_in1, col_in2 = st.columns([5, 1])
                        with col_in1:
                            new_comment = st.text_input("写下你的想法...", key=f"comment_input_{row['id']}",
                                                        label_visibility="collapsed")
                        with col_in2:
                            if st.button("发送", key=f"comment_btn_{row['id']}", use_container_width=True):
                                if new_comment.strip():
                                    ok, msg = db.add_note_comment(row['id'], uid, new_comment)
                                    if ok:
                                        st.rerun()
                                    else:
                                        st.error(msg)
                                else:
                                    st.warning("内容不能为空")
