# Stage 4 实施任务清单

> 基于研发路线图 Stage 4：订单、售后、利润台账
>
> 目标：把系统从“理论利润 + 平台表现反馈”升级为“真实订单、退款、费用、净利可追踪”的经营损益层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 📋 Stage 4 总览

### 核心目标
从“能围绕 SKU 建立商品与供应链事实层”升级为“能围绕订单与售后沉淀真实经营结果”。

### 关键交付物
1. PlatformOrder / PlatformOrderLine 订单中心
2. RefundCase / ReturnCase / AfterSaleIssue 售后中心
3. SettlementEntry / AdCostAllocation / ProfitLedger 利润台账
4. 订单导入、退款对账、净利计算服务
5. SKU / Listing / Supplier 维度真实利润聚合

### 预期成果
- 任意一个在售 SKU 都能追踪真实销售、退款、平台费用和净利
- 系统可以区分“上线前利润预估”和“上线后真实利润”
- 退款、售后、平台费不再只是噪音，而成为经营反馈事实来源
- Stage 2 反馈引擎可逐步从真实订单与利润台账中获得更稳定的数据基础

---

## 🎯 任务分组

### 分组 A：订单中心与订单导入（优先级 P0）
### 分组 B：售后中心与退款对账（优先级 P0）
### 分组 C：利润台账与成本归集（优先级 P0）
### 分组 D：经营聚合与服务接入（优先级 P1）
### 分组 E：测试与验证（优先级 P0）

---

## 分组 A：订单中心与订单导入

### A1. 设计 PlatformOrder 与 PlatformOrderLine Schema

**任务描述**：
建立最小订单中心，为平台订单、订单项、SKU 映射和后续利润计算提供统一事实层。

**具体工作**：
1. 设计 `PlatformOrder` 模型：
   - `id` (UUID, PK)
   - `platform`
   - `region`
   - `platform_order_id`
   - `order_status`
   - `currency`
   - `buyer_country`
   - `ordered_at`
   - `paid_at`
   - `shipped_at`
2. 设计 `PlatformOrderLine` 模型：
   - `platform_order_id` (FK)
   - `platform_listing_id` (nullable, FK)
   - `product_variant_id` (nullable, FK)
   - `platform_sku`
   - `quantity`
   - `unit_price`
   - `gross_revenue`
   - `discount_amount`
3. 建立 Order / OrderLine 与 SKU / Listing 的关联
4. 为 `platform + platform_order_id` 建立唯一约束

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_platform_orders.py`

**验收标准**：
- [ ] 订单与订单项模型定义完成
- [ ] 同一订单可包含多个 order line
- [ ] order line 可映射 SKU 与 listing
- [ ] migration 可成功执行

**预估工作量**：5-7 小时

---

### A2. 设计 FulfillmentRecord Schema

**任务描述**：
记录订单履约过程，区分下单、发货、签收等关键节点，为售后和利润核算提供依据。

**具体工作**：
1. 设计 `FulfillmentRecord`：
   - `id`
   - `platform_order_id`
   - `platform_order_line_id` (nullable)
   - `fulfillment_status`
   - `carrier`
   - `tracking_number`
   - `shipped_at`
   - `delivered_at`
2. 设计履约状态枚举
3. 明确 order / line / fulfillment 关系
4. 兼容单笔订单多包裹场景

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 修改：`backend/migrations/versions/00x_platform_orders.py`
- 修改：`backend/app/core/enums.py` 或相关枚举文件

**验收标准**：
- [ ] 履约记录可独立建模
- [ ] 发货 / 签收节点可追踪
- [ ] 可兼容多包裹或部分发货场景

**预估工作量**：3-5 小时

---

### A3. 实现 OrderIngestionService

**任务描述**：
创建订单导入服务，把平台订单、订单项和履约数据规范写入 ERP Lite 事实层。

**具体工作**：
1. 新增 `OrderIngestionService`
2. 实现方法：
   - `ingest_order(platform, payload)`
   - `ingest_order_lines(order_id, lines_payload)`
   - `ingest_fulfillment(order_id, fulfillment_payload)`
   - `get_order(order_id)`
3. 实现幂等写入规则
4. 补齐 order line 对 SKU / listing 的映射逻辑

**涉及文件**：
- 新增：`backend/app/services/order_ingestion_service.py`

**验收标准**：
- [ ] 可导入订单、订单项和履约记录
- [ ] 重复导入不会产生重复数据
- [ ] 可按平台订单号查询订单
- [ ] SKU / listing 映射逻辑稳定

**预估工作量**：6-8 小时

---

### A4. 增加订单导入与库存联动逻辑

**任务描述**：
在订单导入阶段联动库存服务，支持订单级 reservation 消耗与基础库存扣减。

**具体工作**：
1. 定义订单导入后对库存的影响规则
2. 与 `InventoryAllocator` 集成：
   - consume reservation
   - create reservation when needed
   - record outbound movement
3. 处理取消订单 / 拒付 / 退款时的库存恢复入口
4. 保持与 Stage 3 库存模型兼容

**涉及文件**：
- 修改：`backend/app/services/order_ingestion_service.py`
- 修改：`backend/app/services/inventory_allocator.py`

**验收标准**：
- [ ] 下单后库存事实层可联动
- [ ] 发货后有出库流水
- [ ] 取消 / 退款场景可预留恢复入口

**预估工作量**：5-7 小时

---

## 分组 B：售后中心与退款对账

### B1. 设计 RefundCase / ReturnCase / AfterSaleIssue Schema

**任务描述**：
建立售后中心，追踪退款、退货和售后问题，为真实净利和反馈引擎提供负向经营事实。

**具体工作**：
1. 设计 `RefundCase`：
   - `id`
   - `platform_order_id`
   - `platform_order_line_id` (nullable)
   - `refund_amount`
   - `currency`
   - `refund_reason`
   - `refund_status`
   - `requested_at`
   - `resolved_at`
2. 设计 `ReturnCase`：
   - `return_reason`
   - `return_status`
   - `received_at`
3. 设计 `AfterSaleIssue`：
   - issue_type
   - severity
   - status
   - resolution_note
4. 定义与 order / order line / SKU / listing 的关系

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_after_sales.py`

**验收标准**：
- [ ] 退款 / 退货 / 售后模型定义完成
- [ ] 可关联订单与订单项
- [ ] 退款原因和状态可持久化
- [ ] migration 可成功执行

**预估工作量**：5-7 小时

---

### B2. 实现 RefundAnalysisService

**任务描述**：
创建退款分析服务，统一处理退款写入、退款率查询和退款原因聚合。

**具体工作**：
1. 新增服务类
2. 实现方法：
   - `ingest_refund_case(payload)`
   - `get_refund_rate(product_variant_id=None, listing_id=None)`
   - `summarize_refund_reasons(...)`
   - `link_refund_to_profit_ledger(...)`
3. 聚合维度：
   - SKU
   - listing
   - platform
   - supplier
4. 处理部分退款与整单退款场景

**涉及文件**：
- 新增：`backend/app/services/refund_analysis_service.py`

**验收标准**：
- [ ] 可写入退款案件
- [ ] 可查询退款率
- [ ] 可按原因聚合退款
- [ ] 可与利润台账联动

**预估工作量**：5-7 小时

---

### B3. 实现售后问题分类与归因规则

**任务描述**：
建立最小售后问题分类规则，把售后问题归因到商品、供应商、履约或内容问题上。

**具体工作**：
1. 定义 issue_type 分类：
   - quality_issue
   - logistics_issue
   - mismatch_issue
   - damaged_issue
   - other
2. 增加基础归因规则：
   - 质量问题 -> supplier / sku
   - 物流问题 -> fulfillment / region
   - 描述不符 -> listing / content / expectation
3. 统一归因结果结构
4. 供反馈引擎与调试使用

**涉及文件**：
- 修改：`backend/app/services/refund_analysis_service.py` 或新增 `backend/app/services/after_sale_classification_service.py`

**验收标准**：
- [ ] 售后问题分类规则明确
- [ ] 常见退款原因可归到稳定类别
- [ ] 归因结果结构可复用

**预估工作量**：4-6 小时

---

## 分组 C：利润台账与成本归集

### C1. 设计 SettlementEntry / AdCostAllocation / ProfitLedger Schema

**任务描述**：
建立真实利润台账，把平台费用、退款损失、广告成本与订单收入聚合到统一损益层。

**具体工作**：
1. 设计 `SettlementEntry`：
   - `id`
   - `platform_order_id` (nullable)
   - `platform_order_line_id` (nullable)
   - `entry_type`
   - `amount`
   - `currency`
   - `occurred_at`
   - `source_payload`
2. 设计 `AdCostAllocation`：
   - `product_variant_id`
   - `platform_listing_id` (nullable)
   - `date`
   - `allocated_cost`
   - `allocation_basis`
3. 设计 `ProfitLedger`：
   - `product_variant_id`
   - `platform_order_line_id` (nullable)
   - `gross_revenue`
   - `refund_loss`
   - `platform_fee`
   - `ad_cost`
   - `fulfillment_cost`
   - `net_profit`
4. 定义 ledger 与 order / refund / settlement 的关系

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_profit_ledger.py`

**验收标准**：
- [ ] 利润台账模型定义完成
- [ ] 可表达收入、退款、费用、净利
- [ ] migration 可成功执行

**预估工作量**：5-7 小时

---

### C2. 实现 ProfitLedgerService

**任务描述**：
创建利润台账服务，负责把订单、退款、费用统一折算为真实净利记录。

**具体工作**：
1. 新增 `ProfitLedgerService`
2. 实现方法：
   - `build_order_profit_ledger(order_line_id)`
   - `apply_refund_adjustment(refund_case_id)`
   - `apply_settlement_entry(payload)`
   - `get_profit_snapshot(product_variant_id=None, listing_id=None)`
3. 区分理论利润与真实利润：
   - `PricingAssessment` = 上线前预估
   - `ProfitLedger` = 上线后真实净利
4. 支持重算机制

**涉及文件**：
- 新增：`backend/app/services/profit_ledger_service.py`

**验收标准**：
- [ ] 可生成 order line 级别利润台账
- [ ] 退款后净利可更新
- [ ] settlement entry 可计入净利
- [ ] 可查询利润快照

**预估工作量**：6-8 小时

---

### C3. 增加广告成本分摊规则

**任务描述**：
为利润台账提供最小可用的广告成本分摊规则，使净利不只停留在“扣平台费和退款”的层面。

**具体工作**：
1. 定义分摊策略：
   - 按 SKU
   - 按 listing
   - 按收入占比
   - 按曝光占比（可选）
2. 实现 `allocate_ad_cost(...)`
3. 输出结构化分摊明细
4. 保持规则简单可解释，不引入复杂归因模型

**涉及文件**：
- 修改：`backend/app/services/profit_ledger_service.py`

**验收标准**：
- [ ] 广告成本可写入台账
- [ ] 分摊规则明确且稳定
- [ ] 快照中能看到广告成本影响

**预估工作量**：4-6 小时

---

### C4. 建立 Supplier / Platform / Region 利润聚合接口

**任务描述**：
把单笔订单的真实损益聚合到供应商、平台、地区等经营维度，支持后续反馈与策略控制。

**具体工作**：
1. 实现聚合方法：
   - `get_supplier_profitability(supplier_id)`
   - `get_platform_profitability(platform, region=None)`
   - `get_listing_profitability(listing_id)`
2. 输出关键指标：
   - revenue
   - refund_loss
   - platform_fee
   - ad_cost
   - net_profit
   - profit_margin
3. 保持聚合口径可复现
4. 与 Stage 2 反馈引擎维度兼容

**涉及文件**：
- 修改：`backend/app/services/profit_ledger_service.py`

**验收标准**：
- [ ] 可按 supplier / platform / region 聚合真实利润
- [ ] 关键指标结构稳定
- [ ] 可供反馈与报表复用

**预估工作量**：4-6 小时

---

## 分组 D：经营聚合与服务接入

### D1. 实现经营结果快照查询服务

**任务描述**：
新增统一快照服务，输出 SKU / listing / supplier 的经营结果视图。

**具体工作**：
1. 新增 `OperatingMetricsService` 或扩展现有服务
2. 实现方法：
   - `get_sku_operating_snapshot(product_variant_id)`
   - `get_listing_operating_snapshot(listing_id)`
   - `get_supplier_operating_snapshot(supplier_id)`
3. 聚合内容包括：
   - orders
   - refunds
   - net_profit
   - current_inventory
   - inbound_quantity
4. 返回结构化只读快照

**涉及文件**：
- 新增：`backend/app/services/operating_metrics_service.py`

**验收标准**：
- [ ] SKU / listing / supplier 快照可查询
- [ ] 快照结构稳定
- [ ] 能汇总订单、退款、利润、库存信息

**预估工作量**：5-7 小时

---

### D2. 让 FeedbackAggregator 逐步消费真实损益事实

**任务描述**：
将 Stage 2 的反馈引擎逐步从平台表现和推断信号过渡到更真实的订单/退款/利润事实。

**具体工作**：
1. 审视 `FeedbackAggregator` 现有输入源
2. 增加可选消费：
   - `PlatformOrderLine`
   - `RefundCase`
   - `ProfitLedger`
3. 保持向后兼容：无真实订单数据时仍可 fallback 到 Stage 1-2 数据
4. 优先接入退款率和真实净利指标

**涉及文件**：
- 修改：`backend/app/services/feedback_aggregator.py`
- 可能修改：`backend/app/services/performance_aggregator_service.py`

**验收标准**：
- [ ] FeedbackAggregator 可消费真实损益事实
- [ ] 无订单数据时不影响旧路径
- [ ] 退款和真实净利可成为反馈信号

**预估工作量**：5-7 小时

---

### D3. 增加订单/售后/利润只读 API（可选）

**任务描述**：
提供最小只读 API，便于调试和后续运营可视化验证。

**具体工作**：
1. 设计只读路由：
   - `/orders/{order_id}`
   - `/profit/sku/{sku_id}`
   - `/refunds/{refund_id}`
2. 返回结构化快照
3. 确保不暴露敏感个人信息
4. 与现有 API 风格保持一致

**涉及文件**：
- 新增：`backend/app/api/routes_orders.py`
- 新增：`backend/app/api/routes_profit.py`
- 可能新增：`backend/app/api/routes_after_sales.py`

**验收标准**：
- [ ] 只读 API 可返回结构化数据
- [ ] 不暴露敏感信息
- [ ] 可在测试环境验证

**预估工作量**：5-7 小时

---

## 分组 E：测试与验证

### E1. 新增订单导入与履约测试

**任务描述**：
覆盖订单、订单项、履约导入的核心行为。

**具体工作**：
新增测试：
- `test_ingest_order_creates_platform_order`
- `test_ingest_order_lines_maps_to_listing_and_sku`
- `test_order_ingestion_is_idempotent`
- `test_ingest_fulfillment_updates_status`

**涉及文件**：
- 新增：`backend/tests/test_order_ingestion_service.py`

**验收标准**：
- [ ] 订单导入测试全部通过
- [ ] 幂等和映射逻辑被覆盖

**预估工作量**：4-6 小时

---

### E2. 新增退款与售后分析测试

**任务描述**：
验证退款案件写入、退款率聚合和售后问题分类逻辑。

**具体工作**：
新增测试：
- `test_ingest_refund_case_creates_refund_record`
- `test_get_refund_rate_by_sku_returns_expected_value`
- `test_partial_refund_is_supported`
- `test_after_sale_issue_classification_returns_expected_bucket`

**涉及文件**：
- 新增：`backend/tests/test_refund_analysis_service.py`

**验收标准**：
- [ ] 退款与售后测试全部通过
- [ ] 部分退款和分类场景被覆盖

**预估工作量**：4-6 小时

---

### E3. 新增利润台账测试

**任务描述**：
验证真实净利计算、退款调整、平台费与广告费分摊逻辑。

**具体工作**：
新增测试：
- `test_build_order_profit_ledger_returns_net_profit`
- `test_apply_refund_adjustment_reduces_net_profit`
- `test_apply_settlement_entry_updates_profit_snapshot`
- `test_ad_cost_allocation_is_reflected_in_profit_ledger`
- `test_get_supplier_profitability_aggregates_multiple_orders`

**涉及文件**：
- 新增：`backend/tests/test_profit_ledger_service.py`

**验收标准**：
- [ ] 利润台账测试全部通过
- [ ] 收入、退款、费用、净利边界被覆盖

**预估工作量**：5-7 小时

---

### E4. 新增经营快照与反馈兼容测试

**任务描述**：
验证经营快照服务与 FeedbackAggregator 对真实损益事实的兼容消费能力。

**具体工作**：
新增测试：
- `test_operating_metrics_service_returns_sku_snapshot`
- `test_operating_metrics_service_returns_supplier_snapshot`
- `test_feedback_aggregator_can_consume_profit_and_refund_facts`
- `test_stage4_does_not_break_stage2_feedback_paths`

**涉及文件**：
- 新增：`backend/tests/test_operating_metrics_service.py`
- 修改：`backend/tests/test_feedback_aggregator.py`

**验收标准**：
- [ ] 快照与反馈兼容测试全部通过
- [ ] Stage 2 旧逻辑不回退

**预估工作量**：5-7 小时

---

### E5. Stage 4 回归验证套件

**任务描述**：
建立 Stage 4 的回归命令与验证 checklist。

**建议命令**：
```bash
python -m pytest backend/tests/test_order_ingestion_service.py -v
python -m pytest backend/tests/test_refund_analysis_service.py -v
python -m pytest backend/tests/test_profit_ledger_service.py -v
python -m pytest backend/tests/test_operating_metrics_service.py -v
python -m pytest backend/tests/test_feedback_aggregator.py -v
python -m pytest backend/tests/test_phase1_mvp.py -v
```

**涉及文件**：
- 新增：`docs/roadmap/stage4-verification-checklist.md`

**验收标准**：
- [ ] 核心回归命令明确
- [ ] 手工验证 checklist 明确
- [ ] Stage 1-3 主链路不回退

**预估工作量**：2-3 小时

---

## 📊 任务优先级与依赖关系

### 第一批（并行）
- A1（PlatformOrder / OrderLine Schema）
- B1（Refund / Return / AfterSale Schema）
- C1（Settlement / AdCost / ProfitLedger Schema）

### 第二批（依赖第一批）
- A2（FulfillmentRecord）
- A3（OrderIngestionService）
- B2（RefundAnalysisService）
- C2（ProfitLedgerService）

### 第三批（依赖第二批）
- A4（订单与库存联动）
- B3（售后问题分类与归因）
- C3（广告成本分摊）
- C4（Supplier / Platform / Region 利润聚合）
- E1 / E2（订单与退款测试）

### 第四批（依赖第三批）
- D1（经营快照服务）
- D2（FeedbackAggregator 消费真实损益）
- D3（只读 API，可选）
- E3 / E4（利润与兼容测试）
- E5（回归验证）

---

## 📈 工作量估算

| 分组 | 任务数 | 预估总工时 | 建议人员 |
|------|--------|-----------|---------|
| A | 4 | 19-27h | 后端 |
| B | 3 | 14-20h | 后端 |
| C | 4 | 19-27h | 后端 |
| D | 3 | 15-21h | 后端 |
| E | 5 | 20-29h | 测试 + 后端 |
| **总计** | **19** | **87-124h** | **2 人** |

按 2 人并行投入，Stage 4 可作为从“ERP Lite 商品与供应链核心”升级到“真实经营损益层”的主开发包推进。

---

## ✅ Stage 4 退出标准

### 功能完整性
- [ ] `PlatformOrder` / `PlatformOrderLine` 已可导入和查询
- [ ] `RefundCase` / `ReturnCase` / `AfterSaleIssue` 已可导入和查询
- [ ] `SettlementEntry` / `ProfitLedger` 已可生成和查询
- [ ] SKU / listing / supplier 的真实净利可查询
- [ ] 退款与费用已进入真实经营事实层

### 经营真实性
- [ ] 系统可区分理论利润与真实净利
- [ ] 退款损失会显式影响净利
- [ ] 平台费用与广告费用可计入台账
- [ ] 订单、售后、利润链路可追溯

### 稳定性
- [ ] 订单导入具备幂等性
- [ ] 退款与利润重算逻辑稳定
- [ ] Stage 2 反馈旧路径不受破坏
- [ ] Stage 3 商品 / 库存 / 采购事实层不回退

### 测试覆盖
- [ ] Order ingestion 测试全部通过
- [ ] Refund analysis 测试全部通过
- [ ] Profit ledger 测试全部通过
- [ ] Stage 1-3 核心回归不受影响

---

## 🚀 下一步

完成 Stage 4 后，下一步进入 **Stage 5：多平台统一经营中枢**，把 SKU、库存、价格、表现与利润扩展到跨平台统一管理。

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
