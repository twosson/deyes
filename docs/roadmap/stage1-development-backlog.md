# Stage 1 可执行开发 Backlog

> 基于 `docs/roadmap/stage1-implementation-tasks.md` 拆解的执行版 backlog。
>
> 目标：把 Stage 1 从“规划任务清单”进一步落到“可排期、可分工、可切 PR、可追踪 blocker”的开发执行层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 1. 使用说明

本文档用于把 Stage 1 的 17 个规划任务，进一步转化为：
- 开发批次
- owner lane
- blocker 标记
- 推荐 PR 切分
- 完成定义（Definition of Done）

建议在项目管理工具中映射为：
- Epic = Stage 1
- Milestone = Batch 1 / 2 / 3 / 4
- Feature = 分组 A / B / C / D / E
- Story = 每个 backlog item

---

## 2. Stage 1 执行目标

### 业务目标
让系统从“能选品、能上架”升级为“能看到真实结果，并能开始进行 A/B 测试与平台同步”。

### 开发目标
在不破坏现有主链路的前提下，为系统新增：
1. 表现数据持久化层
2. 表现数据回流服务
3. A/B 测试基础设施
4. 真实平台同步能力
5. 对应测试与验证链路

### 完成定义（Stage 1 DoD）
- [ ] `ListingPerformanceDaily` 和 `AssetPerformanceDaily` 已落表
- [ ] 表现数据可通过 service 写入和查询
- [ ] ContentAsset 支持 `variant_group`
- [ ] 可生成多变体素材
- [ ] A/B 测试可识别赢家并支持 promotion
- [ ] Temu 真实 API 能完成最小同步闭环
- [ ] Stage 1 新增测试可跑通
- [ ] 现有核心回归不退化

---

## 3. 推荐执行批次

### Batch 1：基础数据层与回流服务骨架

**目标**：先把 schema 和基础 service 打牢，形成结果层的最小可用基础。

包含任务：
- A1. ListingPerformanceDaily Schema
- A2. AssetPerformanceDaily Schema
- A3. ContentAsset.variant_group
- B1. ListingMetricsService
- B2. AssetPerformanceService

建议 owner lane：
- **Backend Lane A**：A1 + A2 + A3
- **Backend Lane B**：B1 + B2

完成标志：
- migration 可运行
- 两类 performance service 可写入 / 查询
- 不需要真实平台 credentials 即可在本地验证

---

### Batch 2：同步编排与基础测试

**目标**：把数据回流服务和平台同步框架串起来，并为 Batch 1 建立测试保护网。

包含任务：
- B3. PlatformSyncService
- C1. ContentAssetManagerAgent 多变体生成
- E1. ListingPerformanceDaily 模型测试
- E2. ListingMetricsService 测试

建议 owner lane：
- **Backend Lane A**：B3
- **Agent Lane**：C1
- **QA / Backend Lane**：E1 + E2

完成标志：
- PlatformSyncService 具备清晰的同步入口
- ContentAssetManagerAgent 能生成多变体
- Batch 1 核心变更已有自动化测试保护

---

### Batch 3：A/B 测试管理与 Temu 真实 API

**目标**：建立可经营闭环中的“内容测试”和“真实平台连接”两条关键能力。

包含任务：
- C2. ABTestManager
- C3. Winner Promotion
- D1. Temu 真实 API 集成
- E3. ABTestManager 测试

建议 owner lane：
- **Agent Lane**：C2 + C3
- **Platform Integration Lane**：D1
- **QA Lane**：E3

完成标志：
- 可创建和管理 A/B 测试
- Winner promotion 可追溯
- Temu adapter 能走通最小真实 API 链路

---

### Batch 4：平台扩展、定时同步与集成/E2E 验证

**目标**：把 Stage 1 从“单平台最小闭环”推进到“具备扩展性和验证能力的稳定包”。

包含任务：
- D2. Amazon SP-API Adapter
- D3. Celery 定时同步任务
- E4. Temu 集成测试
- E5. Stage 1 E2E 测试

建议 owner lane：
- **Platform Integration Lane**：D2 + D3
- **QA / Integration Lane**：E4 + E5

完成标志：
- 定时同步框架可运行
- Temu integration test 可在 credentials 环境运行
- 端到端用例可验证完整链路

---

## 4. 可执行 Backlog 明细

> 状态建议使用：`todo / ready / blocked / in_progress / in_review / done`

### 4.1 Batch 1 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S1-A1 | 新增 ListingPerformanceDaily 模型与 migration | Schema | Backend | 无 | 无 | ready |
| S1-A2 | 新增 AssetPerformanceDaily 模型并并入 performance migration | Schema | Backend | 无 | 无 | ready |
| S1-A3 | 为 ContentAsset 增加 variant_group 字段与 migration | Schema | Backend | 无 | 无 | ready |
| S1-B1 | 实现 ListingMetricsService 的 ingest/query/ctr 逻辑 | Service | Backend | A1 | 无 | todo |
| S1-B2 | 实现 AssetPerformanceService 的 ingest/query/top-assets 逻辑 | Service | Backend | A2 | 无 | todo |

### 4.2 Batch 2 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S1-B3 | 实现 PlatformSyncService 骨架与 retry/logging | Service | Backend | B1, B2 | 部分依赖平台 adapter 接口稳定性 | todo |
| S1-C1 | 扩展 ContentAssetManagerAgent 支持 variant_count 与 variant_group | Agent | Agent | A3 | 无 | todo |
| S1-E1 | 编写 ListingPerformanceDaily 模型测试 | Test | QA/Backend | A1 | 无 | todo |
| S1-E2 | 编写 ListingMetricsService 测试 | Test | QA/Backend | B1 | 无 | todo |

### 4.3 Batch 3 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S1-C2 | 新增 ABTestManager Agent 框架 | Agent | Agent | C1, B2 | 无 | todo |
| S1-C3 | 实现 winner promotion 工作流 | Agent/Workflow | Agent | C2 | 可能依赖 listing-asset 关系细节 | todo |
| S1-D1 | 把 TemuAdapter 从 mock 升级为真实 API | Platform | Platform Integration | B3 | **Temu 账号与 API credentials** | blocked |
| S1-E3 | 编写 ABTestManager 测试 | Test | QA | C2, C3 | 无 | todo |

### 4.4 Batch 4 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S1-D2 | 新增 Amazon SP-API Adapter | Platform | Platform Integration | D1 经验复用，但技术上可并行 | **Amazon Seller 账号与 SP-API credentials** | blocked |
| S1-D3 | 新增平台同步 Celery 定时任务与 beat 配置 | Task/Infra | Backend/Platform | B3 | Celery 环境配置 | todo |
| S1-E4 | 编写 Temu 真实 API 集成测试 | Integration Test | QA/Platform | D1 | **Temu credentials 与测试环境** | blocked |
| S1-E5 | 编写 Stage 1 E2E 测试 | E2E Test | QA/Backend | B3, C2, C3 | 依赖前序核心能力稳定 | todo |

---

## 5. 推荐 PR 切分

### PR 1：Performance schema foundation
包含：
- A1
- A2
- A3

目标：
- 先把 DB schema 与 migration 落地
- 变更面集中在 models + migrations

---

### PR 2：Performance services foundation
包含：
- B1
- B2
- E1
- E2

目标：
- 在 schema 稳定后补 service 和基础测试
- 保证回流层先具备最小可测性

---

### PR 3：Platform sync skeleton + asset variants
包含：
- B3
- C1

目标：
- 把平台同步编排和多变体生成能力接上
- 保持与真实平台 API 集成解耦

---

### PR 4：A/B testing management
包含：
- C2
- C3
- E3

目标：
- 把内容测试从“能生成多变体”推进到“能识别赢家并推进更新”

---

### PR 5：Temu real adapter
包含：
- D1
- 必要的 adapter tests / mocks

目标：
- 单独处理高风险外部依赖变更
- 避免真实平台逻辑和通用业务逻辑混在一个 PR

---

### PR 6：Scheduled sync + integration verification
包含：
- D3
- E4
- E5

目标：
- 在真实平台集成可用后，再补定时同步与高层验证

---

### PR 7：Amazon adapter（可独立延后）
包含：
- D2

目标：
- 作为独立平台扩展包，不阻塞 Temu 成为 Stage 1 主平台闭环

---

## 6. Blocker 与外部依赖清单

### 硬 blocker

1. **Temu Seller 账号与 API credentials**
   - 影响：D1, E4
   - 说明：没有 credentials，Temu 真实 API 与集成测试无法完成

2. **Amazon Seller 账号与 SP-API credentials**
   - 影响：D2
   - 说明：Amazon adapter 不能作为默认阻塞项卡住 Stage 1 主路径，建议后置或并行单独推进

### 软 blocker

1. **Celery beat / worker 运行环境**
   - 影响：D3
   - 说明：如果当前环境未固化调度基础设施，可先完成 task 代码，后补真实调度验证

2. **ListingAssetAssociation / asset-listing 映射边界**
   - 影响：C3
   - 说明：winner promotion 依赖 listing 与素材绑定关系稳定

3. **平台 adapter 抽象边界是否已稳定**
   - 影响：B3, D1, D2
   - 说明：若 adapter 接口仍频繁变化，建议先固定 PlatformAdapter 约定

---

## 7. 建议 owner lane

### Backend Lane
负责：
- A1
- A2
- A3
- B1
- B2
- B3
- D3

### Agent Lane
负责：
- C1
- C2
- C3

### Platform Integration Lane
负责：
- D1
- D2

### QA / Verification Lane
负责：
- E1
- E2
- E3
- E4
- E5

### 推荐协作原则
- Backend Lane 优先保障 schema 与 service 稳定
- Agent Lane 不要等待真实平台集成，可先基于 mock / local data 完成 A/B 基础能力
- Platform Integration Lane 单独节奏推进，避免外部 API 卡住整体节奏
- QA Lane 从 Batch 2 开始持续介入，不要等到最后统一补测试

---

## 8. 实际开工建议

### 第一周优先级
- S1-A1
- S1-A2
- S1-A3
- S1-B1
- S1-B2

### 第二周优先级
- S1-B3
- S1-C1
- S1-E1
- S1-E2

### 第三周优先级
- S1-C2
- S1-C3
- S1-D1（若 credentials 就绪）
- S1-E3

### 第四周优先级
- S1-D3
- S1-E5
- S1-E4（若 Temu 环境就绪）
- S1-D2（如果 Amazon 条件已成熟，否则延期）

> 注：如果平台 credentials 未就绪，建议不要让 D1 / D2 卡住 Stage 1 其他任务。Stage 1 的核心闭环可以先以 Temu 为目标主平台推进，Amazon 作为 Stage 1.5 或并行扩展包处理。

---

## 9. 推荐在项目管理工具中的字段

建议每个 backlog item 记录：
- `ID`：如 `S1-A1`
- `Title`
- `Type`：Schema / Service / Agent / Platform / Test / Infra
- `Batch`
- `Owner Lane`
- `Dependencies`
- `External Dependency`
- `Status`
- `PR`
- `Definition of Done`

---

## 10. 最小闭环定义（建议先达成）

如果希望尽快交付 Stage 1 的最小可用版本，建议先完成以下子集：

### Stage 1 MVP 子集
- A1
- A2
- A3
- B1
- B2
- B3
- C1
- C2（最小版）
- E1
- E2

这可以先形成：

```text
Listing / Asset 表现数据回流
+ 多变体素材生成
+ A/B 测试框架骨架
```

### 完整 Stage 1
在 MVP 子集基础上再补：
- C3
- D1
- D2
- D3
- E3
- E4
- E5

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
