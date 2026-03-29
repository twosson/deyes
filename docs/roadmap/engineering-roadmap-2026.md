# Deyes 研发路线图 2026

> 面向研发、架构、数据、平台和测试团队
>
> 定位: AI Native 跨境卖家操作系统 + ERP Lite 内核
> 版本: v2.1
> 更新时间: 2026-03-29

---

## 当前研发基线（2026-03-29）

当前仓库的已实现基线已经不是早期的“推荐分析平台”原型，而是围绕需求验证优先选品与自动化经营方向演进的后端骨架。

**已完成的核心基线**：
- 需求验证优先的候选发现链路（DemandValidator）
- 1688 供应商匹配与竞争集评分（SupplierMatcher）
- 动态利润阈值与定价决策（PricingService）
- 合规风险 + 竞争密度 + 需求发现质量风险（RiskRules）
- 推荐服务作为内部决策引擎（RecommendationService）
- 定价、风控、推荐排序三层的需求上下文集成
- 自动执行方向的文档与基础服务骨架（AutoActionEngine / Approval 方向）

**当前研发重点**：
1. 固化 Stage 0 测试基线与回归可观测性
2. 建立 Stage 1 的表现数据回流（ListingPerformanceDaily / AssetPerformanceDaily）
3. 建立自动优化闭环（调价 / 换素材 / 暂停）
4. 推进多平台发布集成与审批兜底

## 自动化经营方向说明

Deyes 的目标不是把推荐结果展示给人做手动分析，而是在可控边界内自动执行经营动作，并把表现数据回流系统形成持续优化闭环。

因此：
- 推荐服务保留，但定位为内部决策引擎
- 审批工作台替代手动推荐浏览页面
- 性能监控面板替代通用 BI 式推荐分析页面
- 高风险动作需要审批，低风险动作自动执行

### 当前优先级

**P0 - 自动执行与反馈闭环**：
1. AutoActionEngine 服务
   - 自动上架（auto_publish）
   - 自动调价（auto_reprice）
   - 自动暂停（auto_pause）
   - 自动换素材（auto_asset_switch）

2. PlatformListing 状态机
   - draft → pending_approval → approved → published → active → paused
   - 审批边界配置（什么可以自动执行 vs 需要审批）

3. 多平台 API 集成
   - Temu API（上架、调价、暂停）
   - Amazon API
   - AliExpress API
   - RPA 备选方案（API 不可用时）

4. PerformanceDataLoop
   - ListingPerformanceDaily 数据采集
   - AssetPerformanceDaily 数据采集
   - 转化率 / ROI 计算逻辑

5. AI 自动优化
   - 基于性能数据的自动调价
   - 基于转化率的自动素材切换
   - 基于 ROI 的自动暂停

**P1 - 人工审批与监控**：
- 高风险操作需要人工审批（首次上架、大幅调价、下架）
- 低风险操作自动执行（小幅调价、素材切换、暂停）
- 审批边界可配置
- 性能监控面板与异常告警

### API-first, RPA-second 原则

**优先使用平台API**：
- Temu API（官方支持）
- Amazon SP-API（官方支持）
- AliExpress API（官方支持）

**API不可用时使用RPA**：
- Playwright自动化脚本
- 模拟人工操作
- 自动回退机制

### 人工审批边界

**自动执行（无需审批）**：
- 小幅调价（±5%）
- 素材切换（A/B测试胜出）
- 暂停低效商品（ROI < 阈值）
- 库存同步

**需要审批**：
- 首次上架新商品
- 大幅调价（>10%）
- 下架商品
- 高风险品类操作

### 当前能力定位

- DemandValidator / SupplierMatcher / PricingService / RiskRules 仍是当前选品主链路的核心能力
- RecommendationService 保留为内部决策引擎，继续服务审批与自动执行判断
- ApprovalWorkbench 与 Performance Monitoring 是自动化经营方向的操作界面，而不是通用推荐分析页面

### 阶段推进清单

- [ ] AutoActionEngine 服务实现与状态机收口
- [ ] ListingPerformanceDaily / AssetPerformanceDaily 数据回流
- [ ] 转化率 / ROI / 素材表现计算逻辑
- [ ] 基于表现数据的自动调价 / 换素材 / 暂停
- [ ] Temu / Amazon / AliExpress 平台集成
- [ ] API 失败时的 RPA 回退
- [ ] ApprovalWorkbench 与异常告警面板

---

## 1. 文档目标

本文档把产品路线图翻译为可执行的研发路线图，强调：

1. 以当前仓库真实实现为基线，而不是从零设计
2. 先巩固已跑通的 1688 选品闭环，再扩展为 ERP Lite 操作系统
3. 保持 Agent 边界清晰，避免把业务复杂度全部堆进单个 Adapter
4. 通过分阶段的数据模型演进，把“候选商品系统”升级为“SKU 经营系统”

---

## 2. 当前代码基线

### 2.1 已实现的主链路

当前最成熟链路是：

`Candidate discovery -> Supplier competition set -> Pricing -> Risk -> Content asset -> Platform listing -> Historical feedback`

关键实现位置：

- 1688 选品适配器骨架与评分主链路：`backend/app/services/alibaba_1688_adapter.py:147`
- 历史高表现 seed recall 注入点：`backend/app/services/alibaba_1688_adapter.py:365`
- candidate 总分计算：`backend/app/services/alibaba_1688_adapter.py:1606`
- business score 计算：`backend/app/services/alibaba_1688_adapter.py:1679`
- 输出 `normalized_attributes`：`backend/app/services/alibaba_1688_adapter.py:1823`

### 2.2 已实现的数据模型

核心模型已覆盖最小经营闭环：

- 候选商品：`backend/app/db/models.py:88`
- 供应商匹配：`backend/app/db/models.py:136`
- 定价评估：`backend/app/db/models.py:158`
- 风险评估：`backend/app/db/models.py:188`
- 内容资产：`backend/app/db/models.py:258`
- 平台上架记录：`backend/app/db/models.py:322`
- 库存同步日志：`backend/app/db/models.py:394`
- 价格历史：`backend/app/db/models.py:416`

### 2.3 已实现的 Agent 边界

- Product Selector：`backend/app/agents/product_selector.py:80`
- Pricing Analyst：`backend/app/agents/pricing_analyst.py:70`
- Risk Controller：`backend/app/agents/risk_controller.py:60`
- Content Asset Manager：`backend/app/agents/content_asset_manager.py:61`
- Platform Publisher：`backend/app/agents/platform_publisher.py:82`

### 2.4 已实现的反馈能力

- Phase 6 路线文档状态已经进入完成态：`docs/architecture/business-optimization-v5.md:744`
- 历史反馈聚合器已经落地：`backend/app/services/feedback_aggregator.py`
- 已验证历史 prior 会进入 recall/ranking 相关逻辑

### 2.5 当前测试成熟度

以下关键测试已经通过：

- `backend/tests/test_feedback_aggregator.py`
- `backend/tests/test_alibaba_1688_adapter_tmapi.py`
- `backend/tests/test_phase1_mvp.py`
- `backend/tests/test_pricing_service.py`
- `backend/tests/test_risk_rules.py`

这说明：
- 选品闭环主链路可回归
- Phase 6 历史反馈接入稳定
- 最小 MVP 持久化链路已打通

---

## 3. 研发总原则

### 原则 1：保留 Candidate 层，新增 Product/SKU 层

`CandidateProduct` 继续承担“发现期对象”的职责，不要强行让它兼任长期 ERP 主实体。

建议中长期演进为：

- `CandidateProduct`：发现层
- `ProductMaster` / `SPU`：商品主数据层
- `SKU`：库存与经营最小单元
- `PlatformListing`：平台在售单元

### 原则 2：Agent 负责决策，ERP Lite 负责事实

不要把订单、库存、采购、利润全部塞回 Adapter 或 Agent 的 `normalized_attributes`。

建议边界：

- Agent：决策和动作编排
- ERP Lite：商品、库存、采购、订单、利润事实层
- Feedback：从 ERP Lite 和平台表现中抽象成优化信号

### 原则 3：优先增加新表和新服务，避免破坏现有链路

当前主链路已经可跑通。后续演进优先采用：

- 新增表
- 新增服务
- 新增 agent
- 给现有模型追加可选字段

避免大规模重构 `CandidateProduct -> ContentAsset -> PlatformListing` 主链路。

### 原则 4：测试分层必须先行

必须把测试拆为：

- unit
- regression
- integration
- external-platform

Temu 页面抓取类测试不能阻塞核心业务回归。

---

## 4. 目标系统形态

最终系统按 4 层演进：

### 4.1 决策层

- Product Selector
- Pricing Analyst
- Risk Controller
- Content Strategy / A-B Test Manager
- Procurement Agent
- Lifecycle Manager

### 4.2 执行层

- Source adapters
- Content generation services
- Platform publisher / sync
- Inventory allocator
- Purchase order execution

### 4.3 ERP Lite 事实层

- ProductMaster / SKU
- Supplier / SupplierOffer / PurchaseOrder
- Inventory / Warehouse / Shipment
- Order / Refund / Return
- ProfitLedger / SettlementEntry

### 4.4 反馈层

- Listing performance metrics
- Asset performance metrics
- Supplier performance metrics
- Risk outcome feedback
- Pricing outcome feedback
- FeedbackAggregator

---

## 5. 分阶段研发路线图

---

## Stage 0：稳定当前基线

### 目标

把当前已经通过的回归能力沉淀为稳定基线，为后续 schema 演进和多平台扩张做准备。

### 必做交付

1. **测试分层**
   - 把 `backend/tests` 拆分标签：`unit` / `regression` / `integration` / `external`
   - 对 Temu 网页抓取测试增加 `integration` 或 `external-platform` 标记

2. **统一回归入口**
   - 建立核心回归测试集合：
     - `test_feedback_aggregator.py`
     - `test_alibaba_1688_adapter_tmapi.py`
     - `test_phase1_mvp.py`
     - `test_pricing_service.py`
     - `test_risk_rules.py`

3. **观测性增强**
   - 统一 `strategy_run_id` / `candidate_product_id` / `listing_id` 的日志追踪
   - 结构化记录 agent 输入、输出、错误

4. **平台测试隔离**
   - 真实网页/真实平台 API 相关测试从默认回归中剥离

### 涉及文件

- `backend/tests/*`
- `backend/app/core/logging.py`
- `backend/app/agents/base/*`

### 退出标准

- 核心回归一条命令可稳定执行
- 外部平台失败不阻塞主回归
- 任意一条任务链路能通过日志追踪完整定位

---

## Stage 1：补全“可经营闭环”的结果层

### 目标

让当前系统不仅能选品和上架，还能记录真实经营结果并回流。

### 必做交付

#### 1. Listing 表现表
新增建议：

- `ListingPerformanceDaily`
  - `listing_id`
  - `date`
  - `impressions`
  - `clicks`
  - `ctr`
  - `orders`
  - `units_sold`
  - `gross_revenue`
  - `refund_count`
  - `refund_amount`

#### 2. Asset 表现归因表
新增建议：

- `AssetPerformanceDaily`
  - `asset_id`
  - `listing_id`
  - `date`
  - `impressions`
  - `clicks`
  - `ctr`
  - `orders_attributed`
  - `revenue_attributed`

#### 3. 平台同步服务增强
在 `PlatformPublisher` 基础上补齐：

- listing 状态同步
- 库存同步
- 价格同步
- 表现数据拉取

参考位置：`backend/app/agents/platform_publisher.py:82`

#### 4. 平台适配器从 mock 向真实 API 演进
优先顺序：
- Temu
- Amazon
- Ozon

### 新增服务建议

- `backend/app/services/listing_metrics_service.py`
- `backend/app/services/platform_sync_service.py`

### 测试要求

- 新增 performance persistence tests
- 新增 sync reconciliation tests
- 保持 Phase 1 MVP tests 不回退

### 退出标准

- 每个 listing 都能回收到表现数据
- 每个 asset 都能部分归因到表现
- 平台同步任务有稳定重试机制

---

## Stage 2：把 Phase 6 升级为经营反馈引擎

### 目标

让反馈不只作用于 seed/shop/supplier，还能作用于 style、asset pattern、platform、region、price band。

### 必做交付

#### 1. FeedbackAggregator 升级

当前基础已经存在：`backend/app/services/feedback_aggregator.py`

下一步增强：
- `get_style_performance_prior(style: str, category: str | None)`
- `get_platform_region_prior(platform: str, region: str, category: str | None)`
- `get_price_band_prior(category: str, price_band: str)`
- supplier 风险/退款/交期惩罚项

#### 2. Adapter 注入增强
继续强化 1688 adapter 中的注入点：

- recall 注入：`backend/app/services/alibaba_1688_adapter.py:365`
- business score 注入：`backend/app/services/alibaba_1688_adapter.py:1679`
- 输出观察字段：`backend/app/services/alibaba_1688_adapter.py:1823`

#### 3. 反馈特征沉淀规范
约束 `normalized_attributes` 中只写调试和验证需要的派生信号，不要把 ERP 事实层塞进去。

建议保留：
- `historical_seed_prior`
- `historical_shop_prior`
- `historical_supplier_prior`
- `historical_feedback_score`
- `historical_style_prior`
- `historical_platform_region_prior`

#### 4. 负反馈降权机制
不仅要奖励高表现，也要显式惩罚：
- 高退款 seed
- 高风险 style 组合
- 高售后 supplier
- 某平台特定类目低转化 price band

### 新增服务建议

- `backend/app/services/feedback_feature_store.py`
- `backend/app/services/performance_aggregator.py`

### 测试要求

- 继续扩展 `backend/tests/test_feedback_aggregator.py`
- 扩展 `backend/tests/test_alibaba_1688_adapter_tmapi.py`
- 保证原 Phase 1-5 语义不退化

### 退出标准

- 历史反馈显著影响 recall 与 ranking
- 负反馈会明确降权
- 系统可解释为什么偏爱某类 seed / supplier / style

---

## Stage 3：建立 ERP Lite 商品与供应链核心

### 目标

建立最小可用 ERP Lite 事实层，使系统从“候选商品驱动”升级为“SKU 驱动经营”。

### 必做交付

#### 1. 商品主数据层
新增建议：

- `ProductMaster`
  - 主商品概念
  - 与 `CandidateProduct` 关联
- `ProductVariant` / `SKU`
  - sku_code
  - spec attributes
  - status
  - default supplier

#### 2. 供应商主数据层
新增建议：

- `Supplier`
- `SupplierOffer`
- `SupplierLeadTimeHistory`
- `SupplierQualityScore`

说明：
- `SupplierMatch` 保留做“发现/竞争集证据”
- `Supplier` 做“长期运营实体”

#### 3. 采购层
新增建议：

- `PurchaseOrder`
- `PurchaseOrderLine`
- `InboundShipment`
- `GoodsReceipt`

#### 4. 库存层
新增建议：

- `Warehouse`
- `InventoryBalance`
- `InventoryReservation`
- `InventoryMovement`

### Agent / Service 变更

新增：
- `backend/app/agents/procurement_agent.py`
- `backend/app/services/inventory_allocator.py`
- `backend/app/services/supplier_master_service.py`

现有 Agent 边界保持：
- Product Selector 不直接处理库存
- Pricing Analyst 不直接处理采购执行
- Procurement Agent 接管补货与采购建议

### 测试要求

- SKU lifecycle tests
- purchase order creation tests
- inventory allocation tests
- supplier entity resolution tests

### 退出标准

对任意一个 SKU，系统能查询：
- 来源候选商品
- 当前供应商
- 最近采购价
- 当前库存
- 在途数量
- 补货建议

---

## Stage 4：订单、售后、利润台账

### 目标

从“理论利润”升级为“真实经营利润”。

### 必做交付

#### 1. 订单中心
新增建议：

- `PlatformOrder`
- `PlatformOrderLine`
- `FulfillmentRecord`

#### 2. 售后中心
新增建议：

- `RefundCase`
- `ReturnCase`
- `AfterSaleIssue`

#### 3. 利润台账
新增建议：

- `SettlementEntry`
- `AdCostAllocation`
- `ProfitLedger`

#### 4. SKU / Listing 真实利润聚合
聚合维度：
- SKU
- listing
- platform
- region
- supplier
- style / asset variant

### 服务建议

- `backend/app/services/order_ingestion_service.py`
- `backend/app/services/profit_ledger_service.py`
- `backend/app/services/refund_analysis_service.py`

### 与现有模型关系

- `PricingAssessment` 继续保留作为“上线前利润判断”
- `ProfitLedger` 成为“真实净利真相”

### 测试要求

- order ingestion tests
- refund reconciliation tests
- profit ledger calculation tests
- supplier profitability attribution tests

### 退出标准

任意一个在售 SKU 都能得到：
- 理论毛利
- 实际净利
- 退款损失
- 平台费用
- 广告分摊后利润

---

## Stage 5：多平台统一经营中枢

### 目标

让同一 SKU 能跨平台统一管理和优化。

### 必做交付

#### 1. 平台适配器扩展
建议顺序：
- Temu（真实 API 化）
- Amazon
- Ozon
- 其余平台按业务优先级推进

#### 2. 平台策略层
新增建议：

- `PlatformPolicy`
- `PlatformCategoryMapping`
- `PlatformPricingRule`
- `PlatformContentRule`

#### 3. 多币种与地区化
新增建议：

- `ExchangeRate`
- `RegionTaxRule`
- `RegionRiskRule`

#### 4. 多语言内容基础设施
新增建议：

- `LocalizedContent`
- `ContentTemplate`
- `ContentVersion`

### 服务建议

- `backend/app/services/currency_converter.py`
- `backend/app/services/platform_policy_service.py`
- `backend/app/services/localization_service.py`

### 测试要求

- platform mapping tests
- multi-region pricing tests
- exchange rate conversion tests
- localized listing generation tests

### 退出标准

同一 SKU 能在多个平台统一查看：
- 状态
- 库存
- 价格
- 表现
- 利润

---

## Stage 6：自动化经营控制平面

### 目标

把系统从“人驱动动作”升级为“系统驱动动作，人只处理例外”。

### 必做交付

#### 1. 生命周期引擎
新增建议：

- `SkuLifecycleState`
- `LifecycleRule`
- `LifecycleTransitionLog`

典型状态：
- DISCOVERING
- TESTING
- SCALING
- STABLE
- DECLINING
- CLEARANCE
- RETIRED

#### 2. 自动动作引擎
新增建议：

- `ActionRule`
- `ActionExecutionLog`
- `ManualOverride`

自动动作包括：
- 调价
- 换素材
- 降预算
- 扩平台
- 触发补货
- 下架清退

#### 3. 经营控制台 API
需要统一输出：
- 今日异常
- 值得加码 SKU
- 应该清退 SKU
- 供应商异常
- 风险升级事项

### Agent 建议

新增：
- `backend/app/agents/lifecycle_manager.py`
- `backend/app/agents/operations_controller.py`

### 测试要求

- lifecycle transition tests
- rule execution tests
- override / rollback tests
- anomaly detection tests

### 退出标准

- 80% 常规动作自动执行
- 人工只处理异常、审批、策略修正
- 每次自动动作都有可追踪日志和可回滚能力

---

## 6. 数据模型演进建议

### 6.1 保留现有模型不动的部分

建议保留并继续复用：
- `CandidateProduct`
- `SupplierMatch`
- `PricingAssessment`
- `RiskAssessment`
- `ContentAsset`
- `PlatformListing`

因为这些已经有回归测试和主链路依赖。

### 6.2 优先新增而不是替换

优先新增：
- ProductMaster / SKU
- Supplier / SupplierOffer
- Inventory* / PurchaseOrder* / Shipment*
- Order* / Refund* / ProfitLedger*

不要急于把旧模型推翻替换。

### 6.3 关键实体关系

建议最终形成：

`CandidateProduct -> ProductMaster -> SKU -> PlatformListing -> PlatformOrderLine -> ProfitLedger`

并行关系：

- `CandidateProduct -> SupplierMatch`
- `SKU -> SupplierOffer / PurchaseOrder`
- `PlatformListing -> ContentAsset`
- `PlatformListing -> ListingPerformanceDaily`
- `FeedbackAggregator <- performance + risk + pricing + supplier outcomes`

---

## 7. 平台与服务边界建议

### 7.1 不要把 ERP 查询直接塞进 adapter

`Alibaba1688Adapter` 应继续做：
- 召回
- 排序
- 标准化输出

不要让它直接承担：
- 订单分析
- 采购策略
- 库存分配
- 利润台账

### 7.2 FeedbackAggregator 是桥，不是事实库

`FeedbackAggregator` 应负责：
- 从多张事实表读取结果
- 聚合成轻量 prior
- 提供 recall/ranking 用的可解释信号

不应变成：
- 大型特征仓库
- 全量分析平台
- BI 替代品

### 7.3 PlatformPublisher 是执行器，不是经营真相来源

`PlatformPublisher` 负责创建和同步 listing，但：
- 经营结果要落到 metrics / order / profit 表
- 不应只停留在 `PlatformListing.platform_data`

---

## 8. 测试路线图

### 必须长期维持的核心回归

- `backend/tests/test_feedback_aggregator.py`
- `backend/tests/test_alibaba_1688_adapter_tmapi.py`
- `backend/tests/test_phase1_mvp.py`
- `backend/tests/test_pricing_service.py`
- `backend/tests/test_risk_rules.py`

### 后续每个阶段新增测试建议

#### Stage 1
- listing metrics ingestion
- asset attribution
- sync retry / reconciliation

#### Stage 2
- historical style prior
- platform-region prior
- negative feedback demotion

#### Stage 3
- sku creation
- supplier entity linking
- inventory reservation / release
- procurement workflow

#### Stage 4
- order ingestion
- refund matching
- real profit calculation

#### Stage 5
- multi-platform listing policy
- region pricing conversion
- localization correctness

#### Stage 6
- lifecycle transitions
- auto action execution
- rollback / manual override

---

## 9. 当前最优先的研发事项

### P0
1. 测试分层与 CI 固化
2. 平台表现数据回流 schema
3. Listing / Asset 表现聚合服务
4. Temu 真实平台同步能力

### P1
1. FeedbackAggregator 升级
2. style / platform / region / price band prior
3. ProductMaster / SKU 数据模型
4. Supplier 主数据与采购实体

### P2
1. 订单/售后/利润台账
2. 多平台扩展
3. 多币种与本地化

### P3
1. 生命周期引擎
2. 自动动作引擎
3. 高级内容能力（视频/3D）

---

## 10. 收尾建议

Deyes 当前最宝贵的资产不是某一个 Agent，而是这条已经跑通的主干：

`选品 -> 供应商竞争集 -> 定价 -> 风控 -> 素材 -> 上架 -> 反馈`

研发路线图的核心，不是发明更多概念，而是把这条主干稳步升级成：

`Candidate -> SKU -> Listing -> Order -> Profit -> Feedback -> Better Candidate`

这就是 Deyes 从 AI 选品系统成长为 AI Native 卖家操作系统的正确路径。

---

**文档版本**: v1.0
**最后更新**: 2026-03-25
**维护者**: Deyes 研发团队
