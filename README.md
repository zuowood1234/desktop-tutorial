# 🤖 AI 智能投顾系统

一个基于 DeepSeek AI 的 A 股短线交易辅助系统，支持实时分析、历史回测和策略对比。

## ✨ 核心功能

- 📊 **实时分析**：双策略 AI 分析（技术派 + 情绪增强派）
- ⭐ **自选股管理**：支持标签分类和批量导入
- 📅 **每日建议**：自动分析并保存历史建议
- 📈 **历史回测**：365 天长期回测，支持策略对比
- 👑 **用户系统**：多用户支持、权限管理、Token 统计
- 🔄 **自动化任务**：每日自动分析所有自选股

## 🚀 快速开始

### 本地部署

1. **克隆项目**
   ```bash
   git clone https://github.com/yourusername/desktop-tutorial.git
   cd desktop-tutorial
   ```

2. **运行部署脚本**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

3. **配置环境变量**
   编辑 `.env` 文件，填入您的 DeepSeek API Key：
   ```env
   DEEPSEEK_API_KEY=your_api_key_here
   DEEPSEEK_BASE_URL=https://api.deepseek.com
   ```

4. **启动应用**
   ```bash
   source venv/bin/activate
   streamlit run app.py
   ```

5. **访问应用**
   打开浏览器访问：http://localhost:8501

### 首次使用

1. **注册账号**
   - 访问应用后点击"新用户注册"
   - 用户名为 `admin` 将自动获得管理员权限

2. **添加自选股**
   - 进入"⭐ 我的自选"页面
   - 批量导入股票代码（支持逗号或换行分隔）

3. **开始分析**
   - 进入"📊 实时分析"页面
   - 选择自选股或手动输入代码
   - 点击"开始分析"获取 AI 建议

## 🌐 在线部署

项目支持部署到多个云平台，详细步骤请查看 [DEPLOY.md](./DEPLOY.md)

### 推荐部署方案

1. **Streamlit Cloud**（最简单）
   - 免费、一键部署
   - 适合个人项目和小规模使用

2. **Railway**（功能强大）
   - 支持持久化存储
   - 适合生产环境

3. **自建服务器**
   - 完全控制
   - 适合企业部署

## 📊 本地回测

项目支持在本地运行长时间回测任务：

```bash
# 运行批量回测（365天）
python batch_backtest_compare_fast.py

# 查看回测结果
# 结果保存在 backtest_summary_advanced.csv
```

**回测说明**：
- 本地回测结果会保存到 CSV 文件
- Web 应用可以读取并展示这些结果
- 建议在本地运行长时间回测，然后同步结果到云端

## 🏗️ 项目结构

```
desktop-tutorial/
├── app.py                    # Streamlit 主应用
├── main.py                   # 核心分析引擎
├── backtest.py              # 回测引擎
├── database.py              # 数据库管理
├── auto_daily_analysis.py   # 每日自动分析
├── batch_backtest_*.py      # 批量回测脚本
├── requirements.txt         # 依赖列表
├── DEPLOY.md                # 部署指南
└── .env                     # 环境变量（不提交）
```

## 🔧 技术栈

- **前端**：Streamlit
- **后端**：Python 3.11+
- **数据库**：SQLite（可迁移到 PostgreSQL）
- **AI**：DeepSeek API
- **数据源**：AkShare

## 📝 功能说明

### 双策略分析

- **纯技术派**：基于技术指标（MACD、RSI、KDJ、均线）
- **情绪增强派**：技术 + 大盘情绪 + 量比分析

### 回测系统

- 支持 365 天长期回测
- 双策略对比（技术派 vs 情绪派）
- 生成详细回测报告和资金曲线

### 用户系统

- 多用户注册/登录
- 管理员权限管理
- Token 消耗统计
- 用户状态管理（启用/禁用）

## ⚙️ 配置说明

### 环境变量

`.env` 文件配置：

```env
# DeepSeek API
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

### 数据库

首次运行会自动创建 SQLite 数据库 `investor_assistant.db`。

**生产环境建议**：迁移到 PostgreSQL（Supabase/Railway）

## 🐛 常见问题

### Q: API 调用失败？
A: 检查 `.env` 文件中的 API Key 是否正确，网络是否正常。

### Q: 回测结果文件找不到？
A: 确保回测脚本已运行并生成 CSV 文件，或手动上传结果文件。

### Q: 数据库文件丢失？
A: 使用持久化存储（Railway Volume）或迁移到云端数据库。

## 📄 许可证

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📞 联系方式

- GitHub Issues: [项目 Issues](https://github.com/yourusername/desktop-tutorial/issues)
- 文档: [DEPLOY.md](./DEPLOY.md)

---

**⚠️ 免责声明**：本系统仅供学习和研究使用，不构成投资建议。投资有风险，入市需谨慎。
