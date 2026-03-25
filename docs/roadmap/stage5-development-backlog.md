# Stage 5 可执行开发 Backlog

> 基于 `docs/roadmap/stage5-implementation-tasks.md` 拆解的执行版 backlog。
>
> 目标：把 Stage 5 从“多平台统一经营中枢实施清单”进一步落到“可排期、可分工、可切 PR、可追踪 blocker”的开发执行层。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 1. 使用说明

本文档用于把 Stage 5 的 20 个规划任务，进一步转化为：
- 开发批次
- owner lane
- blocker 标记
- 推荐 PR 切分
- MVP 子集
- 完成定义（Definition of Done）

建议在项目管理工具中映射为：
- Epic = Stage 5
- Milestone = Batch 1 / 2 / 3 / 4
- Feature = 分组 A / B / C / D / E
- Story = 每个 backlog item

---

## 2. Stage 5 执行目标

### 业务目标
让系统从“单平台可经营闭环 + ERP Lite 事实层”升级为“多平台统一经营中枢”，让同一 SKU 能跨平台统一管理状态、库存、价格、表现与利润。

### 开发目标
在不破坏现有主链路的前提下，为系统新增：
1. PlatformRegistry / AdapterResolver 与 UnifiedListingService 统一平台接入层
2. PlatformPolicy / CategoryMapping / PricingRule / ContentRule 平台策略层
3. ExchangeRate / RegionTaxRule / RegionRiskRule 与 CurrencyConverter 地区化规则层
4. LocalizedContent / LocalizationService 多语言与本地化内容基础设施
5. SKU / platform / region 维度跨平台经营聚合视图

### 完成定义（Stage 5 DoD）
- [ ] `PlatformListing` 已可稳定承载多平台 / 多地区 / 多市场语义
- [ ] `PlatformPolicy` / `PlatformCategoryMapping` / `PlatformPricingRule` / `PlatformContentRule` 已可查询和使用
- [ ] `CurrencyConverter` 已可做多币种换算
- [ ] 地区化价格、税费、净利换算可工作
- [ ] `LocalizedContent` 已可创建、查询并支持 fallback
- [ ] 同一 SKU 的跨平台经营快照可查询
- [ ] 平台差异化逻辑已部分从 adapter 抽离到策略层
- [ ] Stage 5 测试通过，Stage 1-4 核心回归不受影响

---

## 3. 推荐执行批次

### Batch 1：多平台经营中枢的基础 Schema 层

**目标**：先把多平台 listing、平台策略、地区规则、本地化内容四类基础实体落表，为 Stage 5 的统一经营能力提供事实层与规则层基础。

包含任务：
- A1. 扩展 PlatformListing 支持多平台统一状态管理
- B1. PlatformPolicy / PlatformCategoryMapping Schema
- C1. ExchangeRate / RegionTaxRule / RegionRiskRule Schema
- D1. LocalizedContent / ContentTemplate / ContentVersion Schema

建议 owner lane：
- **Backend Multiplatform Lane A**：A1
- **Backend Policy Lane B**：B1
- **Backend Regional Lane C**：C1
- **Backend Localization Lane D**：D1

完成标志：
- 多平台、平台策略、地区规则、本地化内容四类基础模型已落表
- migration 可运行
- 不依赖真实平台 API 即可先验证 schema 稳定性

---

### Batch 2：统一接入与策略服务基础

**目标**：在 schema 稳定后补齐平台接入、策略读取、币种换算和本地化内容服务，让 Stage 5 的核心服务骨架先可独立工作。

包含任务：
- A2. PlatformRegistry / AdapterResolver
- B2. PlatformPricingRule / PlatformContentRule Schema
- B3. PlatformPolicyService
- C2. CurrencyConverter
- D2. LocalizationService

建议 owner lane：
- **Backend Multiplatform Lane A**：A2
- **Backend Policy Lane B**：B2 + B3
- **Backend Regional Lane C**：C2
- **Backend Localization Lane D**：D2

完成标志：
- 平台适配器可统一注册和解析
- 平台策略可按平台 / 市场 / 地区读取
- 币种换算能力可独立使用
- 本地化内容服务可创建、查询和校验内容

---

### Batch 3：统一 listing 流程、地区化定价与基础测试

**目标**：把平台接入层、策略层、地区规则层和本地化内容层接入真实发布路径，并建立首批自动化测试保护网。

包含任务：
- A3. UnifiedListingService
- A4. 跨平台 SKU 经营视图
- B4. listing 创建/更新接入策略层
- C3. 地区化定价与利润换算接口
- D3. listing 发布流程接入本地化内容
- E1. 统一 listing 与平台策略测试
- E2. 多币种与地区化测试

建议 owner lane：
- **Backend Multiplatform Lane A**：A3
- **Backend Hub / Integration Lane**：A4
- **Backend Policy Lane B**：B4
- **Backend Regional Lane C**：C3
- **Backend Localization Lane D**：D3
- **QA / Multiplatform Lane**：E1 + E2

完成标志：
- 统一 listing 创建 / 更新 / 同步入口可工作
- listing 流程已消费平台策略与本地化内容
- 地区化价格与利润换算可输出结构化结果
- 核心平台接入与地区化路径已有自动化测试保护

---

### Batch 4：跨平台聚合、本地化验证与回归收口

**目标**：把 Stage 5 从“多平台流程可用”推进到“跨平台经营可聚合、可验证、可回归”。

包含任务：
- C4. Region / Platform 经营聚合接口
- E3. 本地化内容测试
- E4. 跨平台经营聚合测试
- E5. Stage 5 回归验证套件

建议 owner lane：
- **Backend Hub / Integration Lane**：C4
- **QA / Multiplatform Lane**：E3 + E4 + E5

完成标志：
- 地区 / 平台地区经营结果可查询
- 本地化内容与跨平台快照行为可验证
- Stage 5 回归命令和 checklist 完整

---

## 4. 可执行 Backlog 明细

> 状态建议使用：`todo / ready / blocked / in_progress / in_review / done`

### 4.1 Batch 1 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S5-A1 | 扩展 PlatformListing 支持多平台统一状态 Schema 与 migration | Schema | Backend Multiplatform A | 无 | 旧数据兼容与 listing 状态语义需保持稳定 | ready |
| S5-B1 | 新增 PlatformPolicy / PlatformCategoryMapping Schema 与 migration | Schema | Backend Policy B | 无 | 平台类目映射口径需先统一 | ready |
| S5-C1 | 新增 ExchangeRate / RegionTaxRule / RegionRiskRule Schema 与 migration | Schema | Backend Regional C | 无 | 税费与风险规则优先级需明确 | ready |
| S5-D1 | 新增 LocalizedContent / ContentTemplate / ContentVersion Schema 与 migration | Schema | Backend Localization D | 无 | 与 ContentAsset 的边界需明确 | ready |

### 4.2 Batch 2 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S5-A2 | 实现 PlatformRegistry / AdapterResolver 与平台能力矩阵 | Service | Backend Multiplatform A | 无 | 平台 adapter 抽象边界需先稳定 | todo |
| S5-B2 | 新增 PlatformPricingRule / PlatformContentRule Schema 与版本管理 | Schema | Backend Policy B | B1 | 规则作用范围需明确到 platform / marketplace / category | todo |
| S5-B3 | 实现 PlatformPolicyService 与 fallback 读取逻辑 | Service | Backend Policy B | B1, B2 | 类目映射与 payload 校验口径需统一 | todo |
| S5-C2 | 实现 CurrencyConverter 与汇率缺失 fallback | Service | Backend Regional C | C1 | 汇率来源与刷新策略需确认 | todo |
| S5-D2 | 实现 LocalizationService 与 locale fallback 逻辑 | Service | Backend Localization D | D1, B2 | locale / marketplace fallback 策略需统一 | todo |

### 4.3 Batch 3 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S5-A3 | 实现 UnifiedListingService 与统一 listing 创建/更新/同步入口 | Service | Backend Multiplatform A | A1, A2 | 平台 adapter 返回结构与错误语义需统一 | todo |
| S5-A4 | 增加 SKU 跨平台经营快照接口 | Service/Aggregation | Backend Hub/Integration | A3, C3 | 平台价格、库存、利润聚合口径需统一 | todo |
| S5-B4 | 把 listing 创建/更新流程接入平台策略层 | Service/Integration | Backend Policy B | A3, B2, B3 | payload 校验失败的结构化错误格式需统一 | todo |
| S5-C3 | 扩展地区化定价与利润换算接口 | Service/Rules | Backend Regional C | C1, C2, B3 | 本位币与本地币利润比较口径需统一 | todo |
| S5-D3 | 把 listing 发布流程接入本地化内容 | Service/Integration | Backend Localization D | A3, D2, B2 | locale 解析与内容版本选择规则需统一 | todo |
| S5-E1 | 新增统一 listing 与平台策略测试 | Test | QA/Multiplatform | A2, A3, B3, B4 | 无 | todo |
| S5-E2 | 新增多币种与地区化测试 | Test | QA/Multiplatform | C1, C2, C3 | 无 | todo |

### 4.4 Batch 4 Backlog

| ID | 标题 | 类型 | Owner Lane | 依赖 | Blocker | 推荐状态 |
|----|------|------|------------|------|---------|---------|
| S5-C4 | 建立 Region / Platform 经营聚合接口 | Service/Aggregation | Backend Hub/Integration | A4, C3 | region / platform 经营指标口径需统一 | todo |
| S5-E3 | 新增本地化内容测试 | Test | QA/Multiplatform | D1, D2, D3 | 无 | todo |
| S5-E4 | 新增跨平台经营聚合测试 | Test | QA/Multiplatform | A4, C4, B4 | 无 | todo |
| S5-E5 | 编写 Stage 5 回归验证 checklist | Verification | QA/Multiplatform | E1, E2, E3, E4 | 无 | todo |

---

## 5. 推荐 PR 切分

### PR 1：Multiplatform schema foundation
包含：
- A1
- B1
- C1
- D1

目标：
- 先把多平台、策略、地区规则、本地化内容的基础 schema 落地
- 变更面集中在 models + migrations

---

### PR 2：Platform registry and policy foundation
包含：
- A2
- B2
- B3

目标：
- 统一平台适配器解析与平台策略读取
- 为后续统一 listing 服务打基础

---

### PR 3：Currency and localization services
包含：
- C2
- D2

目标：
- 补多币种换算与本地化内容服务骨架
- 保持与真实平台发布逻辑解耦

---

### PR 4：Unified listing orchestration
包含：
- A3
- B4
- E1

目标：
- 建立统一 listing 创建/更新/同步入口
- 让平台策略正式接入发布路径并配套基础测试

---

### PR 5：Regional pricing and localized publishing
包含：
- C3
- D3
- E2
- E3

目标：
- 建立地区化价格/利润换算与本地化发布能力
- 配套地区化与本地化测试

---

### PR 6：Multiplatform hub snapshots
包含：
- A4
- C4
- E4

目标：
- 输出 SKU 跨平台经营快照与地区经营聚合
- 配套跨平台聚合测试

---

### PR 7：Stage 5 verification pack
包含：
- E5

目标：
- 收口 Stage 5 回归命令与手工验证入口
- 不把验证工作拖到后续 Stage 6

---

## 6. Blocker 与外部依赖清单

### 硬 blocker

1. **Stage 3-4 的 SKU / Inventory / Profit 事实层必须先稳定**
   - 影响：A4, C3, C4
   - 说明：如果商品、库存、订单、利润事实层口径不稳定，Stage 5 的跨平台聚合只能停留在骨架层

2. **平台 adapter 抽象边界与 capability matrix 未统一**
   - 影响：A2, A3, B4
   - 说明：如果不同平台 adapter 的输入输出和错误语义差异过大，统一 listing 服务会变成新的硬编码汇聚点

### 软 blocker

1. **platform / marketplace / region 字段口径需统一**
   - 影响：A1, B1, C4
   - 说明：字段语义不统一会导致多平台快照和平台地区聚合结果失真

2. **平台类目映射来源与置信度规则需确认**
   - 影响：B1, B3, B4
   - 说明：如果类目映射来源不稳定，策略层很难对发布流程形成稳定约束

3. **汇率来源与刷新机制需明确**
   - 影响：C2, C3
   - 说明：如果汇率缺乏可靠来源或更新时间不清晰，跨币种利润比较容易失真

4. **税费与地区风险规则来源需确认**
   - 影响：C1, C3, C4
   - 说明：税费和地区风险缺少统一来源时，只能先做规则骨架，无法形成真实经营判断

5. **locale / marketplace fallback 策略需统一**
   - 影响：D2, D3
   - 说明：缺失语言、缺失平台内容版本时如何回退，需要在服务层先明确，否则发布路径会产生不一致行为

---

## 7. 建议 owner lane

### Backend Multiplatform Lane A（平台接入与统一 listing）
负责：
- A1
- A2
- A3

### Backend Policy Lane B（平台策略层）
负责：
- B1
- B2
- B3
- B4

### Backend Regional Lane C（多币种与地区规则）
负责：
- C1
- C2
- C3

### Backend Localization Lane D（本地化内容）
负责：
- D1
- D2
- D3

### Backend Hub / Integration Lane（跨平台聚合）
负责：
- A4
- C4

### QA / Multiplatform Lane
负责：
- E1
- E2
- E3
- E4
- E5

### 推荐协作原则
- Multiplatform Lane 优先保证统一接入层存在，而不是把平台差异继续散落到业务流程里
- Policy Lane 的职责是把平台差异从 adapter 中抽离为规则，而不是继续堆硬编码条件分支
- Regional Lane 要优先统一币种、税费、利润口径，再推进跨地区经营聚合
- Localization Lane 不应等待所有平台准备完再启动，可先用默认 locale / fallback 把路径打通
- QA / Multiplatform Lane 应从 Batch 3 开始持续介入，避免等跨平台聚合完成后再集中补测试

---

## 8. 实际开工建议

### 第一周优先级
- S5-A1
- S5-B1
- S5-C1
- S5-D1

### 第二周优先级
- S5-A2
- S5-B2
- S5-B3
- S5-C2
- S5-D2

### 第三周优先级
- S5-A3
- S5-A4
- S5-B4
- S5-C3
- S5-D3
- S5-E1
- S5-E2

### 第四周优先级
- S5-C4
- S5-E3
- S5-E4
- S5-E5

> 注：如果目标是尽快让 Stage 5 的多平台统一经营中枢可用，建议先完成 A1-A3 + B1-B4 + C1-C3 的最小统一发布与地区化规则链路，再补本地化内容深水区和跨平台聚合增强。

---

## 9. 推荐在项目管理工具中的字段

建议每个 backlog item 记录：
- `ID`：如 `S5-B3`
- `Title`
- `Type`：Schema / Service / Integration / Aggregation / Rules / Test / Verification
- `Batch`
- `Owner Lane`
- `Dependencies`
- `Policy Dependency`
- `Status`
- `PR`
- `Definition of Done`

---

## 10. 最小闭环定义（建议先达成）

如果希望尽快交付 Stage 5 的最小可用版本，建议先完成以下子集：

### Stage 5 MVP 子集
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

这可以先形成：

```text
PlatformRegistry / UnifiedListingService 多平台统一发布入口
+ PlatformPolicy / PricingRule / ContentRule 平台策略层
+ CurrencyConverter / 地区化价格与利润换算基础
```

### 完整 Stage 5
在 MVP 子集基础上再补：
- A4
- C4
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
