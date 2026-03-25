# Stage 3 可执行开发 Backlog

> 基于 `docs/roadmap/stage3-implementation-tasks.md` 拆解的执行版 backlog。
>
> 目标：把 Stage 3 从"ERP Lite 商品与供应链核心实施清单"进一步落到"可排期、可分工、可切 PR、可追踪 blocker"的开发执行层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 1. 使用说明

本文档用于把 Stage 3 的 19 个规划任务，进一步转化为：
- 开发批次
- owner lane
- blocker 标记
- 推荐 PR 切分
- MVP 子集
- 完成定义（Definition of Done）

建议在项目管理工具中映射为：
- Epic = Stage 3
- Milestone = Batch 1 / 2 / 3 / 4
- Feature = 分组 A / B / C / D / E
- Story = 每个 backlog item

---

## 2. Stage 3 执行目标

### 业务目标
让系统从"候选商品驱动"升级为"SKU 驱动经营"，建立最小但够用的商品、供应商、采购、库存事实层。

### 开发目标
在不破坏现有主链路的前提下，为系统新增：
1. ProductMaster / SKU 商品主数据层
2. Supplier 主数据与 SupplierOffer 经营实体
3. PurchaseOrder / Inbound / Receipt 采购履约链路
4. InventoryBalance / Movement / Reservation 库存事实层
5. ProcurementAgent 与库存分配服务基础框架

### 完成定义（Stage 3 DoD）
- [ ] `ProductMaster` / `ProductVariant` 已可创建和查询
- [ ] `Supplier` / `SupplierOffer` 已可创建和查询
- [ ] `PurchaseOrder` / `InboundShipment` 已可创建和更新
- [ ] `InventoryBalance` / `InventoryReservation` 已可工作
- [ ] `ProcurementAgent` 已能输出基础补货建议
- [ ] `CandidateProduct -> ProductMaster -> ProductVariant` 路径成立
- [ ] `SupplierMatch -> Supplier -> SupplierOffer` 路径成立
- [ ] 旧有 Candidate / Listing 主链路不受破坏
- [ ] Stage 3 测试通过，Stage 1-2 核心回归不受影响

---

## 3. 推荐执行批次

### Batch 1：ERP Lite 核心 Schema 层

**目标**：先把商品、供应商、库存三大核心实体的 schema 打牢，形成 ERP Lite 事实层的最小可用基础。

包含任务：
- A1. ProductMaster / SKU Schema
- B1. Supplier / SupplierOffer Schema
- C1. Warehouse / InventoryBalance / InventoryMovement Schema

建议 owner lane：
- **Backend ERP Lane A**：A1
- **Backend ERP Lane B**：B1
- **Backend ERP Lane C**：C1

完成标志：
- 三大核心实体 schema 已落表
- migration 可运行
- 不需要业务逻辑即可先验证 schema 稳定性

---

### Batch 2：服务层与生命周期基础

**目标**：在 schema 稳定后补服务层，并为 SKU / Supplier / Inventory 建立基础状态管理能力。

包含任务：
- A2. ProductMasterService
- A3. SKU 生命周期字段
- B2. SupplierMasterService
- B3. PurchaseOrder / InboundShipment Schema
- C2. InventoryReservation Schema

建议 owner lane：
- **Backend ERP Lane A**：A2 + A3
- **Backend ERP Lane B**：B2 + B3
- **Backend ERP Lane C**：C2

完成标志：
- 商品、供应商、采购、库存服务可独立工作
- SKU 生命周期字段已就位
- 采购与库存预留 schema 已补齐

---

### Batch 3：采购与库存服务、核心测试

**目标**：把采购履约和库存分配服务串起来，并为 Batch 1-2 建立测试保护网。

包含任务：
- B4. ProcurementService
- C3. InventoryAllocator
- D2. Listing ↔ SKU 映射
- E1. ProductMaster / SKU 测试
- E2. Supplier / Procurement 测试

建议 owner lane：
- **Backend ERP Lane B**：B4
- **Backend ERP Lane C**：C3
- **Backend Integration Lane**：D2
- **QA / ERP Lane**：E1 + E2

完成标志：
- 采购单可创建和状态流转
- 库存可分配、预留、入库
- Listing 可映射 SKU
- 商品与供应商服务已有自动化测试保护

---

### Batch 4：Agent 编排、补货建议与验证

**目标**：把 Stage 3 从"服务可用"推进到"Agent 可编排、补货可建议、验证可回归"。

包含任务：
- C4. 补货建议接口
- D1. ProcurementAgent
- D3. Snapshot 查询接口
- E3. Inventory 测试
- E4. ProcurementAgent 测试
- E5. Stage 3 回归验证套件

建议 owner lane：
- **Backend ERP Lane C**：C4
- **Agent / Orchestration Lane**：D1
- **Backend Integration Lane**：D3
- **QA / ERP Lane**：E3 + E4 + E5

完成标志：
- ProcurementAgent 可生成补货建议
- SKU / Supplier / Inventory snapshot 可查询
- 库存与 Agent 测试通过
- 验证命令和 checklist 完整

---

## 4. 可执行 Backlog 明细

> 状态建议使用：`todo / ready / blocked / in_progress / in_review / done`

### 4.1 Batch 1 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S3-A1 | 新增 ProductMaster / ProductVariant Schema 与 migration | Schema | Backend ERP A | 无 | 无 | ready |
| S3-B1 | 新增 Supplier / SupplierOffer Schema 与 migration | Schema | Backend ERP B | 无 | 无 | ready |
| S3-C1 | 新增 Warehouse / InventoryBalance / InventoryMovement Schema 与 migration | Schema | Backend ERP C | 无 | 无 | ready |

### 4.2 Batch 2 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S3-A2 | 实现 ProductMasterService 与 candidate 转化逻辑 | Service | Backend ERP A | A1 | Candidate 字段映射规则需明确 | todo |
| S3-A3 | 为 SKU 增加生命周期字段与状态枚举 | Schema/Enum | Backend ERP A | A1 | 无 | todo |
| S3-B2 | 实现 SupplierMasterService 与归一化逻辑 | Service | Backend ERP B | B1 | SupplierMatch 字段质量可能不稳定 | todo |
| S3-B3 | 新增 PurchaseOrder / PurchaseOrderLine / InboundShipment Schema | Schema | Backend ERP B | B1 | 无 | todo |
| S3-C2 | 新增 InventoryReservation Schema | Schema | Backend ERP C | C1 | 无 | todo |

### 4.3 Batch 3 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S3-B4 | 实现 ProcurementService 与 PO 状态流转 | Service | Backend ERP B | B2, B3 | 无 | todo |
| S3-C3 | 实现 InventoryAllocator 与负库存保护 | Service | Backend ERP C | C1, C2 | reservation / balance 一致性规则需明确 | todo |
| S3-D2 | 为 PlatformListing 增加 product_variant_id 映射 | Schema/Integration | Backend Integration | A1 | 历史 listing 回填策略需确认 | todo |
| S3-E1 | 新增 ProductMaster / SKU 测试 | Test | QA/ERP | A1, A2, A3 | 无 | todo |
| S3-E2 | 新增 Supplier / Procurement 测试 | Test | QA/ERP | B1, B2, B3, B4 | 无 | todo |

### 4.4 Batch 4 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S3-C4 | 实现补货建议查询接口 | Service | Backend ERP C | C3 | safety_stock / lead_time 字段来源需确认 | todo |
| S3-D1 | 新增 ProcurementAgent 基础框架 | Agent | Agent/Orchestration | B4, C3, C4 | Agent 与 service 边界需明确 | todo |
| S3-D3 | 增加 SKU / Supplier / Inventory snapshot 查询接口 | Service/API | Backend Integration | A2, B2, C3 | 无 | todo |
| S3-E3 | 新增 Inventory 分配与预留测试 | Test | QA/ERP | C1, C2, C3 | 无 | todo |
| S3-E4 | 新增 ProcurementAgent 编排测试 | Test | QA/ERP | D1 | 无 | todo |
| S3-E5 | 编写 Stage 3 回归验证 checklist | Verification | QA/ERP | E1, E2, E3, E4 | 无 | todo |

---

## 5. 推荐 PR 切分

### PR 1：ERP Lite core schema foundation
包含：
- A1
- B1
- C1

目标：
- 先把三大核心实体 schema 落地
- 变更面集中在 models + migrations

---

### PR 2：Product & SKU service layer
包含：
- A2
- A3
- E1

目标：
- 补商品主数据服务与生命周期字段
- 配套基础测试

---

### PR 3：Supplier & Procurement schema + service
包含：
- B2
- B3
- B4
- E2

目标：
- 补供应商主数据与采购服务
- 配套基础测试

---

### PR 4：Inventory core service
包含：
- C2
- C3
- E3

目标：
- 补库存分配与预留服务
- 配套基础测试

---

### PR 5：Listing-SKU integration + snapshots
包含：
- D2
- D3

目标：
- 把 SKU 与 listing 映射打通
- 补 snapshot 查询接口

---

### PR 6：Procurement orchestration
包含：
- C4
- D1
- E4
- E5

目标：
- 补补货建议与 ProcurementAgent
- 配套 Agent 测试与验证 checklist

---

## 6. Blocker 与外部依赖清单

### 硬 blocker

1. **CandidateProduct 字段映射规则不明确**
   - 影响：A2
   - 说明：从 Candidate 转化为 ProductMaster 时，哪些字段应该映射、哪些应该丢弃，需要明确规则

2. **SupplierMatch 字段质量不稳定**
   - 影响：B2
   - 说明：如果 SupplierMatch 的 supplier_name / supplier_url 很脏，归一化逻辑会很难做

### 软 blocker

1. **reservation / balance 一致性规则需明确**
   - 影响：C3
   - 说明：InventoryReservation 与 InventoryBalance.reserved_quantity 的更新规则需要先统一

2. **历史 listing 回填策略需确认**
   - 影响：D2
   - 说明：如果要把历史 listing 映射到 SKU，回填策略和优先级需要明确

3. **safety_stock / lead_time 字段来源需确认**
   - 影响：C4
   - 说明：补货建议依赖安全库存和交期，这些字段应该从哪里读取需要明确

4. **Agent 与 service 边界需明确**
   - 影响：D1
   - 说明：ProcurementAgent 应该只负责编排，不应该承担库存计算或采购单创建的具体逻辑

---

## 7. 建议 owner lane

### Backend ERP Lane A（商品主数据）
负责：
- A1
- A2
- A3

### Backend ERP Lane B（供应商与采购）
负责：
- B1
- B2
- B3
- B4

### Backend ERP Lane C（库存）
负责：
- C1
- C2
- C3
- C4

### Backend Integration Lane
负责：
- D2
- D3

### Agent / Orchestration Lane
负责：
- D1

### QA / ERP Lane
负责：
- E1
- E2
- E3
- E4
- E5

### 推荐协作原则
- Backend ERP Lane 优先保障 schema 与 service 稳定
- Backend Integration Lane 负责把 ERP Lite 实体与现有 Candidate / Listing 主链路打通
- Agent / Orchestration Lane 不要等待所有 service 完成，可先基于 mock / stub 完成 Agent 骨架
- QA / ERP Lane 从 Batch 2 开始持续介入，避免等到最后统一补测试

---

## 8. 实际开工建议

### 第一周优先级
- S3-A1
- S3-B1
- S3-C1

### 第二周优先级
- S3-A2
- S3-A3
- S3-B2
- S3-B3
- S3-C2

### 第三周优先级
- S3-B4
- S3-C3
- S3-D2
- S3-E1
- S3-E2

### 第四周优先级
- S3-C4
- S3-D1
- S3-D3
- S3-E3
- S3-E4
- S3-E5

> 注：如果目标是尽快让 Stage 3 的 ERP Lite 核心可用，可以先完成 A1-A3 + B1-B4 + C1-C3 的最小服务层，再补 Agent 编排和 snapshot 接口。

---

## 9. 推荐在项目管理工具中的字段

建议每个 backlog item 记录：
- `ID`：如 `S3-C3`
- `Title`
- `Type`：Schema / Service / Agent / Integration / Test / Verification
- `Batch`
- `Owner Lane`
- `Dependencies`
- `Data Dependency`
- `Status`
- `PR`
- `Definition of Done`

---

## 10. 最小闭环定义（建议先达成）

如果希望尽快交付 Stage 3 的最小可用版本，建议先完成以下子集：

### Stage 3 MVP 子集
- A1
- A2
- A3
- B1
- B2
- B3
- B4
- C1
- C2
- C3
- E1
- E2
- E3

这可以先形成：

```text
ProductMaster / SKU 商品主数据层
+ Supplier / SupplierOffer 供应商主数据层
+ PurchaseOrder 采购履约链路
+ InventoryBalance / Reservation 库存事实层
```

### 完整 Stage 3
在 MVP 子集基础上再补：
- C4
- D1
- D2
- D3
- E4
- E5

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
