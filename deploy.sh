#!/bin/bash

# Agent Framework 部署脚本
# 用于快速部署到服务器

set -e

echo "🚀 Agent Framework 部署脚本"
echo "================================"

# 检查 Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker 未安装，请先安装 Docker"
    exit 1
fi

# 检查 Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose 未安装，请先安装 Docker Compose"
    exit 1
fi

# 创建 .env 文件（如果不存在）
if [ ! -f .env ]; then
    echo "📝 创建 .env 配置文件..."
    cat > .env << EOF
# API 配置
SILICONFLOW_API_KEY=your_api_key_here
DEFAULT_MODEL=Qwen/Qwen3-VL-32B-Instruct
BASE_URL=https://api.siliconflow.cn/v1

# 安全配置
SECRET_KEY=$(openssl rand -hex 32)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# 数据库配置
POSTGRES_PASSWORD=$(openssl rand -hex 16)
EOF
    echo "✅ .env 文件已创建，请编辑并填入你的 API 密钥"
    echo "   编辑命令: nano .env 或 vim .env"
    exit 0
fi

# 构建镜像
echo "🔨 构建 Docker 镜像..."
docker-compose build

# 启动服务
echo "🚀 启动服务..."
docker-compose up -d

# 等待服务启动
echo "⏳ 等待服务启动..."
sleep 10

# 检查服务状态
echo "📊 检查服务状态..."
docker-compose ps

# 显示日志
echo ""
echo "✅ 部署完成！"
echo ""
echo "📍 访问地址:"
echo "   - 主页: http://localhost:5000"
echo "   - 风电助手: http://localhost:5000/maintenance-assistant"
echo "   - 工作流: http://localhost:5000/workflow"
echo ""
echo "📝 查看日志: docker-compose logs -f"
echo "🛑 停止服务: docker-compose down"
echo "🔄 重启服务: docker-compose restart"
echo ""
