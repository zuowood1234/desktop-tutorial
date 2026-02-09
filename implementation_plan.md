# A股短线交易助手 - 实施计划

## 阶段一：MVP 原型验证 (已完成)
- [x] **环境准备**：安装 Python, AkShare, DeepSeek SDK。
- [x] **核心脚本**：编写 `main.py` 实现行情抓取 + AI 分析。
- [x] **用户验证**：用户配置 API Key 并成功运行脚本，确认建议质量。

## 阶段二：网页可视化 (Streamlit) (已完成)
- [x] **搭建前端**：使用 Streamlit 搭建了完整的 Web 界面。
- [x] **用户系统**：实现了注册、登录、权限管理（Admin/User）。
- [x] **功能模块**：
    - **自选股**：支持批量添加、标签管理。
    - **实时分析**：支持全量分析自选股，展示技术/情绪双重评分。
    - **每日建议**：自动归档并随时回看每日建议。

## 阶段三：回测系统开发 (已完成)
- [x] **历史数据获取**：实现了批量抓取和本地缓存。
- [x] **回测引擎**：
    - **双策略对比**：技术派 vs 情绪增强派。
    - **年度长跑**：支持 365 天全量回测。
- [x] **结果分析**：
    - 生成年度 ROI 对比表。
    - 计算 Alpha 超额收益。
    - 前端展示“英雄榜”及详细 CSV 报告下载。

## 阶段四：数据库迁移 (SQLite -> Supabase) (已完成)
- [x] **环境准备**：
    - [x] 注册 Supabase 账号并创建 Project。
    - [x] 获取 `SUPABASE_URL` 和 `SUPABASE_KEY`。
    - [x] 安装 `supabase` Python 客户端 (`pip install supabase`).
- [x] **数据库设计 (PostgreSQL)**：
    - [x] `users`: 迁移用户表结构。
    - [x] `watchlist`: 迁移自选股表结构。
    - [x] `daily_recommendations`: 迁移建议历史表。
    - [x] `token_logs`: 迁移 Token 消耗日志。
- [x] **数据迁移**：
    - [x] 编写 `migrate_to_supabase.py` 脚本。
    - [x] 读取本地 `investor_assistant.db` 数据。
    - [x] 写入 Supabase 远程数据库。
- [x] **代码改造**：
    - [x] 重构 `database.py`：用 Supabase Client 替换 SQLite 逻辑。
    - [x] 验证所有 Web 功能（登录、添加自选、查看记录）是否正常。

## 阶段五：自动化与部署 (后续规划)
- [ ] **GitHub Actions**：配置每日定时任务（收盘后自动运行分析）。
- [ ] **云端部署**：尝试部署到 Streamlit Cloud 或其他云平台。
