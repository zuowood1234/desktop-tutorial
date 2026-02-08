# 🚀 项目部署指南

本项目可以部署到多个云平台，支持本地回测和在线访问。

## 📋 部署前准备

### 1. 环境变量配置

创建 `.env` 文件（**不要提交到 Git**）：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

### 2. 数据库初始化

项目使用 SQLite 数据库，首次运行会自动创建。部署到云端时，数据库文件会持久化存储。

## 🌐 部署方案

### 方案一：Streamlit Cloud（推荐 - 最简单）

**优点**：免费、一键部署、自动更新

**步骤**：

1. **准备 GitHub 仓库**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/desktop-tutorial.git
   git push -u origin main
   ```

2. **部署到 Streamlit Cloud**
   - 访问 https://share.streamlit.io
   - 使用 GitHub 账号登录
   - 点击 "New app"
   - 选择仓库和分支
   - **Main file path**: `app.py`
   - **App URL**: 自动生成（如 `your-app.streamlit.app`）

3. **配置环境变量**
   - 在 Streamlit Cloud 的 Settings → Secrets 中添加：
   ```toml
   DEEPSEEK_API_KEY = "your_api_key"
   DEEPSEEK_BASE_URL = "https://api.deepseek.com"
   ```

4. **部署完成**
   - 应用会自动部署并生成公开 URL
   - 每次 push 代码会自动更新

**注意事项**：
- 免费版有资源限制（CPU/内存）
- 数据库文件存储在临时文件系统（重启可能丢失）
- 建议使用外部数据库（如 Supabase）用于生产环境

---

### 方案二：Railway（推荐 - 功能强大）

**优点**：支持持久化存储、数据库、更灵活

**步骤**：

1. **创建 `Procfile`**
   ```
   web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
   ```

2. **创建 `runtime.txt`**（指定 Python 版本）
   ```
   python-3.11.0
   ```

3. **部署到 Railway**
   - 访问 https://railway.app
   - 使用 GitHub 登录
   - 点击 "New Project" → "Deploy from GitHub repo"
   - 选择仓库
   - Railway 会自动检测并部署

4. **配置环境变量**
   - 在 Railway 项目设置中添加环境变量
   - `DEEPSEEK_API_KEY`
   - `DEEPSEEK_BASE_URL`

5. **配置持久化存储**（可选）
   - 添加 Volume 用于存储数据库文件
   - 挂载到 `/app/data` 目录

**费用**：免费额度 $5/月，超出后按量付费

---

### 方案三：Heroku

**步骤**：

1. **创建 `Procfile`**
   ```
   web: streamlit run app.py --server.port=$PORT --server.address=0.0.0.0
   ```

2. **创建 `runtime.txt`**
   ```
   python-3.11.0
   ```

3. **安装 Heroku CLI**
   ```bash
   # macOS
   brew tap heroku/brew && brew install heroku
   ```

4. **部署**
   ```bash
   heroku login
   heroku create your-app-name
   heroku config:set DEEPSEEK_API_KEY=your_key
   heroku config:set DEEPSEEK_BASE_URL=https://api.deepseek.com
   git push heroku main
   ```

**注意**：Heroku 免费版已停止，需要付费计划

---

### 方案四：自建服务器（VPS）

**步骤**：

1. **服务器要求**
   - Ubuntu 20.04+
   - 2GB+ RAM
   - Python 3.8+

2. **安装依赖**
   ```bash
   sudo apt update
   sudo apt install python3-pip python3-venv nginx
   ```

3. **部署应用**
   ```bash
   git clone https://github.com/yourusername/desktop-tutorial.git
   cd desktop-tutorial
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **使用 systemd 运行**
   创建 `/etc/systemd/system/streamlit-app.service`:
   ```ini
   [Unit]
   Description=Streamlit App
   After=network.target

   [Service]
   Type=simple
   User=your_user
   WorkingDirectory=/path/to/desktop-tutorial
   Environment="PATH=/path/to/desktop-tutorial/venv/bin"
   ExecStart=/path/to/desktop-tutorial/venv/bin/streamlit run app.py --server.port=8501
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

5. **配置 Nginx 反向代理**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8501;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

---

## 🔧 生产环境优化建议

### 1. 数据库迁移到云端

当前使用 SQLite，建议迁移到：

- **Supabase**（PostgreSQL，免费额度充足）
- **Railway PostgreSQL**（与 Railway 部署集成）
- **PlanetScale**（MySQL，免费版）

修改 `database.py` 使用 PostgreSQL 连接。

### 2. 文件存储

回测结果 CSV 文件建议存储到：
- **AWS S3** / **Cloudflare R2**
- **Supabase Storage**
- **Railway Volume**（持久化）

### 3. 环境变量管理

使用平台提供的 Secrets 管理，不要硬编码。

### 4. 监控和日志

- 使用 **Sentry** 监控错误
- 使用平台内置日志查看器

---

## 📝 本地回测说明

项目支持**本地回测**和**在线访问**并行：

- **本地回测**：在本地运行 `batch_backtest_compare_fast.py`，结果保存到本地 CSV
- **在线访问**：用户通过 Web 界面查看回测结果（读取 CSV 文件）

**建议**：
- 本地运行长时间回测任务
- 将结果文件同步到云端（Git 或对象存储）
- Web 应用读取云端结果展示

---

## 🚨 常见问题

### Q: 部署后数据库丢失？
A: 使用持久化存储（Railway Volume）或迁移到云端数据库。

### Q: API 调用失败？
A: 检查环境变量是否正确配置，API Key 是否有效。

### Q: 回测结果文件找不到？
A: 确保文件已提交到 Git 或使用对象存储。

### Q: 性能慢？
A: 考虑升级到付费计划，或优化代码（缓存、异步处理）。

---

## 📞 技术支持

如有问题，请查看：
- Streamlit 文档：https://docs.streamlit.io
- Railway 文档：https://docs.railway.app
- 项目 Issues：https://github.com/yourusername/desktop-tutorial/issues
