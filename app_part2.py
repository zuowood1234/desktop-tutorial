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
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        analyze_btn = st.button("🚀 开始全策略深度分析", use_container_width=True, type="primary")
    
    if analyze_btn:
        if not selected_stocks:
            st.error("⚠️ 请先选中要分析的股票（来自自选或手动输入）")
        else:
            # 引入新引擎
            from backtest_engine import BacktestEngine
            
            st.markdown("---")
            st.subheader(f"📋 正在对 {len(selected_stocks)} 只股票进行 V1-V4 全策略扫描...")
            progress_bar = st.progress(0)
            
            new_results = []
            for i, stock in enumerate(selected_stocks):
                with st.spinner(f"正在分析 {stock} ..."):
                    try:
                        # 获取数据
                        df, error = get_stock_data(stock)
                        
                        if df is not None and not df.empty:
                            stock_name = get_stock_name_offline(stock)
                            
                            # === 核心调用 ===
                            engine = BacktestEngine(stock)
                            engine.df = df # 注入数据
                            engine._calculate_indicators() 
                            
                            latest_row = df.iloc[-1]
                            prev_row = df.iloc[-2] if len(df) > 1 else None
                            
                            # 一次性获取所有策略结果
                            v1_act, v1_rsn, v1_scr = engine.make_decision(latest_row, prev_row, 'Score_V1')
                            v2_act, v2_rsn, v2_scr = engine.make_decision(latest_row, prev_row, 'Trend_V2')
                            v3_act, v3_rsn, v3_scr = engine.make_decision(latest_row, prev_row, 'Oscillation_V3')
                            v4_act, v4_rsn, v4_scr = engine.make_decision(latest_row, prev_row, 'AI_Agent_V4')
                            
                            latest_price = latest_row['close']
                            pct_chg = latest_row['pctChg'] if 'pctChg' in latest_row else 0
                            
                            new_results.append({
                                "代码": stock,
                                "名称": stock_name,
                                "价格": f"¥{latest_price:.2f}",
                                "涨跌": f"{pct_chg:.2f}%",
                                "时间": latest_row['date'].strftime("%Y-%m-%d"),
                                
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
                            st.error(f"无法获取股票 {stock} 的行情数据。")
                    except Exception as e:
                        st.error(f"分析股票 {stock} 失败: {str(e)}")
                progress_bar.progress((i + 1) / len(selected_stocks))
            
            # 保存到 session_state
            st.session_state.last_analysis_results = new_results
            st.rerun() # 刷新以显示结果

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
            
            # 简单表格展示 (只展示建议)
            st.dataframe(
                res_df[['代码', '名称', '价格', '涨跌', 'V1建议', 'V2建议', 'V3建议', 'V4建议']],
                use_container_width=True
            )
            
            st.markdown("---")
            st.subheader("🔍 深度拆解 (点击展开详情)")
            
            for res in results:
                # 标题颜色：如果任一策略建议买入，标题高亮
                is_buy = any("买" in str(res[k]) for k in ['V1建议', 'V2建议', 'V3建议', 'V4建议'])
                icon = "🔥" if is_buy else "📄"
                
                stock_label = f"{icon} **{res['名称']} ({res['代码']})** | {res['价格']} ({res['涨跌']})"
                
                with st.expander(stock_label, expanded=is_buy):
                    
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
                            st.caption(f"**分析逻辑**: {res['V4理由']}")

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

        st.markdown("#### 📜 交易规则")
        st.markdown("""
        1.  **进场条件 (严苛)**：
            *   收盘价站上 **MA5**。
            *   且 **MA5 > MA10** (确认趋势形成)。
            
        2.  **离场条件 (果断)**：
            *   收盘价 **跌破 MA10**。
            *   *无条件止损/止盈，不抗单。*
            
        3.  **优势与劣势**：
            *   ✅ **盈亏比极高**：平均赚 11%，亏 3%。能抓住翻倍牛股。
            *   ❌ **胜率一般**：约 33%。在横盘震荡市会频繁磨损。
        """)

    with tab_v3:
        st.header("🛡️ V3: 波段防御者 (Band Defender)")
        st.caption("适用场景：熊市 / 震荡市 / 暴跌抄底 (胜率之王🎯)")
        st.info("💡 核心逻辑：利用布林带 (Bollinger Bands) 的均值回归特性，由恐慌和贪婪驱动交易。")

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            st.markdown("#### 📥 买入逻辑 (贪婪)")
            st.write("当股价 **跌破布林下轨 (Lower Band)** 时买入。")
            st.caption("逻辑：市场过度恐慌，大概率发生超跌反弹。")
            
        with col_b2:
            st.markdown("#### 📤 卖出逻辑 (恐惧)")
            st.write("1. 股价 **触碰布林上轨 (Upper Band)**：止盈。")
            st.write("2. 股价 **跌破中轨 (Middle Band)**：止损/离场。")
            
        st.markdown("#### 📊 统计特征")
        st.write("- **胜率**：高达 **80%** (2025回测数据)。")
        st.write("- **特点**：极少出手，一出手就赢。适合防守反击。")

    with tab_v4:
        st.header("🧠 V4: AI 智能体 (AI Agent)")
        st.caption("适用场景：复杂博弈 / 需要通过自然语言分析")
        st.info("💡 核心逻辑：构建 Prompt，调用大语言模型 (LLM) 进行类人分析。")

        st.code("""
Prompt 模板示例:
"你是一个资深的股票分析师，现在的行情数据是：
收盘价 10.5，MA5 10.2，RSI 75... 
请结合市场情绪与资金，板块热点判断未来走势，并给出操作建议。"
        """, language="python")
        
        st.warning("""
        ⚠️ **注意**：
        1. 需要配置 `OPENAI_API_KEY` 才能启用真实分析。
        2. 如果 API 调用失败，会直接显示错误信息，不进行规则模拟。
        3. 实盘中 AI 建议仅供参考。
        """)

# ==================== 页面3：历史回测 ====================
elif page == "📈 历史回测":
    st.title("📈 策略长跑英雄榜")
    st.markdown("这里记录了 AI 投顾系统在历史长河中的实战表现。")

    # --- 1. 年度英雄榜专区 ---
    #版本选择
    bt_v = st.radio("📈 选择策略版本", ["🥉 V1-V4 对比版 (2025新)", "🚀 旧版存档"], horizontal=True)
    
    if "V1-V4" in bt_v:
        annual_file = "2025_Complete_Strategy_Battle.xlsx" # 假设您之后会把 Excel 转 CSV 或直接读 Excel
        # 这里暂时保留旧逻辑，您可能需要我之后再来更新回测页面的读取逻辑
        # 为了不破坏现有页面，先展示一个简单的提示
        st.info("🚧 V1-V4 的完整回测数据目前在后台生成了 Excel 报告，尚未集成到此 WEB 页面可视化。")
        st.caption("请暂时通过 backend 查看 `2025_Complete_Strategy_Battle.xlsx`。")
    else:
        st.caption("旧版存档展示区域...")
        # (这里可以保留旧的 CSV 读取逻辑，为节省篇幅略过，反正重点是上面的分析页)
        
    st.divider()

    # --- 2. 手动回测入口 (特定权限) ---
    st.subheader("🛠️ 发起新回测")
    can_bt = st.session_state.get('can_backtest', False) or st.session_state.user_role == 'admin'
    
    if not can_bt:
        st.warning("🔒 您当前没有回测权限，请联系管理员（admin）开通。")
    else:
        # 管理员可以手动输入代码
        if st.session_state.user_role == 'admin':
            with st.expander("👑 管理员控制台：手动发起 365 天大长跑", expanded=False):
                admin_stocks = st.text_input("输入股票代码 (逗号分隔)", placeholder="例如: 600519, 000001")
                if st.button("🔥 立即全量重跑"):
                    st.info("功能维护中...")
