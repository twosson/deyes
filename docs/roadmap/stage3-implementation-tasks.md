# Stage 3 实施任务清单

> 基于研发路线图 Stage 3：建立 ERP Lite 商品与供应链核心
>
> 目标：把系统从“候选商品驱动”升级为“SKU 驱动经营”，建立最小但够用的商品、供应商、采购、库存事实层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 📋 Stage 3 总览

### 核心目标
从“能选品、能上架、能接收反馈”升级为“能围绕 SKU 持续经营”。

### 关键交付物
1. ProductMaster / SKU 商品主数据层
2. Supplier 主数据与 SupplierOffer 经营实体
3. PurchaseOrder / Inbound / Receipt 采购履约链路
4. InventoryBalance / Movement / Reservation 库存事实层
5. Procurement Agent 与库存分配服务基础框架

### 预期成果
- 任意候选商品都可沉淀为长期经营的 Product / SKU 实体
- 系统可以区分“发现阶段供应商证据”和“长期合作供应商主数据”
- 采购、到货、库存、补货建议开始基于事实层运作
- 后续订单、利润、自动化经营都具备稳定的实体基础

---

## 🎯 任务分组

### 分组 A：商品主数据层（优先级 P0）
### 分组 B：供应商主数据与采购模型（优先级 P0）
### 分组 C：库存事实层与分配服务（优先级 P0）
### 分组 D：Agent / Service 编排接入（优先级 P1）
### 分组 E：测试与验证（优先级 P0）

---

## 分组 A：商品主数据层

### A1. 设计 ProductMaster 与 ProductVariant / SKU Schema

**任务描述**：
建立 ERP Lite 的商品主数据层，把 `CandidateProduct` 的“发现态对象”与长期经营实体分离。

**具体工作**：
1. 设计 `ProductMaster` 模型：
   - `id` (UUID, PK)
   - `candidate_product_id` (UUID, nullable, FK)
   - `product_name`
   - `category`
   - `brand`
   - `status`
   - `source_type`
   - `created_at` / `updated_at`
2. 设计 `ProductVariant` / `SKU` 模型：
   - `id` (UUID, PK)
   - `product_master_id` (UUID, FK)
   - `sku_code`
   - `variant_name`
   - `spec_attributes` (JSON)
   - `status`
   - `default_supplier_id` (nullable)
3. 定义 `CandidateProduct -> ProductMaster -> ProductVariant` 关系
4. 为 `sku_code`、`product_master_id` 建立索引和唯一约束

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_product_master_and_sku.py`

**验收标准**：
- [ ] `ProductMaster` / `ProductVariant` 模型可创建
- [ ] `CandidateProduct` 可关联到 `ProductMaster`
- [ ] SKU 能表达规格属性
- [ ] migration 可成功执行

**预估工作量**：4-6 小时

---

### A2. 实现 Candidate 到 ProductMaster 的转化服务

**任务描述**：
创建商品主数据服务，把表现良好的候选商品转化为可经营的产品主数据。

**具体工作**：
1. 新增 `ProductMasterService`
2. 实现方法：
   - `create_from_candidate(candidate_product_id)`
   - `get_product_master(product_master_id)`
   - `link_candidate(product_master_id, candidate_product_id)`
   - `create_variant(product_master_id, spec_attributes)`
3. 定义转化时的字段映射：
   - name / category / normalized_attributes / source metadata
4. 处理重复转化和幂等逻辑

**涉及文件**：
- 新增：`backend/app/services/product_master_service.py`

**验收标准**：
- [ ] 可从 `CandidateProduct` 创建 `ProductMaster`
- [ ] 重复调用不会产生重复主数据
- [ ] 可基于 ProductMaster 创建 SKU
- [ ] 字段映射可解释且稳定

**预估工作量**：5-7 小时

---

### A3. 增加 SKU 生命周期基础字段

**任务描述**：
为 SKU 建立最小生命周期状态，便于后续库存、采购、自动化经营接入。

**具体工作**：
1. 定义 SKU 状态枚举：
   - `DRAFT`
   - `ACTIVE`
   - `PAUSED`
   - `ARCHIVED`
2. 增加必要字段：
   - `activated_at`
   - `archived_at`
   - `lifecycle_note`
3. 明确状态切换规则
4. 为后续 Stage 6 生命周期引擎预留兼容空间

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 修改：`backend/app/core/enums.py` 或相关枚举文件
- 修改：`backend/migrations/versions/00x_product_master_and_sku.py`

**验收标准**：
- [ ] SKU 有明确状态枚举
- [ ] 状态切换不会破坏现有主链路
- [ ] 生命周期字段可持久化

**预估工作量**：2-3 小时

---

## 分组 B：供应商主数据与采购模型

### B1. 设计 Supplier 与 SupplierOffer Schema

**任务描述**：
将 `SupplierMatch` 保持为“发现/竞争集证据”，新增 `Supplier` 与 `SupplierOffer` 作为长期经营实体。

**具体工作**：
1. 设计 `Supplier` 模型：
   - `id` (UUID, PK)
   - `supplier_name`
   - `supplier_url`
   - `contact_name`
   - `contact_channel`
   - `country`
   - `status`
   - `identity_signals` (JSON)
2. 设计 `SupplierOffer` 模型：
   - `id` (UUID, PK)
   - `supplier_id` (UUID, FK)
   - `product_variant_id` (UUID, FK)
   - `supplier_sku`
   - `price`
   - `currency`
   - `moq`
   - `lead_time_days`
   - `is_primary`
3. 定义 `SupplierMatch -> Supplier` 的实体归一化关系
4. 为 `supplier_url`、`supplier_id + product_variant_id` 建索引

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_supplier_master.py`

**验收标准**：
- [ ] `Supplier` / `SupplierOffer` 模型定义完成
- [ ] 可表达同一供应商对多个 SKU 的报价
- [ ] 不破坏 `SupplierMatch` 现有职责
- [ ] migration 可成功执行

**预估工作量**：4-6 小时

---

### B2. 实现 Supplier 主数据归一化服务

**任务描述**：
创建 `SupplierMasterService`，把分散的供应商匹配记录沉淀为稳定的长期合作实体。

**具体工作**：
1. 新增服务类
2. 实现方法：
   - `resolve_supplier_entity(supplier_match_id)`
   - `create_supplier_offer(...)`
   - `get_supplier_profile(supplier_id)`
   - `set_primary_offer(product_variant_id, supplier_offer_id)`
3. 归一化规则：
   - supplier_name + supplier_url 去重
   - identity_signals 合并
4. 处理缺失 URL / 名称不一致的 fallback

**涉及文件**：
- 新增：`backend/app/services/supplier_master_service.py`

**验收标准**：
- [ ] `SupplierMatch` 可归一化为 `Supplier`
- [ ] 同一供应商不会重复创建多个主实体
- [ ] SKU 可设置 primary supplier offer
- [ ] 缺失字段时有合理 fallback

**预估工作量**：5-7 小时

---

### B3. 设计 PurchaseOrder / PurchaseOrderLine / InboundShipment Schema

**任务描述**：
建立最小采购履约链路，支持补货、下单、在途跟踪和收货。

**具体工作**：
1. 设计 `PurchaseOrder`：
   - `id` (UUID, PK)
   - `supplier_id`
   - `po_number`
   - `status`
   - `currency`
   - `ordered_at`
   - `expected_arrival_date`
2. 设计 `PurchaseOrderLine`：
   - `purchase_order_id`
   - `product_variant_id`
   - `quantity`
   - `unit_cost`
3. 设计 `InboundShipment`：
   - `purchase_order_id`
   - `shipment_number`
   - `status`
   - `shipped_at`
   - `arrived_at`
4. 明确 PO 与 supplier / SKU / inbound 的关系

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_purchase_order.py`

**验收标准**：
- [ ] 采购单模型定义完成
- [ ] 采购单可关联 supplier 与 SKU
- [ ] 在途记录可独立表示
- [ ] migration 可成功执行

**预估工作量**：5-7 小时

---

### B4. 实现采购服务基础框架

**任务描述**：
创建 `ProcurementService`，负责采购单创建、状态查询和到货更新。

**具体工作**：
1. 新增服务类
2. 实现方法：
   - `create_purchase_order(supplier_id, lines)`
   - `get_purchase_order(po_id)`
   - `mark_shipped(po_id, shipment_payload)`
   - `mark_received(po_id, receipt_payload)`
3. 实现采购单编号生成规则
4. 更新 PO / inbound 状态流转

**涉及文件**：
- 新增：`backend/app/services/procurement_service.py`

**验收标准**：
- [ ] 可创建采购单及行项目
- [ ] 发货 / 收货状态可更新
- [ ] 状态流转清晰可追踪
- [ ] 服务类可独立测试

**预估工作量**：5-7 小时

---

## 分组 C：库存事实层与分配服务

### C1. 设计 Warehouse / InventoryBalance / InventoryMovement Schema

**任务描述**：
建立库存中心基础模型，为可用库存、在途库存和库存变动提供事实来源。

**具体工作**：
1. 设计 `Warehouse` 模型：
   - `id`
   - `warehouse_code`
   - `warehouse_name`
   - `country`
   - `status`
2. 设计 `InventoryBalance`：
   - `product_variant_id`
   - `warehouse_id`
   - `on_hand_quantity`
   - `reserved_quantity`
   - `inbound_quantity`
   - `available_quantity`
3. 设计 `InventoryMovement`：
   - `movement_type`
   - `quantity`
   - `reference_type`
   - `reference_id`
   - `occurred_at`
4. 明确库存余额与流水关系

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_inventory_core.py`

**验收标准**：
- [ ] 仓库与库存模型定义完成
- [ ] 同一 SKU 可按仓库记录余额
- [ ] 库存流水可追溯来源
- [ ] migration 可成功执行

**预估工作量**：5-7 小时

---

### C2. 增加 InventoryReservation Schema

**任务描述**：
为后续订单分配和平台占用提供库存预留能力。

**具体工作**：
1. 设计 `InventoryReservation`：
   - `id`
   - `product_variant_id`
   - `warehouse_id`
   - `quantity`
   - `reservation_type`
   - `reference_type`
   - `reference_id`
   - `status`
2. 定义 reservation 生命周期：
   - `ACTIVE`
   - `RELEASED`
   - `CONSUMED`
3. 明确与 `InventoryBalance.reserved_quantity` 的一致性规则
4. 支持平台 listing / future order 的占用预留

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 修改：`backend/migrations/versions/00x_inventory_core.py`

**验收标准**：
- [ ] 预留模型可创建
- [ ] reservation 状态定义清晰
- [ ] 可与库存余额联动

**预估工作量**：3-5 小时

---

### C3. 实现 InventoryAllocator 服务

**任务描述**：
创建库存分配服务，统一处理库存占用、释放、入库和出库。

**具体工作**：
1. 新增 `InventoryAllocator`
2. 实现方法：
   - `allocate(product_variant_id, quantity, warehouse_id=None)`
   - `release_reservation(reservation_id)`
   - `receive_inbound(purchase_order_id, receipt_lines)`
   - `record_movement(...)`
3. 处理 available / reserved / inbound 的更新规则
4. 保证幂等和负库存保护

**涉及文件**：
- 新增：`backend/app/services/inventory_allocator.py`

**验收标准**：
- [ ] 可成功创建库存预留
- [ ] 可释放 reservation
- [ ] 收货后库存余额会更新
- [ ] 不会出现负库存

**预估工作量**：6-8 小时

---

### C4. 增加补货建议查询接口

**任务描述**：
为后续 Procurement Agent 提供基础的补货建议能力。

**具体工作**：
1. 在库存服务或独立服务中实现：
   - `get_reorder_suggestion(product_variant_id)`
2. 基于以下字段给出建议：
   - available_quantity
   - inbound_quantity
   - safety_stock
   - lead_time_days
3. 提供简单建议结果：
   - `ok`
   - `watch`
   - `reorder`
4. 保持规则型实现，不引入复杂预测模型

**涉及文件**：
- 修改：`backend/app/services/inventory_allocator.py` 或新增 `backend/app/services/replenishment_service.py`

**验收标准**：
- [ ] 可给出基础补货建议
- [ ] 建议逻辑可解释
- [ ] 不依赖订单系统也能工作

**预估工作量**：3-5 小时

---

## 分组 D：Agent / Service 编排接入

### D1. 新增 ProcurementAgent 基础框架

**任务描述**：
创建 `ProcurementAgent`，负责把库存与采购建议串联成最小采购动作编排。

**具体工作**：
1. 新增 Agent 类
2. 实现方法：
   - `suggest_replenishment(product_variant_id)`
   - `create_procurement_plan(product_variant_id)`
   - `execute_purchase_order(plan_id or payload)`
3. 集成：
   - `SupplierMasterService`
   - `InventoryAllocator`
   - `ProcurementService`
4. 明确 Agent 只负责决策与编排，不承担库存事实计算

**涉及文件**：
- 新增：`backend/app/agents/procurement_agent.py`

**验收标准**：
- [ ] Agent 可生成补货建议
- [ ] Agent 可创建采购计划或采购单
- [ ] 与 service 边界清晰

**预估工作量**：5-7 小时

---

### D2. 建立 SKU 与 PlatformListing 的映射扩展

**任务描述**：
为后续平台统一经营做准备，让平台 listing 能逐步映射到长期经营的 SKU。

**具体工作**：
1. 在 `PlatformListing` 中增加可选 `product_variant_id` 关联
2. 保持现有 listing 发布流程兼容
3. 明确映射策略：
   - 新发布 listing 可选绑定 SKU
   - 历史 listing 可延迟回填
4. 更新相关查询和序列化逻辑

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 修改：`backend/migrations/versions/00x_listing_sku_link.py`
- 可能修改：相关 service / API schema

**验收标准**：
- [ ] listing 可选关联 SKU
- [ ] 不绑定 SKU 的旧数据仍可正常工作
- [ ] 后续库存/订单系统可沿此关系扩展

**预估工作量**：4-6 小时

---

### D3. 增加 Supplier / SKU / Inventory 查询服务接口

**任务描述**：
补齐 ERP Lite 基础查询接口，支持后续 API、调试和 Agent 消费。

**具体工作**：
1. 为 Product / Supplier / Inventory 服务增加查询方法
2. 提供聚合读取：
   - `get_sku_snapshot(product_variant_id)`
   - `get_supplier_snapshot(supplier_id)`
   - `get_inventory_snapshot(product_variant_id)`
3. 返回结构化快照：
   - 主数据
   - 主供应商
   - 当前库存
   - 在途数量
4. 保持只读接口简单稳定

**涉及文件**：
- 修改：
  - `backend/app/services/product_master_service.py`
  - `backend/app/services/supplier_master_service.py`
  - `backend/app/services/inventory_allocator.py`

**验收标准**：
- [ ] SKU / Supplier / Inventory 可独立查询
- [ ] snapshot 返回结构稳定
- [ ] 可供后续 API / Agent 复用

**预估工作量**：4-6 小时

---

## 分组 E：测试与验证

### E1. 新增 ProductMaster / SKU 模型测试

**任务描述**：
为商品主数据层编写模型测试与服务测试。

**具体工作**：
新增测试：
- `test_create_product_master_from_candidate`
- `test_create_product_variant_with_spec_attributes`
- `test_product_master_service_is_idempotent`
- `test_sku_status_fields_persist`

**涉及文件**：
- 新增：`backend/tests/test_product_master_service.py`

**验收标准**：
- [ ] Product / SKU 测试全部通过
- [ ] 幂等和字段映射被覆盖

**预估工作量**：4-6 小时

---

### E2. 新增 Supplier 主数据与采购模型测试

**任务描述**：
覆盖 Supplier 归一化、SupplierOffer、PurchaseOrder 的核心场景。

**具体工作**：
新增测试：
- `test_resolve_supplier_match_into_supplier_entity`
- `test_create_supplier_offer_for_sku`
- `test_create_purchase_order_with_lines`
- `test_mark_purchase_order_received_updates_status`

**涉及文件**：
- 新增：`backend/tests/test_supplier_master_service.py`
- 新增：`backend/tests/test_procurement_service.py`

**验收标准**：
- [ ] Supplier / Procurement 测试全部通过
- [ ] 采购状态流转场景被覆盖

**预估工作量**：5-7 小时

---

### E3. 新增库存分配与预留测试

**任务描述**：
验证库存余额、reservation、入库和负库存保护逻辑。

**具体工作**：
新增测试：
- `test_allocate_creates_inventory_reservation`
- `test_release_reservation_restores_available_quantity`
- `test_receive_inbound_updates_inventory_balance`
- `test_inventory_allocator_prevents_negative_stock`
- `test_reorder_suggestion_returns_reorder_when_below_safety_stock`

**涉及文件**：
- 新增：`backend/tests/test_inventory_allocator.py`

**验收标准**：
- [ ] Inventory 测试全部通过
- [ ] reservation / inbound / availability 边界被覆盖

**预估工作量**：5-7 小时

---

### E4. 新增 ProcurementAgent 编排测试

**任务描述**：
验证 ProcurementAgent 能基于库存快照和供应商数据产出采购建议。

**具体工作**：
新增测试：
- `test_procurement_agent_suggests_reorder_for_low_stock_sku`
- `test_procurement_agent_uses_primary_supplier_offer`
- `test_procurement_agent_creates_purchase_order_payload`
- `test_procurement_agent_does_not_bypass_inventory_service_rules`

**涉及文件**：
- 新增：`backend/tests/test_procurement_agent.py`

**验收标准**：
- [ ] Agent 编排测试全部通过
- [ ] Agent / Service 边界保持清晰

**预估工作量**：4-6 小时

---

### E5. Stage 3 回归验证套件

**任务描述**：
建立 Stage 3 的目标回归命令和人工验证 checklist。

**建议命令**：
```bash
python -m pytest backend/tests/test_product_master_service.py -v
python -m pytest backend/tests/test_supplier_master_service.py -v
python -m pytest backend/tests/test_procurement_service.py -v
python -m pytest backend/tests/test_inventory_allocator.py -v
python -m pytest backend/tests/test_phase1_mvp.py -v
python -m pytest backend/tests/test_feedback_aggregator.py -v
```

**涉及文件**：
- 新增：`docs/roadmap/stage3-verification-checklist.md`

**验收标准**：
- [ ] 核心回归命令明确
- [ ] 手工验证 checklist 明确
- [ ] Stage 1-2 主链路不回退

**预估工作量**：2-3 小时

---

## 📊 任务优先级与依赖关系

### 第一批（并行）
- A1（ProductMaster / SKU Schema）
- B1（Supplier / SupplierOffer Schema）
- C1（Warehouse / InventoryBalance Schema）

### 第二批（依赖第一批）
- A2（ProductMasterService）
- A3（SKU 生命周期字段）
- B2（SupplierMasterService）
- B3（PurchaseOrder Schema）
- C2（InventoryReservation）

### 第三批（依赖第二批）
- B4（ProcurementService）
- C3（InventoryAllocator）
- D2（Listing ↔ SKU 映射）
- E1 / E2（商品与供应商测试）

### 第四批（依赖第三批）
- C4（补货建议）
- D1（ProcurementAgent）
- D3（Snapshot 查询接口）
- E3 / E4（库存与 Agent 测试）
- E5（回归验证）

---

## 📈 工作量估算

| 分组 | 任务数 | 预估总工时 | 建议人员 |
|------|--------|-----------|---------|
| A | 3 | 11-16h | 后端 |
| B | 4 | 19-27h | 后端 |
| C | 4 | 17-25h | 后端 |
| D | 3 | 13-19h | 后端 + Agent |
| E | 5 | 20-29h | 测试 + 后端 |
| **总计** | **19** | **80-116h** | **2 人** |

按 2 人并行投入，Stage 3 可作为从“反馈闭环”升级到“ERP Lite 事实层”的主开发包推进。

---

## ✅ Stage 3 退出标准

### 功能完整性
- [ ] `ProductMaster` / `ProductVariant` 已可创建和查询
- [ ] `Supplier` / `SupplierOffer` 已可创建和查询
- [ ] `PurchaseOrder` / `InboundShipment` 已可创建和更新
- [ ] `InventoryBalance` / `InventoryReservation` 已可工作
- [ ] `ProcurementAgent` 已能输出基础补货建议

### 实体关系完整性
- [ ] `CandidateProduct -> ProductMaster -> ProductVariant` 路径成立
- [ ] `SupplierMatch -> Supplier -> SupplierOffer` 路径成立
- [ ] `ProductVariant -> InventoryBalance / PurchaseOrderLine / PlatformListing` 路径成立
- [ ] 旧有 Candidate / Listing 主链路不受破坏

### 稳定性
- [ ] 库存不会出现负数
- [ ] reservation / inbound / available 的更新规则稳定
- [ ] 采购状态流转可追踪
- [ ] 新增 schema 不破坏 Stage 1-2 能力

### 测试覆盖
- [ ] Product / SKU 测试全部通过
- [ ] Supplier / Procurement 测试全部通过
- [ ] Inventory / Reservation 测试全部通过
- [ ] Stage 1-2 核心回归不受影响

---

## 🚀 下一步

完成 Stage 3 后，下一步进入 **Stage 4：订单、售后、利润台账**，把 ERP Lite 从“商品 + 供应链核心”继续扩展到真实经营损益层。

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
