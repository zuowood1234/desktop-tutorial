#!/bin/bash

# AI 智能投顾系统 - 快速部署脚本

echo "🚀 开始部署 AI 智能投顾系统..."

# 检查 Python 版本
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "📌 Python 版本: $python_version"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 升级 pip
echo "⬆️  升级 pip..."
pip install --upgrade pip

# 安装依赖
echo "📥 安装依赖包..."
pip install -r requirements.txt

# 检查环境变量文件
if [ ! -f ".env" ]; then
    echo "⚠️  未找到 .env 文件，正在创建模板..."
    cat > .env << EOF
# DeepSeek API 配置
DEEPSEEK_API_KEY=your_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
EOF
    echo "✅ 已创建 .env 模板，请编辑并填入您的 API Key"
else
    echo "✅ .env 文件已存在"
fi

# 初始化数据库（首次运行会自动创建）
echo "💾 数据库将在首次运行时自动创建"

echo ""
echo "✅ 部署完成！"
echo ""
echo "📝 下一步："
echo "1. 编辑 .env 文件，填入您的 DeepSeek API Key"
echo "2. 运行应用: streamlit run app.py"
echo "3. 或使用: python -m streamlit run app.py"
echo ""
echo "🌐 本地访问: http://localhost:8501"
