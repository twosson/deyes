# Deyes 系统架构设计 v4.0

> 跨境电商数字员工系统 - 完整技术架构
>
> 版本: v4.0 | 更新: 2026-03-19 | 状态: 生产就绪

---

## 📋 目录

1. [系统概览](#系统概览)
2. [核心技术栈](#核心技术栈)
3. [GPU资源分配](#gpu资源分配)
4. [图像生成架构](#图像生成架构)
5. [LLM推理架构](#llm推理架构)
6. [存储架构](#存储架构)
7. [性能指标](#性能指标)
8. [成本分析](#成本分析)

---

## 系统概览

### 设计目标

- **日产能**: 8,000套产品（1主图 + 8详情页）
- **质量标准**: 92分（电商主图专业级）
- **风格一致性**: 90%+
- **产品变形率**: <5%
- **硬件**: 8x RTX 4090 (24GB/卡)

### 架构分层

```
┌─────────────────────────────────────────────────────────┐
│                    业务编排层                              │
│         LangGraph + CrewAI + n8n + Celery              │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    AI推理层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  ComfyUI     │  │   SGLang     │  │  Qwen-Edit   │  │
│  │  图像生成     │  │  LLM推理     │  │  图像编辑     │  │
│  │  (卡0-3)     │  │  (卡6-7)     │  │  (卡5)       │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    存储层                                 │
│  PostgreSQL │ Redis │ Qdrant │ MinIO                   │
└─────────────────────────────────────────────────────────┘
```

---

## 核心技术栈

### 图像生成层 ⭐⭐⭐⭐⭐

| 组件 | 版本/模型 | 作用 | 显存 |
|------|----------|------|------|
| **基础模型** | FLUX.1-dev (FP8) | 文生图基础模型 | 13GB |
| **加速LoRA** | Turbo LoRA | 3倍速度提升 | 200MB |
| **风格迁移** | IPAdapter Plus | 爆款风格复刻 | 3.7GB |
| **结构控制** | ControlNet (Canny+Depth) | 防止产品变形 | 3GB |
| **局部编辑** | FLUX Fill | 背景替换、文字编辑 | 3GB |
| **批量引擎** | ComfyUI | 工作流编排 | - |

**为什么选 FLUX.1 而不是 FLUX.2?**
- FLUX.2-dev 需要 54GB+ 显存（单卡装不下）
- FLUX.1-dev + IPAdapter + ControlNet 质量已达 92分
- FLUX.1 生态更成熟，Turbo LoRA 只支持 FLUX.1

### LLM推理层 ⭐⭐⭐⭐⭐

| 组件 | 版本/模型 | 作用 | 显存 |
|------|----------|------|------|
| **推理引擎** | SGLang | 29%比vLLM快 | - |
| **基础模型** | Qwen3.5-35B-A3B (FP8) | 多模态LLM | 15.4GB/卡 |
| **视觉模型** | Qwen2-VL | 图像理解 | 8GB |
| **并行方式** | Tensor Parallel (2卡) | 提升吞吐量 | - |

**为什么选 Qwen3.5 而不是 DeepSeek-R1?**
- 原生多模态（图文视频统一处理）
- 201语言支持（覆盖所有跨境市场）
- 推理速度快（无需思考链）
- 阿里电商基因（理解SKU、MOQ等术语）

### 存储层

| 组件 | 作用 | 性能 |
|------|------|------|
| **MinIO** | 对象存储（图片） | 500MB/s |
| **PostgreSQL** | 结构化数据 | 10K TPS |
| **Redis** | 缓存队列 | 100K OPS |
| **Qdrant** | 向量检索 | 10K QPS |

### 编排层

| 组件 | 作用 |
|------|------|
| **LangGraph** | 全局Agent编排 |
| **CrewAI** | 角色协作 |
| **n8n** | 轻量工作流 |
| **Celery** | 高并发任务队列（500+并发） |

---

## GPU资源分配

### 8卡 RTX 4090 分配方案

```
┌─────────────────────────────────────────────────────────┐
│  卡0-1: ComfyUI 实例1 (主图生成)                          │
│  ├─ FLUX.1-dev (FP8): 13GB                              │
│  ├─ IPAdapter Plus: 3.7GB                               │
│  ├─ ControlNet (Canny+Depth): 3GB                       │
│  ├─ Turbo LoRA: 200MB                                   │
│  └─ 工作内存: 4GB                                        │
│  总计: ~24GB ✅                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  卡2-3: ComfyUI 实例2 (详情页生成)                        │
│  └─ 同上配置                                             │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  卡4: FLUX Fill (局部编辑)                               │
│  ├─ FLUX.1-dev (共享): 13GB                             │
│  ├─ Fill模块: 3GB                                       │
│  └─ 工作内存: 8GB                                        │
│  总计: ~24GB ✅                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  卡5: Qwen-Image-Edit (高级编辑)                         │
│  ├─ Qwen-Image-Edit: 8GB                                │
│  └─ 工作内存: 16GB                                       │
│  总计: ~24GB ✅                                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  卡6-7: SGLang (Qwen3.5-35B-A3B)                        │
│  ├─ Tensor Parallel: 15.4GB/卡                          │
│  ├─ 提示词生成、质量检测                                  │
│  └─ 并发: 25-30个Agent                                  │
│  总计: ~15.4GB/卡 ✅                                     │
└─────────────────────────────────────────────────────────┘
```

### 显存利用率

- **总显存**: 8 × 24GB = 192GB
- **实际使用**: ~182GB
- **利用率**: 95% ✅

---

## 图像生成架构

### 主图复刻工作流

```
┌─────────────────────────────────────────────────────────┐
│  输入                                                     │
│  ├─ 产品图 (自己的，白底/透明背景)                        │
│  ├─ 爆款参考图 (1-3张，目标风格)                          │
│  └─ 提示词 (Qwen3.5自动生成)                             │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  ComfyUI 工作流                                          │
│                                                          │
│  1. Load Checkpoint                                      │
│     ├─ FLUX.1-dev-fp8.safetensors                       │
│     └─ Turbo LoRA (weight: 0.8)                         │
│                                                          │
│  2. Preprocessing                                        │
│     ├─ Canny Edge Detection (产品图)                     │
│     └─ Depth Map Estimation (产品图)                     │
│                                                          │
│  3. IPAdapter Apply                                      │
│     ├─ 参考图1 (weight: 0.85, style+composition)        │
│     ├─ 参考图2 (weight: 0.75, style)                    │
│     └─ 参考图3 (weight: 0.65, color)                    │
│                                                          │
│  4. ControlNet Apply                                     │
│     ├─ Canny (strength: 0.8)                            │
│     └─ Depth (strength: 0.7)                            │
│                                                          │
│  5. CLIP Text Encode                                     │
│     ├─ Positive: "高端产品摄影，白色背景，柔和光影..."     │
│     └─ Negative: "模糊，低质，畸形，水印"                 │
│                                                          │
│  6. KSampler                                             │
│     ├─ steps: 8 (Turbo LoRA加速)                        │
│     ├─ CFG: 3.5                                         │
│     ├─ sampler: dpmpp_2m_sde_gpu                        │
│     └─ denoise: 0.45                                    │
│                                                          │
│  7. Save Image                                           │
│     └─ /data/deyes/comfyui/output/{sku}/main.png       │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  输出                                                     │
│  ├─ 主图 (1024×1024, 风格一致性 90%+)                    │
│  ├─ 元数据 (prompt, 参数, 参考图ID)                      │
│  └─ 质量评分 (Qwen3.5-VL自动打分)                        │
└─────────────────────────────────────────────────────────┘
```

### 关键参数

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| **IPAdapter weight** | 0.75-0.95 | 太高容易过度相似 |
| **ControlNet Canny** | 0.7-0.9 | 边缘保持强度 |
| **ControlNet Depth** | 0.6-0.8 | 深度保持强度 |
| **Denoising** | 0.35-0.55 | 保留原产品细节 |
| **Resolution** | 1024×1024 | 电商标准尺寸 |
| **Steps** | 8 | Turbo LoRA加速 |

### 详情页场景图工作流

基础流程同主图，但调整：
- 参考图换成生活场景/模特使用图
- IPAdapter weight 降低: 0.6-0.8
- ControlNet strength 降低: 0.5-0.7
- Denoise 提高: 0.5-0.7 (更多变化)

### 局部编辑工作流

```
1. Load Image (已生成的主图)
2. Create Mask (SAM自动检测 或 手动绘制)
3. FLUX Fill / Qwen-Image-Edit
   ├─ Inpaint区域: mask
   ├─ Prompt: "替换为白色纯色背景"
   └─ Strength: 0.8
4. Save Image
```

---

## LLM推理架构

### SGLang 部署配置

```yaml
sglang:
  image: lmsysorg/sglang:latest
  container_name: deyes-sglang
  command: >
    python -m sglang.launch_server
    --model /data/models/llm/Qwen3.5-35B-A3B
    --tp 2
    --mem-fraction-static 0.85
    --enable-torch-compile
    --trust-remote-code
  ports:
    - "30000:30000"
  volumes:
    - /data/deyes/models:/data/models
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            device_ids: ['6', '7']
            capabilities: [gpu]
```

### 性能指标

| 指标 | SGLang | vLLM | 提升 |
|------|--------|------|------|
| **吞吐量** | 200-250 tokens/s | 150 tokens/s | +33-67% |
| **并发请求** | 25-30个 | 15-20个 | +50-67% |
| **多轮对话** | 2-3倍快 | 基准 | RadixAttention |

### 典型应用场景

1. **提示词生成**
   - 输入: 爆款主图 + 产品图 + 类目
   - 输出: 结构化FLUX提示词
   - 时间: 2-3秒

2. **质量检测**
   - 输入: 生成的主图
   - 输出: 质量评分 (0-100)
   - 时间: 1-2秒

3. **商品描述生成**
   - 输入: 产品图 + 卖点
   - 输出: 多语言商品描述
   - 时间: 3-5秒

---

## 存储架构

### MinIO 对象存储

```
/data/deyes/minio/
├── product-images/          # 产品原图
│   ├── {sku}/
│   │   ├── main.jpg
│   │   ├── detail_1.jpg
│   │   └── ...
├── generated-images/        # 生成的图片
│   ├── {sku}/
│   │   ├── main_{timestamp}.png
│   │   ├── detail_1_{timestamp}.png
│   │   └── ...
├── reference-images/        # 爆款参考图
│   ├── {category}/
│   │   ├── ref_001.jpg
│   │   └── ...
└── temp/                    # 临时文件
```

**性能**:
- 读取: 500MB/s
- 写入: 300MB/s
- 并发: 1000+ 连接

### PostgreSQL 数据库

```sql
-- 产品表
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(100) UNIQUE,
    title TEXT,
    category VARCHAR(50),
    status VARCHAR(20),
    created_at TIMESTAMP
);

-- 图片表
CREATE TABLE images (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    type VARCHAR(20),  -- main, detail, reference
    url TEXT,
    metadata JSONB,
    quality_score INTEGER,
    created_at TIMESTAMP
);

-- 任务表
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    product_id INTEGER REFERENCES products(id),
    type VARCHAR(50),
    status VARCHAR(20),
    result JSONB,
    created_at TIMESTAMP
);
```

### Redis 缓存

```
# 任务队列
celery:queue:image_generation
celery:queue:llm_inference
celery:queue:quality_check

# 缓存
cache:prompt:{hash}
cache:quality_score:{image_id}
cache:reference_images:{category}

# 会话
session:agent:{agent_id}
```

### Qdrant 向量数据库

```python
# 爆款图片向量索引
collection_name = "reference_images"
vector_size = 768  # CLIP embedding

# 用途
- 相似图片检索
- 风格匹配
- 去重检测
```

---

## 性能指标

### 图像生成性能

| 任务类型 | 单张时间 | 并发能力 | 日产量 (20h) |
|---------|---------|---------|-------------|
| **主图** (1024×1024) | 8-12s | 8张/批 | 28,800张 |
| **详情页场景图** | 10-15s | 6张/批 | 17,280张 |
| **局部编辑** | 5-10s | 4张/批 | 14,400张 |

**套数产能** (1主图 + 8详情页):
- 理论: 28,800 / 9 = **3,200套/天**
- 实际 (考虑队列、重试): **2,400-2,800套/天**
- 峰值 (优化后): **3,500套/天**

### LLM推理性能

| 任务类型 | 单次时间 | 并发能力 | 日产量 (20h) |
|---------|---------|---------|-------------|
| **提示词生成** | 2-3s | 25个 | 600,000次 |
| **质量检测** | 1-2s | 30个 | 1,080,000次 |
| **商品描述** | 3-5s | 20个 | 288,000次 |

### 系统整体性能

- **日产能**: 2,400-2,800套 (保守估计)
- **峰值产能**: 3,500套 (优化后)
- **目标需求**: 8,000套
- **满足度**: 30-44% ⚠️

**⚠️ 产能缺口分析**:
- 当前架构: 2,400-2,800套/天
- 目标需求: 8,000套/天
- 缺口: 5,200-5,600套/天

**解决方案**:
1. **水平扩展**: 增加到 24卡 (3台服务器)
2. **混合方案**: 80%本地 + 20%API (FLUX 1.1 Pro)
3. **优化工作流**: 减少不必要的步骤

---

## 成本分析

### 硬件成本

```
已有硬件:
- 8x RTX 4090: 80,000元

需采购硬件:
- 主板 (8卡PCIe 4.0): 8,000元
- CPU (Xeon/EPYC): 15,000元
- 内存 (256GB ECC): 8,000元
- 存储 (6TB NVMe): 4,000元
- 电源 (2×2000W): 6,000元
- 机箱 (4U机架): 3,000元
- 散热 (风冷): 2,000元

总计: 126,000元
```

### 运营成本

```
电费:
- 功耗: 3450W (8卡) + 550W (其他) = 4000W
- 电价: 0.6元/kWh
- 日成本: 4kW × 20h × 0.6元 = 48元
- 月成本: 48元 × 30天 = 1,440元

软件:
- 2Captcha: 2元/天 = 60元/月

维护:
- 人工: 500元/月

总计: 2,000元/月
```

### 单套成本

```
纯本地方案:
- 日成本: 50元
- 日产能: 2,800套
- 单套成本: 0.018元

混合方案 (80%本地 + 20%API):
- 本地成本: 50元/天
- API成本: 530元/天 (FLUX 1.1 Pro)
- 总成本: 580元/天
- 日产能: 8,000套
- 单套成本: 0.073元
```

### 投资回收

```
对比云服务 (全API):
- 云服务成本: 2,650元/天 (8,000套)
- 本地成本: 50元/天 (2,800套)
- 节省: 98.1%

投资回收期:
- 硬件投资: 126,000元
- 月节省: 78,000元 (vs 云服务)
- 回收期: 1.6个月 ✅
```

---

## 部署架构

### Docker Compose 配置

```yaml
version: '3.8'

services:
  # 基础服务
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

  redis:
    image: redis:7-alpine
    container_name: deyes-redis
    command: redis-server --appendonly yes --maxmemory 2gb
    volumes:
      - /data/deyes/redis:/data
    ports:
      - "6379:6379"
    networks:
      - deyes_network
    restart: unless-stopped

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

  # AI推理服务
  sglang:
    image: lmsysorg/sglang:latest
    container_name: deyes-sglang
    command: >
      python -m sglang.launch_server
      --model /data/models/llm/Qwen3.5-35B-A3B
      --tp 2
      --mem-fraction-static 0.85
      --enable-torch-compile
      --trust-remote-code
    ports:
      - "30000:30000"
    volumes:
      - /data/deyes/models:/data/models
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['6', '7']
              capabilities: [gpu]
    networks:
      - deyes_network
    restart: unless-stopped

  comfyui-1:
    image: comfyui/comfyui:latest
    container_name: deyes-comfyui-1
    volumes:
      - /data/deyes/models:/data/models
      - /data/deyes/comfyui/output:/output
    ports:
      - "8188:8188"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['0', '1']
              capabilities: [gpu]
    networks:
      - deyes_network
    restart: unless-stopped

  comfyui-2:
    image: comfyui/comfyui:latest
    container_name: deyes-comfyui-2
    volumes:
      - /data/deyes/models:/data/models
      - /data/deyes/comfyui/output:/output
    ports:
      - "8189:8188"
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              device_ids: ['2', '3']
              capabilities: [gpu]
    networks:
      - deyes_network
    restart: unless-stopped

networks:
  deyes_network:
    external: true
```

---

## 下一步

1. **[统一部署指南](../../DEPLOYMENT.md)** - 开始部署
2. **[ComfyUI 完整部署指南](../deployment/comfyui-deployment-guide.md)** - 图像服务专项配置
3. **[Agent定义](../agents/agent-definitions.md)** - 了解24个数字员工
4. **[核心业务流程](../workflows/core-business-flows.md)** - 业务流程设计

---

## 参考资料

- [FLUX for E-Commerce](https://www.mimicpc.com/learn/flux-for-product-cutout-and-background-replacement-in-e-commerce)
- [ComfyUI IPAdapter Plus](https://www.runcomfy.com/comfyui-nodes/ComfyUI_IPAdapter_plus/)
- [FLUX ControlNet Guide](https://comfyui-wiki.com/en/tutorial/advanced/flux-controlnet-workflow-guide)
- [SGLang Documentation](https://github.com/sgl-project/sglang)
- [Qwen3.5 Documentation](https://huggingface.co/Qwen)

---

**版本历史**:
- v4.0 (2026-03-19): 整合 IPAdapter + ControlNet，质量提升到92分
- v3.0 (2026-03-17): SGLang + Qwen3.5 + FLUX.1 + Turbo LoRA
- v2.0 (2026-03-15): vLLM + MinIO 优化
- v1.0 (2026-03-10): 初始架构设计
