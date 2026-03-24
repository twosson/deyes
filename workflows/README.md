# ComfyUI 工作流使用指南

## 文件说明

| 文件 | 用途 | GPU | 依赖 |
|------|------|-----|------|
| `basic-test-workflow.json` | 基础测试 (推荐先用这个) | 任意 | 无 |
| `main-image-workflow.json` | 主图生成 (完整版) | 卡0-1 | IPAdapter + ControlNet |
| `detail-page-workflow.json` | 详情页生成 (完整版) | 卡2-3 | IPAdapter + ControlNet |

## 必需的自定义节点

在 ComfyUI 中安装以下自定义节点：

```bash
cd /path/to/ComfyUI/custom_nodes

# IPAdapter Plus (风格迁移)
git clone https://github.com/xinntao/ComfyUI_IPAdapter_plus

# ControlNet Auxiliary (Canny/Depth预处理)
git clone https://github.com/Fannovel16/comfyui_controlnet_aux

# FLUX ControlNet
git clone https://github.com/kijai/ComfyUI-FLUX-Controlnet-Union
```

## 必需的模型文件

### 基础模型 (放入 `ComfyUI/models/checkpoints/`)

```
flux1-dev-fp8.safetensors       # 13GB, 主模型
```

### LoRA (放入 `ComfyUI/models/loras/`)

```
flux_turbo_lora.safetensors     # Turbo加速, 3倍提速
```

### ControlNet (放入 `ComfyUI/models/controlnet/`)

```
flux-controlnet-canny.safetensors
flux-controlnet-depth.safetensors
```

### IPAdapter (放入 `ComfyUI/models/ipadapter/`)

```
ipadapter_plus_flux.safetensors
```

### CLIP Vision (放入 `ComfyUI/models/clip_vision/`)

```
clip_vision_vit_h.safetensors
```

## 参数对比

| 参数 | 主图 | 详情页 |
|------|------|--------|
| IPAdapter weight | 0.85 | 0.70 |
| ControlNet Canny | 0.8 | 0.6 |
| ControlNet Depth | 0.7 | 0.6 |
| Denoise | 0.45 | 0.60 |
| 参考图类型 | 白底产品图 | 生活场景图 |

## 快速开始 (推荐)

### 第一步：基础测试

1. 打开 ComfyUI Web UI (http://localhost:8188)
2. 点击右侧 "Load" 按钮
3. 选择 `basic-test-workflow.json`
4. 点击 "Queue Prompt" 生成测试图片

**这个工作流不需要任何自定义节点**，只用 FLUX.1-dev + Turbo LoRA，可以快速验证：
- FLUX 模型是否正确加载
- Turbo LoRA 是否工作
- GPU 是否正常运行
- 生成速度和质量

### 第二步：安装 IPAdapter (可选)

如果基础测试通过，再安装完整功能所需的自定义节点：

```bash
cd /path/to/ComfyUI/custom_nodes

# IPAdapter Plus (风格迁移)
git clone https://github.com/cubiq/ComfyUI_IPAdapter_plus

# ControlNet Auxiliary (Canny/Depth预处理)
git clone https://github.com/Fannovel16/comfyui_controlnet_aux
```

重启 ComfyUI 后，就可以使用完整版工作流了。

## 使用步骤

### 1. 导入工作流

1. 打开 ComfyUI Web UI (http://localhost:8188)
2. 点击右侧 "Load" 按钮
3. 选择工作流文件

### 2. 准备参考图

**主图参考图要求:**
- 白色或浅色背景
- 产品居中，清晰
- 分辨率: 512x512 ~ 1024x1024
- 格式: JPG/PNG

**详情页参考图要求:**
- 生活场景/使用场景
- 模特互动（如有）
- 自然光线
- 分辨率: 512x512 ~ 1024x1024

### 3. 调整参数

根据效果调整关键参数：

| 效果问题 | 调整建议 |
|----------|----------|
| 产品变形 | 提高 ControlNet Canny 到 0.9 |
| 风格不一致 | 提高 IPAdapter weight 到 0.95 |
| 细节丢失 | 降低 Denoise 到 0.35 |
| 画面模糊 | 增加 Steps 到 12 |
| 过度拟合 | 降低 IPAdapter weight 到 0.6 |

### 4. 批量生成

修改 `EmptyLatentImage` 节点的 batch_size 参数：
- batch_size=1: 单张测试
- batch_size=4: 批量生成4张

## 工作流节点链

```
Load Checkpoint (FLUX.1-dev-fp8)
    │
    ▼
LoraLoader (Turbo LoRA, weight=0.8)
    │
    ├─────────────────────────────────┐
    │                                 │
    ▼                                 ▼
LoadImage ──► Canny Preprocessor    CLIP Text Encode (+)
    │               │                     │
    │               ▼                     │
    └───────► Depth Preprocessor          │
                    │                     │
                    ▼                     ▼
              IPAdapter Apply ──────► ControlNet Apply (Canny)
              (weight=0.85)                │
                                           ▼
                                    ControlNet Apply (Depth)
                                           │
                                           ▼
                                      KSampler
                                      (steps=8, CFG=3.5,
                                       denoise=0.45)
                                           │
                                           ▼
                                      VAEDecode
                                           │
                                           ▼
                                      SaveImage
```

## 性能基准

| 指标 | 主图 | 详情页 |
|------|------|--------|
| 单张时间 | 8-12秒 | 10-15秒 |
| 日产量 (20h) | 28,800张 | 17,280张 |
| 显存占用 | ~22GB | ~22GB |

## 故障排查

### 显存不足 (OOM)

```bash
# 减小 batch_size
# 或使用更小的分辨率
# 或启用 --lowvram 模式
python main.py --lowvram
```

### 找不到节点

检查自定义节点是否正确安装：
```bash
ls ComfyUI/custom_nodes/
```

### 模型加载失败

检查模型路径和文件名是否正确：
```bash
ls ComfyUI/models/checkpoints/
ls ComfyUI/models/loras/
ls ComfyUI/models/controlnet/
```

## 下一步

1. 测试单张生成效果
2. 调整参数优化质量
3. 配置批量生成
4. 接入 API 自动化调用