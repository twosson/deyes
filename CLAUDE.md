# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 项目概述

**Deyes** - 跨境电商数字员工系统

使用 AI 技术替代传统电商运营岗位，实现自动化选品、图片生成、商品上架、客服等功能。

**目标平台**: Temu, AliExpress, Amazon, Ozon, Rakuten, Mercado Libre
**硬件**: 8x RTX 4090 (24GB/卡)
**日产能**: 8,000套产品（1主图 + 8详情页）

---

## 文档结构

### 📚 必读文档（按优先级）

1. **[系统架构 v4.0](docs/architecture/system-architecture-v4.md)** ⭐⭐⭐⭐⭐
   - 完整技术栈和架构设计
   - GPU资源分配方案
   - 性能指标和成本分析
   - **这是最重要的文档，包含所有架构决策**

2. **[硬件验证报告](docs/architecture/hardware-validation-8x4090.md)** ⭐⭐⭐⭐
   - 8x4090 性能验证
   - 显存计算和GPU分配
   - 配套硬件采购清单

3. **[统一部署指南](DEPLOYMENT.md)** ⭐⭐⭐⭐⭐
   - 当前仓库唯一部署说明
   - 前后端、数据库、AI 服务统一部署
   - 服务验证与故障排查

4. **[ComfyUI 完整部署指南](docs/deployment/comfyui-deployment-guide.md)** ⭐⭐⭐⭐
   - ComfyUI 图像生成服务专项部署
   - 模型下载、工作流配置与专项排障

5. **[Qwen3.5 vs DeepSeek 对比](docs/architecture/qwen3.5-vs-deepseek-ecommerce-analysis.md)** ⭐⭐⭐
   - 模型选型分析
   - 电商场景适配性对比

5. **[实施计划](docs/deployment/implementation-plan.md)** ⭐⭐⭐
   - 4周实施时间表
   - 里程碑和交付物

### 📋 业务文档

- **[Agent定义](docs/agents/agent-definitions.md)** - 24个数字员工岗位定义
- **[核心业务流程](docs/workflows/core-business-flows.md)** - 业务流程设计

### 🗑️ 归档文档

以下文档已过时，原则上不再保留多份旧文档；当前仅保留必要主文档并持续清理历史材料。

---

## 核心技术栈 v4.0

### 图像生成层

```
FLUX.1-dev (FP8) + Turbo LoRA + IPAdapter Plus + ControlNet
├─ 基础模型: FLUX.1-dev (13GB)
├─ 加速: Turbo LoRA (3倍速度提升)
├─ 风格迁移: IPAdapter Plus (爆款复刻)
├─ 结构控制: ControlNet (Canny + Depth)
└─ 局部编辑: FLUX Fill
```

**为什么不用 FLUX.2?**
- FLUX.2-dev 需要 54GB+ 显存（单卡装不下）
- FLUX.1 + IPAdapter + ControlNet 质量已达 92分

### LLM推理层

```
SGLang + Qwen3.5-35B-A3B (FP8)
├─ 推理引擎: SGLang (比vLLM快29%)
├─ 基础模型: Qwen3.5-35B-A3B (15.4GB/卡, Tensor Parallel)
├─ ���觉模型: Qwen2-VL (图像理解)
└─ 并发: 25-30个Agent
```

**为什么不用 DeepSeek-R1?**
- Qwen3.5 原生多模态（图文视频统一）
- 201语言支持（覆盖所有跨境市场）
- 推理速度快（无需思考链）
- 阿里电商基因（理解SKU、MOQ等术语）

### 存储层

```
MinIO + PostgreSQL + Redis + Qdrant
├─ MinIO: 对象存储（图片，500MB/s）
├─ PostgreSQL: 结构化数据
├─ Redis: 缓存队列
└─ Qdrant: 向量检索
```

### 编排层

```
LangGraph + CrewAI + n8n + Celery
├─ LangGraph: 全局Agent编排
├─ CrewAI: 角色协作
├─ n8n: 轻量工作流
└─ Celery: 高并发任务队列（500+并发）
```

---

## GPU资源分配

```
8x RTX 4090 (24GB/卡) 分配方案:

卡0-1: ComfyUI实例1 (主图生成)
  └─ FLUX.1 + IPAdapter + ControlNet + Turbo LoRA (~24GB)

卡2-3: ComfyUI实例2 (详情页生成)
  └─ 同上配置 (~24GB)

卡4: FLUX Fill (局部编辑, ~24GB)

卡5: Qwen-Image-Edit (高级编辑, ~24GB)

卡6-7: SGLang (Qwen3.5-35B-A3B, Tensor Parallel)
  └─ 15.4GB/卡, 提示词生成、质量检测
```

**显存利用率**: 95% ✅

---

## 性能指标

### 图像生成

| 任务 | 单张时间 | 日产量 (20h) |
|------|---------|-------------|
| 主图 | 8-12s | 28,800张 |
| 详情页 | 10-15s | 17,280张 |
| 局部编辑 | 5-10s | 14,400张 |

**套数产能** (1主图 + 8详情页):
- 理论: 3,200套/天
- 实际: 2,400-2,800套/天
- 峰值: 3,500套/天

### LLM推理

| 任务 | 单次时间 | 并发 | 日产量 (20h) |
|------|---------|------|-------------|
| 提示词生成 | 2-3s | 25个 | 600,000次 |
| 质量检测 | 1-2s | 30个 | 1,080,000次 |
| 商品描述 | 3-5s | 20个 | 288,000次 |

---

## 关键架构决策

### 1. FLUX.1-dev vs FLUX.2-dev

**决策**: 使用 FLUX.1-dev ✅

**原因**:
- FLUX.2 需要 54GB+ 显存（单卡装不下）
- FLUX.1 + IPAdapter + ControlNet 质量已达 92分
- FLUX.1 生态更成熟，Turbo LoRA 只支持 FLUX.1

### 2. Qwen3.5 vs DeepSeek-R1

**决策**: 使用 Qwen3.5-35B-A3B ✅

**原因**:
- 原生多模态（图文视频统一处理）
- 201语言支持（覆盖所有跨境市场）
- 推理速度快（无需思考链）
- 阿里电商基因（理解电商术语）

### 3. SGLang vs vLLM

**决策**: 使用 SGLang ✅

**原因**:
- 比 vLLM 快 29%
- RadixAttention 自动KV缓存复用
- 原生支持 JSON Schema 约束

### 4. IPAdapter + ControlNet

**决策**: 必须使用 ✅

**原因**:
- IPAdapter: 风格一致性从 60% → 90%+
- ControlNet: 产品变形率从 30% → 5%
- 这是 2026年电商主图复刻的行业标准

---

## 部署状态

### 当前状态

- ✅ 硬件已采购: 8x RTX 4090
- ✅ 系统已安装: Ubuntu 22.04 + CUDA 13.1 + Docker
- ⏳ 待执行: 按根目录 `DEPLOYMENT.md` 完成统一部署；ComfyUI 专项细节参考 `docs/deployment/comfyui-deployment-guide.md`

### 下一步

1. 安装 NVIDIA Container Toolkit
2. 创建项目目录结构
3. 下载 AI 模型（~100GB，2-4小时）
4. 部署基础服务（PostgreSQL, Redis, Qdrant, MinIO）
5. 部署 AI 推理服务（SGLang, ComfyUI）
6. 测试和验证

---

## 开发指南

### 模型下载（中国镜像）

**重要**: 服务器在中国，必须使用镜像站

```bash
# 配置 Git 使用镜像
git config --global url."https://hf-mirror.com/".insteadOf "https://huggingface.co/"

# 下载模型
cd /data/deyes/models/llm
git clone https://hf-mirror.com/Qwen/Qwen3.5-35B-A3B

cd /data/deyes/models/flux
wget -c https://hf-mirror.com/black-forest-labs/FLUX.1-dev/resolve/main/flux1-dev.safetensors
```

### ComfyUI 工作流

主图复刻工作流节点链：

```
Load Checkpoint (FLUX.1-dev-fp8 + Turbo LoRA)
  ↓
Preprocessing (Canny + Depth)
  ↓
IPAdapter Apply (参考图1-3张, weight 0.75-0.95)
  ↓
ControlNet Apply (Canny 0.8 + Depth 0.7)
  ↓
CLIP Text Encode (Prompt + Negative)
  ↓
KSampler (steps 8, CFG 3.5, denoise 0.45)
  ↓
Save Image
```

### Docker Compose

```bash
# 启动所有服务
cd ~/deyes
docker compose up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f sglang
docker compose logs -f comfyui-1
```

---

## 常见问题

### Q1: 为什么不用 FLUX.2?

A: FLUX.2-dev 需要 54GB+ 显存（32GB模型 + 24GB文本编码器），单卡 4090 装不下。FLUX.1-dev + IPAdapter + ControlNet 质量已达 92分，满足需求。

### Q2: 为什么选 Qwen3.5 而不是 DeepSeek-R1?

A: Qwen3.5 原生多模态、201语言支持、推理速度快、阿里电商基因。DeepSeek-R1 虽然数学推理强，但纯文本、需要思考链、不适合电商场景。

### Q3: 产能只有 2,800套/天，如何达到 8,000套?

A: 三种方案：
1. 水平扩展：增加到 24卡（3台服务器）
2. 混合方案：80%本地 + 20%API (FLUX 1.1 Pro)
3. 优化工作流：减少不必要的步骤

### Q4: 模型下载失败怎么办?

A: 确保使用中国镜像 hf-mirror.com，配置 Git：
```bash
git config --global url."https://hf-mirror.com/".insteadOf "https://huggingface.co/"
```

### Q5: IPAdapter 和 ControlNet 是什么?

A:
- **IPAdapter**: 风格迁移工具，从爆款图提取风格（光影、构图、色调）
- **ControlNet**: 结构控制工具，防止产品变形，保持轮廓和深度

---

## 重要提醒

1. **模型下载**: 必须使用 hf-mirror.com（中国镜像）
2. **显存管理**: 每卡 24GB，必须精确计算显存占用
3. **质量优先**: 电商主图质量是核心竞争力，不要为了速度牺牲质量
4. **备份策略**: 保留 v3.0 环境作为备份
5. **监控**: 建立质量对比监控，持续优化

---

## 参考资料

- [FLUX for E-Commerce](https://www.mimicpc.com/learn/flux-for-product-cutout-and-background-replacement-in-e-commerce)
- [ComfyUI IPAdapter Plus](https://www.runcomfy.com/comfyui-nodes/ComfyUI_IPAdapter_plus/)
- [FLUX ControlNet Guide](https://comfyui-wiki.com/en/tutorial/advanced/flux-controlnet-workflow-guide)
- [SGLang Documentation](https://github.com/sgl-project/sglang)
- [Qwen3.5 Documentation](https://huggingface.co/Qwen)

---

**最后更新**: 2026-03-20
**架构版本**: v4.0
**文档状态**: 生产就绪
