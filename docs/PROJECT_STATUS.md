# Deyes 项目状态报告

**最后更新**: 2026-03-29
**架构版本**: v4.0
**项目阶段**: 需求优先选品架构 + 自动化经营方向

---

## 一、项目概览

**Deyes** 是一个基于 AI 技术的跨境电商自动化运营系统，目标是用数字员工替代传统电商运营岗位，实现从选品、内容生成、商品上架到客服的全流程自动化。

### 核心指标

- **目标平台**: Temu, AliExpress, Amazon, Ozon, Rakuten, Mercado Libre
- **硬件配置**: 8x RTX 4090 (24GB/卡)
- **日产能**: 2,400-2,800 套产品（1 主图 + 8 详情页）
- **峰值产能**: 3,500 套/天
- **GPU 利用率**: 95%

---

## 二、最新交付（2026-03-29）

### Phase 1 ERP Lite 核心实现完成

**核心变更**：
- ✅ ProductMaster / ProductVariant 模型与服务（`backend/app/db/models.py:634-689`）
- ✅ Supplier / SupplierOffer 模型与服务（`backend/app/db/models.py:691-741`）
- ✅ PurchaseOrder / PurchaseOrderItem / InboundShipment 模型与服务（`backend/app/db/models.py:744-825`）
- ✅ InventoryLevel / InventoryMovement 模型与服务（`backend/app/db/models.py:827-870`）
- ✅ CandidateConversionService - 候选转 SKU 服务（`backend/app/services/candidate_conversion_service.py`）
- ✅ ProductMasterService - 商品主数据服务（`backend/app/services/product_master_service.py`）
- ✅ SupplierMasterService - 供应商主数据服务（`backend/app/services/supplier_master_service.py`）
- ✅ ProcurementService - 采购服务（`backend/app/services/procurement_service.py`）
- ✅ InventoryAllocator - 库存分配服务（`backend/app/services/inventory_allocator.py`）
- ✅ DirectorWorkflow 集成 candidate → master 转换（`backend/app/agents/director_workflow.py:120`）
- ✅ AutoActionEngine 集成 variant 关联与 inventory_mode（`backend/app/services/auto_action_engine.py:228-253`）
- ✅ 数据库迁移 007_erp_lite_procurement（`backend/migrations/versions/20260329_0000_007_erp_lite_procurement.py`）

**影响范围**：
- 候选产品现在可转化为 ProductMaster + ProductVariant（SKU）
- SKU 支持 pre_order / stock_first 双模式
- PlatformListing 现在可关联 product_variant_id 和 inventory_mode
- ContentAsset 现在可关联 product_variant_id
- 建立了采购、库存、供应商的基础事实层

**测试状态**：
- ✅ CandidateConversionService 测试（10 个测试用例）
- ✅ ProductMasterService 测试（8 个测试用例）
- ✅ DirectorWorkflow 集成测试（3 个测试用例）
- ✅ Dual-mode Phase1 集成测试（2 个测试用例）
- ✅ SupplierMasterService 测试（6 个测试用例）
- ✅ ProcurementService 测试（3 个测试用例）
- ✅ InventoryAllocator 测试（6 个测试用例）

**文档**：
- `backend/PHASE1_WORKFLOW_INTEGRATION.md` - Phase1 工作流集成总结
- `docs/roadmap/dual-mode-operations-plan.md` - 双模式经营架构实施计划

---

### 需求上下文集成完成

**核心变更**：
- ✅ 定价服务已纳入需求发现上下文（`backend/app/services/pricing_service.py`）
- ✅ 风控规则已纳入需求发现质量风险（`backend/app/services/risk_rules.py`）
- ✅ 推荐排序已纳入需求上下文加减分（`backend/app/services/recommendation_service.py`）
- ✅ 推荐理由已输出需求发现来源与降级信息

**影响范围**：
- 定价决策现在考虑需求发现质量
- 风险评估现在包含需求发现质量风险规则（user=0, generated=10, fallback=25, none=40）
- 推荐排序现在根据需求上下文调整分数（-6 至 +3 分）
- 推荐理由现在包含需求发现来源说明

**测试状态**：
- 本地测试通过：`backend/tests/test_risk_rules.py`（9 passed）
- 本地测试通过：`backend/tests/test_competition_risk.py`（15 passed）
- 本地测试通过：`backend/tests/test_recommendation_service.py`（18 passed）
- 推荐 API 测试已更新但本地执行受阻（缺少 asyncpg 依赖）

---

## 三、已完成模块（✅）

### 3.1 产品选品系统（需求验证优先）

**需求验证层** - `backend/app/services/demand_validator.py:100`
- ✅ Google Trends 搜索量验证（>500/月）
- ✅ Helium 10 API 集成（可选增强，自动回退）
- ✅ 竞争密度评估（<5000 搜索结果）
- ✅ 趋势方向分类（rising/stable/declining）
- ✅ Redis 缓存（24h TTL）

**供应商匹配层** - `backend/app/services/supplier_matcher.py:39`
- ✅ 1688 多路召回（默认、销量、工厂、图像相似）
- ✅ 供应商竞争集评分（多维度加权）
- ✅ 历史反馈先验（90 天回溯）

**定价计算层** - `backend/app/services/pricing_service.py:17`
- ✅ 基础阈值: 35%
- ✅ 平台特定: Amazon 40%, Temu 30%, AliExpress 35%
- ✅ 品类特定: Electronics 25%, Jewelry 50%, Home 35%
- ✅ 需求上下文集成（2026-03-29）

**产品优先级评分层** - `backend/app/services/product_scoring_service.py:1`
- ✅ 提取 ProductScoringService，支持独立测试与复用
- ✅ ProductSelectorAgent 委托评分逻辑，保留原有排序行为

**风控评估层** - `backend/app/services/risk_rules.py`
- ✅ 合规风险评分（0-100）
- ✅ 竞争密度风险评分（高=80, 中=50, 低=20）
- ✅ 需求发现质量风险评分（user=0, generated=10, fallback=25, none=40）
- ✅ 组合风险评分: 合规 * 0.6 + 竞争 * 0.4

**动态关键词生成** - `backend/app/services/keyword_generator.py:48`
- ✅ 每晚生成 top 50 趋势关键词（23:00 UTC）
- ✅ 扩展到 200+ 长尾关键词
- ✅ Redis 缓存（24h TTL）
- ✅ 定时任务：`backend/app/workers/tasks_keyword_research.py:108`

**季节性日历** - `backend/app/core/seasonal_calendar.py`
- ✅ 90 天前瞻日历
- ✅ 11 个年度事件（情人节、Prime Day、黑五、圣诞等）
- ✅ 品类特定加权（情人节珠宝 +50%，黑五电子 +60%）
- ✅ 自动优先级调整

### 3.2 推荐系统（内部决策服务）

**推荐服务** - `backend/app/services/recommendation_service.py:39`
- ✅ 推荐分数算法（0-100）: 优先级 40% + 利润率 30% + 风险反向 20% + 供应商质量 10% + 需求上下文调整
- ✅ 推荐等级: HIGH (≥75), MEDIUM (60-74), LOW (<60)
- ✅ 推荐理由生成（利润率、季节性、竞争密度、风险、销量、评分、需求发现来源）
- ✅ 需求上下文集成（2026-03-29）

**推荐 API** - `backend/app/api/routes_recommendations.py`
- ✅ GET /recommendations - 推荐列表
- ✅ GET /candidates/{id}/recommendation - 推荐详情
- ✅ POST /recommendations/{id}/feedback - 用户反馈
- ✅ GET /recommendations/stats/trends - 时间趋势分析
- ✅ GET /recommendations/stats/by-platform - 平台对比分析
- ✅ GET /recommendations/stats/feedback - 反馈统计
- ✅ GET /recommendations/stats/overview - 推荐概览

**定位说明**：
- 推荐服务已降级为内部决策引擎，不再作为主产品形态
- 推荐分数用于候选排序与自动上架决策
- 推荐 API 保留用于审批工作台与监控面板

### 3.3 自动执行引擎（2026-03-27 强化）

**AutoActionEngine** - `backend/app/services/auto_action_engine.py:51`
- ✅ 自动上架（auto_publish）
- ✅ 自动调价（auto_reprice）
- ✅ 自动暂停（auto_pause）
- ✅ 自动换素材（auto_asset_switch）
- ✅ Temu API-first, RPA-second fallback
- ✅ 审批输入改为服务端 source-of-truth 重算
- ✅ 客户端 recommendation_score / risk_score / margin_percentage 仅保留兼容，不再作为审批真值
- ✅ 修复利润率阈值单位比较错误（配置 ratio vs 存储 percentage）

### 3.4 用户反馈机制（2026-03-27 新增）

**数据模型** - `backend/app/db/models.py:271`
- ✅ RecommendationFeedback 表
- ✅ FeedbackAction 枚举（ACCEPTED/REJECTED/DEFERRED）
- ✅ 数据库迁移脚本（002_recommendation_feedback.sql）

**服务层** - `backend/app/services/recommendation_feedback_service.py:9`
- ✅ 反馈创建服务
- ✅ RunEvent 审计日志集成
- ✅ 支持可选文本评论

**前端 UI** - `frontend/src/pages/recommendations/RecommendationsPage.vue`
- ✅ 反馈按钮（接受/拒绝/延后）
- ✅ TanStack Query mutation
- ✅ 自动刷新推荐列表

### 3.5 数据看板（2026-03-27 新增）

**时间趋势分析** - `RecommendationsPage.vue:146`
- ✅ 按日/周/月聚合推荐数量和平均分数
- ✅ ECharts 双轴图（柱状图 + 折线图）

**平台对比分析** - `RecommendationsPage.vue:186`
- ✅ 按 source_platform 聚合推荐质量
- ✅ 对比 Temu/Amazon/AliExpress 的推荐数量和平均分数

**用户反馈统计** - `RecommendationsPage.vue:227`
- ✅ 展示反馈分布（accepted/rejected/deferred）
- ✅ ECharts 柱状图

### 3.6 Helium 10 集成（2026-03-27 新增）

**API 客户端** - `backend/app/clients/helium10.py:26`
- ✅ 完整 API 客户端实现
- ✅ Redis 缓存（24h TTL）
- ✅ 错误处理（401, 429, 500, timeout）
- ✅ 自动回退到 Google Trends

**配置层** - `backend/app/core/config.py:116`
- ✅ demand_validation_use_helium10: bool (default: False)
- ✅ demand_validation_helium10_api_key: str (default: '')
- ✅ demand_validation_cache_ttl_seconds: int (default: 86400)

**单元测试**
- ✅ backend/tests/test_helium10_client.py（15 个测试）
- ✅ backend/tests/test_demand_validator.py（4 个 Helium 10 集成测试）

---

## 四、待完成模块（⏳）

### 4.1 AI 服务部署

**ComfyUI 图像生成服务**
- ⏳ FLUX.1-dev 模型下载（~100GB）
- ⏳ IPAdapter + ControlNet 工作流配置
- ⏳ GPU 0-5 分配和测试
- 📖 参考: `docs/deployment/comfyui-deployment-guide.md`

**SGLang LLM 推理服务**
- ⏳ Qwen3.5-35B-A3B 模型下载
- ⏳ Tensor Parallel 配置（GPU 6-7）
- ⏳ 推理速度和并发测试

**MinIO 对象存储**
- ⏳ MinIO 服务部署
- ⏳ 图片上传和访问测试

**Qdrant 向量检索**
- ⏳ Qdrant 服务部署
- ⏳ 图像相似度检索测试

### 4.2 内容资产管理

**ContentAsset 模型** - `backend/app/db/models.py:295`
- ⏳ 图像质量评分
- ⏳ 版本控制
- ⏳ 使用统计

### 4.3 平台发布

**PlatformListing 模型** - `backend/app/db/models.py:366`
- ⏳ Temu/Amazon API 集成
- ⏳ 库存同步
- ⏳ 价格同步

### 4.4 A/B 测试

**Experiment 模型**
- ⏳ 素材对比测试
- ⏳ 转化率追踪

### 4.5 性能追踪

**AssetPerformanceDaily 模型**
- ⏳ 图像性能追踪
- ⏳ 转化率分析

**ListingPerformanceDaily 模型**
- ⏳ 商品性能追踪
- ⏳ 销售数据分析

---

## 五、技术架构

### 5.1 图像生成层

```
FLUX.1-dev (FP8) + Turbo LoRA + IPAdapter Plus + ControlNet
├─ 基础模型: FLUX.1-dev (13GB, FP8 量化)
├─ 加速: Turbo LoRA (3倍速度提升, 8-12s/张)
├─ 风格迁移: IPAdapter Plus (爆款复刻, 风格一致性 90%+)
├─ 结构控制: ControlNet (Canny + Depth, 产品变形率 <5%)
└─ 局部编辑: FLUX Fill (5-10s/张)
```

**GPU 分配:**
- 卡 0-1: ComfyUI 实例 1（主图生成）
- 卡 2-3: ComfyUI 实例 2（详情页生成）
- 卡 4: FLUX Fill（局部编辑）
- 卡 5: Qwen-Image-Edit（高级编辑）

### 5.2 LLM 推理层

```
SGLang + Qwen3.5-35B-A3B (FP8)
├─ 推理引擎: SGLang (比 vLLM 快 29%, RadixAttention KV 缓存复用)
├─ 基础模型: Qwen3.5-35B-A3B (15.4GB/卡, Tensor Parallel)
├─ 视觉模型: Qwen2-VL (图像理解)
└─ 并发: 25-30 个 Agent
```

**GPU 分配:**
- 卡 6-7: SGLang (Tensor Parallel, 提示词生成、质量检测)

### 5.3 存储与编排层

**存储层:**
- MinIO: 对象存储（图片，500MB/s）
- PostgreSQL: 结构化数据
- Redis: 缓存队列（24h TTL）
- Qdrant: 向量检索

**编排层:**
- LangGraph: 全局 Agent 编排
- CrewAI: 角色协作
- n8n: 轻量工作流
- Celery: 高并发任务队列（500+ 并发）

---

## 六、业务流程

### 6.1 产品选品流程（需求验证优先）

```
1. 需求验证 (DemandValidator)
   ├─ Google Trends / Helium 10 搜索量验证 (>500/月)
   ├─ 竞争密度评估 (<5000 搜索结果)
   ├─ 趋势方向分类 (rising/stable/declining)
   └─ Redis 缓存 (24h TTL)

2. 平台抓取 (SourceAdapter)
   └─ 仅抓取通过需求验证的关键词

3. 供应商匹配 (SupplierMatcher)
   ├─ 1688 多路召回
   ├─ 供应商竞争集评分
   └─ 历史反馈先验（90 天回溯）

4. 定价计算 (PricingService)
   ├─ 基础阈值: 35%
   ├─ 平台特定阈值
   ├─ 品类特定阈值
   └─ 需求上下文调整

5. 风控评估 (RiskRules)
   ├─ 合规风险评分
   ├─ 竞争密度风险评分
   ├─ 需求发现质量风险评分
   └─ 组合风险评分

6. 推荐生成 (RecommendationService)
   ├─ 推荐分数计算 (0-100)
   ├─ 需求上下文调整
   ├─ 推荐等级判断 (HIGH/MEDIUM/LOW)
   └─ 推荐理由生成

7. 用户反馈 (RecommendationFeedback)
   ├─ 接受/拒绝/延后
   ├─ 可选文本评论
   └─ RunEvent 审计日志
```

### 6.2 推荐评分算法

```python
recommendation_score = (
    priority_score * 40 +           # 优先级 40% (季节性、销量、评分、竞争)
    margin_score * 30 +             # 利润率 30%
    risk_score_inverse * 20 +       # 风险反向 20%
    supplier_quality * 10 +         # 供应商质量 10%
    demand_adjustment               # 需求上下文调整 (-6 至 +3)
)
```

**推荐等级:**
- HIGH (≥75): 强烈推荐
- MEDIUM (60-74): 可以考虑
- LOW (<60): 不建议

---

## 七、当前优先级

### P0（立即执行）

1. **回归测试可观测性增强**
   - 统一 `strategy_run_id` / `candidate_product_id` / `listing_id` 的日志追踪
   - 结构化记录 agent 输入、输出、错误

2. **性能数据反馈闭环**
   - ListingPerformanceDaily 数据采集
   - AssetPerformanceDaily 数据采集
   - 转化率/ROI计算

3. **AI自动优化**
   - 基于性能数据的自动调价算法
   - 基于转化率的自动素材切换
   - 基于ROI的自动暂停逻辑

### P1（短期）

1. **ComfyUI 部署**
   - 按 `docs/deployment/comfyui-deployment-guide.md` 部署
   - 下载 FLUX.1-dev 模型（~100GB）
   - 配置 IPAdapter + ControlNet 工作流

2. **SGLang 部署**
   - 部署 Qwen3.5-35B-A3B（Tensor Parallel）
   - 配置 GPU 6-7
   - 测试推理速度和并发

3. **端到端测试**
   - 选品 → 图像生成 → 推荐 → 反馈 → 上架
   - 验证完整业务流程

### P2（中期）

1. **内容资产管理**
   - 实现 ContentAsset 模型
   - 图像质量评分
   - 版本控制

2. **平台发布**
   - 实现 PlatformListing 模型
   - Temu/Amazon API 集成
   - 库存同步

3. **A/B 测试**
   - 实现 Experiment 模型
   - 素材对比测试
   - 转化率追踪

---

## 八、关键指标监控

### 8.1 业务指标

- 候选产品数量
- 推荐数量（HIGH/MEDIUM/LOW）
- 平均推荐分数
- 用户反馈接受率
- 平均利润率
- 红海产品占比

### 8.2 技术指标

- GPU 利用率
- 图像生成速度（张/秒）
- LLM 推理速度（次/秒）
- API 调用成功率
- 缓存命中率
- 数据库查询性能

### 8.3 成本指标

- 硬件成本
- 电费成本
- API 调用成本
- 人工审核成本
- 单套产品成本

---

## 九、风险与挑战

### 9.1 硬件风险

- 8x4090 显存利用率 95%，无冗余
- 单卡故障影响整体产能

### 9.2 API 依赖风险

- Google Trends 限流
- Helium 10 API 成本
- 1688 API 稳定性

### 9.3 质量风险

- FLUX.1 质量 92 分，可能不满足高端市场
- IPAdapter 风格迁移依赖参考图质量

### 9.4 成本风险

- 8x4090 硬件成本 ~$16,000
- 电费成本（8 卡 * 450W * 20h/天）
- API 调用成本

---

## 十、总结

Deyes 项目已完成核心选品推荐系统的构建，具备需求验证、供应商匹配、定价计算、风控评估、推荐生成、用户反馈、数据分析等完整功能。技术架构采用 FLUX.1-dev + Qwen3.5 + SGLang 的组合，GPU 资源利用率达 95%。

**当前状态**: 核心选品推荐系统已完成，需求上下文集成已完成，AI 服务待部署

**下一步重点**: 完成 AI 服务部署（ComfyUI + SGLang），实现端到端业务流程验证，建立性能数据反馈闭环

**长期目标**: 实现日产能 8,000 套，覆盖 6 大跨境电商平台，成为跨境电商自动化运营的行业标杆

---

**文档维护**: 本文档应在每次重大功能交付后更新
