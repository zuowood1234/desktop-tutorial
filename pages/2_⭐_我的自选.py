import streamlit as st
import time
import re
from utils import get_db, get_cached_stock_name, inject_custom_css, check_authentication, render_sidebar

st.set_page_config(page_title="我的自选 - AI 智能投顾", layout="wide")
inject_custom_css()
check_authentication()
render_sidebar()

db = get_db()
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
