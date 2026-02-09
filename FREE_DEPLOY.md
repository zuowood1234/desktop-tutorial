# 🆓 免费部署方案指南

本项目有多个**完全免费**的部署方案，让您可以将应用发布到互联网。

## 🎯 推荐方案：Streamlit Cloud（最简单、完全免费）

### ✅ 优点
- **完全免费**，无使用限制
- 一键部署，5 分钟完成
- 自动更新（每次 push 代码自动部署）
- 自动生成公开 URL
- 支持环境变量配置

### 📝 部署步骤

#### 1. 确保代码已推送到 GitHub
```bash
# 如果还没推送，执行：
./push_to_github.sh
# 或手动执行：
git add .
git commit -m "准备部署"
git push origin main
```

#### 2. 访问 Streamlit Cloud
- 打开浏览器访问：**https://share.streamlit.io**
- 使用您的 **GitHub 账号**登录

#### 3. 创建新应用
1. 点击右上角 **"New app"** 按钮
2. 选择仓库：`zuowood1234/desktop-tutorial`
3. 选择分支：`main`
4. **Main file path**: 输入 `app.py`
5. **App URL**: 可以自定义（如：`ai-investment-advisor`）
   - 最终 URL 将是：`https://ai-investment-advisor.streamlit.app`

#### 4. 配置环境变量（重要！）
1. 在应用页面，点击右上角 **"⋮"** (三个点)
2. 选择 **"Settings"**
3. 点击 **"Secrets"** 标签
4. 添加以下内容：
```toml
DEEPSEEK_API_KEY = "your_actual_api_key_here"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
```
5. 点击 **"Save"**

#### 5. 部署完成！
- 点击 **"Deploy"** 按钮
- 等待 1-2 分钟，应用会自动部署
- 部署完成后，您会得到一个公开 URL
- 任何人都可以通过这个 URL 访问您的应用

### 🔄 自动更新
- 每次您 `git push` 代码到 GitHub
- Streamlit Cloud 会自动检测并重新部署
- 无需手动操作

---

## 🌟 其他免费方案

### 方案二：Railway（免费额度充足）

**免费额度**：$5/月免费额度，通常足够使用

**步骤**：
1. 访问 https://railway.app
2. 使用 GitHub 登录
3. 点击 "New Project" → "Deploy from GitHub repo"
4. 选择您的仓库
5. 在 Variables 中添加环境变量
6. 自动部署完成

**优点**：
- 支持持久化存储（数据库不会丢失）
- 性能更好
- 支持自定义域名

---

### 方案三：Render（免费版）

**免费额度**：有限制，但适合小项目

**步骤**：
1. 访问 https://render.com
2. 使用 GitHub 登录
3. 创建新的 Web Service
4. 选择仓库
5. 配置环境变量
6. 部署

---

### 方案四：Fly.io（免费额度）

**免费额度**：3 个共享 CPU，256MB RAM

**步骤**：
1. 访问 https://fly.io
2. 安装 flyctl CLI
3. 使用 GitHub 登录
4. 运行 `fly launch`
5. 自动部署

---

## 📊 方案对比

| 方案 | 免费额度 | 部署难度 | 数据库持久化 | 推荐度 |
|------|---------|---------|-------------|--------|
| **Streamlit Cloud** | ✅ 完全免费 | ⭐ 非常简单 | ⚠️ 临时存储 | ⭐⭐⭐⭐⭐ |
| **Railway** | ✅ $5/月免费 | ⭐⭐ 简单 | ✅ 支持 | ⭐⭐⭐⭐ |
| **Render** | ⚠️ 有限制 | ⭐⭐ 简单 | ✅ 支持 | ⭐⭐⭐ |
| **Fly.io** | ✅ 免费额度 | ⭐⭐⭐ 中等 | ✅ 支持 | ⭐⭐⭐ |

## 🎯 推荐选择

### 如果您是新手 → **Streamlit Cloud**
- 最简单，5 分钟完成
- 完全免费
- 适合学习和演示

### 如果需要生产环境 → **Railway**
- 免费额度充足
- 数据库持久化
- 性能更好

## 🚀 快速开始（Streamlit Cloud）

1. **推送代码**（如果还没推送）：
   ```bash
   ./push_to_github.sh
   ```

2. **访问 Streamlit Cloud**：
   - https://share.streamlit.io
   - 使用 GitHub 登录

3. **一键部署**：
   - 选择仓库
   - 输入 `app.py`
   - 配置环境变量
   - 点击 Deploy

4. **完成！** 获得公开 URL

## ⚠️ 注意事项

1. **环境变量**：必须配置 `DEEPSEEK_API_KEY`，否则应用无法运行
2. **数据库**：Streamlit Cloud 使用临时存储，重启可能丢失数据
3. **API 限制**：注意 DeepSeek API 的调用频率限制
4. **公开访问**：部署后应用是公开的，任何人都可以访问

## 📞 需要帮助？

如果遇到问题：
1. 查看 [DEPLOY.md](./DEPLOY.md) 详细文档
2. 查看 Streamlit Cloud 文档：https://docs.streamlit.io/streamlit-community-cloud
3. 检查 GitHub Issues

---

**🎉 祝您部署顺利！**
