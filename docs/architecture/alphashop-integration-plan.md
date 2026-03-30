# AlphaShop 与外部产品整合方案

**日期**: 2026-03-30
**状态**: 分析完成，待可接入性验证
**目的**: 将本次关于 AlphaShop、供应商匹配、采购执行、选品增强的结论沉淀为可持续执行的设计文档，避免后续上下文丢失。

---

## 1. 结论摘要

### 1.1 总结结论

AlphaShop 不应替代 Deyes，而应作为 **外部能力层** 的一个节点接入系统。

推荐定位：

- **Deyes 保留**：经营决策内核
  - 选品最终判定
  - 利润/税费/风险/平台策略
  - 生命周期与运营控制平面
  - 审批、回滚、人工覆盖
- **AlphaShop 提供**：外部执行与情报能力
  - 供应商发现 / 图搜找货
  - 询盘自动化
  - 下单执行
  - 订单状态同步
  - 图片翻译 / 素材处理
  - MCP 工具接入（榜单、图搜、查询类工具）

### 1.2 优先级结论

按业务价值和现有系统短板，推荐接入顺序如下：

1. **采购执行层**：询盘、下单、订单状态同步
2. **供应商发现层**：供应商候选召回、图搜找货
3. **需求情报增强层**：榜单、趋势、竞品信号
4. **本地化增强层**：图片翻译、营销图处理
5. **MCP 工具层**：作为 Agent 的查询工具

### 1.3 最关键判断

- **选品能力**：AlphaShop 可能增强“市场情报/候选召回”，但不应替代 Deyes 的最终选品决策。
- **供应商匹配**：AlphaShop 大概率能显著增强当前 Deyes 的供应商召回与图搜能力。
- **采购链路**：AlphaShop 的询盘/下单能力最适合率先整合，因为 Deyes 当前采购体系已有骨架，但缺真实执行通道。

---

## 2. Deyes 当前能力与短板

## 2.1 当前已有能力

### 采购与库存

- `backend/app/services/procurement_service.py`
  - `create_purchase_order()`：创建采购单
  - `submit_purchase_order()`：内部提交状态流转
  - `confirm_purchase_order()`：内部确认状态流转
- `backend/app/services/inventory_allocator.py`
  - 入库、出库、调整、预占、收货处理
- `backend/app/db/models.py`
  - `Supplier`
  - `SupplierOffer`
  - `PurchaseOrder`
  - `PurchaseOrderItem`
  - `InboundShipment`

### 选品与供应商匹配

- `backend/app/agents/product_selector.py`
  - 需求优先的选品流程
- `backend/app/services/demand_validator.py`
  - 搜索量、趋势、竞争密度验证
- `backend/app/services/product_scoring_service.py`
  - 优先级排序（季节性 / 销量 / 评分 / 竞争）
- `backend/app/services/supplier_matcher.py`
  - 当前供应商匹配/提取逻辑

## 2.2 当前核心短板

### A. 需求验证框架正确，但外部信号强度不足

`DemandValidator` 当前主要依赖：

- Google Trends / pytrends
- Helium 10（可选）
- 启发式竞争密度估算

问题：

- 搜索量在部分情况下是估算值，不是强真实值
- 竞争密度很多时候是启发式近似
- 没有更强的平台侧榜单/竞品/评论信号融合

### B. 供应商匹配是最大短板之一

`SupplierMatcherService` 当前更像“结果提取器”，不是强供应商召回引擎：

- 优先使用上游 adapter 已给出的 supplier_candidates
- 再从 raw payload 提取字段
- 否则 fallback

这意味着：

- 没有真正的主动供应商发现
- 没有图搜找货能力
- 没有强排序模型
- 在缺失真实数据时能力较弱

### C. 采购链路缺真实执行通道

当前 `ProcurementService` 的“提交采购单”，本质还是内部状态流转。

缺口：

- 没有批量询盘能力
- 没有供应商回复同步
- 没有真正的外部下单能力
- 没有订单状态同步
- 没有物流状态回流
- 没有采购执行闭环反馈

这正是 AlphaShop 最可能补上的位置。

---

## 3. AlphaShop 的最佳定位

## 3.1 不应承担的职责

AlphaShop **不应承担**：

- 最终选品决策
- 最终利润判断
- 平台税费与风险判定
- 生命周期与运营控制逻辑
- 审批/回滚 source-of-truth

这些必须保留在 Deyes 内部。

## 3.2 最适合承担的职责

### 1) 采购执行层

- 发送询盘
- 追踪询盘状态
- 在 1688 下单
- 拉取订单状态
- 拉取物流状态

### 2) 供应商发现层

- 供应商候选召回
- 图搜找货
- 近似供应商发现
- 1688 生态数据补充

### 3) 需求情报增强层

- 榜单热度
- 类目机会
- 竞品信号
- 平台趋势辅助

### 4) 本地化增强层

- 图片翻译
- 素材处理
- 高质量营销图增强

### 5) MCP 工具层

适合作为 Agent 的“读型工具”：

- 榜单查询
- 图搜查询
- 规则/文档查询
- 外部工具调用

不适合作为“关键写操作”通道。

---

## 4. 与采购体系的结合方式

## 4.1 核心原则

### 原则一：Deyes 决策，AlphaShop 执行

- Deyes 决定：
  - 采购什么
  - 向谁采购
  - 采购多少
  - 是否审批通过
- AlphaShop 执行：
  - 发询盘
  - 下订单
  - 拉状态
  - 拉物流

### 原则二：Deyes 保留主记录

所有关键采购实体和状态仍然存储在 Deyes：

- 询盘记录
- 正式报价
- 采购单
- 外部订单 ID
- 同步时间
- 物流状态
- 回传 payload

### 原则三：必须支持多通道

不能把采购链路绑定为单通道 AlphaShop。

建议支持：

- `alphashop`
- `direct_1688`
- `manual`

---

## 5. 推荐架构设计

## 5.1 新增抽象层

### A. `SupplierDiscoveryProvider`

作用：统一供应商发现接口。

候选 provider：

- AlphaShopProvider
- Alibaba1688Provider
- ImageSearchProvider
- InternalSupplierHistoryProvider

### B. `MarketIntelProvider`

作用：统一需求/市场情报接口。

候选 provider：

- Helium10Provider
- AlphaShopIntelProvider
- MarketplaceSearchProvider
- InternalPerformanceProvider

### C. `ProcurementExecutionProvider`

作用：统一采购执行接口。

候选 provider：

- AlphaShopProcurementProvider
- Direct1688ProcurementProvider
- ManualProcurementProvider

---

## 5.2 采购执行层建议接口

建议接口定义如下：

- `send_inquiry(...)`
- `get_inquiry_status(...)`
- `create_order(...)`
- `get_order_status(...)`
- `cancel_order(...)`

由 `ProcurementExecutionRouter` 按规则路由到具体 provider。

---

## 5.3 推荐路由原则

路由可基于：

- 供应商是否支持 AlphaShop
- 订单金额
- 紧急程度
- 供应商历史稳定性
- 外部通道可用性

参考策略：

1. 支持 AlphaShop 且风险低的订单：优先 `alphashop`
2. 高金额/高风险订单：优先 `manual`
3. AlphaShop 不可用：回退 `direct_1688` 或 `manual`

---

## 6. 数据模型扩展建议

## 6.1 新增 `SupplierInquiry`

建议新增询盘实体，字段至少包括：

- `variant_id`
- `supplier_id`
- `quantity`
- `target_price`
- `required_delivery_date`
- `status`
- `execution_provider`
- `external_inquiry_id`
- `supplier_response`
- `quoted_price`
- `quoted_moq`
- `quoted_lead_time_days`
- `sent_at`
- `replied_at`
- `expires_at`

用途：

- 追踪询盘生命周期
- 同步供应商回复
- 将回复沉淀为 `SupplierOffer`

## 6.2 扩展 `PurchaseOrder`

建议在 `backend/app/db/models.py` 的 `PurchaseOrder` 上新增：

- `execution_provider`
- `external_order_id`
- `external_order_url`
- `tracking_number`
- `logistics_provider`
- `logistics_status`
- `last_synced_at`

用途：

- 记录外部订单关系
- 跟踪物流状态
- 追踪外部同步时间

---

## 7. 目标业务流程

### 7.1 供应商发现与询盘

1. Deyes 识别某 SKU 存在采购需求
2. `SupplierDiscoveryProvider` 召回候选供应商
3. Deyes 内部重排与筛选
4. 创建 `SupplierInquiry`
5. 通过 AlphaShop 批量发送询盘
6. 定时同步回复
7. 将回复转为 `SupplierOffer`

### 7.2 报价评估与采购单创建

1. Deyes 比较多个报价
2. 结合价格、MOQ、交期、历史表现做决策
3. 创建 `PurchaseOrder`
4. 审批通过后进入执行

### 7.3 下单执行与状态同步

1. `ProcurementExecutionRouter` 选择执行通道
2. AlphaShop 在外部执行下单
3. Deyes 记录 `external_order_id`
4. 定时同步订单状态
5. 同步物流信息
6. 到货后触发入库

### 7.4 入库与反馈闭环

1. `InventoryAllocator.receive_inbound_shipment()` 收货
2. 更新库存与入库记录
3. 记录供应商实际表现：
   - 回复率
   - 回复时效
   - 交期准确率
   - 质量问题
4. 反哺后续供应商排序与采购决策

---

## 8. 开发计划

## Phase 0：AlphaShop 可接入性验证

### 目标
确认 AlphaShop 是否具备可稳定接入的正式能力。

### 要验证的问题

1. 是否有官方 API，而不仅是页面功能
2. 鉴权方式是什么
3. 是否支持：
   - 创建询盘
   - 查询询盘状态
   - 创建订单
   - 查询订单状态
   - 查询物流状态
4. 是否支持 webhook / callback
5. 是否支持幂等
6. 是否有测试环境 / 沙箱能力

### 结果判断

- **A 档**：有正式 API，可进入正式集成
- **B 档**：仅有 UI / 非正式接口，只能作为弱执行通道或浏览器自动化通道

### 产出

- AlphaShop 接口清单
- 鉴权与限制说明
- 最小 POC：一次询盘、一次下单、一次状态同步

---

## Phase 1：采购执行抽象层

### 目标
建立 `ProcurementExecutionProvider` 抽象，不把业务代码绑死在 AlphaShop。

### 建议新增文件

- `backend/app/clients/alphashop.py`
- `backend/app/services/procurement_execution_router.py`
- `backend/app/services/providers/base_procurement_provider.py`
- `backend/app/services/providers/alphashop_procurement_provider.py`

### 涉及现有文件

- `backend/app/services/procurement_service.py`
- `backend/app/db/models.py`

### 验收标准

- 采购提交流程不依赖 конкрет provider
- 可按规则路由到 `alphashop` / `manual`
- provider 失败时可回退

---

## Phase 2：询盘能力接入

### 目标
让 Deyes 能自动化批量询盘，并把回复沉淀为报价。

### 建议新增文件

- `backend/app/services/inquiry_service.py`
- 对应 migration
- 对应测试文件

### 关键能力

- 创建询盘记录
- 通过 AlphaShop 发送询盘
- 定时同步回复
- 将回复转换为 `SupplierOffer`

### 验收标准

- 支持一对多询盘
- 支持状态同步
- 支持从回复生成正式报价

---

## Phase 3：PO 下单与状态同步

### 目标
让 Deyes 的 PO 能真正提交到外部，并同步真实订单状态。

### 需要扩展

- `PurchaseOrder` 外部执行字段
- `submit_purchase_order_via_provider(...)`
- `sync_purchase_order_status(...)`

### 对接库存

- 与 `InventoryAllocator.receive_inbound_shipment()` 串联

### 验收标准

- 已审批 PO 可提交到外部
- 能记录外部订单号
- 能同步状态与物流信息

---

## Phase 4：供应商闭环评分

### 目标
让采购结果反哺供应商选择。

### 需要追踪的指标

- 询盘回复率
- 回复时效
- 报价稳定性
- MOQ 适配度
- 承诺交期 vs 实际交期
- 质量问题率
- 售后/争议率

### 影响范围

- `SupplierMatcherService`
- 后续可影响 `ProductScoringService`

### 验收标准

- 供应商具备历史表现评分
- 后续召回排序使用该评分

---

## Phase 5：需求情报增强

### 目标
把 AlphaShop 用作证据来源，而不是最终判断者。

### 插入点

- `backend/app/services/demand_validator.py`
- `backend/app/agents/product_selector.py`

### 正确方式

由 AlphaShop 提供：

- 榜单热度
- 图搜找货密度
- 类目机会
- 竞品信号

再由 Deyes 结合：

- 利润
- 风险
- 平台策略
- 历史经营反馈

做最终判定。

---

## Phase 6：运营控制平面接入

### 目标
把采购执行纳入 Operations Console。

### 推荐可视化对象

- 待回复询盘
- 待确认订单
- 长时间未同步订单
- 异常物流
- 采购失败重试队列

这样采购链路就能进入现有运营控制平面，而不是独立黑盒。

---

## 9. 首期 MVP 范围

建议第一轮只做以下 4 项：

1. **AlphaShop 可接入性验证**
2. **SupplierInquiry 模型 + InquiryService**
3. **PurchaseOrder 外部执行字段 + submit/sync**
4. **Manual fallback 通道**

完成后，Deyes 将从“有采购骨架”升级为“具备真实询盘、下单、状态同步能力的采购系统”。

---

## 10. 关键文件清单

### 现有可能修改的文件

- `backend/app/services/procurement_service.py`
- `backend/app/services/inventory_allocator.py`
- `backend/app/services/supplier_matcher.py`
- `backend/app/services/demand_validator.py`
- `backend/app/db/models.py`

### 建议新增的文件

- `backend/app/clients/alphashop.py`
- `backend/app/services/inquiry_service.py`
- `backend/app/services/procurement_execution_router.py`
- `backend/app/services/providers/base_procurement_provider.py`
- `backend/app/services/providers/alphashop_procurement_provider.py`
- migration 文件
- 测试文件：
  - `backend/tests/test_inquiry_service.py`
  - `backend/tests/test_procurement_alphashop_integration.py`

---

## 11. 风险与边界

### 风险

1. AlphaShop 可能没有正式开放 API
2. 外部通道可能存在稳定性问题
3. 成本可能高于预期
4. 供应商覆盖范围可能有限
5. 订单/物流同步可能存在延迟

### 缓解措施

- 保留 `manual` 通道
- 保留未来 `direct_1688` 通道
- 不将 AlphaShop 作为唯一 source-of-truth
- 所有关键状态保留在 Deyes 内部
- 对执行动作做审计、重试、超时控制

### 非目标

当前阶段不建议：

- 让 AlphaShop 替代 Deyes 的最终选品决策
- 让 AlphaShop 接管利润/风险/平台策略逻辑
- 将采购链路完全绑定为 AlphaShop 单通道
- 让 MCP 直接承载关键写操作

---

## 12. 推荐策略（最终落地）

### 最佳策略

**Deyes = 决策与经营内核**
**AlphaShop = 采购/供应商/图搜/本地化的外部能力插件**

### 最推荐路径

- 先接采购执行层
- 再接供应商发现层
- 再做需求情报增强
- 最后再考虑图片翻译与 MCP 工具扩展

### 关键原则

- 多源情报
- 自主决策
- 多通道执行
- 内部主记录
- 可审计可回退

---

## 13. 后续继续推进时的优先阅读清单

后续如继续推进 AlphaShop 整合，建议优先阅读：

1. 本文档：`docs/architecture/alphashop-integration-plan.md`
2. `backend/app/services/procurement_service.py`
3. `backend/app/services/inventory_allocator.py`
4. `backend/app/services/supplier_matcher.py`
5. `backend/app/services/demand_validator.py`
6. `backend/app/agents/product_selector.py`
7. `backend/app/db/models.py`

---

## 14. 当前建议动作

如果下一步继续实施，建议先做：

1. AlphaShop API / 文档可接入性验证
2. 设计 `ProcurementExecutionProvider` 抽象
3. 设计 `SupplierInquiry` 数据模型与 migration
4. 定义最小询盘与下单 POC

---

## 15. 工程化接口与类设计

本节将上述方案进一步细化为可落地的工程设计，便于后续直接进入编码。

### 15.1 推荐目录结构

建议新增或扩展以下目录：

```text
backend/app/
├── clients/
│   └── alphashop.py
├── services/
│   ├── inquiry_service.py
│   ├── procurement_execution_router.py
│   ├── supplier_discovery_router.py
│   ├── market_intel_router.py
│   └── providers/
│       ├── base_procurement_provider.py
│       ├── alphashop_procurement_provider.py
│       ├── manual_procurement_provider.py
│       ├── base_supplier_discovery_provider.py
│       ├── alphashop_supplier_provider.py
│       ├── base_market_intel_provider.py
│       └── alphashop_market_intel_provider.py
└── workers/
    ├── tasks_procurement_sync.py
    └── tasks_inquiry_sync.py
```

说明：

- `clients/alphashop.py`：只负责 HTTP / 鉴权 / 请求签名 / 响应解析
- `services/providers/*`：做 provider 级别的语义封装
- `*_router.py`：负责多 provider 路由
- `inquiry_service.py` / `procurement_service.py`：负责业务层编排
- `workers/tasks_*`：负责定时同步

---

### 15.2 AlphaShop Client 设计

建议文件：`backend/app/clients/alphashop.py`

职责：

- 鉴权
- 请求发送
- 超时与重试
- 原始响应解析
- 错误标准化

建议接口：

```python
class AlphaShopClient:
    async def send_inquiry(self, payload: dict) -> dict: ...
    async def get_inquiry(self, inquiry_id: str) -> dict: ...
    async def create_order(self, payload: dict) -> dict: ...
    async def get_order(self, order_id: str) -> dict: ...
    async def cancel_order(self, order_id: str) -> dict: ...
    async def search_suppliers(self, payload: dict) -> dict: ...
    async def image_search_suppliers(self, payload: dict) -> dict: ...
    async def get_market_signals(self, payload: dict) -> dict: ...
```

设计原则：

- 不在 client 中掺杂业务判断
- 所有响应保留 `raw_payload`
- 所有异常统一转为内部 `ProviderError` / `RetryableProviderError`
- 与现有 client 风格保持一致，参考：
  - `backend/app/clients/helium10.py`
  - `backend/app/clients/platform_api_base.py`

---

### 15.3 ProcurementExecutionProvider 抽象

建议文件：`backend/app/services/providers/base_procurement_provider.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class InquiryRequest:
    supplier_external_id: str
    variant_id: str
    quantity: int
    target_price: Optional[float] = None
    required_delivery_date: Optional[str] = None
    notes: Optional[str] = None

@dataclass
class InquirySyncResult:
    external_inquiry_id: str
    status: str
    quoted_price: Optional[float] = None
    quoted_currency: Optional[str] = None
    quoted_moq: Optional[int] = None
    quoted_lead_time_days: Optional[int] = None
    supplier_response: Optional[dict] = None
    raw_payload: Optional[dict] = None

@dataclass
class OrderRequest:
    supplier_external_id: str
    po_number: str
    currency: str
    items: list[dict]
    notes: Optional[str] = None

@dataclass
class OrderSyncResult:
    external_order_id: str
    status: str
    tracking_number: Optional[str] = None
    logistics_provider: Optional[str] = None
    logistics_status: Optional[str] = None
    raw_payload: Optional[dict] = None

class ProcurementExecutionProvider(ABC):
    provider_name: str

    @abstractmethod
    async def send_inquiry(self, request: InquiryRequest) -> InquirySyncResult: ...

    @abstractmethod
    async def get_inquiry_status(self, external_inquiry_id: str) -> InquirySyncResult: ...

    @abstractmethod
    async def create_order(self, request: OrderRequest) -> OrderSyncResult: ...

    @abstractmethod
    async def get_order_status(self, external_order_id: str) -> OrderSyncResult: ...

    @abstractmethod
    async def cancel_order(self, external_order_id: str) -> OrderSyncResult: ...
```

好处：

- 便于后续加 `direct_1688` / `manual`
- 业务服务层不依赖 AlphaShop 私有字段
- 测试时可直接 mock provider，不必 mock HTTP

---

### 15.4 AlphaShop Procurement Provider

建议文件：`backend/app/services/providers/alphashop_procurement_provider.py`

职责：

- 将内部标准请求转换为 AlphaShop API payload
- 将 AlphaShop 返回映射为内部标准结果

建议接口实现：

```python
class AlphaShopProcurementProvider(ProcurementExecutionProvider):
    provider_name = "alphashop"

    def __init__(self, client: AlphaShopClient):
        self.client = client

    async def send_inquiry(self, request: InquiryRequest) -> InquirySyncResult: ...
    async def get_inquiry_status(self, external_inquiry_id: str) -> InquirySyncResult: ...
    async def create_order(self, request: OrderRequest) -> OrderSyncResult: ...
    async def get_order_status(self, external_order_id: str) -> OrderSyncResult: ...
    async def cancel_order(self, external_order_id: str) -> OrderSyncResult: ...
```

映射建议：

- AlphaShop 侧原始状态必须保留到 `raw_payload`
- 内部只暴露统一状态枚举，避免业务层理解多套状态机

---

### 15.5 Manual Procurement Provider

建议文件：`backend/app/services/providers/manual_procurement_provider.py`

职责：

- 作为可靠 fallback
- 不调用任何外部 API
- 生成“待人工执行”的标准结果

建议行为：

- `send_inquiry()`：创建待人工处理状态，返回 `status="pending_manual_action"`
- `create_order()`：创建待人工下单状态，返回 `status="pending_manual_action"`
- `get_*_status()`：从本地状态记录读取，避免空实现

这样即使 AlphaShop 不可用，采购流程仍可继续闭环。

---

### 15.6 ProcurementExecutionRouter 设计

建议文件：`backend/app/services/procurement_execution_router.py`

职责：

- 根据规则选择 provider
- 封装 provider fallback

建议接口：

```python
class ProcurementExecutionRouter:
    def __init__(self, providers: dict[str, ProcurementExecutionProvider]):
        self.providers = providers

    def get_provider(self, provider_name: str) -> ProcurementExecutionProvider: ...

    def select_provider(
        self,
        supplier: Supplier,
        po: PurchaseOrder | None = None,
        preferred_provider: str | None = None,
    ) -> ProcurementExecutionProvider: ...
```

推荐路由规则：

1. 若显式指定 `preferred_provider`，优先使用
2. 若供应商 `metadata` 标记 `alphashop_enabled=true`，优先 AlphaShop
3. 若订单金额超过阈值，走 `manual`
4. 若 AlphaShop 不可用，回退到 `manual`

---

### 15.7 InquiryService 设计

建议文件：`backend/app/services/inquiry_service.py`

职责：

- 创建询盘记录
- 发送询盘
- 同步回复
- 将回复转为正式报价

建议方法：

```python
class InquiryService:
    async def create_inquiry(...): ...
    async def send_inquiry(...): ...
    async def sync_inquiry(...): ...
    async def sync_pending_inquiries(...): ...
    async def convert_inquiry_to_offer(...): ...
```

关键约束：

- 同一 `variant_id + supplier_id + active status` 避免重复询盘
- 同步回复时要幂等
- 仅在回复状态满足条件时才能转为 `SupplierOffer`

建议状态：

- `draft`
- `sent`
- `replied`
- `expired`
- `cancelled`
- `failed`

---

### 15.8 ProcurementService 扩展设计

现有文件：`backend/app/services/procurement_service.py`

建议新增方法：

```python
class ProcurementService:
    async def submit_purchase_order_via_provider(
        self,
        db: AsyncSession,
        po_id: UUID,
        provider_name: str | None = None,
    ) -> POResult: ...

    async def sync_purchase_order_status(
        self,
        db: AsyncSession,
        po_id: UUID,
    ) -> POResult: ...

    async def sync_submitted_purchase_orders(
        self,
        db: AsyncSession,
        limit: int = 100,
    ) -> list[POResult]: ...
```

迁移思路：

- 保留现有 `submit_purchase_order()` 作为内部状态流转入口，避免立即破坏兼容性
- 新增 `submit_purchase_order_via_provider()` 作为外部执行路径
- 后续逐步将调用方切到新入口

---

### 15.9 SupplierDiscoveryProvider 抽象

建议文件：`backend/app/services/providers/base_supplier_discovery_provider.py`

目标：增强 `SupplierMatcherService`，从提取型逻辑进化为多源召回 + 内部重排。

建议标准结果：

```python
@dataclass
class SupplierDiscoveryCandidate:
    supplier_name: str
    supplier_url: str
    supplier_external_id: str | None
    supplier_price: Decimal | None
    currency: str | None
    moq: int | None
    lead_time_days: int | None
    confidence_score: Decimal
    raw_payload: dict
```

然后由 `SupplierMatcherService` 完成：

- 去重
- 标准化
- 与内部 `Supplier` / `SupplierOffer` 对齐
- 历史表现重排

---

### 15.10 MarketIntelProvider 抽象

建议文件：`backend/app/services/providers/base_market_intel_provider.py`

目标：增强 `DemandValidator`，但不替代其最终判断权。

建议标准结果：

```python
@dataclass
class MarketSignal:
    keyword: str
    region: str | None
    platform: str | None
    demand_score: float | None
    competition_score: float | None
    trend_score: float | None
    review_sentiment_score: float | None
    source_name: str
    source_confidence: float
    raw_payload: dict
```

使用原则：

- 只作为证据层
- 最终 passed/rejected 仍由 `DemandValidator` 内部规则输出

---

## 16. 数据模型细化建议

### 16.1 `SupplierInquiry` 推荐字段

建议新增模型：

```python
class SupplierInquiry(Base, UpdateTimestampMixin):
    id: UUID
    supplier_id: UUID
    variant_id: UUID
    quantity: int
    target_price: Decimal | None
    required_delivery_date: datetime | None
    status: InquiryStatus
    execution_provider: str | None
    external_inquiry_id: str | None
    quoted_price: Decimal | None
    quoted_currency: str | None
    quoted_moq: int | None
    quoted_lead_time_days: int | None
    supplier_response: dict | None
    raw_payload: dict | None
    sent_at: datetime | None
    replied_at: datetime | None
    expires_at: datetime | None
```

索引建议：

- `(supplier_id, variant_id, status)`
- `external_inquiry_id`
- `execution_provider`

---

### 16.2 `PurchaseOrder` 扩展字段

建议新增：

```python
execution_provider: str | None
external_order_id: str | None
external_order_url: str | None
tracking_number: str | None
logistics_provider: str | None
logistics_status: str | None
last_synced_at: datetime | None
raw_payload: dict | None
```

注意：

- 若已有 `metadata` 风格字段，可权衡是否部分进 `raw_payload`
- 但 `external_order_id` / `tracking_number` 应独立字段，便于查询与索引

---

## 17. 状态机建议

### 17.1 询盘状态机

```text
DRAFT -> SENT -> REPLIED -> CONVERTED_TO_OFFER
            └-> EXPIRED
            └-> FAILED
            └-> CANCELLED
```

### 17.2 采购单状态机（扩展后）

现有采购状态继续保留，同时增加外部同步语义：

```text
DRAFT -> SUBMITTED -> CONFIRMED -> RECEIVED
            └-> FAILED_EXTERNAL_SUBMISSION
            └-> CANCELLED
```

其中：

- `SUBMITTED`：本地已提交到执行通道
- `CONFIRMED`：外部订单已被供应商接受/确认
- `RECEIVED`：货物已到并入库

---

## 18. 配置项建议

建议在 `backend/app/core/config.py` 中新增：

```python
# AlphaShop
alphashop_base_url: str = ""
alphashop_api_key: str = ""
alphashop_timeout: int = 30
alphashop_max_retries: int = 3
alphashop_enabled: bool = False

# Procurement routing
procurement_default_provider: str = "manual"
procurement_enable_alphashop: bool = False
procurement_manual_threshold_amount: float = 10000.0
procurement_sync_batch_limit: int = 100

# Inquiry
inquiry_default_expiry_hours: int = 72
inquiry_sync_interval_minutes: int = 30
```

设计原则：

- 默认关闭 AlphaShop 能力，避免未配置时误触发
- 以 feature flag 方式逐步放量
- 为同步任务留出独立配置项

---

## 19. 后台任务建议

建议新增 worker 任务：

### 19.1 `tasks_inquiry_sync.py`

职责：

- 扫描 `sent` 状态的询盘
- 调用 provider 同步状态
- 更新回复内容
- 将合格回复转为报价（可选自动 / 人工触发）

### 19.2 `tasks_procurement_sync.py`

职责：

- 扫描 `submitted` 状态的 PO
- 调用 provider 同步订单状态
- 更新物流信息
- 对异常状态发出告警/事件

建议具备：

- 幂等执行
- 单批次处理上限
- 错误隔离
- 重试与死信记录

---

## 20. API 层建议

若后续要提供内部控制台能力，建议新增 API：

- `GET /procurement/inquiries`
- `POST /procurement/inquiries`
- `POST /procurement/inquiries/{id}/send`
- `POST /procurement/inquiries/{id}/sync`
- `POST /procurement/inquiries/{id}/convert-offer`
- `POST /procurement/purchase-orders/{id}/submit-external`
- `POST /procurement/purchase-orders/{id}/sync`

这些 API 适合后续接入 Operations Console。

---

## 21. 测试计划细化

### 21.1 单元测试

建议新增：

- `backend/tests/test_alphashop_client.py`
- `backend/tests/test_inquiry_service.py`
- `backend/tests/test_procurement_execution_router.py`
- `backend/tests/test_alphashop_procurement_provider.py`

覆盖点：

- payload 构造
- provider 结果映射
- 错误处理与重试
- 路由策略
- 状态机转换

### 21.2 集成测试

建议新增：

- `backend/tests/test_procurement_alphashop_integration.py`
- `backend/tests/test_supplier_discovery_multisource.py`

覆盖点：

- 询盘创建 -> 发送 -> 同步 -> 转 offer
- PO 提交 -> 外部状态同步 -> 入库
- AlphaShop 不可用 -> manual fallback

### 21.3 回归测试

必须确保不破坏现有：

- `ProcurementService` 的本地 PO 流程
- `InventoryAllocator` 的收货流程
- `SupplierMatcherService` 的现有提取逻辑

---

## 22. 分阶段落地顺序（工程版）

### Sprint A：抽象与可接入性验证

- 验证 AlphaShop 是否有正式 API
- 新增配置项
- 新增 `AlphaShopClient`
- 新增 `ProcurementExecutionProvider` 抽象
- 新增 `ManualProcurementProvider`

### Sprint B：询盘 MVP

- 新增 `SupplierInquiry` 模型与 migration
- 实现 `InquiryService`
- 实现 AlphaShop 询盘发送与状态同步
- 实现从回复生成 `SupplierOffer`

### Sprint C：PO 外部执行 MVP

- 扩展 `PurchaseOrder`
- 实现 `submit_purchase_order_via_provider()`
- 实现 `sync_purchase_order_status()`
- 打通到入库同步链路

### Sprint D：供应商发现增强

- 引入 `SupplierDiscoveryProvider`
- AlphaShop supplier recall 接入
- 与现有 `SupplierMatcherService` 结合重排

### Sprint E：需求情报增强

- 引入 `MarketIntelProvider`
- 将 AlphaShop 市场信号接入 `DemandValidator`

---

## 23. 编码时的约束与注意事项

1. 不要在业务服务层直接写 AlphaShop HTTP 调用
2. 所有外部写操作必须带审计日志
3. 所有同步任务必须幂等
4. 所有 provider 必须支持 graceful fallback
5. 所有 AlphaShop 返回的关键原始字段都要保留 `raw_payload`
6. 不要让 AlphaShop 私有状态直接泄露到核心业务层
7. 不要让未配置 AlphaShop 时影响现有系统运行

---

**备注**：
本文件用于沉淀本轮上下文中的关键分析结论与实施计划。后续如需进入编码阶段，应先依据 Phase 0 结果确认 AlphaShop 的真实 API 能力，再决定是走正式 API 集成，还是降级为浏览器自动化/人工辅助通道。
