import streamlit as st
import time
import pandas as pd
from utils import get_db, get_cached_stock_name, inject_custom_css, check_authentication, render_sidebar

st.set_page_config(page_title="历史复盘 - AI 智能投顾", layout="wide")
inject_custom_css()
check_authentication()
render_sidebar()

db = get_db()
st.title("📅 历史复盘 (每日收盘建议)")
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
