# Stage 6 可执行开发 Backlog

> 基于 `docs/roadmap/stage6-implementation-tasks.md` 拆解的执行版 backlog。
>
> 目标：把 Stage 6 从“自动化经营控制平面实施清单”进一步落到“可排期、可分工、可切 PR、可追踪 blocker”的开发执行层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 1. 使用说明

本文档用于把 Stage 6 的 19 个规划任务，进一步转化为：
- 开发批次
- owner lane
- blocker 标记
- 推荐 PR 切分
- MVP 子集
- 完成定义（Definition of Done）

建议在项目管理工具中映射为：
- Epic = Stage 6
- Milestone = Batch 1 / 2 / 3 / 4
- Feature = 分组 A / B / C / D / E
- Story = 每个 backlog item

---

## 2. Stage 6 执行目标

### 业务目标
让系统从“统一管理与分析”升级为“系统驱动动作、人只处理例外”的自动化经营控制平面。

### 开发目标
在不破坏现有主链路的前提下，为系统新增：
1. SKU 生命周期引擎与生命周期信号快照
2. 自动动作规则层、动作引擎与安全阈值机制
3. 异常检测服务与控制台聚合服务
4. ManualOverride、审批与回滚能力
5. 自动动作可追踪、可解释、可审计的基础设施

### 完成定义（Stage 6 DoD）
- [ ] `SkuLifecycleState` / `LifecycleRule` / `LifecycleTransitionLog` 已可创建和查询
- [ ] `LifecycleEngineService` 已可评估生命周期状态并写入迁移日志
- [ ] `ActionRule` / `ActionExecutionLog` 已可创建和查询
- [ ] `ActionEngineService` 已可生成并执行关键经营动作
- [ ] `AnomalyDetectionService` 已可识别核心经营异常
- [ ] `OperationsControlPlaneService` 与控制台只读 API 已可查询
- [ ] `ManualOverride` / `OverrideService` / rollback 已可工作
- [ ] 高风险动作具备安全阈值、审批或 suggest-only 保护
- [ ] Stage 6 测试通过，Stage 1-5 核心回归不受影响

---

## 3. 推荐执行批次

### Batch 1：自动化控制平面的基础 Schema 与异常骨架

**目标**：先把生命周期、动作规则、人工覆盖三类控制平面实体落表，并补异常检测基础服务骨架，为后续自动化动作和审批回滚打基础。

包含任务：
- A1. SkuLifecycleState / LifecycleRule / LifecycleTransitionLog Schema
- B1. ActionRule / ActionExecutionLog Schema
- C1. AnomalyDetectionService
- D1. ManualOverride Schema

建议 owner lane：
- **Backend Lifecycle Lane A**：A1
- **Backend Action Lane B**：B1
- **Backend Control Plane Lane C**：C1
- **Backend Override Lane D**：D1

完成标志：
- 生命周期、动作、人工覆盖三类基础模型已落表
- migration 可运行
- 异常检测服务可输出基础结构化异常 payload

---

### Batch 2：生命周期引擎、动作引擎与 override 服务

**目标**：在 schema 稳定后补服务层，使生命周期判断、动作评估与人工覆盖规则具备最小可用逻辑。

包含任务：
- A2. LifecycleEngineService
- A3. 生命周期信号聚合接口
- B2. ActionEngineService
- D2. OverrideService

建议 owner lane：
- **Backend Lifecycle Lane A**：A2 + A3
- **Backend Action Lane B**：B2
- **Backend Override Lane D**：D2

完成标志：
- 生命周期状态可评估并写日志
- 动作引擎可生成候选动作并记录执行日志
- override 规则可在生命周期与动作路径中生效

---

### Batch 3：安全阈值、关键动作接入与控制台入口

**目标**：把生命周期状态与动作引擎接入关键经营动作，同时建立控制台聚合与只读 API，并为核心自动化路径建立测试保护网。

包含任务：
- B3. 降级执行策略与安全阈值
- B4. 关键自动动作执行路径接入
- C2. OperationsControlPlaneService
- C3. 经营控制台只读 API
- E1. 生命周期引擎测试
- E2. 动作引擎与安全阈值测试

建议 owner lane：
- **Backend Action Lane B**：B3 + B4
- **Backend Control Plane Lane C**：C2 + C3
- **QA / Automation Lane**：E1 + E2

完成标志：
- 高风险动作具备阈值和 suggest-only / dry-run 保护
- 至少 3 类关键动作已接入统一引擎
- 控制台聚合服务与只读 API 可查询
- 生命周期与动作引擎路径已有自动化测试保护

---

### Batch 4：审批、回滚、审计与回归收口

**目标**：把 Stage 6 从“自动动作可运行”推进到“可审批、可回滚、可审计、可回归验证”。

包含任务：
- C4. 自动动作审批入口（可选）
- D3. 动作回滚机制
- E3. 异常检测与控制台测试
- E4. 人工覆盖与审计测试
- E5. Stage 6 回归验证套件

建议 owner lane：
- **Backend Control Plane Lane C**：C4
- **Backend Override / Action Lane**：D3
- **QA / Automation Lane**：E3 + E4 + E5

完成标志：
- 高风险动作可进入审批流
- 关键动作回滚机制可工作并保留审计日志
- 异常检测、审批、override、回滚路径可验证
- Stage 6 回归命令和 checklist 完整

---

## 4. 可执行 Backlog 明细

> 状态建议使用：`todo / ready / blocked / in_progress / in_review / done`

### 4.1 Batch 1 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S6-A1 | 新增 SkuLifecycleState / LifecycleRule / LifecycleTransitionLog Schema 与 migration | Schema | Backend Lifecycle A | 无 | 生命周期状态定义与迁移语义需先统一 | ready |
| S6-B1 | 新增 ActionRule / ActionExecutionLog Schema 与 migration | Schema | Backend Action B | 无 | action_type 枚举与 target_scope 语义需统一 | ready |
| S6-C1 | 实现 AnomalyDetectionService 与结构化异常 payload | Service | Backend Control Plane C | Stage 4-5 事实层稳定 | 异常阈值与指标口径需统一 | ready |
| S6-D1 | 新增 ManualOverride Schema 与 migration | Schema | Backend Override D | 无 | override 作用域与优先级规则需先明确 | ready |

### 4.2 Batch 2 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S6-A2 | 实现 LifecycleEngineService 与状态迁移逻辑 | Service | Backend Lifecycle A | A1, A3 | 生命周期规则阈值需保守，避免误迁移 | todo |
| S6-A3 | 建立生命周期信号快照接口 | Service/Aggregation | Backend Lifecycle A | C1 | OperatingMetrics / Feedback / Inventory 信号口径需统一 | todo |
| S6-B2 | 实现 ActionEngineService 与动作执行日志 | Service | Backend Action B | B1, A2, D2 | 引擎与底层 service 的职责边界需明确 | todo |
| S6-D2 | 实现 OverrideService 并接入生命周期/动作引擎 | Service | Backend Override D | D1, A2, B2 | override 的过期与冲突规则需统一 | todo |

### 4.3 Batch 3 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S6-B3 | 在 ActionEngineService 中实现安全阈值与 dry-run / suggest-only | Service/Rules | Backend Action B | B2 | 高风险动作阈值与默认执行策略需确认 | todo |
| S6-B4 | 接入调价 / 补货 / 换素材 / 下架等关键自动动作 | Service/Integration | Backend Action B | B2, B3 | 各动作的可自动执行边界需统一 | todo |
| S6-C2 | 新增 OperationsControlPlaneService 并输出控制台聚合视图 | Service/Aggregation | Backend Control Plane C | A2, B2, C1 | 控制台卡片字段结构需统一 | todo |
| S6-C3 | 新增经营控制台只读 API | API/Debug | Backend Control Plane C | C2 | 返回结构与敏感字段过滤需明确 | todo |
| S6-E1 | 新增生命周期引擎测试 | Test | QA/Automation | A1, A2, A3, D2 | 无 | todo |
| S6-E2 | 新增动作引擎与安全阈值测试 | Test | QA/Automation | B1, B2, B3, B4 | 无 | todo |

### 4.4 Batch 4 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S6-C4 | 新增自动动作审批入口（可选） | API/Approval | Backend Control Plane C | C3, B3 | 审批后动作执行路径需明确 | todo |
| S6-D3 | 建立关键动作回滚机制与审计日志 | Service/Audit | Backend Override/Action | B4, D2 | 哪些动作支持回滚需先明确 | todo |
| S6-E3 | 新增异常检测与控制台测试 | Test | QA/Automation | C1, C2, C3 | 无 | todo |
| S6-E4 | 新增人工覆盖与审计测试 | Test | QA/Automation | D1, D2, D3, C4 | 无 | todo |
| S6-E5 | 编写 Stage 6 回归验证 checklist | Verification | QA/Automation | E1, E2, E3, E4 | 无 | todo |

---

## 5. 推荐 PR 切分

### PR 1：Lifecycle, action, and override schema foundation
包含：
- A1
- B1
- D1

目标：
- 先把生命周期、动作规则、人工覆盖三类控制平面实体落地
- 变更面集中在 models + migrations

---

### PR 2：Anomaly detection foundation
包含：
- C1

目标：
- 先建立结构化异常检测能力
- 为生命周期判断和控制台聚合提供统一异常输入

---

### PR 3：Lifecycle engine core
包含：
- A2
- A3
- E1

目标：
- 建立生命周期状态评估与信号快照能力
- 配套基础测试

---

### PR 4：Action engine core
包含：
- B2
- B3
- E2

目标：
- 建立动作引擎与安全阈值机制
- 配套动作与阈值测试

---

### PR 5：Override and rollback layer
包含：
- D2
- D3
- E4

目标：
- 建立人工覆盖优先级与关键动作回滚能力
- 配套 override / 审计测试

---

### PR 6：Control plane aggregation and API
包含：
- C2
- C3
- E3

目标：
- 建立经营控制台聚合服务与只读 API
- 配套异常检测和控制台测试

---

### PR 7：Automation action integrations
包含：
- B4
- C4
- E5

目标：
- 接入关键自动动作与审批入口
- 收口 Stage 6 回归验证入口

---

## 6. Blocker 与外部依赖清单

### 硬 blocker

1. **Stage 3-5 的事实层、利润层与多平台聚合口径必须先稳定**
   - 影响：A2, A3, B2, C1, C2
   - 说明：如果库存、利润、平台快照、地区化聚合口径不稳定，Stage 6 自动化只会放大错误

2. **自动动作的默认执行边界与高风险动作策略需先明确**
   - 影响：B3, B4, C4, D3
   - 说明：如果哪些动作可自动执行、哪些必须审批没有清晰边界，控制平面将难以落地且风险过高

### 软 blocker

1. **生命周期状态迁移阈值需统一**
   - 影响：A1, A2
   - 说明：如果 testing / scaling / stable / declining / clearance 的进入条件不稳定，生命周期会频繁抖动

2. **异常检测阈值和证据口径需统一**
   - 影响：C1, C2
   - 说明：sales drop、refund spike、margin collapse、stockout risk 的判定标准不稳定会导致异常过多或漏报

3. **override 优先级与过期规则需明确**
   - 影响：D1, D2
   - 说明：人工覆盖若没有统一优先级和有效期规则，会与自动规则长期冲突

4. **回滚支持范围需确认**
   - 影响：D3, E4
   - 说明：并非所有动作都天然可回滚，需要先明确调价、内容版本、listing 状态等支持范围

5. **控制台 API 返回结构与敏感字段过滤需统一**
   - 影响：C3, C4
   - 说明：如果聚合返回结构经常变化，后续 UI 和调试工具难以稳定复用

---

## 7. 建议 owner lane

### Backend Lifecycle Lane A（生命周期引擎）
负责：
- A1
- A2
- A3

### Backend Action Lane B（自动动作引擎）
负责：
- B1
- B2
- B3
- B4

### Backend Control Plane Lane C（异常检测与控制台）
负责：
- C1
- C2
- C3
- C4

### Backend Override Lane D（人工覆盖与回滚）
负责：
- D1
- D2
- D3

### QA / Automation Lane
负责：
- E1
- E2
- E3
- E4
- E5

### 推荐协作原则
- Lifecycle Lane 优先把状态判断做成规则型、可解释、可审计，而不是直接堆复杂模型
- Action Lane 的职责是编排动作，不接管 Stage 3-5 的事实计算逻辑
- Control Plane Lane 负责聚合异常、审批、建议和待处理事项，不应重新实现底层业务规则
- Override Lane 必须优先保证“人工覆盖优先于自动规则”的边界明确
- QA / Automation Lane 应从 Batch 2 开始持续介入，避免等控制台和审批功能完成后再一次性补测试

---

## 8. 实际开工建议

### 第一周优先级
- S6-A1
- S6-B1
- S6-C1
- S6-D1

### 第二周优先级
- S6-A2
- S6-A3
- S6-B2
- S6-D2

### 第三周优先级
- S6-B3
- S6-B4
- S6-C2
- S6-C3
- S6-E1
- S6-E2

### 第四周优先级
- S6-C4
- S6-D3
- S6-E3
- S6-E4
- S6-E5

> 注：如果目标是尽快让 Stage 6 的自动化控制平面形成最小可用版本，建议先完成 A1-A3 + B1-B3 + C1-C2 + D1-D2 的“生命周期判断 + 动作建议 + 异常视图 + 人工覆盖”子集，再补审批流、关键动作深接入与回滚增强。

---

## 9. 推荐在项目管理工具中的字段

建议每个 backlog item 记录：
- `ID`：如 `S6-B3`
- `Title`
- `Type`：Schema / Service / Rules / Integration / Aggregation / API / Approval / Audit / Test / Verification
- `Batch`
- `Owner Lane`
- `Dependencies`
- `Automation Dependency`
- `Status`
- `PR`
- `Definition of Done`

---

## 10. 最小闭环定义（建议先达成）

如果希望尽快交付 Stage 6 的最小可用版本，建议先完成以下子集：

### Stage 6 MVP 子集
- A1
- A2
- A3
- B1
- B2
- B3
- C1
- C2
- D1
- D2
- E1
- E2
- E3

这可以先形成：

```text
SKU 生命周期判断
+ 自动动作建议 / dry-run / suggest-only
+ 经营异常检测
+ 控制台聚合视图
+ 人工覆盖优先级
```

### 完整 Stage 6
在 MVP 子集基础上再补：
- B4
- C3
- C4
- D3
- E4
- E5

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
