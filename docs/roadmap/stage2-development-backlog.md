# Stage 2 可执行开发 Backlog

> 基于 `docs/roadmap/stage2-implementation-tasks.md` 拆解的执行版 backlog。
>
> 目标：把 Stage 2 从“反馈引擎实施清单”进一步落到“可排期、可分工、可切 PR、可追踪 blocker”的开发执行层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 1. 使用说明

本文档用于把 Stage 2 的 18 个规划任务，进一步转化为：
- 开发批次
- owner lane
- blocker 标记
- 推荐 PR 切分
- MVP 子集
- 完成定义（Definition of Done）

建议在项目管理工具中映射为：
- Epic = Stage 2
- Milestone = Batch 1 / 2 / 3 / 4
- Feature = 分组 A / B / C / D / E
- Story = 每个 backlog item

---

## 2. Stage 2 执行目标

### 业务目标
让系统从“历史先验加分”升级为“经营结果驱动反馈引擎”，使真实经营结果可以显著影响选品 recall、ranking 和解释性输出。

### 开发目标
在不破坏现有 Phase 1-6 主链路语义的前提下，为系统新增：
1. 可复现的反馈聚合口径
2. style / platform-region / price band prior
3. 负反馈 penalty 机制
4. Adapter 注入与 candidate 特征推断
5. 解释性输出、调试接口与测试保护网

### 完成定义（Stage 2 DoD）
- [ ] style prior 已可查询和使用
- [ ] platform-region prior 已可查询和使用
- [ ] price band prior 已可查询和使用
- [ ] negative feedback penalty 已可查询和使用
- [ ] 1688 adapter 已接入 Stage 2 反馈信号
- [ ] `normalized_attributes` 可观测新增反馈信号
- [ ] explanation payload 可说明加分 / 降权原因
- [ ] Stage 2 测试通过，Phase 1-6 原语义不退化

---

## 3. 推荐执行批次

### Batch 1：反馈口径与基础特征层

**目标**：先定义反馈口径，建立 price band 与 style taxonomy 这样的基础特征工具，为后续 prior 聚合提供统一输入。

包含任务：
- A1. 反馈聚合口径规范
- A2. PriceBandService
- A3. StyleTaxonomyService
- B1. style prior（最先接入的一类新 prior）

建议 owner lane：
- **Backend/Data Lane**：A1
- **Backend Feature Lane**：A2 + A3
- **Feedback Lane**：B1

完成标志：
- style / asset pattern / price band 的基础语义已稳定
- style prior 可单独工作
- 不需要改动 adapter 即可先验证聚合逻辑

---

### Batch 2：核心 prior 扩展与可观测信号

**目标**：补齐 platform-region / price band / negative penalty，并先把关键结果打到可观测字段里。

包含任务：
- B2. platform-region prior
- B3. price band prior
- B4. negative feedback penalty
- D1. normalized_attributes 调试信号扩展

建议 owner lane：
- **Feedback Lane**：B2 + B3 + B4
- **Adapter Lane**：D1

完成标志：
- Stage 2 核心 prior/penalty 能独立查询
- normalized_attributes 中能看到关键反馈信号
- 为后续 adapter 注入和测试打基础

---

### Batch 3：聚合服务抽离、adapter 注入与核心测试

**目标**：把聚合逻辑从 FeedbackAggregator 中抽离，并正式接入 1688 adapter 的 recall/ranking 路径。

包含任务：
- B5. PerformanceAggregatorService
- C1. historical feedback score 注入点扩展
- C2. candidate style / price band 推断
- E1. FeedbackAggregator 测试扩展
- E2. 1688 Adapter 聚焦测试

建议 owner lane：
- **Feedback Architecture Lane**：B5
- **Adapter Lane**：C1 + C2
- **QA / Regression Lane**：E1 + E2

完成标志：
- FeedbackAggregator 成为轻量 facade
- adapter 已实际消费 Stage 2 prior/penalty
- 有自动化测试确保 recall/ranking/observability 路径稳定

---

### Batch 4：排序策略收口、解释器与调试能力

**目标**：把 Stage 2 从“功能可用”推进到“行为更稳、解释更清晰、便于验证与调试”。

包含任务：
- C3. 降权不淘汰排序策略
- D2. FeedbackExplanationService
- D3. 反馈调试 API（可选）
- E3. 反馈解释器测试
- E4. Stage 2 回归验证套件

建议 owner lane：
- **Adapter/Ranking Lane**：C3
- **Explainability Lane**：D2 + D3
- **QA / Verification Lane**：E3 + E4

完成标志：
- penalty 不会导致过早误杀候选
- explanation payload 可供调试和 UI 复用
- 验证命令和手工 checklist 完整

---

## 4. 可执行 Backlog 明细

> 状态建议使用：`todo / ready / blocked / in_progress / in_review / done`

### 4.1 Batch 1 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S2-A1 | 编写 Stage 2 反馈聚合口径规范文档 | Spec | Backend/Data | Stage 1 数据模型已存在 | 无 | ready |
| S2-A2 | 新增 PriceBandService 并实现 resolve_price_band | Service | Backend Feature | 无 | 类目与价格字段口径需确认 | ready |
| S2-A3 | 新增 StyleTaxonomyService 并统一 style_tags / asset_pattern 语义 | Service | Backend Feature | Stage 1 ContentAsset 数据结构稳定 | 现有 style_tags 离散度可能较高 | ready |
| S2-B1 | 在 FeedbackAggregator 中实现 style prior | Feedback | Feedback Lane | A1, A3 | 依赖 style 标签质量 | todo |

### 4.2 Batch 2 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S2-B2 | 在 FeedbackAggregator 中实现 platform-region prior | Feedback | Feedback Lane | A1 | Stage 1 的 platform / region 数据完整度 | todo |
| S2-B3 | 在 FeedbackAggregator 中实现 price band prior | Feedback | Feedback Lane | A1, A2 | 平台价格字段一致性 | todo |
| S2-B4 | 在 FeedbackAggregator 中实现 negative feedback penalty | Feedback | Feedback Lane | A1, B1, B2, B3 | 负反馈阈值需保守，避免误杀 | todo |
| S2-D1 | 扩展 normalized_attributes 输出 Stage 2 调试信号 | Adapter/Observability | Adapter Lane | B1, B2, B3, B4 | 字段命名需保持稳定 | todo |

### 4.3 Batch 3 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S2-B5 | 抽离 PerformanceAggregatorService 并收口 FeedbackAggregator | Refactor/Service | Feedback Architecture | B1, B2, B3, B4 | 聚合逻辑拆分时需避免接口漂移 | todo |
| S2-C1 | 在 1688 adapter 中注入 Stage 2 prior 与 penalty | Adapter | Adapter Lane | B2, B3, B4, B5 | 必须保持 final_score 语义不变 | todo |
| S2-C2 | 为 candidate 推断 style / price_band 特征并注入 normalized_attributes | Adapter | Adapter Lane | A2, A3, C1 | raw_payload / normalized_attributes 字段可能不一致 | todo |
| S2-E1 | 扩展 FeedbackAggregator 单元测试 | Test | QA/Regression | B1, B2, B3, B4, B5 | 无 | todo |
| S2-E2 | 扩展 1688 Adapter Stage 2 聚焦测试 | Test | QA/Regression | C1, C2, D1 | 无 | todo |

### 4.4 Batch 4 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S2-C3 | 实现“降权不淘汰”的排序策略与 penalty 下限 | Ranking | Adapter/Ranking | C1, B4 | 排序稳定性需要反复校正 | todo |
| S2-D2 | 新增 FeedbackExplanationService | Explainability | Explainability Lane | B5, C1, D1 | explanation 结构需先统一 | todo |
| S2-D3 | 新增反馈调试 API（可选） | API/Debug | Explainability/API | D2 | 是否暴露到默认测试环境需确认 | todo |
| S2-E3 | 新增 FeedbackExplanationService 测试 | Test | QA | D2 | 无 | todo |
| S2-E4 | 编写 Stage 2 回归验证 checklist | Verification | QA | E1, E2, E3 | 无 | todo |

---

## 5. 推荐 PR 切分

### PR 1：Feedback spec + feature primitives
包含：
- A1
- A2
- A3

目标：
- 先统一 Stage 2 反馈口径
- 落基础特征服务，不直接耦合 adapter

---

### PR 2：Core priors and penalty in FeedbackAggregator
包含：
- B1
- B2
- B3
- B4

目标：
- 先让 FeedbackAggregator 具备完整的 Stage 2 prior / penalty 能力
- 不着急做大范围结构重构

---

### PR 3：Observability signals
包含：
- D1

目标：
- 尽早把 feedback signals 暴露出来
- 便于测试、调试和人工校验

---

### PR 4：Aggregator architecture refactor
包含：
- B5

目标：
- 在功能正确后再抽离聚合逻辑
- 降低一次性大改引入回归风险

---

### PR 5：Adapter injection
包含：
- C1
- C2
- E1
- E2

目标：
- 正式把 Stage 2 反馈信号打进 recall / ranking / normalized_attributes
- 同时配套核心回归测试

---

### PR 6：Ranking stabilization + explainability
包含：
- C3
- D2
- E3
- E4

目标：
- 完善排序策略与 explanation 层
- 补足验证和解释能力

---

### PR 7：Feedback debug API（可独立后置）
包含：
- D3

目标：
- 作为调试增强项独立推进
- 不阻塞 Stage 2 主路径交付

---

## 6. Blocker 与外部依赖清单

### 硬 blocker

1. **Stage 1 数据质量与字段完整度**
   - 影响：B1, B2, B3, B4, C1, C2
   - 说明：如果 `ListingPerformanceDaily`、`AssetPerformanceDaily`、`PlatformListing`、`SupplierMatch` 数据不足，Stage 2 的 prior/penalty 只能停留在逻辑完成，难以形成真实验证闭环

### 软 blocker

1. **style_tags 离散度和历史质量不稳定**
   - 影响：A3, B1, C2
   - 说明：如果现有 style_tags 很脏，style prior 的收益会被大幅削弱

2. **platform / region / category 字段口径可能不统一**
   - 影响：A1, B2
   - 说明：platform-region prior 的稳定性依赖平台与地区字段标准化

3. **platform_price / pricing assessment 口径不一致**
   - 影响：A2, B3
   - 说明：price band prior 需要明确使用哪个价格来源作为 band 计算输入

4. **FeedbackAggregator 结构可能已偏重，抽离时有接口漂移风险**
   - 影响：B5, C1, D2
   - 说明：建议先做完整功能，再做聚合逻辑抽离

5. **adapter 中 candidate 原始字段来源不稳定**
   - 影响：C2
   - 说明：style / price_band 推断可能需要兼容 raw_payload、normalized_attributes、content 数据多个来源

---

## 7. 建议 owner lane

### Backend/Data Lane
负责：
- A1
- A2
- A3

### Feedback Lane
负责：
- B1
- B2
- B3
- B4

### Feedback Architecture Lane
负责：
- B5

### Adapter / Ranking Lane
负责：
- C1
- C2
- C3
- D1

### Explainability / API Lane
负责：
- D2
- D3

### QA / Regression Lane
负责：
- E1
- E2
- E3
- E4

### 推荐协作原则
- Feedback Lane 先把 prior/penalty 算法做稳定，再交给 Adapter Lane 接入
- Adapter Lane 在 Stage 2 中最关键的职责是“接入但不破坏现有排序语义”
- Explainability 不要过早先行，应建立在可稳定输出的 feedback signals 之上
- QA / Regression Lane 应从 Batch 2 就开始介入，避免等到 adapter 接完后再一次性补测试

---

## 8. 实际开工建议

### 第一周优先级
- S2-A1
- S2-A2
- S2-A3
- S2-B1

### 第二周优先级
- S2-B2
- S2-B3
- S2-B4
- S2-D1

### 第三周优先级
- S2-B5
- S2-C1
- S2-C2
- S2-E1
- S2-E2

### 第四周优先级
- S2-C3
- S2-D2
- S2-E3
- S2-E4
- S2-D3（如需要）

> 注：如果目标是尽快让 Stage 2 对 recall / ranking 生效，可以在 B5 抽离前先完成 B1-B4 + C1 + D1 的最小接入路径，再做结构重构。

---

## 9. 推荐在项目管理工具中的字段

建议每个 backlog item 记录：
- `ID`：如 `S2-B3`
- `Title`
- `Type`：Spec / Service / Feedback / Adapter / Ranking / Explainability / API / Test / Verification
- `Batch`
- `Owner Lane`
- `Dependencies`
- `Data Dependency`
- `Status`
- `PR`
- `Definition of Done`

---

## 10. 最小闭环定义（建议先达成）

如果希望尽快交付 Stage 2 的最小可用版本，建议先完成以下子集：

### Stage 2 MVP 子集
- A1
- A2
- A3
- B1
- B2
- B3
- B4
- C1（最小版）
- D1
- E1
- E2

这可以先形成：

```text
style / platform-region / price-band priors
+ negative feedback penalty
+ recall / ranking 接入
+ normalized_attributes 可观测信号
```

### 完整 Stage 2
在 MVP 子集基础上再补：
- B5
- C2
- C3
- D2
- D3
- E3
- E4

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
