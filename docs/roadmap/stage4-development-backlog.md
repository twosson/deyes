# Stage 4 可执行开发 Backlog

> 基于 `docs/roadmap/stage4-implementation-tasks.md` 拆解的执行版 backlog。
>
> 目标：把 Stage 4 从“订单、售后、利润台账实施清单”进一步落到“可排期、可分工、可切 PR、可追踪 blocker”的开发执行层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 1. 使用说明

本文档用于把 Stage 4 的 19 个规划任务，进一步转化为：
- 开发批次
- owner lane
- blocker 标记
- 推荐 PR 切分
- MVP 子集
- 完成定义（Definition of Done）

建议在项目管理工具中映射为：
- Epic = Stage 4
- Milestone = Batch 1 / 2 / 3 / 4
- Feature = 分组 A / B / C / D / E
- Story = 每个 backlog item

---

## 2. Stage 4 执行目标

### 业务目标
让系统从“理论利润 + 平台表现反馈”升级为“真实订单、退款、费用、净利可追踪”的经营损益层。

### 开发目标
在不破坏现有主链路的前提下，为系统新增：
1. PlatformOrder / PlatformOrderLine 订单中心
2. RefundCase / ReturnCase / AfterSaleIssue 售后中心
3. SettlementEntry / AdCostAllocation / ProfitLedger 利润台账
4. 订单导入、退款分析、净利计算服务
5. SKU / Listing / Supplier 维度真实利润聚合与经营快照

### 完成定义（Stage 4 DoD）
- [ ] `PlatformOrder` / `PlatformOrderLine` 已可导入和查询
- [ ] `RefundCase` / `ReturnCase` / `AfterSaleIssue` 已可导入和查询
- [ ] `SettlementEntry` / `ProfitLedger` 已可生成和查询
- [ ] SKU / listing / supplier 的真实净利可查询
- [ ] 系统可区分理论利润与真实净利
- [ ] 退款损失会显式影响净利
- [ ] 订单、售后、利润链路可追溯
- [ ] Stage 4 测试通过，Stage 1-3 核心回归不受影响

---

## 3. 推荐执行批次

### Batch 1：真实经营损益层的核心 Schema

**目标**：先把订单、售后、利润台账三大核心实体落表，为真实经营结果沉淀打基础。

包含任务：
- A1. PlatformOrder / PlatformOrderLine Schema
- B1. RefundCase / ReturnCase / AfterSaleIssue Schema
- C1. SettlementEntry / AdCostAllocation / ProfitLedger Schema

建议 owner lane：
- **Backend Ledger Lane A**：A1
- **Backend Ledger Lane B**：B1
- **Backend Ledger Lane C**：C1

完成标志：
- 订单、售后、利润三类核心事实层已落表
- migration 可运行
- 不依赖外部平台接口即可先验证 schema 完整性

---

### Batch 2：订单、退款、利润服务骨架

**目标**：在 schema 稳定后补服务层，使订单导入、退款分析、利润台账具备最小可用逻辑。

包含任务：
- A2. FulfillmentRecord Schema
- A3. OrderIngestionService
- B2. RefundAnalysisService
- C2. ProfitLedgerService

建议 owner lane：
- **Backend Ledger Lane A**：A2 + A3
- **Backend Ledger Lane B**：B2
- **Backend Ledger Lane C**：C2

完成标志：
- 订单、履约、退款、利润服务可独立工作
- 幂等和重算逻辑已有初步定义
- 为后续库存联动和反馈兼容打基础

---

### Batch 3：库存联动、成本归集与基础测试

**目标**：把订单、退款、利润和库存、广告费、聚合能力串起来，并为服务层建立测试保护网。

包含任务：
- A4. 订单导入与库存联动
- B3. 售后问题分类与归因
- C3. 广告成本分摊规则
- C4. Supplier / Platform / Region 利润聚合
- E1. 订单导入与履约测试
- E2. 退款与售后分析测试

建议 owner lane：
- **Backend Ledger Lane A**：A4
- **Backend Ledger Lane B**：B3
- **Backend Ledger Lane C**：C3 + C4
- **QA / Ledger Lane**：E1 + E2

完成标志：
- 订单与库存已联动
- 售后问题可以做基础归因
- 广告成本和利润聚合已可工作
- 订单与退款路径已有自动化测试保护

---

### Batch 4：经营快照、反馈兼容与验证收口

**目标**：把 Stage 4 从“真实损益层可用”推进到“可聚合、可反馈、可调试、可回归验证”。

包含任务：
- D1. OperatingMetricsService
- D2. FeedbackAggregator 消费真实损益事实
- D3. 订单/售后/利润只读 API（可选）
- E3. Profit ledger 测试
- E4. 经营快照与反馈兼容测试
- E5. Stage 4 回归验证套件

建议 owner lane：
- **Backend Integration Lane**：D1 + D2
- **API / Debug Lane**：D3
- **QA / Ledger Lane**：E3 + E4 + E5

完成标志：
- SKU / listing / supplier 经营快照可查询
- FeedbackAggregator 可渐进消费真实订单 / 退款 / 利润事实
- Stage 4 回归命令和 checklist 完整

---

## 4. 可执行 Backlog 明细

> 状态建议使用：`todo / ready / blocked / in_progress / in_review / done`

### 4.1 Batch 1 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S4-A1 | 新增 PlatformOrder / PlatformOrderLine Schema 与 migration | Schema | Backend Ledger A | 无 | 无 | ready |
| S4-B1 | 新增 RefundCase / ReturnCase / AfterSaleIssue Schema 与 migration | Schema | Backend Ledger B | 无 | 无 | ready |
| S4-C1 | 新增 SettlementEntry / AdCostAllocation / ProfitLedger Schema 与 migration | Schema | Backend Ledger C | 无 | 无 | ready |

### 4.2 Batch 2 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S4-A2 | 新增 FulfillmentRecord Schema 与履约状态枚举 | Schema/Enum | Backend Ledger A | A1 | 无 | todo |
| S4-A3 | 实现 OrderIngestionService 与幂等导入逻辑 | Service | Backend Ledger A | A1, A2 | 平台 order payload 字段映射需确认 | todo |
| S4-B2 | 实现 RefundAnalysisService 与退款率聚合逻辑 | Service | Backend Ledger B | B1 | refund reason 字段口径需统一 | todo |
| S4-C2 | 实现 ProfitLedgerService 与净利重算逻辑 | Service | Backend Ledger C | C1, A3, B2 | 理论利润与真实净利边界需明确 | todo |

### 4.3 Batch 3 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S4-A4 | 实现订单导入与库存联动逻辑 | Service/Integration | Backend Ledger A | A3 | 订单与 reservation 消耗规则需明确 | todo |
| S4-B3 | 实现售后问题分类与归因规则 | Service/Rules | Backend Ledger B | B2 | issue_type 分类标准需先统一 | todo |
| S4-C3 | 在 ProfitLedgerService 中实现广告成本分摊 | Service/Rules | Backend Ledger C | C2 | 广告成本来源与分摊口径需确认 | todo |
| S4-C4 | 增加 Supplier / Platform / Region 利润聚合接口 | Service/Aggregation | Backend Ledger C | C2, C3 | 平台与地区维度口径需统一 | todo |
| S4-E1 | 新增订单导入与履约测试 | Test | QA/Ledger | A1, A2, A3 | 无 | todo |
| S4-E2 | 新增退款与售后分析测试 | Test | QA/Ledger | B1, B2, B3 | 无 | todo |

### 4.4 Batch 4 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S4-D1 | 新增 OperatingMetricsService 并输出经营快照 | Service/Aggregation | Backend Integration | A3, B2, C2, C4 | snapshot 字段结构需统一 | todo |
| S4-D2 | 让 FeedbackAggregator 渐进消费真实损益事实 | Feedback/Integration | Backend Integration | D1, C2, B2 | 必须保持 Stage 2 fallback 路径可用 | todo |
| S4-D3 | 新增订单/售后/利润只读 API（可选） | API/Debug | API/Debug | D1 | 敏感字段过滤需明确 | todo |
| S4-E3 | 新增利润台账测试 | Test | QA/Ledger | C2, C3, C4 | 无 | todo |
| S4-E4 | 新增经营快照与反馈兼容测试 | Test | QA/Ledger | D1, D2 | 无 | todo |
| S4-E5 | 编写 Stage 4 回归验证 checklist | Verification | QA/Ledger | E1, E2, E3, E4 | 无 | todo |

---

## 5. 推荐 PR 切分

### PR 1：Orders, after-sales, and ledger schema foundation
包含：
- A1
- B1
- C1

目标：
- 先把订单、售后、利润三类事实实体落地
- 变更面集中在 models + migrations

---

### PR 2：Order ingestion service layer
包含：
- A2
- A3
- E1

目标：
- 补订单与履约导入服务
- 配套基础测试

---

### PR 3：Refund and after-sale analysis
包含：
- B2
- B3
- E2

目标：
- 建立退款分析和售后分类能力
- 配套基础测试

---

### PR 4：Profit ledger core
包含：
- C2
- C3
- C4
- E3

目标：
- 建立真实净利、广告成本和聚合利润能力
- 配套利润台账测试

---

### PR 5：Inventory coupling + operating snapshots
包含：
- A4
- D1
- E4

目标：
- 让订单与库存联动
- 输出经营快照并补兼容测试

---

### PR 6：Feedback fact upgrade + verification
包含：
- D2
- E5

目标：
- 把 Stage 2 feedback 输入源逐步升级到真实损益事实
- 收口 Stage 4 验证入口

---

### PR 7：Read-only debug APIs（可独立后置）
包含：
- D3

目标：
- 作为调试增强项独立推进
- 不阻塞 Stage 4 主路径交付

---

## 6. Blocker 与外部依赖清单

### 硬 blocker

1. **平台订单 payload 字段映射未统一**
   - 影响：A3
   - 说明：不同平台订单字段命名和语义不一致，OrderIngestionService 需要先有统一映射口径

2. **理论利润与真实净利边界需明确**
   - 影响：C2, D2
   - 说明：如果 `PricingAssessment` 和 `ProfitLedger` 的职责边界不清晰，后续反馈和报表都会混乱

### 软 blocker

1. **refund reason / issue_type 分类口径需统一**
   - 影响：B2, B3
   - 说明：退款原因和售后问题分类如果不稳定，会影响聚合和反馈信号质量

2. **广告成本来源与分摊口径需确认**
   - 影响：C3
   - 说明：如果广告费没有明确来源或口径，分摊规则只能停留在骨架层

3. **订单与 reservation 消耗规则需明确**
   - 影响：A4
   - 说明：订单创建、发货、取消、退款分别如何影响库存，需要先定义一致规则

4. **snapshot 字段结构需统一**
   - 影响：D1, D3
   - 说明：SKU / listing / supplier 快照若结构不统一，后续控制台和 API 复用会困难

5. **必须保持 Stage 2 fallback 路径可用**
   - 影响：D2
   - 说明：在真实订单数据不足时，FeedbackAggregator 仍需继续消费 Stage 1-2 的旧输入源

---

## 7. 建议 owner lane

### Backend Ledger Lane A（订单与履约）
负责：
- A1
- A2
- A3
- A4

### Backend Ledger Lane B（售后与退款）
负责：
- B1
- B2
- B3

### Backend Ledger Lane C（利润台账）
负责：
- C1
- C2
- C3
- C4

### Backend Integration Lane
负责：
- D1
- D2

### API / Debug Lane
负责：
- D3

### QA / Ledger Lane
负责：
- E1
- E2
- E3
- E4
- E5

### 推荐协作原则
- Ledger Lane 优先保障订单、退款、利润的事实边界清晰
- Backend Integration Lane 负责把 Stage 4 的真实损益层与 Stage 2 feedback / Stage 3 inventory 打通
- API / Debug Lane 可以后置，不应阻塞主功能交付
- QA / Ledger Lane 应从 Batch 2 起持续介入，避免最后一次性补测试

---

## 8. 实际开工建议

### 第一周优先级
- S4-A1
- S4-B1
- S4-C1

### 第二周优先级
- S4-A2
- S4-A3
- S4-B2
- S4-C2

### 第三周优先级
- S4-A4
- S4-B3
- S4-C3
- S4-C4
- S4-E1
- S4-E2

### 第四周优先级
- S4-D1
- S4-D2
- S4-E3
- S4-E4
- S4-E5
- S4-D3（如需要）

> 注：如果目标是尽快让 Stage 4 的真实经营损益层可用，可以先完成 A1-A4 + B1-B2 + C1-C2 的最小真实订单/退款/利润链路，再补广告分摊、快照聚合与调试 API。

---

## 9. 推荐在项目管理工具中的字段

建议每个 backlog item 记录：
- `ID`：如 `S4-C2`
- `Title`
- `Type`：Schema / Service / Rules / Aggregation / Feedback / API / Test / Verification
- `Batch`
- `Owner Lane`
- `Dependencies`
- `Data Dependency`
- `Status`
- `PR`
- `Definition of Done`

---

## 10. 最小闭环定义（建议先达成）

如果希望尽快交付 Stage 4 的最小可用版本，建议先完成以下子集：

### Stage 4 MVP 子集
- A1
- A2
- A3
- A4
- B1
- B2
- C1
- C2
- E1
- E2
- E3

这可以先形成：

```text
PlatformOrder / PlatformOrderLine 订单中心
+ RefundCase 售后退款中心
+ ProfitLedger 真实净利台账
+ 订单 → 退款 → 净利 的最小闭环
```

### 完整 Stage 4
在 MVP 子集基础上再补：
- B3
- C3
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
