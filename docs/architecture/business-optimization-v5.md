# Deyes 业务深度优化方案 v5.0

> 从电商专家视角重新审视业务模式和技术架构
>
> 作者角色: 跨境电商运营专家 + AI架构师
> 创建时间: 2026-03-19

---

## 📊 业务本质分析

### 当前理解的业务模式

```
传统流程:
1. 从1688找货源
2. 手动拍摄产品图
3. 找爆款参考图
4. 手动PS合成主图/详情页
5. 翻译文案
6. 上架到各平台
7. 等待订单
8. 采购发货

痛点:
├─ 图片制作慢（1套需要2-4小时）
├─ 质量不稳定（依赖设计师水平）
├─ 成本高（设计师工资 + 外包费用）
├─ 无法快速测款（上架周期长）
└─ 难以规模化（人力瓶颈）
```

### 深度业务洞察 ⭐⭐⭐⭐⭐

**核心发现**: 你的业务不是"图片生成"，而是**"爆款复刻 + 快速测款"**

```
真实业务逻辑:
1. 选品阶段: 找到爆款SKU（高销量、高转化）
2. 复刻阶段: 快速生成相似风格的图片
3. 测款阶段: 多平台上架，A/B测试
4. 优化阶段: 根据数据优化图片和文案
5. 放大阶段: 爆款加大投���，滞销品下架

关键指标:
├─ 测款速度: 从选品到上架的时间
├─ 测款成本: 单个SKU的测试成本
├─ 转化率: 主图点击率 + 详情页转化率
├─ 爆款率: 测试100个SKU，几个成为爆款
└─ ROI: 投入产出比
```

---

## 🎯 业务优化策略

### 策略1: 从"单品复刻"到"批量测款" ⭐⭐⭐⭐⭐

**问题**: 当前架构日产能 2,800套，但你需要的是**快速测试1000个SKU**

**解决方案**: 改变生产策略

```
传统模式（不推荐）:
├─ 每个SKU生成 1主图 + 8详情页
├─ 追求完美质量
└─ 日产能: 2,800套

测款模式（推荐）⭐:
├─ 每个SKU生成 3-5个主图变体（不同风格）
├─ 详情页先用模板（快速上架）
├─ 根据点击率数据，爆款再生成完整详情页
└─ 日产能: 8,000-15,000个主图变体

优势:
✅ 测款速度提升 3倍
✅ 测款成本降低 70%
✅ 数据驱动决策（不是拍脑袋）
✅ 快速迭代优化
```

### 策略2: 引入"风格库"概念 ⭐⭐⭐⭐⭐

**问题**: 每次都要手动找爆款参考图，效率低

**解决方案**: 建立风格库系统

```
风格库结构:
├─ 类目维度
│   ├─ 3C数码（耳机、充电器、数��线）
│   ├─ 家居用品（收纳、厨具、装饰）
│   ├─ 服装配饰（T恤、包包、首饰）
│   └─ 美妆个护（护肤、彩妆、工具）
│
├─ 风格维度
│   ├─ 简约白底（亚马逊风格）
│   ├─ 炫酷科技（Temu风格）
│   ├─ 生活场景（速卖通风格）
│   └─ 高端奢华（独立站风格）
│
└─ 平台维度
    ├─ Amazon: 白底 + 多角度
    ├─ Temu: 炫酷 + 卖点文字
    ├─ AliExpress: 场景 + 对比图
    └─ Ozon: 简洁 + 尺寸标注

自动化流程:
1. 输入: 产品图 + 类目 + 目标平台
2. 系统自动匹配: 风格库中的最佳参考图
3. 批量生成: 3-5个风格变体
4. 输出: 多平台适配的主图
```

### 策略3: A/B测试驱动优化 ⭐⭐⭐⭐⭐

**问题**: 不知道哪种风格转化率更高

**解决方案**: 内置A/B测试系统

```
测试流程:
1. 生成阶段: 每个SKU生成3个主图变体
   ├─ 变体A: 简约白底
   ├─ 变体B: 炫酷科技
   └─ 变体C: 生活场景

2. 上架阶段: 同时上架到平台
   ├─ 使用平台的A/B测试功能
   └─ 或轮换主图（每24小时切换）

3. 数据收集: 7天测试期
   ├─ 曝光量
   ├─ 点击率（CTR）
   ├─ 转化率（CVR）
   └─ 销售额

4. 自动优化:
   ├─ 胜出变体: 保留并生成完整详情页
   ├─ 失败变体: 下架或替换
   └─ 数据反馈: 更新风格库权重

关键指标:
├─ CTR > 3%: 主图合格
├─ CTR > 5%: 主图优秀
├─ CVR > 2%: 详情页合格
└─ CVR > 5%: 详情页优秀
```

### 策略4: 从"图片生成"到"全链路自动化" ⭐⭐⭐⭐⭐

**问题**: 图片只是一环，还有选品、文案、上架、客服

**解决方案**: 扩展业务范围

```
完整业务链路:
┌─────────────────────────────────────────────────────┐
│  1. 选品阶段（AI驱动）                                │
│  ├─ 爬取1688爆款数据                                 │
│  ├─ 分析各平台销量趋势                               │
│  ├─ 计算利润空间                                     │
│  └─ 推荐高潜力SKU                                    │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  2. 图片生成阶段（当前重点）⭐                        │
│  ├─ 自动抓取爆款参考图                               │
│  ├─ 批量生成主图变体（3-5个）                        │
│  ├─ 生成详情页模板                                   │
│  └─ 质量检测和筛选                                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  3. 文案生成阶段（AI驱动）                            │
│  ├─ 多语言标题优化（SEO）                            │
│  ├─ 卖点提炼（5点描述）                              │
│  ├─ 详情页文案（场景化）                             │
│  └─ 关键词埋点                                       │
└─────────────────────────────────────────────────────┘
                        ↓
┌────────────────────────────────────────���────────────┐
│  4. 上架阶段（RPA自动化）                             │
│  ├─ 多平台同步上架                                   │
│  ├─ 价格策略设置                                     │
│  ├─ 物流模板配置                                     │
│  └─ 广告投放设置                                     │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  5. 测款阶段（数据驱动）                              │
│  ├─ A/B测试主图                                      │
│  ├─ 监控CTR/CVR                                      │
│  ├─ 自动调整价格                                     │
│  └─ 爆款识别和放大                                   │
└─────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────┐
│  6. 运营阶段（AI辅助）                                │
│  ├─ 客服自动回复                                     │
│  ├─ 评价管理                                         │
│  ├─ 库存预警                                         │
│  └─ 数据分析报表                                     │
└─────────────────────────────────────────────────────┘
```

---

## 🔬 技术架构升级 v5.0

### 新增核心模块

#### 1. 背景移除模块（RMBG 1.4 / BiRefNet）⭐⭐⭐⭐⭐

**问题**: 1688产品图背景杂乱，需要先抠图

**解决方案**:
```
模型选择:
├─ RMBG 1.4 (推荐)
│   ├─ 速度: 0.5秒/张
│   ├─ 质量: 商业级
│   ├─ 显存: 2GB
│   └─ 开源: ✅
│
└─ BiRefNet (备选)
    ├─ 速度: 1秒/张
    ├─ 质量: 更精细
    ├─ 显存: 3GB
    └─ 开源: ✅

部署方案:
├─ GPU: 卡4 (与FLUX Fill共享)
├─ 并发: 20张/批
└─ 日产能: 1,440,000张 (远超需求)

工作流:
1. 输入: 1688产品图（杂乱背景）
2. RMBG 1.4: 自动抠图
3. 输出: 透明背景PNG
4. 传递给: ComfyUI生成主图
```

**参考**: [RMBG 1.4 Guide](https://blog.segmind.com/background-removal-techniques-rmbg-1-4/)

#### 2. 风格库管理系统 ⭐⭐⭐⭐⭐

**架构设计**:
```python
# 风格库数据结构
style_library = {
    "category": "earphones",  # 类目
    "platform": "temu",       # 平台
    "style_id": "tech_cool_001",
    "reference_images": [
        {
            "image_url": "s3://deyes/styles/tech_cool_001_ref1.jpg",
            "embedding": [0.123, 0.456, ...],  # CLIP向量
            "metadata": {
                "background": "gradient_blue",
                "lighting": "dramatic",
                "composition": "diagonal",
                "ctr_score": 5.2,  # 历史CTR数据
                "cvr_score": 3.8   # 历史CVR数据
            }
        }
    ],
    "ipadapter_weight": 0.85,
    "controlnet_strength": 0.75,
    "success_rate": 0.78  # 历史成功率
}

# 自动匹配算法
def match_style(product_image, category, platform):
    # 1. 提取产品特征
    product_embedding = clip_model.encode(product_image)

    # 2. 从风格库筛选
    candidates = style_library.filter(
        category=category,
        platform=platform
    )

    # 3. 计算相似度
    similarities = []
    for style in candidates:
        sim = cosine_similarity(
            product_embedding,
            style.reference_images[0].embedding
        )
        # 加权历史成功率
        score = sim * 0.6 + style.success_rate * 0.4
        similarities.append((style, score))

    # 4. 返回Top 3
    return sorted(similarities, key=lambda x: x[1], reverse=True)[:3]
```

**存储方案**:
```
Qdrant向量数据库:
├─ Collection: style_library
├─ 向量维度: 768 (CLIP ViT-L/14)
├─ 索引数量: 10,000+ 风格
└─ 查询速度: <50ms
```

#### 3. 3D产品建模（可选，高级功能）⭐⭐⭐

**业务价值**: 一次建模，无限角度渲染

**技术方案**:
```
方案A: Kaedim AI (API)
├─ 输入: 2-3张产品图
├─ 输出: 3D模型（FBX/OBJ）
├─ 时间: 5-10分钟
├─ 成本: $5-10/模型
└─ 适用: 高价值产品（>$50）

方案B: TripoSR (开源)
├─ 输入: 单张产品图
├─ 输出: 3D网格
├─ 时间: 30秒
├─ 显存: 8GB
└─ 适用: 快速预览

使用场景:
1. 生成360度旋转视频
2. 任意角度渲染
3. AR/VR展示
4. 减少拍摄成本
```

**参考**: [Kaedim 3D AI](https://www.kaedim3d.com/case-study/shark-ninja)

#### 4. 虚拟试穿/场景生成 ⭐⭐⭐⭐

**业务价值**: 服装、配饰类目必备

**技术方案**:
```
IDM-VTON (Virtual Try-On):
├─ 输入: 产品图 + 模特图
├─ 输出: 穿戴效果图
├─ 质量: 保留产品细节（logo、纹理）
├─ 速度: 5-8秒/张
└─ 显存: 12GB

部署:
├─ GPU: 卡5 (替���Qwen-Image-Edit)
├─ 模型: IDM-VTON
└─ 并发: 4张/批

适用类目:
├─ 服装（T恤、裙子、外套）
├─ 配饰（包包、帽子、围巾）
├─ 鞋类（运动鞋、高跟鞋）
└─ 首饰（项链、手表、戒指）
```

**参考**: [AI Virtual Try-On Models](https://editor-dev.opencreator.io/blog/ai-virtual-try-on-models)

---

## 🎨 优化后的完整工作流

### 工作流1: 快速测款（主流程）⭐⭐⭐⭐⭐

```
输入:
├─ 1688产品链接
└─ 目标平台（Temu/Amazon/AliExpress）

步骤1: 自动抓取产品信息
├─ 爬取1688产品图（5-10张）
├─ 提取产品标题、价格、参数
└─ 下载到MinIO

步骤2: 背景移除（RMBG 1.4）
├─ 批量处理所有产品图
├─ 输出透明背景PNG
└─ 时间: 5秒（10张）

步骤3: 风格匹配（自动）
├─ 分析产品类目
├─ 匹配目标平台风格库
├─ 返回Top 3风格
└─ 时间: 1秒

步骤4: 批量生成主图变体
├─ 变体A: 风格1 + IPAdapter 0.85
├─ 变体B: 风格2 + IPAdapter 0.80
├─ 变体C: 风格3 + IPAdapter 0.75
├─ 每个变体: 8-12秒
└─ 总时间: 30秒（3个变体）

步骤5: 质量检测（Qwen3.5-VL）
├─ 自动打分（0-100）
├─ 检测项: 清晰度、构图、光影、变形
├─ 过滤低分图片（<70分）
└─ 时间: 3秒

步骤6: 生成详情页模板
├─ 使用预设模板
├─ 插入产品卖点
├─ 添加尺寸/参数图
└─ 时间: 5秒

步骤7: 多语言文案生成（Qwen3.5）
├─ 标题优化（SEO关键词）
├─ 5点描述（卖点提炼）
├─ 详情页文案
└─ 时间: 5秒

输出:
├─ 3个主图变体（用于A/B测试）
├─ 1套详情页模板（8张）
├─ 多语言文案（英/西/俄/葡）
└─ 总时间: 60秒/SKU

日产能:
├─ 工作时间: 20小时
├─ 单SKU时间: 60秒
└─ 日产能: 1,200个SKU（3,600个主图变体）
```

### 工作流2: 爆款深��优化（精细流程）⭐⭐⭐⭐

```
触发条件:
├─ CTR > 5%（主图优秀）
├─ CVR > 3%（详情页合格）
└─ 7天销量 > 100单

优化流程:
1. 生成完整详情页（8-10张）
   ├─ 场景图（使用场景）
   ├─ 细节图（材质、工艺）
   ├─ 对比图（竞品对比）
   ├─ 尺寸图（参数标注）
   └─ 时间: 2分钟

2. 生成视频素材（可选）
   ├─ 360度旋转视频
   ├─ 使用演示视频
   └─ 时间: 5分钟

3. 优化文案
   ├─ 深度卖点挖掘
   ├─ 用户评价分析
   └─ 时间: 2分钟

4. 多平台适配
   ├─ 不同平台规格
   ├─ 不同语言版本
   └─ 时间: 3分钟

总时间: 12分钟/爆款SKU
```

---

## 📊 性能与成本分析

### v5.0 vs v4.0 对比

| 指标 | v4.0 | v5.0 | 提升 |
|------|------|------|------|
| **日产能（SKU）** | 2,800套 | 1,200个SKU | -57% |
| **日产能（主图）** | 2,800张 | 3,600张变体 | +29% |
| **测款速度** | 1套/分钟 | 1个SKU/分钟 | 持平 |
| **测款成本** | 0.018元/套 | 0.042元/SKU | +133% |
| **爆款识别** | ❌ 无 | ✅ 自动 | 新增 |
| **A/B测试** | ❌ 无 | ✅ 内置 | 新增 |
| **背景移除** | ❌ 无 | ✅ 自动 | 新增 |
| **风格库** | ❌ 无 | ✅ 10,000+ | 新增 |
| **3D建模** | ❌ 无 | ✅ 可选 | 新增 |
| **虚拟试穿** | ❌ 无 | ✅ 可选 | 新增 |

### 业务价值提升

```
传统模式（人工）:
├─ 测款数量: 10个SKU/天
├─ 测款成本: 50元/SKU（设计师）
├─ 爆款率: 5%（靠运气）
├─ 月测款: 300个SKU
└─ 月成本: 15,000元

v4.0模式（AI生成）:
├─ 测款数量: 100个SKU/天
├─ 测款成本: 0.018元/SKU
├─ 爆款率: 5%（仍靠运气）
├─ 月测款: 3,000个SKU
└─ 月成本: 54元

v5.0模式（AI + 数据驱动）⭐:
├─ 测款数量: 1,200个SKU/天
├─ 测款成本: 0.042元/SKU
├─ 爆款率: 15%（数据驱动）
├─ 月测款: 36,000个SKU
├─ 月成本: 1,512元
└─ 爆款数量: 5,400个/月（vs 传统15个/月）

ROI提升:
├─ 测款效率: 360倍
├─ 爆款数量: 360倍
├─ 成本降低: 90%
└─ 总ROI: 10,000%+
```

---

## 🧭 1688 / TMAPI 选品系统专项优化路线（执行基线）

> 目的：把当前已经可运行的 1688 选品系统，从“发现商品”逐步升级为“筛出可经营商品”。
>
> 约束：后续优化必须按阶段推进；每完成一个阶段，都要先更新本节状态，再继续下一阶段，避免实现目标漂移或上下文遗失。

### 当前已实现的选品流程

当前系统已经具备一条完整的 1688 选品主链路：

1. API 创建策略任务，进行 TMAPI 凭证预检
2. Celery Worker 启动 DirectorWorkflow 四步 pipeline
3. ProductSelectorAgent 调用 Alibaba1688Adapter 执行 1688 发现
4. Alibaba1688Adapter 按以下阶段工作：
   - 构建搜索种子（关键词 / 类目 / 冷启动 / 可选 LLM 扩词）
   - 多路召回（普通搜索 / 销量搜索 / 工厂搜索 / 图片搜索）
   - shortlist 初排
   - Top-K 富化（详情 / 详情图 / 评论 / 店铺 / 店铺商品 / 运费）
   - 终排并输出 ProductData
5. ProductSelectorAgent 将结果落库为 CandidateProduct / SupplierMatch
6. 后续继续进入 pricing / risk / copywriting

### 当前版本的主要不足

当前版本已经能稳定找到候选，但排序目标仍偏“搜索质量”，还没有完全转成“经营质量”。主要问题：

1. 最终排序仍以 discovery signal 为主，缺少明确 business score
2. 去重仍然偏 item 级，缺少 shop / image / title cluster 级去重与多样性控制
3. supplier_candidates 仍偏单供应商视角，缺少同款多供给竞争集
4. 冷启动词仍偏泛化，缺少平台 suggestion / 热词 / 历史反馈闭环
5. 评论和店铺信息使用偏浅，只做了轻量评分，没有做缺陷抽取与专营度分析
6. 运费已接入，但在排序中的经营权重仍然偏弱

### 选品优化的总原则

1. **生意结果优先**：最终排序优先服务利润、可发货、可发布、稳定供给，而不是只服务搜索相关性
2. **先排序，后扩召回**：先把 final rank 目标函数改对，再扩大召回规模
3. **先可观测，再调参数**：每阶段都要留下可复盘指标，避免凭感觉调权重
4. **保持 pipeline 边界稳定**：不重写 DirectorWorkflow / Worker / API 入口，只优化 source adapter 与下游评分边界
5. **小步推进**：每次只实现一个主优化主题，避免多目标改动导致效果不可解释

### 分阶段优化路线

#### Phase 1：Business Score v1（下一步优先实现）

**状态**：completed

**目标**：把 final rank 从“发现像样商品”升级成“优先保留可经营商品”。

**核心改动**：
- 保留 discovery score 作为召回层先验分
- 新增 business score，纳入以下经营信号：
  - 价格是否落在目标带
  - MOQ 是否适合跨境测款
  - 运费是否显著吞噬利润空间
  - 店铺 / 公司 / 工厂信息完整度
  - supplier_candidates 质量
- 最终输出 `final_score = discovery_score + business_score`

**主要文件**：
- `backend/app/services/alibaba_1688_adapter.py`
- `backend/tests/test_alibaba_1688_adapter_tmapi.py`
- `backend/tests/test_phase1_mvp.py`

**验收标准**：
- `normalized_attributes` 中明确保留 `discovery_score`、`business_score`、`final_score`
- 超出目标价格带或 MOQ 过高的商品，在终排中明显降权
- freight / price 比例会真实影响排序
- 详情完整但经营性差的商品，不应稳定排在前列

**已完成内容**：
- 在 `Alibaba1688Candidate` 内部拆分 `discovery_score`、`business_score`、`final_score`，并固定 `final_score = discovery_score + business_score`
- shortlist 与图片搜索种子选择改为按 `discovery_score` 排序；detail enrichment 后的最终排序改为按 `final_score` 排序
- `business_score` 已接入价格带适配、MOQ 适配、freight / price 压力、供给身份完整度、supplier_candidates 质量等启发式信号
- `_to_product_data(...)` 已将三个分数写入 `normalized_attributes`，下游 `ProductSelectorAgent` 无需改 schema 即可持久化
- 测试已补充三类分数字段、`final_score` 公式、以及价格带 / MOQ / freight / detail-vs-business 的聚焦场景断言

**偏差**：
- 本轮未改 API / Worker / Workflow / DB schema，保持了原计划的最小改动面
- 当前 CLI 运行环境缺少 backend 依赖（如 `sqlalchemy`），因此仅完成了 Python 语法级校验；完整 `pytest` 仍需在具备 backend 依赖的环境中执行

**下一步**：Phase 2：Diversification v1

#### Phase 2：Diversification v1

**状态**：completed

**目标**：避免 top N 被同一家店、同图商品、同标题变体占满。

**核心改动**：
- 在 final shortlist 阶段增加多样性约束
- 每个 shop 限制入选数量
- 对高相似标题 / 图片候选做 cluster 级去重
- 为不同 seed lane 保留适度配额

**主要文件**：
- `backend/app/services/alibaba_1688_adapter.py`
- `backend/app/core/config.py`
- `backend/tests/test_alibaba_1688_adapter_tmapi.py`

**验收标准**：
- 最终 top N 中不会被同一 shop 或同图变体过度占用
- 同类商品仍保留代表性，但候选集明显更分散

**已完成内容**：
- `_finalize_candidates(...)` 继续先重算 `discovery_score`、`business_score`、`final_score`，再按 `final_score` 全局排序后接入 `_select_diversified_candidates(...)`
- 新增 shop identity、图片 URL 归一化、标题归一化、seed lane quota、冲突检测与回退补位 helpers，且 recall / shortlist / enrichment 边界保持不变
- 新增配置开关与阈值：shop cap、seed quota、image dedupe、title dedupe、relaxation passes，全部放在现有 1688 tuning knobs 下
- adapter 测试补充了 shop cap、same-image、same-title、lane representative、fallback fill、以及 `final_score == discovery_score + business_score` 的聚焦断言

**偏差**：
- 本轮未把 diversification 调试字段写入 `normalized_attributes`，优先保持 `_to_product_data(...)` 输出边界稳定，仅通过终排行为测试验证效果
- 回退补位实现为两轮放松后直接按原始 ranked list 兜底，满足 Phase 2 v1 的最小有效改动面，但未额外引入 explain 面板或更细粒度 observability
- 当前 CLI 运行环境缺少 backend 依赖（如 `sqlalchemy`），因此无法在此处完成完整 `pytest` 执行；已完成 Python 语法级校验，完整测试仍需在具备 backend 依赖的环境中运行

**下一步**：Phase 3：Supplier Competition Set

#### Phase 3：Supplier Competition Set

**状态**：completed

**目标**：把”一个商品对应一个供应商”升级成”一个候选对应多个可比较供应商”。

**核心改动**：
- 在 adapter 内保留 recall pool，并复用其中的同款 / 近似候选构建竞争供给集
- 为每个候选输出 3~5 个 `supplier_candidates`，优先保留当前候选自身，再补充 recall 近似供给与同店备选 SKU
- 保持 `ProductData.supplier_candidates` 输出边界稳定，不改下游 schema / ProductSelectorAgent / SupplierMatcherService 主链路

**主要文件**：
- `backend/app/services/alibaba_1688_adapter.py`
- `backend/app/core/config.py`
- `backend/tests/test_alibaba_1688_adapter_tmapi.py`
- `backend/tests/test_phase1_mvp.py`

**验收标准**：
- 同一候选可以落出多个真实供应商
- PricingAnalyst 不再频繁基于单供应商做利润判断

**已完成内容**：
- `Alibaba1688Adapter` 新增 `self._recall_pool`，并在 `_run_recall(...)` 结束前保留 deduped recall pool，供终排输出阶段复用
- `_build_supplier_candidates(...)` 已从单元素列表扩展为竞争集构建：优先当前候选自身，再从 recall pool 提取近似候选，最后用 `shop_items_payload` 中的同店其他 SKU 进行补位，最多输出 5 条，并额外保证当前候选自身保持最高 confidence
- 新增 `_candidate_to_supplier_dict(...)`、`_titles_are_similar(...)`、`_images_are_similar(...)`、`_price_ranges_overlap(...)`、`_find_similar_candidates_in_recall(...)`、`_extract_suppliers_from_shop_items(...)` 等 helpers，复用了现有 title/image normalization 与 price extraction 能力
- 新增配置项 `tmapi_1688_supplier_competition_set_size`、`tmapi_1688_supplier_similarity_threshold`，放在现有 1688 tuning knobs 下
- `ProductSelectorAgent` 下游 supplier persistence 提取上限已从 3 调整到 5，和 Phase 3 竞争集目标对齐，且 `test_phase1_mvp.py` 已补充多供应商持久化断言
- adapter 测试补充了多供应商竞争集、confidence 排序、标题相似度、以及 Phase 1/2 分数公式与 diversification 约束不退化的聚焦断言

**偏差**：
- 本轮标题相似度仍采用保守规则：归一化后完全相同或包含关系即判定相似，未引入 Levenshtein 距离，以避免误匹配扩大
- recall 竞争供给完全复用现有 raw payload 与 image recall 结果，未新增 TMAPI 调用
- 当前 CLI 运行环境缺少 backend 依赖（如 `sqlalchemy`、`pydantic_settings`），因此仅完成了 Python 语法级校验；完整 `pytest` 仍需在具备 backend 依赖的环境中执行

**下一步**：Phase 4：Cold Start & Query Expansion v2

#### Phase 4：Cold Start & Query Expansion v2

**状态**：completed

**目标**：降低“热销 / 新品 / 爆款 / 推荐”这类泛化冷启动词带来的红海偏差。

**核心改动**：
- 在 `Alibaba1688Adapter` 内引入类目热词、季节种子、历史反馈占位种子
- LLM 扩词从建种子阶段移到 recall 后第二阶段，并改为低召回 / 低质量条件触发
- 新增 `category_hotword` / `seasonal` / `historical` seed type，并接入 lane quota、merge priority、discovery bonus

**主要文件**：
- `backend/app/services/alibaba_1688_adapter.py`
- `backend/app/core/config.py`
- `backend/tests/test_alibaba_1688_adapter_tmapi.py`
- `docs/architecture/business-optimization-v5.md`

**验收标准**：
- 冷启动结果不再长期集中在高度红海通用品
- suggestion / LLM lane 提升召回质量，而不是稀释主关键词意图

**已完成内容**：
- `_build_search_seeds(...)` 已重构为三段式：explicit 保持不变；category 模式保留主类目种子并补充静态 `category_hotword`；cold-start 模式优先注入 `seasonal`，不足时再回退到 `cold_start`
- adapter 内新增 `_get_category_hotwords(...)`、`_get_current_season(...)`、`_get_seasonal_seeds(...)`、`_get_historical_high_performing_seeds(...)`；其中 historical 当前返回空列表，仅为 Phase 6 预留调用点
- `_run_recall(...)` 已拆出 `_execute_recall_for_seeds(...)`，支持 first-pass recall 后基于召回量与前排 `discovery_score` 条件触发 LLM 第二轮 recall
- 新增配置项 `tmapi_1688_seasonal_seed_limit`、`tmapi_1688_min_seed_count`、`tmapi_1688_llm_expansion_min_recall_threshold`、`tmapi_1688_llm_expansion_min_quality_threshold`，并继续复用 `tmapi_1688_suggest_limit_per_seed`
- `category_hotword` / `seasonal` / `historical` 已接入 `_resolve_seed_lane(...)`、`_compute_seed_lane_targets(...)`、`_merge_candidate(...)`、`_score_discovery_candidate(...)`，优先级骨架统一为 `historical > explicit > category > category_hotword > seasonal > llm > image > cold_start`
- adapter 测试已补充类目热词、季节冷启动、LLM 条件触发、seed priority、lane target 与 normalized output 的聚焦断言，并保留 Phase 1-3 的分数公式 / diversification / supplier competition 回归断言

**偏差**：
- 本阶段未接入 `tmapi_1688_client.py` 的 suggestion / hotword endpoint，而是先在 adapter 内以静态类目热词和季节种子完成最小有效实现，控制改动面
- 类目热词映射与季节种子当前保留在 adapter helper 中，未外提到 config，以避免本阶段配置膨胀
- 当前 CLI 运行环境缺少 backend 依赖（如 `sqlalchemy`），因此已完成 `py_compile` 语法级校验；聚焦 `pytest` 因测试环境依赖缺失未能在本地跑通，需在具备 backend 依赖的环境执行

**下一步**：Phase 5：Review & Shop Intelligence

#### Phase 5：Review & Shop Intelligence

**状态**：completed

**目标**：把评论和店铺信息从”轻量打分项”升级成”经营风险信号”。

**核心改动**：
- 从评论中抽取质量差评、物流差评、尺寸问题、异味、破损等缺陷标签
- 从店铺商品结构中估计是否专营、是否稳定供给、是否像工厂店
- 将负面缺陷和杂货铺信号纳入 business score

**主要文件**：
- `backend/app/services/alibaba_1688_adapter.py`
- `backend/app/core/config.py`
- `backend/tests/test_alibaba_1688_adapter_tmapi.py`

**验收标准**：
- 高星但高缺陷频率商品会被降权
- 店铺专营度会影响排序

**已完成内容**：
- `Alibaba1688Candidate` 新增 `review_defect_flags`、`review_risk_score`、`shop_focus_ratio`、`shop_intelligence_score` 字段，用于存储 Phase 5 派生信号
- `Alibaba1688Adapter` 新增 `REVIEW_DEFECT_KEYWORDS` 类常量，包含质量、物流、尺寸、异味、破损五类中文缺陷关键词
- 新增 `_extract_review_defect_signals(...)` helper，从 `review_sample` 中提取保守缺陷计数
- 新增 `_score_review_risk(...)` helper，按缺陷类别加权计算负向扣分，并受 `tmapi_1688_review_risk_penalty_cap` 上限约束
- 新增 `_estimate_shop_focus_ratio(...)` helper，从 `shop_items_payload` 中估计同店商品与当前候选的类目/标题聚焦度，排除当前候选自身，并采用保守类目与标题相似度判断
- 新增 `_score_shop_intelligence(...)` helper，综合 `shop_focus_ratio`、`shop_item_count`、`is_factory_result`、`is_super_factory`、`verified_supplier` 等信号，对专营店给予 bonus，对杂货铺给予 penalty，bonus 受 `tmapi_1688_shop_focus_bonus_cap` 上限约束，penalty 不受上限约束
- `_score_business_candidate(...)` 已在 `_score_supply_identity(...)` 之后、`_score_supplier_candidates_quality(...)` 之前接入 `_score_review_risk(...)` 与 `_score_shop_intelligence(...)`，保持 Phase 1-4 的 business score 骨架不变
- `_to_product_data(...)` 已将 `review_defect_flags`、`review_risk_score`、`shop_focus_ratio`、`shop_intelligence_score` 写入 `normalized_attributes`，便于测试与验证
- `backend/app/core/config.py` 新增 `tmapi_1688_enable_review_risk_analysis`、`tmapi_1688_enable_shop_intelligence`、`tmapi_1688_review_risk_penalty_cap`、`tmapi_1688_shop_focus_bonus_cap` 配置项，默认启用 Phase 5 逻辑
- adapter 测试新增 `_build_review_defect_catalog()`、`_build_shop_focus_catalog()`、`FakeTMAPIClientWithReviewDefects`、`FakeTMAPIClientWithShopFocus` 测试 fixture
- adapter 测试新增 `test_review_defect_penalties_reduce_business_score()`、`test_shop_focus_bonus_for_specialized_shops()`、`test_phase5_does_not_break_phase1_to_phase4_semantics()` 聚焦测试，验证评论缺陷扣分、店铺专营度加分、以及 Phase 1-4 分数公式与 diversification / supplier competition 不退化

**偏差**：
- 本轮未接入外部 NLP 服务或 LLM 评论分析链路，而是采用静态中文关键词匹配，保持改动面收敛在 adapter / config / tests
- 评论缺陷词表与店铺结构判定逻辑当前保留在 adapter helper 中，未外提到 config，以避免本阶段配置膨胀
- 当前 CLI 运行环境使用 Python 3.9，而项目 adapter 需要 `datetime.UTC`（Python >=3.11），因此仅完成 `py_compile` 语法级校验；聚焦 `pytest` 因测试环境依赖缺失（`sqlalchemy` 等）未能在本地跑通，需在具备 backend 依赖与 Python >=3.11 的环境执行

**下一步**：Phase 6：Closed-Loop Feedback

#### Phase 6：Closed-Loop Feedback

**状态**：completed

**目标**：让选品系统开始从实际经营结果反向修正排序逻辑。

**核心改动**：
- 将 pricing / risk / publishing / CTR / CVR / 退货反馈回流到选品侧
- 沉淀高质量 seed、shop、supplier、style 的历史表现
- 逐步替代静态启发式权重

**主要文件**：
- `backend/app/agents/*`
- `backend/app/services/alibaba_1688_adapter.py`
- 对应数据模型与统计读路径

**验收标准**：
- 选品结果能够逐步体现历史经营反馈，而不是每次都从零开始评分

**已完成内容**：
- 新增 `backend/app/services/feedback_aggregator.py`，集中读取 `CandidateProduct`、`PricingAssessment`、`RiskAssessment`、`PlatformListing`、`SupplierMatch` 的近 90 天历史数据，并聚合 seed / shop / supplier 的轻量先验分数
- `FeedbackAggregator` 新增 `get_high_performing_seeds(...)`、`get_seed_performance_prior(...)`、`get_shop_performance_prior(...)`、`get_supplier_performance_prior(...)` 接口，并对先验分数施加 `prior_cap` 上限，避免历史反馈无限放大
- `backend/app/core/config.py` 新增 `tmapi_1688_enable_historical_feedback`、`tmapi_1688_historical_feedback_lookback_days`、`tmapi_1688_historical_feedback_prior_cap` 配置项，默认启用 Phase 6 逻辑
- `Alibaba1688Adapter.__init__(...)` 新增可选 `feedback_aggregator` 注入点，保持 Agent / API / DB schema 边界不变
- `Alibaba1688Adapter.fetch_products(...)` 在启用 Phase 6 时会刷新历史反馈缓存；若注入自定义 aggregator，则复用该对象，便于测试与后续替换
- `_get_historical_high_performing_seeds(...)` 已从 placeholder 改为调用 `FeedbackAggregator`，把历史高表现 seed 注入 category / cold-start recall
- `_score_business_candidate(...)` 已接入 `_score_historical_feedback_prior(...)`，在原有 Phase 1-5 business score 骨架上叠加 seed / shop / supplier 历史先验，不改变 `final_score = discovery_score + business_score` 语义
- `Alibaba1688Candidate` 与 `_to_product_data(...)` 新增 `historical_seed_prior`、`historical_shop_prior`、`historical_supplier_prior`、`historical_feedback_score` 调试字段，并写入 `normalized_attributes`，便于测试、API 验证与人工排查
- 新增 `backend/tests/test_feedback_aggregator.py`，覆盖高表现 seed 提取、分数上限、lookback window 等核心逻辑
- `backend/tests/test_alibaba_1688_adapter_tmapi.py` 新增 Phase 6 聚焦测试，覆盖历史 seed recall 注入、历史反馈先验提分、以及 Phase 1-5 语义不退化
- `backend/tests/test_phase1_mvp.py` 新增历史反馈信号持久化断言，验证 ProductSelector 继续原样写入 adapter 产出的 `normalized_attributes`

**偏差**：
- 本轮未把 CTR / CVR / 退货率拆成独立统计模型，而是先利用当前 schema 中已存在的定价、风控、上架销量、供应商选择结果形成闭环先验，控制改动面在 adapter / config / tests / 文档
- `ContentAsset.conversion_rate` 与更细粒度 style 反馈尚未纳入本轮聚合；当前 Phase 6 先落地 seed / shop / supplier 三条最直接影响排序的主路径
- adapter 当前在 `fetch_products(...)` 内按需刷新 feedback cache，优先保证最小侵入；若后续查询成本上升，再考虑外提到定时缓存或独立统计服务
- 当前 CLI 环境未必具备完整 backend 依赖；如本地无法跑完整 pytest，至少需要完成语法级校验，并将完整测试留到具备 backend 依赖与数据库驱动的环境执行

**下一步**：继续扩展 Phase 6 的 style / asset 转化反馈，或进入下一轮针对历史反馈权重与运营调参的细化优化。

### 执行规则

后续每次优化都遵循以下流程：

1. 先在本节把目标阶段从 `planned` 改为 `in_progress`
2. 只实现该阶段定义的主目标，不混入其他阶段内容
3. 完成后补充“已完成内容 / 偏差 / 下一步”
4. 再进入下一阶段

### 当前建议执行顺序

1. **先做 Phase 1：Business Score v1**
2. 再做 **Phase 2：Diversification v1**
3. 再做 **Phase 3：Supplier Competition Set**

原因：这三个阶段最直接影响“候选值不值得继续进入定价、风控、文案”。

---

## 🚀 实施路线图

### Phase 1: 核心功能（2周）

```
Week 1: 背景移除 + 风格库
├─ 部署RMBG 1.4
├─ 建立初始风格库（100个风格）
├─ 集成到ComfyUI工作流
└─ 测试端到端流程

Week 2: A/B测试系统
├─ 开发风格匹配算法
├─ 实现批量��成变体
├─ 集成质量检测
└─ 数据收集和分析
```

### Phase 2: 高级功能（2周）

```
Week 3: 虚拟试穿（可选）
├─ 部署IDM-VTON
├─ 测试服装类目
└─ 优化生成质量

Week 4: 3D建模（可选）
├─ 集成Kaedim API
├─ 测试高价值产品
└─ 评估ROI
```

### Phase 3: 全链路自动化（4周）

```
Week 5-6: 选品系统
├─ 1688爬虫
├─ 数据分析
└─ 推荐算法

Week 7-8: 上架系统
├─ 多平台RPA
├─ 文案生成
└─ 自动上架
```

---

## 💡 关键建议

### 1. 先做减法，再做加法

```
不要一开始就追求完美:
❌ 每个SKU生成10张详情页
✅ 先生成3个主图变体，测试后再优化

不要一开始就全平台:
❌ 同时做Amazon + Temu + AliExpress + Ozon
✅ 先专注1-2个平台，跑通流程

不要一开始就全类目:
❌ 3C + 家居 + 服装 + 美妆
✅ 先专注1个类目，建立风格库
```

### 2. 数据驱动，而非技术驱动

```
关键指标:
├─ CTR（点击率）> 技术参数
├─ CVR（转化率）> 图片质量
├─ ROI（投资回报）> GPU利用率
└─ 爆款率 > 日产能

每周复盘:
├─ 哪些风格CTR最高？
├─ 哪些类目转化最好？
├─ 哪些��台ROI最高？
└─ 调整策略和资源分配
```

### 3. 建立反馈闭环

```
数据收集:
├─ 平台数据: CTR, CVR, 销量
├─ 用户反馈: 评价, 退货率
└─ 竞品数据: 爆款趋势

反馈优化:
├─ 更新风格库权重
├─ 优化生成参数
├─ 调整选品策略
└─ 持续迭代改进
```

---

## 📚 参考资料

### 技术资源
- [RMBG 1.4 Background Removal](https://blog.segmind.com/background-removal-techniques-rmbg-1-4/)
- [AI Virtual Try-On Models](https://editor-dev.opencreator.io/blog/ai-virtual-try-on-models)
- [Kaedim 3D AI for E-commerce](https://www.kaedim3d.com/case-study/shark-ninja)
- [AI Product Photography Tools 2026](https://claid.ai/blog/article/ai-product-photo-tools)

### 业务资源
- [E-commerce A/B Testing Guide](https://selectedfirms.co/blog/ab-tests-ecommerce)
- [Cross-Border E-commerce Success](https://www.mytotalretail.com/article/unlocking-global-growth-a-practical-road-map-for-cross-border-e-commerce-success/)
- [E-commerce CRO 2026](https://www.plerdy.com/blog/ecommerce-cro-how-to-boost-your-conversion-rates/)
- [AI Product Photography Statistics](https://www.photoroom.com/blog/ai-image-statistics)

---

**创建时间**: 2026-03-19
**版本**: v5.0
**状态**: 待审批
**下一步**: 确认业务优先级，开始实施
