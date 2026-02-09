#!/bin/bash

# 推送代码到 GitHub 的脚本

echo "🚀 开始准备推送到 GitHub..."

# 检查 git 状态
echo "📋 当前 Git 状态："
git status --short

# 添加所有文件（.gitignore 会自动排除敏感文件）
echo ""
echo "📦 添加文件到暂存区..."
git add .gitignore .streamlit/ DEPLOY.md Procfile runtime.txt setup.sh
git add app.py auto_daily_analysis.py backtest.py database.py main.py stock_names.py
git add batch_backtest*.py merge_backtest_results.py fix_names.py
git add requirements.txt README.md DEPLOY.md
git add implementation_plan.md requirement.md
git add test/

# 提交更改
echo ""
echo "💾 提交更改..."
git commit -m "添加完整项目代码和部署配置

- 添加 Streamlit Web 应用 (app.py)
- 添加核心分析引擎和回测系统
- 添加用户系统和数据库管理
- 添加部署配置文件 (Procfile, runtime.txt)
- 添加部署文档 (DEPLOY.md)
- 更新 README 和 .gitignore"

# 推送到 GitHub
echo ""
echo "📤 推送到 GitHub..."
git push origin main

echo ""
echo "✅ 完成！代码已推送到 GitHub"
echo "📍 仓库地址: https://github.com/zuowood1234/desktop-tutorial"
