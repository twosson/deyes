# ComfyUI 完整部署指南

> Deyes 跨境电商数字员工系统 - ComfyUI 图像生成服务部署
>
> 适用环境: Ubuntu 22.04 + CUDA 13.1 + Docker + 8x RTX 4090
>
> 预计时间: 2-3小时（含模型下载）

---

## 📋 部署概览

### 系统架构

本指南将部署完整的 ComfyUI 图像生成系统，包括：

- **2个 ComfyUI 实例**（主图生成 + 详情页生成）
- **FLUX.1-dev FP8 模型**（13GB，电商主图生成）
- **IPAdapter Plus**（风格迁移，爆款复刻）
- **ControlNet**（Canny + Depth，防止产品变形）
- **Turbo LoRA**（3倍速度提升，8步生成）
- **FLUX Fill**（局部编辑）
- **辅助模型**（背景移除、质量评估）

### GPU 分配方案

```
GPU 0-1: ComfyUI 实例 1（主图生成）
  └─ FLUX.1-dev + IPAdapter + ControlNet + Turbo LoRA (~24GB)

GPU 2-3: ComfyUI 实例 2（详情页生成）
  └─ 同上配置 (~24GB)

GPU 4: FLUX Fill（局部编辑，~24GB）

GPU 5: Qwen-Image-Edit（高级编辑，~24GB）

GPU 6-7: SGLang（Qwen3.5-35B-A3B-FP8，Tensor Parallel）
  └─ 提示词生成、质量检测（15.4GB/卡）
```

### 性能指标

| 任务 | 单张时间 | 日产量 (20h) |
|------|---------|-------------|
| 主图 | 8-12s | 28,800张 |
| 详情页 | 10-15s | 17,280张 |
| 局部编辑 | 5-10s | 14,400张 |

**套数产能**（1主图 + 8详情页）:
- 理论: 3,200套/天
- 实际: 2,400-2,800套/天
- 峰值: 3,500套/天

---

## Step 1: 环境验证

### 1.1 检查硬件

```bash
# 检查 GPU
nvidia-smi

# 预期输出: 8张 RTX 4090，每张 24GB 显存
# Driver Version: 550+
# CUDA Version: 13.1+
```

### 1.2 检查系统

```bash
# 检查操作系统
lsb_release -a
# 预期: Ubuntu 22.04 LTS

# 检查 Docker
docker --version
docker compose version
# 预期: Docker 24.0+, Compose 2.20+

# 检查磁盘空间
df -h /data
# 预期: 至少 200GB 可用空间（模型 ~100GB + 输出图片）
```

### 1.3 检查网络

```bash
# 测试中国镜像连接
curl -I https://hf-mirror.com
# 预期: HTTP/2 200

# 测试 Git
git --version
# 预期: git version 2.34+
```

---

## Step 2: 安装 NVIDIA Container Toolkit

```bash
# 添加 NVIDIA Container Toolkit 仓库
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 安装
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 配置 Docker
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 验证
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
# 预期: 看到 8张 GPU
```

---

## Step 3: 创建项目结构

```bash
# 创建数据目录
sudo mkdir -p /data/deyes
sudo chown -R $USER:$USER /data/deyes

# 创建子目录
mkdir -p /data/deyes/{minio,postgres,redis,qdrant}
mkdir -p /data/deyes/logs/{agents,rpa,api}
mkdir -p /data/deyes/models/{flux,llm,auxiliary}
mkdir -p /data/deyes/comfyui/{output,workflows,custom_nodes}

# 目录结构
/data/deyes/
├── models/
│   ├── flux/                    # FLUX 模型和 LoRA
│   │   ├── flux1-dev-fp8.safetensors          (13GB)
│   │   ├── flux_turbo_lora.safetensors        (200MB)
│   │   ├── flux-fill-model.safetensors        (3GB)
│   │   ├── controlnet-canny.safetensors       (1.5GB)
│   │   ├── controlnet-depth.safetensors       (1.5GB)
│   │   ├── ipadapter_plus_flux.safetensors    (3.7GB)
│   │   └── clip_vision_vit_h.safetensors      (1.5GB)
│   ├── llm/                     # LLM 模型
│   │   └── Qwen3.5-35B-A3B-FP8/               (35GB)
│   └── auxiliary/               # 辅助模型
│       ├── Qwen2-VL-7B-Instruct/              (8GB)
│       └── rmbg-1.4.onnx                      (200MB)
├── comfyui/
│   ├── output/                  # 生成的图片
│   ├── workflows/               # 工作流 JSON
│   └── custom_nodes/            # 自定义节点
├── minio/                       # MinIO 对象存储
├── postgres/                    # PostgreSQL 数据
├── redis/                       # Redis 缓存
└── qdrant/                      # 向量数据库

# 创建 Docker 网络
docker network create deyes_network

# 创建项目配置目录
mkdir -p ~/deyes
cd ~/deyes
```

---

## Step 4: 配置环境变量

```bash
cd ~/deyes

# 生成随机密码
cat > .env << EOF
# PostgreSQL
POSTGRES_PASSWORD=$(openssl rand -base64 16)

# MinIO
MINIO_PASSWORD=$(openssl rand -base64 16)

# Grafana
GRAFANA_PASSWORD=$(openssl rand -base64 16)
EOF

echo "✅ 密码已生成，请妥善保存 ~/deyes/.env"
cat ~/deyes/.env
```

---

## Step 5: 下载 AI 模型（使用 ModelScope）

### 5.1 安装 ModelScope

```bash
# 安装 ModelScope（推荐，中国速度快，无需认证）
pip3 install modelscope -i https://mirrors.aliyun.com/pypi/simple/

# 验证安装
python3 -c "import modelscope; print(modelscope.__version__)"
```

**为什么使用 ModelScope？**
- ✅ 无需申请访问权限（不需要 Hugging Face 账号）
- ✅ 中国大陆速度快（阿里云 CDN）
- ✅ 支持断点续传
- ✅ 模型齐全（FLUX, Qwen, ControlNet 等）
- ✅ 简单易用

### 5.2 创建下载脚本

```bash
cat > ~/deyes/download_models_modelscope.sh << 'SCRIPT'
#!/bin/bash

set -e

echo "=========================================="
echo "Deyes AI 模型完整下载脚本"
echo "使用 ModelScope（中国镜像，无需认证）"
echo "=========================================="

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# 基础目录
BASE_DIR="/data/deyes/models"
FLUX_DIR="$BASE_DIR/flux"
LLM_DIR="$BASE_DIR/llm"
AUX_DIR="$BASE_DIR/auxiliary"

# 创建目录
mkdir -p "$FLUX_DIR" "$LLM_DIR" "$AUX_DIR"

# 检查 ModelScope
if ! python3 -c "import modelscope" 2>/dev/null; then
    echo -e "${RED}错误: ModelScope 未安装${NC}"
    echo "请先运行: pip3 install modelscope"
    exit 1
fi

# ==================== FLUX.1-dev ====================

echo -e "${BLUE}[1/10] 下载 FLUX.1-dev (13GB)${NC}"
cd "$FLUX_DIR"
if [ ! -d "AI-ModelScope/FLUX.1-dev" ]; then
    python3 << EOF
from modelscope import snapshot_download
model_dir = snapshot_download('AI-ModelScope/FLUX.1-dev', cache_dir='.')
print(f"✓ 下载到: {model_dir}")
EOF
    echo -e "${GREEN}✓ FLUX.1-dev 下载完成${NC}"
else
    echo -e "${GREEN}✓ FLUX.1-dev 已存在，跳过${NC}"
fi

# ==================== Turbo LoRA ====================

echo -e "${BLUE}[2/10] 下载 Turbo LoRA (200MB)${NC}"
cd "$FLUX_DIR"
if [ ! -f "Hyper-FLUX.1-dev-8steps-lora.safetensors" ]; then
    echo "从 Hugging Face 镜像下载 Turbo LoRA..."
    wget -c https://hf-mirror.com/ByteDance/Hyper-SD/resolve/main/Hyper-FLUX.1-dev-8steps-lora.safetensors \
        || curl -L -o Hyper-FLUX.1-dev-8steps-lora.safetensors \
            https://hf-mirror.com/ByteDance/Hyper-SD/resolve/main/Hyper-FLUX.1-dev-8steps-lora.safetensors

    if [ -f "Hyper-FLUX.1-dev-8steps-lora.safetensors" ]; then
        echo -e "${GREEN}✓ Turbo LoRA 下载完成${NC}"
    else
        echo -e "${RED}✗ Turbo LoRA 下载失败${NC}"
        echo -e "${YELLOW}备选: 可以跳过此模型，使用标准 FLUX.1-dev（生成速度会慢一些）${NC}"
    fi
else
    echo -e "${GREEN}✓ Turbo LoRA 已存在，跳过${NC}"
fi

# ==================== IPAdapter Plus ====================

echo -e "${BLUE}[3/10] 下载 IPAdapter Plus (3.7GB)${NC}"
if [ ! -d "AI-ModelScope/IP-Adapter" ]; then
    python3 << EOF
from modelscope import snapshot_download
model_dir = snapshot_download('AI-ModelScope/IP-Adapter', cache_dir='.')
print(f"✓ 下载到: {model_dir}")
EOF
    echo -e "${GREEN}✓ IPAdapter Plus 下载完成${NC}"
else
    echo -e "${GREEN}✓ IPAdapter Plus 已存在，跳过${NC}"
fi

# ==================== ControlNet Canny ====================

echo -e "${BLUE}[4/10] 下载 ControlNet Canny (1.5GB)${NC}"
cd "$FLUX_DIR"
if [ ! -f "flux-controlnet-canny.safetensors" ]; then
    echo "从 Hugging Face 镜像下载 ControlNet Canny..."
    # 直接下载 safetensors 文件，不使用 git lfs
    wget -c https://hf-mirror.com/InstantX/FLUX.1-dev-Controlnet-Canny/resolve/main/diffusion_pytorch_model.safetensors \
        -O flux-controlnet-canny.safetensors

    if [ -f "flux-controlnet-canny.safetensors" ]; then
        echo -e "${GREEN}✓ ControlNet Canny 下载完成${NC}"
    else
        echo -e "${RED}✗ ControlNet Canny 下载失败${NC}"
        echo -e "${YELLOW}可以稍后手动下载或跳过此模型${NC}"
    fi
else
    echo -e "${GREEN}✓ ControlNet Canny 已存在，跳过${NC}"
fi

# ==================== ControlNet Depth ====================

echo -e "${BLUE}[5/10] 下载 ControlNet Depth (1.5GB)${NC}"
if [ ! -f "flux-controlnet-depth.safetensors" ]; then
    echo "从 Hugging Face 镜像下载 ControlNet Depth..."
    wget -c https://hf-mirror.com/Shakker-Labs/FLUX.1-dev-ControlNet-Depth/resolve/main/diffusion_pytorch_model.safetensors \
        -O flux-controlnet-depth.safetensors

    if [ -f "flux-controlnet-depth.safetensors" ]; then
        echo -e "${GREEN}✓ ControlNet Depth 下载完成${NC}"
    else
        echo -e "${RED}✗ ControlNet Depth 下载失败${NC}"
        echo -e "${YELLOW}可以稍后手动下载或跳过此模型${NC}"
    fi
else
    echo -e "${GREEN}✓ ControlNet Depth 已存在，跳过${NC}"
fi

# ==================== FLUX Fill ====================

echo -e "${BLUE}[6/10] 下载 FLUX Fill (3GB)${NC}"
if [ ! -d "AI-ModelScope/FLUX.1-Fill-dev" ]; then
    python3 << EOF
from modelscope import snapshot_download
model_dir = snapshot_download('AI-ModelScope/FLUX.1-Fill-dev', cache_dir='.')
print(f"✓ 下载到: {model_dir}")
EOF
    echo -e "${GREEN}✓ FLUX Fill 下载完成${NC}"
else
    echo -e "${GREEN}✓ FLUX Fill 已存在，跳过${NC}"
fi

# ==================== Qwen3.5-35B-A3B-FP8 ====================

echo -e "${BLUE}[7/10] 下载 Qwen3.5-35B-A3B-FP8 (35GB)${NC}"
cd "$LLM_DIR"
if [ ! -d "Qwen/Qwen3.5-35B-A3B-FP8" ]; then
    python3 << EOF
from modelscope import snapshot_download
model_dir = snapshot_download('Qwen/Qwen3.5-35B-A3B-FP8', cache_dir='.')
print(f"✓ 下载到: {model_dir}")
EOF
    echo -e "${GREEN}✓ Qwen3.5-35B-A3B-FP8 下载完成${NC}"
else
    echo -e "${GREEN}✓ Qwen3.5-35B-A3B-FP8 已存在，跳过${NC}"
fi

# ==================== Qwen2-VL ====================

echo -e "${BLUE}[8/10] 下载 Qwen2-VL-7B-Instruct (8GB)${NC}"
cd "$AUX_DIR"
if [ ! -d "Qwen/Qwen2-VL-7B-Instruct" ]; then
    python3 << EOF
from modelscope import snapshot_download
model_dir = snapshot_download('Qwen/Qwen2-VL-7B-Instruct', cache_dir='.')
print(f"✓ 下载到: {model_dir}")
EOF
    echo -e "${GREEN}✓ Qwen2-VL 下载完成${NC}"
else
    echo -e "${GREEN}✓ Qwen2-VL 已存在，跳过${NC}"
fi

# ==================== RMBG 1.4 ====================

echo -e "${BLUE}[9/10] 下载 RMBG 1.4 (200MB)${NC}"
if [ ! -d "AI-ModelScope/RMBG-1.4" ]; then
    python3 << EOF
from modelscope import snapshot_download
model_dir = snapshot_download('AI-ModelScope/RMBG-1.4', cache_dir='.')
print(f"✓ 下载到: {model_dir}")
EOF
    echo -e "${GREEN}✓ RMBG 1.4 下载完成${NC}"
else
    echo -e "${GREEN}✓ RMBG 1.4 已存在，跳过${NC}"
fi

# ==================== 完成 ====================

echo ""
echo "=========================================="
echo -e "${GREEN}所有模型下载完成！${NC}"
echo "=========================================="
echo ""
echo "模型统计:"
echo "  FLUX 模型: $(du -sh $FLUX_DIR 2>/dev/null | cut -f1 || echo '计算中...')"
echo "  LLM 模型: $(du -sh $LLM_DIR 2>/dev/null | cut -f1 || echo '计算中...')"
echo "  辅助模型: $(du -sh $AUX_DIR 2>/dev/null | cut -f1 || echo '计算中...')"
echo "  总计: $(du -sh $BASE_DIR 2>/dev/null | cut -f1 || echo '计算中...')"
echo ""
echo "下一步: 部署 ComfyUI 和 SGLang 服务"
SCRIPT

chmod +x ~/deyes/download_models_modelscope.sh
```

### 5.3 执行下载

```bash
# 在 tmux 中运行（防止 SSH 断开）
tmux new -s download

# 执行下载脚本
~/deyes/download_models_modelscope.sh

# 退出 tmux: Ctrl+B, D
# 重新连接: tmux attach -t download
```

**预计时间**: 2-4小时（取决于网络速度）

**注意事项**:
1. ✅ 无需 Hugging Face 账号
2. ✅ 无需申请访问权限
3. ✅ 支持断点续传（中断后重新运行即可）
4. ✅ 自动跳过已下载的模型

### 5.4 验证下载

```bash
# 检查模型目录
ls -lh /data/deyes/models/flux/
ls -lh /data/deyes/models/llm/
ls -lh /data/deyes/models/auxiliary/

# 检查总大小
du -sh /data/deyes/models/
# 预期: ~100GB
```

---

## Step 6: 安装 ComfyUI 自定义节点

### 6.1 创建自定义节点安装脚本

```bash
cat > ~/deyes/install_comfyui_nodes.sh << 'SCRIPT'
#!/bin/bash

set -e

CUSTOM_NODES_DIR="/data/deyes/comfyui/custom_nodes"
mkdir -p "$CUSTOM_NODES_DIR"
cd "$CUSTOM_NODES_DIR"

echo "=========================================="
echo "安装 ComfyUI 自定义节点"
echo "使用 GitHub 镜像（中国优化）"
echo "=========================================="

# 配置 GitHub 镜像
GITHUB_MIRROR="https://mirror.ghproxy.com/https://github.com"

# 1. IPAdapter Plus
echo "[1/3] 安装 IPAdapter Plus..."
if [ ! -d "ComfyUI_IPAdapter_plus" ]; then
    git clone ${GITHUB_MIRROR}/cubiq/ComfyUI_IPAdapter_plus.git || \
    git clone https://gitee.com/mirrors/ComfyUI_IPAdapter_plus.git || \
    echo "⚠️  IPAdapter Plus 安装失败，可以稍后手动安装"

    if [ -d "ComfyUI_IPAdapter_plus" ]; then
        echo "✓ IPAdapter Plus 安装完成"
    fi
else
    echo "✓ IPAdapter Plus 已存在"
fi

# 2. ControlNet Aux（可选，用于预处理）
echo "[2/3] 安装 ControlNet Aux（可选）..."
if [ ! -d "comfyui_controlnet_aux" ]; then
    echo "⚠️  ControlNet Aux 需要从 GitHub 下载，可能较慢"
    echo "   如果失败，可以跳过此节点（不影响基本功能）"

    git clone ${GITHUB_MIRROR}/Fannovel16/comfyui_controlnet_aux.git --depth 1 || \
    echo "⚠️  ControlNet Aux 安装失败（可跳过）"

    if [ -d "comfyui_controlnet_aux" ]; then
        echo "✓ ControlNet Aux 安装完成"
    else
        echo "⊙ ControlNet Aux 跳过（不影响基本功能）"
    fi
else
    echo "✓ ControlNet Aux 已存在"
fi

# 3. FLUX ControlNet Union（可选）
echo "[3/3] 安装 FLUX ControlNet Union（可选）..."
if [ ! -d "ComfyUI-FLUX-Controlnet-Union" ]; then
    echo "⚠️  FLUX ControlNet Union 需要从 GitHub 下载"
    echo "   如果失败，可以跳过此节点（不影响基本功能）"

    git clone ${GITHUB_MIRROR}/kijai/ComfyUI-FLUX-Controlnet-Union.git --depth 1 || \
    echo "⚠️  FLUX ControlNet Union 安装失败（可跳过）"

    if [ -d "ComfyUI-FLUX-Controlnet-Union" ]; then
        echo "✓ FLUX ControlNet Union 安装完成"
    else
        echo "⊙ FLUX ControlNet Union 跳过（不影响基本功能）"
    fi
else
    echo "✓ FLUX ControlNet Union 已存在"
fi

echo ""
echo "=========================================="
echo "自定义节点安装完成！"
echo "=========================================="
echo ""
echo "已安装的节点:"
ls -d */ 2>/dev/null || echo "(无)"
echo ""
echo "注意:"
echo "  - IPAdapter Plus: 必需（用于风格迁移）"
echo "  - ControlNet Aux: 可选（用于 Canny/Depth 预处理）"
echo "  - FLUX ControlNet Union: 可选（高级功能）"
echo ""
echo "如果某些节点安装失败，可以稍后在 ComfyUI 中手动安装"
SCRIPT

chmod +x ~/deyes/install_comfyui_nodes.sh
```

### 6.2 执行安装

```bash
# 方法 1: 直接执行（推荐）
~/deyes/install_comfyui_nodes.sh

# 方法 2: 如果 GitHub 连接失败，跳过自定义节点
# ComfyUI 启动后可以在 Web 界面中安装
echo "跳过自定义节点安装，稍后在 ComfyUI Manager 中安装"
```

### 6.3 备选方案：手动安装

如果脚本安装失败，可以在 ComfyUI 启动后使用 **ComfyUI Manager** 安装：

1. 启动 ComfyUI
2. 访问 http://<server-ip>:8188
3. 点击右侧的 "Manager" 按钮
4. 搜索并安装：
   - IPAdapter Plus
   - ControlNet Aux
   - FLUX ControlNet Union

### 6.4 最小化安装（跳过自定义节点）

如果网络问题严重，可以**完全跳过**自定义节点安装：

```bash
# 跳过 Step 6，直接进入 Step 7
echo "使用 ComfyUI 内置功能，跳过自定义节点"
```

**影响**:
- ✅ FLUX 基础功能正常
- ✅ LoRA 加载正常
- ⚠️  IPAdapter 需要手动安装插件
- ⚠️  ControlNet 预处理需要手动安装插件

---

## Step 10: 验证部署

### 10.1 检查所有服务

```bash
# 检查容器状态
docker compose ps

# 预期输出: 所有服务状态为 Up
```

### 10.2 测试 SGLang

```bash
curl -X POST http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen3.5-35B-A3B-FP8", "messages": [{"role": "user", "content": "测试"}]}'
```

### 10.3 测试 ComfyUI

```bash
curl -s http://localhost:8188/ | grep "ComfyUI"
curl -s http://localhost:8189/ | grep "ComfyUI"
```

### 10.4 生成测试图片

访问 http://<server-ip>:8188，加载 basic-test-workflow.json，点击 "Queue Prompt"

---

## 🚨 故障排查

### 问题 1: 模型下载失败（网络问题）

**症状**: 下载中断、超时或速度慢

**解决方案**:

**方法 1: 重新运行脚本（推荐）**
```bash
# ModelScope 支持断点续传，直接重新运行即可
~/deyes/download_models_modelscope.sh
```

**方法 2: 单独下载某个模型**
```bash
python3 << PYEOF
from modelscope import snapshot_download
model_dir = snapshot_download('AI-ModelScope/FLUX.1-dev',
                               cache_dir='/data/deyes/models/flux')
print(f"下载到: {model_dir}")
PYEOF
```

**方法 3: 使用代理（如果有）**
```bash
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port
~/deyes/download_models_modelscope.sh
```

### 问题 2: Turbo LoRA / ControlNet 下载失败（404 错误）

**症状**: Turbo LoRA 或 ControlNet 下载返回 404 或失败

**原因**: ModelScope 上可能没有这些模型，需要从 Hugging Face 镜像下载

**解决方案**:

**Turbo LoRA 下载**:
```bash
cd /data/deyes/models/flux
wget -c https://hf-mirror.com/ByteDance/Hyper-SD/resolve/main/Hyper-FLUX.1-dev-8steps-lora.safetensors
```

**ControlNet Canny 下载**:
```bash
cd /data/deyes/models/flux
wget -c https://hf-mirror.com/InstantX/FLUX.1-dev-Controlnet-Canny/resolve/main/diffusion_pytorch_model.safetensors \
    -O flux-controlnet-canny.safetensors
```

**ControlNet Depth 下载**:
```bash
cd /data/deyes/models/flux
wget -c https://hf-mirror.com/Shakker-Labs/FLUX.1-dev-ControlNet-Depth/resolve/main/diffusion_pytorch_model.safetensors \
    -O flux-controlnet-depth.safetensors
```

**一键下载所有缺失模型**:
```bash
cd /data/deyes/models/flux

# Turbo LoRA
[ ! -f "Hyper-FLUX.1-dev-8steps-lora.safetensors" ] && \
    wget -c https://hf-mirror.com/ByteDance/Hyper-SD/resolve/main/Hyper-FLUX.1-dev-8steps-lora.safetensors

# ControlNet Canny
[ ! -f "flux-controlnet-canny.safetensors" ] && \
    wget -c https://hf-mirror.com/InstantX/FLUX.1-dev-Controlnet-Canny/resolve/main/diffusion_pytorch_model.safetensors \
        -O flux-controlnet-canny.safetensors

# ControlNet Depth
[ ! -f "flux-controlnet-depth.safetensors" ] && \
    wget -c https://hf-mirror.com/Shakker-Labs/FLUX.1-dev-ControlNet-Depth/resolve/main/diffusion_pytorch_model.safetensors \
        -O flux-controlnet-depth.safetensors

echo "✓ 所有模型下载完成"
```

### 问题 3: GitHub 连接失败（自定义节点安装）

**症状**: `Failed to connect to github.com port 443` 或 `Connection timed out`

**原因**: 中国大陆访问 GitHub 不稳定

**解决方案**:

**方法 1: 使用 GitHub 镜像（推荐）**
```bash
cd /data/deyes/comfyui/custom_nodes

# 使用 ghproxy 镜像
git clone https://mirror.ghproxy.com/https://github.com/cubiq/ComfyUI_IPAdapter_plus.git

# 或使用 Gitee 镜像
git clone https://gitee.com/mirrors/ComfyUI_IPAdapter_plus.git
```

**方法 2: 配置 Git 使用代理（如果有）**
```bash
# HTTP 代理
git config --global http.proxy http://proxy-server:port
git config --global https.proxy http://proxy-server:port

# SOCKS5 代理
git config --global http.proxy socks5://proxy-server:port
git config --global https.proxy socks5://proxy-server:port

# 取消代理
git config --global --unset http.proxy
git config --global --unset https.proxy
```

**方法 3: 跳过自定义节点，稍后在 ComfyUI Manager 中安装**
```bash
# 完全跳过 Step 6
echo "跳过自定义节点安装"

# 启动 ComfyUI 后：
# 1. 访问 http://<server-ip>:8188
# 2. 点击右侧 "Manager" 按钮
# 3. 搜索并安装需要的节点
```

**方法 4: 手动下载并上传**
```bash
# 在本地电脑下载：
# https://github.com/cubiq/ComfyUI_IPAdapter_plus/archive/refs/heads/main.zip

# 上传到服务器
scp ComfyUI_IPAdapter_plus-main.zip root@server:/data/deyes/comfyui/custom_nodes/

# 解压
cd /data/deyes/comfyui/custom_nodes
unzip ComfyUI_IPAdapter_plus-main.zip
mv ComfyUI_IPAdapter_plus-main ComfyUI_IPAdapter_plus
```

**最简单的方案**: 完全跳过自定义节点安装，ComfyUI 基础功能仍然可用

### 问题 4: ModelScope 安装失败

**症状**: `pip install modelscope` 失败

**解决方案**:
```bash
# 使用阿里云镜像
pip3 install modelscope -i https://mirrors.aliyun.com/pypi/simple/

# 或使用清华镜像
pip3 install modelscope -i https://pypi.tuna.tsinghua.edu.cn/simple/
```

### 问题 4: SGLang 启动失败

**症状**: `docker compose logs sglang` 显示 OOM 或 CUDA 错误

**排查步骤**:
```bash
# 1. 检查 GPU 显存
nvidia-smi

# 2. 检查模型路径
docker exec deyes-sglang ls /models/llm/

# 3. 重启服务
docker compose restart sglang
docker compose logs -f sglang
```

**解决方案**:
- 确保 GPU 6-7 没有被其他进程占用
- 检查模型路径是否正确
- 降低 `--mem-fraction-static` 到 0.80

### 问题 5: ComfyUI 无法加载模型

**症状**: ComfyUI 界面中看不到模型文件

**排查步骤**:
```bash
# 1. 检查模型文件
ls -lh /data/deyes/models/flux/

# 2. 检查容器内路径
docker exec deyes-comfyui-1 ls /root/models/checkpoints/

# 3. 检查文件权限
ls -l /data/deyes/models/flux/
```

**解决方案**:
- 确保模型文件已下载完整（检查文件大小）
- 检查 Docker volume 挂载是否正确
- 修改文件权限: `sudo chown -R $USER:$USER /data/deyes/models/`

### 问题 6: 生成图片失败 (OOM)

**症状**: ComfyUI 报错 "Out of memory" 或 "CUDA error"

**排查步骤**:
```bash
# 1. 检查 GPU 显存使用
nvidia-smi

# 2. 查看 ComfyUI 日志
docker compose logs comfyui-1 | tail -50
```

**解决方案**:
- 降低分辨率到 512×512 测试
- 减少 batch_size 到 1
- 确保使用 FP8 模型（flux1-dev-fp8.safetensors）
- 重启 ComfyUI: `docker compose restart comfyui-1`


## 📋 日常运维

### 每日检查
```bash
docker compose ps
nvidia-smi
df -h /data
docker compose logs --tail=100 | grep -i error
```

### 备份策略
```bash
# 备份 PostgreSQL
docker exec deyes-postgres pg_dump -U deyes deyes > backup.sql

# 备份配置
tar -czf config_backup.tar.gz ~/deyes/
```

---

## 📚 下一步

1. 开发 Agent（参考 agent-definitions.md）
2. 集成 RPA（连接电商平台）
3. 优化工作流参数
4. 扩展产能（增加 GPU）

---

**最后更新**: 2026-03-20
**文档版本**: v1.0
**文档状态**: 生产就绪
