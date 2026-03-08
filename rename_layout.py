import codecs

with codecs.open('pages/6_📓_交易笔记.py', 'r', 'utf-8') as f:
    lines = f.readlines()

col_right_content = []
# Start from line index 104 (st.markdown("---"))
for line in lines[104:]:
    if line.strip() == 'st.markdown("---")' and not col_right_content:
        continue # skip the first divider
    if line.strip() == "":
        col_right_content.append("\n")
    else:
        col_right_content.append("    " + line)

new_code = "".join(lines[:24]) + """
# ====== 页面布局拆分 ======
col_left, col_right = st.columns([2.5, 7.5], gap="large")

with col_left:
    st.subheader("🗓️ 交易日历")
    
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
""" + "".join(col_right_content)

with codecs.open('pages/6_📓_交易笔记.py', 'w', 'utf-8') as f:
    f.write(new_code)
