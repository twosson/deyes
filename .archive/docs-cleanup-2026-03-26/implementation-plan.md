# Deyes 系统部署实施计划

> 硬件已到位，开始系统部署 - 4周上线计划

## 📅 总体时间表

```
Week 1 (3.19-3.25): 基础环境搭建
Week 2 (3.26-4.01): 核心服务部署
Week 3 (4.02-4.08): Agent开发与测试
Week 4 (4.09-4.15): 压力测试与上线
```

---

## Week 1: 基础环境搭建 (3.19-3.25)

### Day 1-2: 硬件组装与系统安装

#### 任务清单

**1. 服务器组装**
```bash
硬件检查清单:
□ 8 × RTX 4090 GPU
□ 主板 (8卡PCIe 4.0支持)
□ CPU (Xeon/EPYC)
□ 256GB DDR4 ECC内存
□ 2TB NVMe (系统盘)
□ 4TB NVMe (数据盘)
□ 2 × 2000W电源
□ 4U机箱
□ 散热系统 (风冷/水冷)

组装步骤:
1. 安装CPU + 散热器
2. 安装内存条 (8×32GB)
3. 安装主板到机箱
4. 安装电源 (2×2000W)
5. 安装NVMe SSD (2个M.2插槽)
6. 安装8张RTX 4090 (检查PCIe插槽)
7. 连接所有电源线
8. 连接散热系统
9. 理线并固定
```

**2. 操作系统安装**
```bash
# 推荐: Ubuntu 22.04 LTS Server

# 下载ISO
wget https://releases.ubuntu.com/22.04/ubuntu-22.04.5-live-server-amd64.iso

# 制作启动U盘 (在另一台电脑)
# Windows: 使用Rufus
# Linux: sudo dd if=ubuntu-22.04.5-live-server-amd64.iso of=/dev/sdX bs=4M

# 安装配置:
- 语言: English
- 键盘: US
- 网络: 配置静态IP (推荐)
- 存储:
  - /dev/nvme0n1 (2TB) → 系统盘
    - / : 100GB (ext4)
    - /boot : 2GB (ext4)
    - swap : 32GB
    - /home : 剩余空间
  - /dev/nvme1n1 (4TB) → 数据盘
    - /data : 全部空间 (ext4)
- 用户: deyes
- SSH: 安装OpenSSH Server
- 软件: 不选择额外软件包

# 安装后首次启动
ssh deyes@<server-ip>
```

**3. 系统基础配置**
```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装基础工具
sudo apt install -y \
    build-essential \
    git \
    curl \
    wget \
    vim \
    htop \
    tmux \
    net-tools \
    iotop \
    nvtop

# 配置时区
sudo timedatectl set-timezone Asia/Shanghai

# 配置主机名
sudo hostnamectl set-hostname deyes-server

# 创建数据目录
sudo mkdir -p /data/deyes
sudo chown -R deyes:deyes /data/deyes
```

### Day 3: NVIDIA驱动与Docker安装

**1. NVIDIA驱动安装**
```bash
# 检查GPU
lspci | grep -i nvidia
# 应该看到8个RTX 4090

# 添加NVIDIA驱动PPA
sudo add-apt-repository ppa:graphics-drivers/ppa
sudo apt update

# 安装最新驱动 (推荐550+)
sudo apt install -y nvidia-driver-550

# 重启
sudo reboot

# 验证安装
nvidia-smi
# 应该看到8张RTX 4090，每张24GB显存
```

**2. Docker安装**
```bash
# 卸载旧版本
sudo apt remove docker docker-engine docker.io containerd runc

# 安装依赖
sudo apt install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# 添加Docker GPG密钥
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# 添加Docker仓库
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 安装Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# 添加用户到docker组
sudo usermod -aG docker deyes
newgrp docker

# 验证安装
docker --version
docker compose version
```

**3. NVIDIA Container Toolkit安装**
```bash
# 添加NVIDIA Container Toolkit仓库
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo apt-key add -
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 安装
sudo apt update
sudo apt install -y nvidia-container-toolkit

# 配置Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 验证
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
# 应该看到8张GPU
```

### Day 4-5: 存储与网络配置

**1. 数据盘配置**
```bash
# 创建目录结构
mkdir -p /data/deyes/{minio,postgres,redis,qdrant,logs,models}

# 设置权限
sudo chown -R deyes:deyes /data/deyes

# 目录结构
/data/deyes/
├── minio/              # MinIO对象存储
├── postgres/           # PostgreSQL数据
├── redis/              # Redis持久化
├── qdrant/             # 向量数据库
├── logs/               # 系统日志
│   ├── agents/
│   ├── rpa/
│   └── api/
└── models/             # AI模型文件
    ├── llm/            # Qwen3.5等
    ├── flux/           # FLUX.2 dev
    └── auxiliary/      # 辅助模型
```

**2. 网络配置**
```bash
# 创建Docker网络
docker network create deyes_network

# 配置防火墙 (UFW)
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 3000/tcp    # Dashboard
sudo ufw allow 8069/tcp    # Odoo
sudo ufw enable

# 配置静态IP (如果需要)
sudo vim /etc/netplan/00-installer-config.yaml
```

**3. 下载AI模型**
```bash
# 创建下载脚本
cat > /data/deyes/download_models.sh << 'EOF'
#!/bin/bash

# Qwen3.5-35B-A3B
echo "Downloading Qwen3.5-35B-A3B..."
cd /data/deyes/models/llm
git lfs install
git clone https://huggingface.co/Qwen/Qwen3.5-35B-A3B

# FLUX.2 dev
echo "Downloading FLUX.2 dev..."
cd /data/deyes/models/flux
wget https://huggingface.co/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors

# Turbo LoRA
echo "Downloading Turbo LoRA..."
wget https://huggingface.co/ByteDance/Hyper-SD/resolve/main/Hyper-FLUX.1-dev-8steps-lora.safetensors

# Qwen2-VL (可选)
echo "Downloading Qwen2-VL..."
cd /data/deyes/models/auxiliary
git clone https://huggingface.co/Qwen/Qwen2-VL-7B-Instruct

echo "All models downloaded!"
EOF

chmod +x /data/deyes/download_models.sh

# 执行下载 (需要较长时间，建议tmux中运行)
tmux new -s download
/data/deyes/download_models.sh
# Ctrl+B, D 退出tmux
```

---

## Week 2: 核心服务部署 (3.26-4.01)

### Day 6-7: 基础设施服务

**1. 创建项目结构**
```bash
cd /home/deyes
git init deyes
cd deyes

# 创建目录结构
mkdir -p {backend,frontend,agents,rpa-worker,monitoring,scripts}
mkdir -p docker/{postgres,redis,minio,sglang,comfyui}
```

**2. Docker Compose配置**
```bash
# 创建 docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  # ==================== 数据存储层 ====================

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
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  # ==================== AI推理层 ====================

  sglang:
    image: lmsysorg/sglang:latest
    container_name: deyes-sglang
    command: >
      python -m sglang.launch_server
      --model-path /models/Qwen3.5-35B-A3B
      --tp 4
      --mem-fraction-static 0.85
      --port 30000
      --host 0.0.0.0
    volumes:
      - /data/deyes/models/llm:/models
    ports:
      - "30000:30000"
    networks:
      - deyes_network
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['4', '5', '6', '7']
              capabilities: [gpu]
    restart: unless-stopped

  comfyui:
    build: ./docker/comfyui
    container_name: deyes-comfyui
    volumes:
      - /data/deyes/models/flux:/app/models/checkpoints
      - /data/deyes/models/flux:/app/models/loras
      - /data/deyes/minio/images:/app/output
    ports:
      - "8188:8188"
    networks:
      - deyes_network
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0', '1', '2', '3']
              capabilities: [gpu]
    restart: unless-stopped

networks:
  deyes_network:
    external: true

EOF

# 创建 .env 文件
cat > .env << 'EOF'
POSTGRES_PASSWORD=your_secure_password_here
MINIO_PASSWORD=your_minio_password_here
EOF
```

**3. 启动基础服务**
```bash
# 启动数据库和存储
docker compose up -d postgres redis qdrant minio

# 等待服务就绪
sleep 30

# 检查服务状态
docker compose ps
docker compose logs postgres
docker compose logs redis

# 初始化MinIO
# 访问 http://<server-ip>:9001
# 登录: admin / <MINIO_PASSWORD>
# 创建bucket: product-images
```

### Day 8-9: AI推理服务部署

**1. ComfyUI Dockerfile**
```bash
mkdir -p docker/comfyui
cat > docker/comfyui/Dockerfile << 'EOF'
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

# 安装Python和依赖
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    git \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 克隆ComfyUI
WORKDIR /app
RUN git clone https://github.com/comfyanonymous/ComfyUI.git .

# 安装Python依赖
RUN pip3 install --no-cache-dir \
    torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
RUN pip3 install --no-cache-dir -r requirements.txt

# 安装Turbo LoRA支持
RUN cd custom_nodes && \
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git

EXPOSE 8188

CMD ["python3", "main.py", "--listen", "0.0.0.0", "--port", "8188"]
EOF
```

**2. 构建并启动AI服务**
```bash
# 构建ComfyUI镜像
docker compose build comfyui

# 启动SGLang
docker compose up -d sglang

# 等待模型加载 (约5-10分钟)
docker compose logs -f sglang

# 启动ComfyUI
docker compose up -d comfyui

# 验证SGLang
curl http://localhost:30000/health

# 验证ComfyUI
curl http://localhost:8188/
```

**3. 性能测试**
```bash
# 测试SGLang
cat > test_sglang.py << 'EOF'
import requests
import time

url = "http://localhost:30000/v1/chat/completions"
data = {
    "model": "Qwen3.5-35B-A3B",
    "messages": [{"role": "user", "content": "你好，请介绍一下你自己"}],
    "max_tokens": 500
}

start = time.time()
response = requests.post(url, json=data)
end = time.time()

print(f"Response: {response.json()}")
print(f"Time: {end - start:.2f}s")
print(f"Tokens/s: {500 / (end - start):.2f}")
EOF

python3 test_sglang.py

# 测试ComfyUI
# 访问 http://<server-ip>:8188
# 加载FLUX.2 dev工作流
# 生成测试图片
```

### Day 10: 监控系统部署

**1. 添加监控服务到docker-compose.yml**
```yaml
  prometheus:
    image: prom/prometheus:latest
    container_name: deyes-prometheus
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - /data/deyes/prometheus:/prometheus
    ports:
      - "9090:9090"
    networks:
      - deyes_network
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: deyes-grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - /data/deyes/grafana:/var/lib/grafana
    ports:
      - "3001:3000"
    networks:
      - deyes_network
    restart: unless-stopped

  node-exporter:
    image: prom/node-exporter:latest
    container_name: deyes-node-exporter
    ports:
      - "9100:9100"
    networks:
      - deyes_network
    restart: unless-stopped

  nvidia-exporter:
    image: nvidia/dcgm-exporter:latest
    container_name: deyes-nvidia-exporter
    ports:
      - "9400:9400"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0', '1', '2', '3', '4', '5', '6', '7']
              capabilities: [gpu]
    networks:
      - deyes_network
    restart: unless-stopped
```

**2. Prometheus配置**
```bash
mkdir -p monitoring
cat > monitoring/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'node'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'nvidia'
    static_configs:
      - targets: ['nvidia-exporter:9400']

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:5432']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
EOF

# 启动监控服务
docker compose up -d prometheus grafana node-exporter nvidia-exporter
```

---

## Week 3: Agent开发与测试 (4.02-4.08)

### Day 11-12: MVP Agent实现

**1. 创建Agent框架**
```bash
cd /home/deyes/deyes/agents

# 安装Python依赖
cat > requirements.txt << 'EOF'
crewai==0.1.0
langgraph==0.0.20
langchain==0.1.0
pydantic==2.5.0
httpx==0.26.0
redis==5.0.1
psycopg2-binary==2.9.9
minio==7.2.0
pillow==10.2.0
EOF

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. 实现选品Agent**
```python
# agents/selector.py
from crewai import Agent, Task, Crew
from langchain_openai import ChatOpenAI
import httpx

# SGLang客户端
llm = ChatOpenAI(
    model="Qwen3.5-35B-A3B",
    base_url="http://sglang:30000/v1",
    api_key="EMPTY"
)

selector_agent = Agent(
    role="Product Selector",
    goal="Find profitable products from target platforms",
    backstory="Expert in e-commerce market analysis with 10 years experience",
    llm=llm,
    tools=[
        # TODO: 添加工具
    ],
    verbose=True
)

# 测试
if __name__ == "__main__":
    task = Task(
        description="Find 5 profitable products from Temu in electronics category",
        agent=selector_agent,
        expected_output="List of 5 products with profit analysis"
    )

    crew = Crew(agents=[selector_agent], tasks=[task])
    result = crew.kickoff()
    print(result)
```

**3. 实现图像复刻Agent**
```python
# agents/image_replicator.py
from crewai import Agent
import httpx
from PIL import Image
import io

class ImageReplicatorAgent:
    def __init__(self):
        self.comfyui_url = "http://comfyui:8188"
        self.llm = ChatOpenAI(
            model="Qwen3.5-35B-A3B",
            base_url="http://sglang:30000/v1",
            api_key="EMPTY"
        )

    async def analyze_image(self, image_url):
        """使用Qwen3.5多模态分析竞品图片"""
        # TODO: 实现图像分析
        pass

    async def generate_images(self, prompt, num_images=8):
        """调用ComfyUI生成图片"""
        # TODO: 实现图片生成
        pass
```

### Day 13-14: 集成测试

**1. 端到端测试脚本**
```python
# tests/test_e2e.py
import asyncio
from agents.selector import selector_agent
from agents.image_replicator import ImageReplicatorAgent

async def test_full_pipeline():
    # 1. 选品
    print("Step 1: Product Selection...")
    products = await selector_agent.run("Find 1 product from Temu")

    # 2. 图像生成
    print("Step 2: Image Generation...")
    image_agent = ImageReplicatorAgent()
    images = await image_agent.generate_images(products[0])

    # 3. 验证
    assert len(images) == 8
    print("✅ E2E test passed!")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
```

### Day 15: 数据库Schema设计

```sql
-- schema.sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL,
    source_platform VARCHAR(50),
    source_url TEXT,
    supplier_1688_id VARCHAR(100),
    purchase_price DECIMAL(10,2),
    prices JSONB,
    images JSONB,
    copies JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_products_status ON products(status);
CREATE INDEX idx_products_sku ON products(sku);

-- 执行
docker exec -i deyes-postgres psql -U deyes -d deyes < schema.sql
```

---

## Week 4: 压力测试与上线 (4.09-4.15)

### Day 16-17: 性能压力测试

**1. 负载测试脚本**
```python
# tests/load_test.py
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

async def generate_product(product_id):
    start = time.time()
    # 模拟完整流程
    # 1. 选品
    # 2. 图像生成
    # 3. 文案生成
    # 4. 入库
    await asyncio.sleep(6)  # 模拟6秒处理时间
    end = time.time()
    return end - start

async def load_test(num_products=100):
    tasks = [generate_product(i) for i in range(num_products)]
    results = await asyncio.gather(*tasks)

    avg_time = sum(results) / len(results)
    print(f"Average time: {avg_time:.2f}s")
    print(f"Throughput: {3600 / avg_time:.2f} products/hour")

if __name__ == "__main__":
    asyncio.run(load_test(100))
```

**2. GPU监控**
```bash
# 实时监控GPU
watch -n 1 nvidia-smi

# 或使用nvtop
sudo apt install nvtop
nvtop
```

### Day 18: 24小时稳定性测试

```bash
# 启动24小时测试
tmux new -s stability_test

# 在tmux中运行
python3 tests/load_test.py --duration 86400 --rate 0.1

# 监控脚本
cat > monitor.sh << 'EOF'
#!/bin/bash
while true; do
    echo "=== $(date) ==="
    docker compose ps
    nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv
    echo ""
    sleep 300  # 每5分钟记录一次
done
EOF

chmod +x monitor.sh
./monitor.sh > /data/deyes/logs/stability_test.log 2>&1 &
```

### Day 19-20: 优化与调整

**根据测试结果优化:**
1. 调整SGLang并发参数
2. 优化ComfyUI批处理
3. 调整Redis缓存策略
4. 数据库索引优化

### Day 21: 正式上线

**1. 最终检查清单**
```bash
□ 所有服务正常运行
□ GPU温度 < 80°C
□ 24小时稳定性测试通过
□ 数据备份策略就绪
□ 监控告警配置完成
□ 文档完整
```

**2. 启动生产环境**
```bash
# 停止测试环境
docker compose down

# 清理测试数据
# 谨慎操作！

# 启动生产环境
docker compose up -d

# 验证
docker compose ps
curl http://localhost:30000/health
curl http://localhost:8188/
```

---

## 📋 每日检查清单

### 每日必做
```bash
# 1. 检查服务状态
docker compose ps

# 2. 检查GPU状态
nvidia-smi

# 3. 检查磁盘空间
df -h

# 4. 检查日志
docker compose logs --tail=100

# 5. 备份数据库
docker exec deyes-postgres pg_dump -U deyes deyes > backup_$(date +%Y%m%d).sql
```

---

## 🚨 故障排查

### 常见问题

**1. SGLang启动失败**
```bash
# 检查显存
nvidia-smi

# 检查模型路径
docker exec deyes-sglang ls /models

# 查看日志
docker compose logs sglang
```

**2. ComfyUI生成失败**
```bash
# 检查模型文件
docker exec deyes-comfyui ls /app/models/checkpoints

# 重启服务
docker compose restart comfyui
```

**3. 数据库连接失败**
```bash
# 检查PostgreSQL
docker exec deyes-postgres pg_isready -U deyes

# 重置密码
docker exec -it deyes-postgres psql -U deyes
ALTER USER deyes WITH PASSWORD 'new_password';
```

---

## 📚 下一步文档

完成部署后，需要创建:
1. API接口文档
2. Agent开发指南
3. 运维手册
4. 故障排查手册

---

## ⚠️ 重要提醒

1. **备份**: 每天备份PostgreSQL数据库
2. **监控**: 实时监控GPU温度和利用率
3. **日志**: 定期清理日志文件
4. **更新**: 定期更新Docker镜像和模型
5. **安全**: 修改所有默认密码

**准备好开始了吗？从Week 1 Day 1开始执行！**
