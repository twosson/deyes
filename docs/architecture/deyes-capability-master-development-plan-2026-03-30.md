# Deyes 能力整合与商品策略总体开发计划

**日期**: 2026-03-30
**状态**: 统一规划版 / 可作为后续实施主文档
**适用范围**: AlphaShop / 1688 官方开放平台 / 采购执行 / 供应商发现 / 需求情报 / 固定组合 SKU / 跟卖策略

---

## 0. 文档目的

本文件用于把本轮讨论中的所有核心结论统一沉淀为一个可执行的开发计划，避免信息分散在多个会话和多个局部文档中。

本文件覆盖：

1. **AlphaShop API / Agent / MCP / 可接入性结论**
2. **1688 官方开放平台优先接入结论**
3. **Deyes 当前采购、选品、供应商匹配、listing 能力评估**
4. **固定组合商品（Bundle / Kit / Multipack）能力规划**
5. **跟卖（Join Existing Listing / Follow Selling）能力规划**
6. **统一的实施优先级、架构改造方向、测试计划**

---

## 1. 总体结论

### 1.1 最核心判断

Deyes 后续能力建设应分成三条主线：

1. **外部采购与供应商能力接入**
2. **组合商品能力建设**
3. **listing 策略扩展能力建设**

其中优先级建议为：

- **P0：1688 官方开放平台 + Deyes 采购抽象层完善**
- **P1：固定组合 SKU / Bundle 能力**
- **P2：跟卖能力（仅对支持共享 listing 的平台）**
- **P3：AlphaShop 可选增强（仅限未来出现正式 API 的能力）**

### 1.2 关于 AlphaShop 的最终结论

**AlphaShop 当前不应作为 Deyes 的核心系统集成对象。**

原因不是它没有业务价值，而是：

- 当前公开信息下，**没有确认到正式公开 API 平台**
- 没有公开开发者门户
- 没有正式 OpenAPI / SDK / webhook 文档
- 没有证据表明其询盘、下单、订单同步、物流同步可稳定程序化接入
- 浏览器自动化虽然理论上可行，但稳定性、合规性、维护成本都不适合作为主通道

因此：

- **AlphaShop 不适合做 P0 采购执行通道**
- **1688 官方开放平台应替代 AlphaShop 成为 P0 外部采购对接对象**
- AlphaShop 可保留为：
  - 人工辅助工具
  - 潜在情报源
  - 若未来正式开放 API，可再重新评估接入

### 1.3 关于组合商品的最终结论

**固定组合商品完全值得做。**

并且：

- 现有 Deyes 数据模型和选品流程都还是**单品导向**
- 但 Qwen3.5 或更强模型，完全可以承担“组合机会发现、互补商品推理、组合评分、组合内容生成”
- 该能力比跟卖更符合 Deyes 当前“差异化经营”方向
- 组合商品能直接提升：
  - 客单价
  - 差异化竞争力
  - 库存利用率
  - 同供应商采购效率

因此 Bundle 能力应排在跟卖之前。

### 1.4 关于跟卖的最终结论

**跟卖值得支持，但不应作为当前第一优先级。**

原因：

- 跟卖只适用于部分平台（如 Amazon 一类共享 catalog 的平台）
- 对 Temu 这类以独立 listing 为主的平台帮助有限
- 合规与品牌授权风险较高
- 当前 Deyes 的 listing 架构是围绕“创建新 listing”设计的，并未抽象出“加入现有 listing”策略

因此建议：

- 先完成自建 listing 与 Bundle 能力
- 后续再以“listing strategy”扩展方式加入 follow-selling
- 跟卖应首先面向共享 listing 机制成熟的平台，而不是全平台统一铺开

---

## 2. 现状评估：Deyes 当前代码能力与缺口

### 2.1 采购链路现状

当前 Deyes 已有采购骨架，但还不是“真实外部采购执行系统”。

已有能力：

- `backend/app/services/procurement_service.py`
  - `create_purchase_order()`
  - `submit_purchase_order()`
  - `confirm_purchase_order()`
- `backend/app/services/inventory_allocator.py`
  - 入库、预占、出库、收货等库存动作
- `backend/app/db/models.py`
  - `Supplier`
  - `SupplierOffer`
  - `PurchaseOrder`
  - `PurchaseOrderItem`
  - `InboundShipment`

核心缺口：

- 没有批量询盘实体
- 没有供应商回复同步机制
- 没有真实外部下单执行接口
- 没有订单状态同步
- 没有物流状态回流
- 没有采购执行闭环评分

换句话说：

**当前采购更多是 ERP 内部状态管理，不是外部执行闭环。**

### 2.2 选品链路现状

当前 Deyes 的选品流程设计方向正确，但仍是单品逻辑。

已有能力：

- `backend/app/agents/product_selector.py`
- `backend/app/services/demand_validator.py`
- `backend/app/services/product_scoring_service.py`
- `backend/app/services/recommendation_service.py`

当前特征：

- 先做需求验证
- 再做平台抓取
- 再做供应商匹配
- 最后做利润、风险、优先级综合评分

核心缺口：

- 没有“商品间关系分析”
- 没有“固定组合机会发现”
- 没有“Bundle 评分与推荐”
- 没有“组合内容生成”

### 2.3 供应商匹配现状

当前 `SupplierMatcherService` 更接近“提取器 + fallback”，不是强多源召回引擎。

已有行为：

- 优先使用 adapter 已给出的 supplier candidates
- 尝试从 1688 payload 抽取供应商信息
- 没有真实可用信息时 fallback 到 mock supplier

核心缺口：

- 没有独立供应商发现抽象层
- 没有图搜找货能力抽象
- 没有跨源召回与去重
- 没有历史表现驱动的统一排序

### 2.4 listing 策略现状

当前 Deyes 的平台上架体系是：

- `PlatformPublisherAgent` 组织素材、价格、文案
- `UnifiedListingService.create_listing()` 调平台 adapter 创建 listing
- `PlatformListing` 记录平台商品映射

核心缺口：

- 没有 `listing_strategy` 概念
- 没有 `join_existing_listing` / follow-selling 抽象
- 没有可跟卖 listing 搜索能力
- 没有产品一致性校验能力
- 没有 Buy Box / 跟卖竞争分析能力

### 2.5 商品模型现状

当前商品模型还是“单 master + 单 variant”的基础结构。

已有模型：

- `ProductMaster`
- `ProductVariant`

缺口：

- 没有 `ProductBundle`
- 没有 `BundleComponent`
- 没有 `BundleOpportunity`
- 没有 bundle pricing / inventory strategy
- 没有虚拟库存或组件扣减策略

---

## 3. AlphaShop API / Agent / MCP 分析结论

### 3.1 关于 AlphaShop API 的结论

基于公开网页、公开资料与可见文档的分析，当前结论是：

**未发现 AlphaShop 正式公开的开发者 API 体系。**

当前未确认到：

- 正式 API 文档入口
- 开发者门户
- API Key 管理机制
- OpenAPI / Swagger
- SDK
- webhook / callback
- 询盘 / 下单 / 订单同步 / 物流同步的正式接口说明

当前仅看到的弱信号：

- 社区资料中提到一个疑似图片翻译相关端点
- 但该信息并非官方开发文档
- 也不能证明 AlphaShop 对采购执行链路提供正式可接入 API

因此不能把 AlphaShop 视为一个已经验证可接入的开放 API 平台。

### 3.2 关于 AlphaShop Agent 能力的结论

AlphaShop 更像：

- 面向用户的 AI 助手产品
- 通过 Web UI / 插件承载工作流
- 帮助做选品、找厂、询盘辅助、内容处理

而不是：

- 开发者可组合调用的稳定 Agent 基础设施
- 可直接嵌入 Deyes 工作流的正式 API Agent 平台

因此它更适合作为：

- **人工使用的外部工具**
- **未来可能的情报源**
- **若将来开放 API 后的插件型 provider**

### 3.3 关于 AlphaShop MCP 的结论

本轮分析中，**未发现 AlphaShop 官方公开的 MCP Server / MCP Tool 文档**。

因此当前不建议：

- 把 AlphaShop 视为可直接消费的官方 MCP 服务
- 把关键业务写操作依赖在 AlphaShop MCP 上

如果未来 AlphaShop 真的开放 API，Deyes 也更适合：

- **由 Deyes 自己封装 provider / client / tool adapter**
- 而不是把 AlphaShop 当成系统内的 source-of-truth

### 3.4 AlphaShop 当前最合理定位

当前最合理定位是三选一：

1. **人工辅助工具**
   - 运营使用 AlphaShop 做市场调研、图搜、询盘辅助
   - 结果再回填 Deyes

2. **未来的可选情报源**
   - 如果未来提供正式 API，可作为：
     - 供应商发现增强
     - 图片翻译增强
     - 市场信号增强

3. **观察对象**
   - 持续观察其是否推出正式开发者能力

---

## 4. AlphaShop 与 1688 官方开放平台的战略区分

### 4.1 不是同一个东西

- **AlphaShop**：面向用户的 AI 助手 / 产品化应用
- **1688 官方开放平台**：面向开发者的 API 平台

### 4.2 对 Deyes 的意义不同

如果目标是：

- 稳定系统集成
- 长期维护
- 程序化询盘 / 下单 / 状态同步
- 合规与 SLA

则优先对象必须是：

**1688 官方开放平台**

如果目标是：

- 给运营人员提供更强工具
- 辅助找货 / 选品 / 图搜
- 先做手工过渡方案

则 AlphaShop 仍然有价值。

### 4.3 最终战略决策

后续路线应调整为：

- **P0：1688 官方开放平台接入**
- **P1：Deyes 采购抽象层与执行闭环完善**
- **P2：AlphaShop 仅作为可选增强或人工辅助能力**

---

## 5. 统一能力建设目标

### 5.1 外部能力建设目标

目标不是“把 Deyes 改造成 AlphaShop 的壳”，而是：

- Deyes 保留经营决策内核
- 外部系统只作为能力提供者
- 所有关键业务状态保留在 Deyes 内部
- 所有通道都必须可切换、可回退、可审计

### 5.2 商品策略建设目标

Deyes 应支持三类商品经营策略：

1. **Create New Listing（自建 listing）**
2. **Bundle Listing（固定组合 SKU）**
3. **Join Existing Listing（跟卖 / 加入现有 listing）**

三者不应混在一个硬编码流程里，而应被抽象为统一的 strategy layer。

---

## 6. 目标架构

## 6.1 外部能力抽象层

建议引入三类 provider：

### A. `ProcurementExecutionProvider`

职责：

- send inquiry
- get inquiry status
- create order
- get order status
- cancel order

候选实现：

- `Alibaba1688ProcurementProvider`
- `AlphaShopProcurementProvider`（未来可选）
- `ManualProcurementProvider`

### B. `SupplierDiscoveryProvider`

职责：

- 搜索供应商
- 图搜找货
- 返回标准化 supplier candidates

候选实现：

- `Alibaba1688SupplierProvider`
- `AlphaShopSupplierProvider`（未来可选）
- `InternalSupplierHistoryProvider`

### C. `MarketIntelProvider`

职责：

- 趋势信号
- 榜单信号
- 竞品信号
- 类目机会

候选实现：

- `Helium10Provider`
- `AlphaShopIntelProvider`（未来可选）
- `MarketplaceSignalProvider`
- `InternalPerformanceProvider`

## 6.2 商品策略抽象层

建议新增：

```python
class ListingStrategy(str, Enum):
    CREATE_NEW = "create_new"
    JOIN_EXISTING = "join_existing"
    BUNDLE = "bundle"
```

并在上架侧按策略分流：

- `create_new_listing(...)`
- `join_existing_listing(...)`
- `create_bundle_listing(...)`

## 6.3 Bundle 能力层

建议新增：

- `ProductBundle`
- `BundleComponent`
- `BundleOpportunity`
- `BundleDiscoveryService`
- `BundleDiscoveryAgent`

## 6.4 运营控制平面接入

所有新增能力最终都应进入 Operations Console：

- 待发送询盘
- 已发送待回复询盘
- 已外部提交待同步 PO
- 异常物流
- Bundle 候选机会
- 跟卖候选与风控提示

---

## 7. 开发主计划

# Track A：1688 官方开放平台与采购执行能力

## A1. 官方接入研究与能力映射

目标：

- 确认 1688 官方开放平台接入门槛
- 梳理其可覆盖的能力
- 形成 Deyes 内部标准接口映射

输出：

- 1688 能力矩阵
- 鉴权方式说明
- 询盘 / 下单 / 订单同步 / 物流同步映射表
- 是否支持 sandbox / test environment 的结论

## A2. 外部采购执行抽象层

新增：

- `backend/app/services/providers/base_procurement_provider.py`
- `backend/app/services/procurement_execution_router.py`
- `backend/app/services/providers/manual_procurement_provider.py`
- `backend/app/services/providers/alibaba_1688_procurement_provider.py`

原则：

- 业务服务层不直接依赖平台私有 API
- provider 失败可 fallback
- 所有原始返回保留 `raw_payload`

## A3. 询盘模型与询盘服务

新增：

- `SupplierInquiry` 模型
- migration
- `backend/app/services/inquiry_service.py`

核心能力：

- 创建询盘草稿
- 向一个或多个供应商发送询盘
- 定时同步回复
- 将回复转为 `SupplierOffer`

建议字段：

- variant_id
- supplier_id
- quantity
- target_price
- status
- execution_provider
- external_inquiry_id
- supplier_response
- quoted_price
- quoted_currency
- quoted_moq
- quoted_lead_time_days
- sent_at
- replied_at
- expires_at
- raw_payload

## A4. PO 外部执行与同步

扩展：

- `PurchaseOrder` 模型
- `ProcurementService`

建议新增字段：

- execution_provider
- external_order_id
- external_order_url
- tracking_number
- logistics_provider
- logistics_status
- last_synced_at
- raw_payload

建议新增方法：

- `submit_purchase_order_via_provider(...)`
- `sync_purchase_order_status(...)`
- `sync_submitted_purchase_orders(...)`

## A5. 后台同步任务

新增：

- `backend/app/workers/tasks_inquiry_sync.py`
- `backend/app/workers/tasks_procurement_sync.py`

要求：

- 幂等
- 可重试
- 错误隔离
- 有同步批次限制

## A6. 人工 fallback 通道

必须保留：

- `ManualProcurementProvider`

目标：

- 即使外部平台不可用，采购链路仍能继续
- 为人工运营提供明确待处理队列

---

# Track B：供应商发现与情报增强

## B1. 供应商发现抽象层

新增：

- `backend/app/services/providers/base_supplier_discovery_provider.py`
- `backend/app/services/supplier_discovery_router.py`

目标：

- 从“提取型 supplier matcher”升级到“多源召回 + 内部重排”

## B2. SupplierMatcherService 重构

改造方向：

- 兼容现有提取逻辑
- 新增多 provider 召回入口
- 新增去重
- 新增标准化
- 新增历史表现加权

## B3. MarketIntelProvider 抽象

新增：

- `backend/app/services/providers/base_market_intel_provider.py`
- `backend/app/services/market_intel_router.py`

目标：

- 外部情报只作为“证据层”
- 最终是否通过仍由 Deyes 的 `DemandValidator` 输出

## B4. AlphaShop 的保留接入点

AlphaShop 当前只保留以下候选位置：

- `AlphaShopSupplierProvider`（未来若出现正式 API）
- `AlphaShopIntelProvider`（未来若出现正式 API）
- `AssetDerivationService` 的图片翻译增强（未来若出现正式 API）

当前不实施：

- AlphaShop 采购执行主通道
- AlphaShop 浏览器自动化生产化方案

---

# Track C：固定组合商品（Bundle）能力

## C1. 数据模型建设

新增：

- `ProductBundle`
- `BundleComponent`
- `BundleOpportunity`

建议核心字段：

### `ProductBundle`
- bundle_variant_id
- bundle_type
- pricing_strategy
- bundle_price
- discount_percentage
- inventory_strategy

### `BundleComponent`
- bundle_id
- component_variant_id
- quantity
- is_primary

### `BundleOpportunity`
- strategy_run_id
- anchor_candidate_id
- complementary_keywords
- bundle_type
- opportunity_score
- confidence_score
- reasoning
- status

## C2. 规则版组合发现

新增：

- `backend/app/services/bundle_discovery_service.py`

先支持三类规则：

1. 同品类多件装
2. 同供应商互补组合
3. 同类目功能互补组合

目标：

- 先验证业务价值
- 不依赖模型调用即可上线内部试验

## C3. AI 版组合发现

新增：

- `backend/app/agents/bundle_discovery.py`

职责：

- 推理互补商品
- 评估组合机会
- 生成组合内容

可用输入信号：

- candidate product 基础属性
- 平台搭配购买数据
- 供应商可采购性
- 历史经营反馈

## C4. 组合定价与库存策略

扩展：

- `PricingService`
- `InventoryAllocator`
- `UnifiedListingService`

需要明确：

- bundle price 如何计算
- 组件库存如何扣减
- 是否支持虚拟库存
- 是否允许独立 bundle price 与折扣 price

## C5. 上架与内容集成

扩展：

- `PlatformPublisherAgent`
- `UnifiedListingService`
- 内容资产选择逻辑

目标：

- 让 bundle 不只是数据层存在，而是能真正发布成平台商品

---

# Track D：listing 策略扩展与跟卖能力

## D1. listing_strategy 抽象

扩展：

- `PlatformListing`
- `UnifiedListingService`
- `PlatformPublisherAgent`

建议新增字段：

- `listing_strategy`
- `target_listing_id`
- `product_match_confidence`
- `compliance_check_status`
- `buy_box_competition_score`

## D2. 平台能力矩阵

先建立平台级判断：

- 哪些平台支持共享 listing
- 哪些平台支持 join existing listing
- 哪些平台必须自建 listing

建议先支持：

- Amazon 类平台
- Ozon 类支持共享 catalog 的平台

当前不建议优先推进：

- Temu 跟卖

## D3. 跟卖候选发现

新增能力：

- 搜索已有 listing
- 判断是否可加入
- 返回候选 listing 列表

需要判断：

- listing 是否开放多卖家竞争
- 是否需要品牌授权
- 当前价格带和竞争强度是否合适

## D4. 产品一致性与合规检查

新增能力：

- 图片一致性校验
- 属性一致性校验
- 授权/品牌风险校验
- 灰色跟卖风险提示

原则：

- 只有高置信度一致时，才允许加入现有 listing
- 不为高风险灰色跟卖提供自动化主流程

## D5. join existing listing 执行能力

平台 adapter 需要扩展支持：

- `create_listing(...)`
- `join_listing(...)`

业务上需要支持：

- 跟卖价格策略
- 物流/库存策略
- 后续销售表现监控

---

# Track E：Operations Console 接入

## E1. 采购链路可视化

新增页面或模块：

- 询盘列表
- 待回复询盘
- 外部订单同步状态
- 物流异常列表
- 人工 fallback 待处理队列

## E2. 商品策略可视化

新增页面或模块：

- Bundle 候选机会列表
- Bundle 审批与转化
- 跟卖候选列表
- 跟卖合规风险面板

## E3. 审批与回滚

对于高风险操作必须纳入现有控制平面：

- 高金额采购提交
- 跟卖加入现有 listing
- 高风险 bundle 发布

---

## 8. 推荐实施顺序

### 第一阶段：外部采购主通道与采购闭环

先做：

1. 1688 官方开放平台调研与能力映射
2. `ProcurementExecutionProvider` 抽象
3. `ManualProcurementProvider`
4. `SupplierInquiry` 模型与 `InquiryService`
5. `PurchaseOrder` 外部执行字段与同步能力
6. 后台同步任务

原因：

- 当前 Deyes 在采购执行链路上的缺口最直接
- 该能力一旦打通，会立刻把采购从“内部状态流转”升级为“真实执行闭环”

### 第二阶段：Bundle 能力

随后做：

1. Bundle 数据模型
2. 规则版 BundleDiscoveryService
3. Bundle 定价与库存策略
4. AI 版 BundleDiscoveryAgent
5. Bundle 发布链路

原因：

- Bundle 更符合 Deyes 的差异化经营能力
- 比跟卖更贴合“自有经营决策 + 供应链整合”方向

### 第三阶段：listing strategy 扩展与跟卖

最后做：

1. listing_strategy 抽象
2. 平台能力矩阵
3. 跟卖候选发现
4. 一致性与合规检查
5. join existing listing adapter 支持

原因：

- 跟卖平台依赖性更强
- 风控和合规复杂度更高
- 当前不是所有目标平台都需要此能力

### 第四阶段：AlphaShop 可选增强

仅在以下条件满足时再做：

- AlphaShop 发布正式 API
- 有明确鉴权和限流说明
- 能覆盖某一项能力且优于现有接入

优先考虑接入的位置：

1. 图片翻译增强
2. 供应商图搜增强
3. 市场情报增强

不优先考虑：

- AlphaShop 采购执行主通道

---

## 9. 文件改动建议清单

### 9.1 建议新增文件

```text
backend/app/
├── clients/
│   ├── alibaba_1688_open.py
│   └── alphashop.py                  # 仅未来可选
├── services/
│   ├── inquiry_service.py
│   ├── procurement_execution_router.py
│   ├── supplier_discovery_router.py
│   ├── market_intel_router.py
│   ├── bundle_discovery_service.py
│   └── providers/
│       ├── base_procurement_provider.py
│       ├── alibaba_1688_procurement_provider.py
│       ├── manual_procurement_provider.py
│       ├── base_supplier_discovery_provider.py
│       ├── base_market_intel_provider.py
│       ├── alphashop_supplier_provider.py      # 未来可选
│       └── alphashop_market_intel_provider.py  # 未来可选
├── agents/
│   └── bundle_discovery.py
└── workers/
    ├── tasks_inquiry_sync.py
    └── tasks_procurement_sync.py
```

### 9.2 建议扩展的现有文件

- `backend/app/services/procurement_service.py`
- `backend/app/services/supplier_matcher.py`
- `backend/app/services/demand_validator.py`
- `backend/app/services/unified_listing_service.py`
- `backend/app/agents/platform_publisher.py`
- `backend/app/db/models.py`
- `backend/app/core/config.py`
- `backend/app/services/pricing_service.py`
- `backend/app/services/inventory_allocator.py`

### 9.3 建议新增测试文件

- `backend/tests/test_1688_open_client.py`
- `backend/tests/test_inquiry_service.py`
- `backend/tests/test_procurement_execution_router.py`
- `backend/tests/test_1688_procurement_provider.py`
- `backend/tests/test_supplier_discovery_multisource.py`
- `backend/tests/test_bundle_discovery_service.py`
- `backend/tests/test_bundle_discovery_agent.py`
- `backend/tests/test_bundle_inventory_pricing.py`
- `backend/tests/test_listing_strategy_follow_sell.py`

---

## 10. 测试计划

### 10.1 单元测试

覆盖：

- provider payload 构造
- provider 响应映射
- 路由逻辑
- 状态机转换
- Bundle 规则匹配
- 跟卖合规判定

### 10.2 集成测试

覆盖：

- 询盘创建 → 发送 → 同步 → 转报价
- PO 创建 → 外部提交 → 状态同步 → 到货入库
- Bundle 候选发现 → 转正式 bundle → 发布
- 跟卖候选发现 → 合规校验 → 加入 listing

### 10.3 回归测试

必须保证不破坏：

- 现有采购本地流程
- 现有库存收货流程
- 现有 supplier matcher 抽取逻辑
- 现有 create listing 流程
- 现有 operations console

---

## 11. 风险与边界

### 11.1 外部集成风险

- 1688 官方开放平台接入门槛可能较高
- AlphaShop 可能长期不开放正式 API
- 外部平台规则变更会影响 provider 稳定性

### 11.2 商品策略风险

- Bundle 需要解决库存扣减与价格计算一致性
- 跟卖涉及品牌授权、灰色跟卖与投诉风险

### 11.3 工程边界

当前阶段不建议：

- 用浏览器自动化把 AlphaShop 做成核心生产通道
- 让 AlphaShop 替代 Deyes 的最终利润/风险/经营决策
- 在没有 `listing_strategy` 抽象前硬编码跟卖逻辑
- 在没有 bundle 数据模型前，用临时字段拼装组合 SKU

---

## 12. 最终推荐路线

### 推荐路线一句话总结

**Deyes 保持经营决策内核，优先接入 1688 官方开放平台补齐真实采购执行，再建设 Bundle 能力，最后扩展跟卖策略；AlphaShop 仅保留为人工辅助与未来可选增强。**

### 最终优先级

1. **1688 官方开放平台 + Deyes 采购执行抽象层**
2. **SupplierInquiry / PO 外部执行 / 同步闭环**
3. **Bundle 数据模型与规则版组合发现**
4. **Bundle AI 化与发布链路**
5. **listing_strategy 抽象与跟卖能力**
6. **AlphaShop 可选增强能力**

---

## 13. 与现有文档的关系

本文件建议作为本轮讨论的**主开发计划文档**使用。

相关辅助文档：

- `docs/architecture/alphashop-integration-plan.md`
  - 早期 AlphaShop 整合方案，保留其抽象层设计价值
- `docs/architecture/alphashop-phase0-verification.md`
  - AlphaShop 可接入性验证依据
- `docs/architecture/session-2026-03-30-summary.md`
  - 本轮讨论摘要

若后续进入实施阶段，建议优先以本文件为主，再回看上述文档中的局部细节。

---

## 14. 后续执行建议

如果下一步继续推进，建议按以下动作开始：

1. 产出 1688 官方开放平台能力映射文档
2. 设计 `ProcurementExecutionProvider` 与 `ManualProcurementProvider`
3. 设计 `SupplierInquiry` 模型与 migration
4. 设计 `PurchaseOrder` 外部执行字段
5. 产出 Bundle 数据模型设计稿
6. 定义 `listing_strategy` 枚举与扩展方案

---

**备注**：
本文件为统一开发计划，不代表所有能力应同时开工。应严格按优先级推进，并在每个阶段先验证外部依赖的真实性、合规性与可维护性。