#!/bin/bash

# Deyes 快速部署脚本
# 从当前状态 (Ubuntu 22.04 + CUDA 13.1 + Docker) 继续部署

set -e

echo "=========================================="
echo "Deyes 系统部署脚本"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为root
if [ "$EUID" -eq 0 ]; then
    echo -e "${RED}❌ 请不要使用root用户运行此脚本${NC}"
    exit 1
fi

# Step 1: 环境验证
echo -e "${YELLOW}[Step 1/7] 验证环境...${NC}"
echo ""

# 检查NVIDIA驱动
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}❌ nvidia-smi 未找到，请先安装NVIDIA驱动${NC}"
    exit 1
fi

GPU_COUNT=$(nvidia-smi --list-gpus | wc -l)
if [ "$GPU_COUNT" -ne 8 ]; then
    echo -e "${YELLOW}⚠️  检测到 $GPU_COUNT 张GPU，预期8张${NC}"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}✅ GPU检测: $GPU_COUNT 张${NC}"

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker 未安装${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker 已安装: $(docker --version)${NC}"

# 检查磁盘空间
DISK_SPACE=$(df -BG /data 2>/dev/null | awk 'NR==2 {print $4}' | sed 's/G//')
if [ -z "$DISK_SPACE" ]; then
    echo -e "${YELLOW}⚠️  /data 目录不存在，将使用根目录${NC}"
    DISK_SPACE=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
fi

if [ "$DISK_SPACE" -lt 500 ]; then
    echo -e "${YELLOW}⚠️  可用磁盘空间: ${DISK_SPACE}GB，建议至少500GB${NC}"
    read -p "是否继续？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo -e "${GREEN}✅ 磁盘空间: ${DISK_SPACE}GB 可用${NC}"
echo ""

# Step 2: 安装NVIDIA Container Toolkit
echo -e "${YELLOW}[Step 2/7] 安装NVIDIA Container Toolkit...${NC}"
echo ""

if docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
    echo -e "${GREEN}✅ NVIDIA Container Toolkit 已安装${NC}"
else
    echo "安装 NVIDIA Container Toolkit..."

    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

    curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit

    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker

    echo -e "${GREEN}✅ NVIDIA Container Toolkit 安装完成${NC}"
fi
echo ""

# Step 3: 创建项目结构
echo -e "${YELLOW}[Step 3/7] 创建项目结构...${NC}"
echo ""

sudo mkdir -p /data/deyes
sudo chown -R $USER:$USER /data/deyes

mkdir -p /data/deyes/{minio,postgres,redis,qdrant,logs,models}
mkdir -p /data/deyes/models/{llm,flux,auxiliary}
mkdir -p /data/deyes/logs/{agents,rpa,api}

cd ~
mkdir -p deyes
cd deyes

# 创建Docker网络
if ! docker network inspect deyes_network &> /dev/null; then
    docker network create deyes_network
    echo -e "${GREEN}✅ Docker网络已创建${NC}"
else
    echo -e "${GREEN}✅ Docker网络已存在${NC}"
fi

echo -e "${GREEN}✅ 项目结构已创建${NC}"
echo ""

# Step 4: 创建配置文件
echo -e "${YELLOW}[Step 4/7] 创建配置文件...${NC}"
echo ""

# 生成随机密码
POSTGRES_PASS=$(openssl rand -base64 16)
MINIO_PASS=$(openssl rand -base64 16)
GRAFANA_PASS=$(openssl rand -base64 16)

cat > .env << EOF
# PostgreSQL
POSTGRES_PASSWORD=$POSTGRES_PASS

# MinIO
MINIO_PASSWORD=$MINIO_PASS

# Grafana
GRAFANA_PASSWORD=$GRAFANA_PASS
EOF

echo -e "${GREEN}✅ 配置文件已创建: ~/deyes/.env${NC}"
echo -e "${YELLOW}⚠️  请保存这些密码！${NC}"
echo ""

# Step 5: 创建docker-compose.yml
echo -e "${YELLOW}[Step 5/7] 创建docker-compose.yml...${NC}"
echo ""

cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    container_name: deyes-postgres
    environment:
      POSTGRES_DB: deyes
      POSTGRES_USER: deyes
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - /data/deyes/postgres:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    networks:
      - deyes_network
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U deyes"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: deyes-redis
    command: redis-server --appendonly yes --maxmemory 2gb --maxmemory-policy allkeys-lru
    volumes:
      - /data/deyes/redis:/data
    ports:
      - "6379:6379"
    networks:
      - deyes_network
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  qdrant:
    image: qdrant/qdrant:latest
    container_name: deyes-qdrant
    volumes:
      - /data/deyes/qdrant:/qdrant/storage
    ports:
      - "6333:6333"
    networks:
      - deyes_network
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    container_name: deyes-minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: admin
      MINIO_ROOT_PASSWORD: ${MINIO_PASSWORD}
    volumes:
      - /data/deyes/minio:/data
    ports:
      - "9000:9000"
      - "9001:9001"
    networks:
      - deyes_network
    restart: unless-stopped

networks:
  deyes_network:
    external: true
EOF

echo -e "${GREEN}✅ docker-compose.yml 已创建${NC}"
echo ""

# Step 6: 启动基础服务
echo -e "${YELLOW}[Step 6/7] 启动基础服务...${NC}"
echo ""

docker compose up -d

echo "⏳ 等待服务启动..."
sleep 30

docker compose ps

echo ""
echo -e "${GREEN}✅ 基础服务已启动${NC}"
echo ""

# Step 7: 创建模型下载脚本
echo -e "${YELLOW}[Step 7/7] 创建模型下载脚本...${NC}"
echo ""

cat > download_models.sh << 'SCRIPT_EOF'
#!/bin/bash

set -e

echo "=========================================="
echo "开始下载AI模型"
echo "预计时间: 2-4小时"
echo "总大小: ~82GB"
echo "=========================================="

# 安装git-lfs
if ! command -v git-lfs &> /dev/null; then
    sudo apt-get install -y git-lfs
fi

git lfs install

# 1. 下载 Qwen3.5-35B-A3B
echo ""
echo "[1/3] 下载 Qwen3.5-35B-A3B (~70GB)..."
cd /data/deyes/models/llm
if [ ! -d "Qwen3.5-35B-A3B" ]; then
    git clone https://huggingface.co/Qwen/Qwen3.5-35B-A3B
    echo "✅ Qwen3.5-35B-A3B 下载完成"
else
    echo "⚠️  Qwen3.5-35B-A3B 已存在，跳过"
fi

# 2. 下载 FLUX.2 dev
echo ""
echo "[2/3] 下载 FLUX.2 dev (~12GB)..."
cd /data/deyes/models/flux
if [ ! -f "flux1-dev.safetensors" ]; then
    wget -c https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors
    echo "✅ FLUX.2 dev 下载完成"
else
    echo "⚠️  FLUX.2 dev 已存在，跳过"
fi

# 3. 下载 Turbo LoRA
echo ""
echo "[3/3] 下载 Turbo LoRA (~200MB)..."
if [ ! -f "Hyper-FLUX.1-dev-8steps-lora.safetensors" ]; then
    wget -c https://huggingface.co/ByteDance/Hyper-SD/resolve/main/Hyper-FLUX.1-dev-8steps-lora.safetensors
    echo "✅ Turbo LoRA 下载完成"
else
    echo "⚠️  Turbo LoRA 已存在，跳过"
fi

echo ""
echo "=========================================="
echo "✅ 所有模型下载完成！"
echo "=========================================="

du -sh /data/deyes/models/*
SCRIPT_EOF

chmod +x download_models.sh

echo -e "${GREEN}✅ 模型下载脚本已创建${NC}"
echo ""

# 完成
echo "=========================================="
echo -e "${GREEN}✅ 部署脚本执行完成！${NC}"
echo "=========================================="
echo ""
echo "📋 部署摘要:"
echo "  - 项目目录: ~/deyes"
echo "  - 数据目录: /data/deyes"
echo "  - 配置文件: ~/deyes/.env"
echo ""
echo "🔐 服务密码 (保存到安全位置):"
echo "  PostgreSQL: $POSTGRES_PASS"
echo "  MinIO: $MINIO_PASS"
echo "  Grafana: $GRAFANA_PASS"
echo ""
echo "🌐 服务访问:"
echo "  - PostgreSQL: localhost:5432"
echo "  - Redis: localhost:6379"
echo "  - Qdrant: http://localhost:6333"
echo "  - MinIO Console: http://localhost:9001"
echo ""
echo "📥 下一步: 下载AI模型"
echo "  方式1 (推荐): tmux new -s download -d '~/deyes/download_models.sh 2>&1 | tee /data/deyes/logs/download.log'"
echo "  方式2: ~/deyes/download_models.sh"
echo ""
echo "  查看进度: tail -f /data/deyes/logs/download.log"
echo "  进入tmux: tmux attach -t download"
echo "  退出tmux: Ctrl+B, D"
echo ""
echo "⏳ 模型下载需要2-4小时，完成后继续部署AI服务"
echo ""
