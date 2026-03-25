# Deyes 路线图与实施清单总览

> 目标：为产品、研发、测试和管理协作提供统一入口，串联产品路线图、研发路线图、Stage 1-6 实施任务清单与执行版 backlog。
>
> 版本: v1.2
> 创建时间: 2026-03-25
> 更新时间: 2026-03-25

---

## 1. 文档导航

### 核心路线图

1. **产品路线图**
   - `docs/roadmap/product-roadmap-2026.md`
   - 面向对象：创始人、产品、业务、投资人
   - 关注重点：战略定位、阶段目标、业务价值、风险与节奏

2. **研发路线图**
   - `docs/roadmap/engineering-roadmap-2026.md`
   - 面向对象：研发、架构、数据、测试
   - 关注重点：当前代码基线、架构原则、阶段交付、实体演进、服务边界

### 分阶段实施清单

3. **Stage 1 实施任务清单：可经营闭环**
   - `docs/roadmap/stage1-implementation-tasks.md`
   - 主题：平台表现数据回流、Listing 表现中心、A/B 测试基础、真实平台同步

4. **Stage 2 实施任务清单：经营反馈引擎**
   - `docs/roadmap/stage2-implementation-tasks.md`
   - 主题：FeedbackAggregator 升级、style/platform/region/price band prior、负反馈降权、解释性输出

5. **Stage 3 实施任务清单：ERP Lite 商品与供应链核心**
   - `docs/roadmap/stage3-implementation-tasks.md`
   - 主题：ProductMaster / SKU、Supplier / SupplierOffer、采购单、库存中心、ProcurementAgent

6. **Stage 4 实施任务清单：订单、售后、利润台账**
   - `docs/roadmap/stage4-implementation-tasks.md`
   - 主题：订单中心、售后中心、利润台账、退款对账、真实净利聚合

7. **Stage 5 实施任务清单：多平台统一经营中枢**
   - `docs/roadmap/stage5-implementation-tasks.md`
   - 主题：多平台 listing 管理、平台策略层、多币种、地区化、本地化内容

8. **Stage 6 实施任务清单：自动化经营控制平面**
   - `docs/roadmap/stage6-implementation-tasks.md`
   - 主题：生命周期引擎、自动动作引擎、异常检测、控制台、审批与回滚

### 执行版 Backlog

9. **Stage 1 Development Backlog**
   - `docs/roadmap/stage1-development-backlog.md`
   - 主题：Batch 1-4、owner lane、PR 切分、blocker、MVP 子集

10. **Stage 2 Development Backlog**
    - `docs/roadmap/stage2-development-backlog.md`
    - 主题：反馈特征、adapter 注入、解释性输出的执行层拆解

11. **Stage 3 Development Backlog**
    - `docs/roadmap/stage3-development-backlog.md`
    - 主题：ERP Lite 核心 schema / service / procurement / inventory 的执行层拆解

12. **Stage 4 Development Backlog**
    - `docs/roadmap/stage4-development-backlog.md`
    - 主题：订单、售后、利润台账、反馈兼容的执行层拆解

13. **Stage 5 Development Backlog**
    - `docs/roadmap/stage5-development-backlog.md`
    - 主题：平台注册、UnifiedListing、策略层、地区化、多币种、本地化内容的执行层拆解

14. **Stage 6 Development Backlog**
    - `docs/roadmap/stage6-development-backlog.md`
    - 主题：生命周期引擎、自动动作引擎、异常检测、控制台、override、回滚的执行层拆解

---

## 2. 项目总览摘要

### 当前文档资产

- 核心路线图文档：**2 份**
- 分阶段实施清单：**6 份**
- 执行版 backlog：**6 份**（Stage 1-6）
- 已拆解实施任务：**112 项**（Stage 1-6）
- 已进入执行层拆解的阶段：**Stage 1-6**
- 覆盖范围：**从表现回流、反馈引擎、ERP Lite 核心、真实经营损益层，到多平台统一经营与自动化控制平面**

### 当前阶段化定位

- **Stage 0**：稳定当前基线
  - 已在研发路线图中定义
  - 当前尚未单独拆成独立任务清单文档
- **Stage 1-6**：已全部完成实施任务拆解
  - 可直接用于排期、立项、架构评审和研发拆分
- **Stage 1-4**：已完成执行版 backlog 拆解
  - 可直接用于项目管理工具建卡、分工、PR 切分和冲刺执行
- **Stage 5-6**：已完成执行版 backlog 拆解
  - 可用于多平台统一经营中枢与自动化控制平面的排期、分工与执行推进

### 一句话理解整套规划

这套规划的本质是把 Deyes 从：

```text
选品工具链
```

逐步升级为：

```text
Candidate → SKU → Listing → Order → Profit → Feedback → Automated Actions
```

---

## 3. 工作量总表

> 说明：本总表按任务数、规模等级、建议投入角色进行汇总。
> 如需查看每个阶段内更细的拆分与原始估算字段，请直接查看对应 Stage 文档。

### 3.1 Stage 级别总表

| 阶段 | 核心主题 | 任务数 | 规模等级 | 建议投入角色 | 主要输出 |
|------|---------|--------|----------|-------------|---------|
| Stage 1 | 可经营闭环 | 17 | 大型 | 后端 / 平台集成 / 测试 | 表现数据回流、A/B 测试基础、平台同步 |
| Stage 2 | 经营反馈引擎 | 18 | 大型 | 后端 / 算法 / 测试 | style/platform/region/price-band feedback priors |
| Stage 3 | ERP Lite 商品与供应链核心 | 19 | 大型 | 后端 / Agent / 测试 | Product / SKU / Supplier / Inventory 事实层 |
| Stage 4 | 订单、售后、利润台账 | 19 | 大型 | 后端 / 数据 / 测试 | Order / Refund / Profit 真实经营损益层 |
| Stage 5 | 多平台统一经营中枢 | 20 | 超大型 | 后端 / 平台策略 / 本地化 / 测试 | 平台策略层、多币种、多地区、本地化内容 |
| Stage 6 | 自动化经营控制平面 | 19 | 大型 | 后端 / Agent / 控制平面 / 测试 | Lifecycle / Action Engine / Operations Control Plane |
| **总计** | **Stage 1-6** | **112** | **多阶段组合项目** | **后端 + 平台 + 数据 + 测试 + Agent** | **从结果层到自动化经营的完整骨架** |

### 3.2 开发包级别总表

| 开发包 | 包含阶段 | 任务数 | 规模等级 | 核心价值 |
|--------|---------|--------|----------|---------|
| 包 1：结果闭环 | Stage 1 + Stage 2 | 35 | 超大型 | 让系统能看到结果，并让结果影响下一轮选品与排序 |
| 包 2：ERP Lite 核心 | Stage 3 + Stage 4 | 38 | 超大型 | 让系统拥有商品、供应链、订单、售后、利润的长期事实层 |
| 包 3：规模化经营 | Stage 5 + Stage 6 | 39 | 超大型 | 让系统支持跨平台统一管理，并开始自动执行经营动作 |

### 3.3 执行层覆盖情况

| 阶段 | 是否已有执行版 backlog | 推荐用途 |
|------|----------------------|---------|
| Stage 1 | 是 | 直接开工、建卡、切 PR |
| Stage 2 | 是 | 反馈引擎增强、adapter 接入、测试推进 |
| Stage 3 | 是 | ERP Lite 核心实体与服务排期 |
| Stage 4 | 是 | 订单/退款/利润层排期与集成推进 |
| Stage 5 | 是 | 多平台统一经营中枢排期与策略层推进 |
| Stage 6 | 是 | 自动化控制平面排期、审批回滚与控制台推进 |

### 3.4 管理视角下的结论

- **Stage 1-2** 适合定义为“先把闭环跑通”的第一优先级开发包
- **Stage 3-4** 是从“优化工具”升级为“经营系统”的关键分水岭
- **Stage 5-6** 不建议过早投入，应该建立在事实层和利润层稳定之后
- 从任务规模看，**Stage 3-6 没有一个是真正的小包**，都应该按独立阶段治理，而不是当作顺手增强
- 当前在文档层已具备从 **Stage 1-6** 全阶段执行版 backlog
- 实际项目管理工具最适合优先直接执行的仍是：**Stage 1-4**，Stage 5-6 更适合作为后续排期准备
- Stage 5-6 backlog 已生成，可用于后续多平台与自动化控制平面的排期与拆分

---

## 4. 推荐阅读顺序

### 面向产品 / 业务 / 管理

建议按以下顺序阅读：
1. `product-roadmap-2026.md`
2. `engineering-roadmap-2026.md`
3. 本文档
4. `stage1-implementation-tasks.md`
5. `stage2-implementation-tasks.md`
6. 根据资源情况决定是否继续进入 Stage 3-6

### 面向研发 / 架构 / 测试

建议按以下顺序阅读：
1. `engineering-roadmap-2026.md`
2. 本文档
3. `stage1-development-backlog.md`
4. `stage2-development-backlog.md`
5. `stage3-development-backlog.md`
6. `stage4-development-backlog.md`
7. 需要看阶段原始范围时，再回看对应 implementation tasks 文档

### 面向项目启动会 / 排期会

建议使用顺序：
1. `engineering-roadmap-2026.md` 中的“当前最优先研发事项”
2. 本文档中的“工作量总表”和“建议执行顺序”
3. `stage1-development-backlog.md` 作为首个开发包执行入口
4. `stage2-development-backlog.md` 作为反馈闭环增强包执行入口
5. `stage3-development-backlog.md` 与 `stage4-development-backlog.md` 作为 ERP Lite 核心排期入口

---

## 5. Stage 1-6 总体演进关系

### Stage 0：稳定基线
- 目标：固化当前可运行主链路
- 重点：测试分层、日志追踪、平台测试隔离
- 说明：已在研发路线图中定义，为后续所有阶段提供稳定基线

### Stage 1：可经营闭环
- 目标：从“能选品、能上架”升级为“能回收真实表现数据”
- 重点：ListingPerformanceDaily、AssetPerformanceDaily、平台同步、A/B 测试基础
- 输出：表现数据开始回流系统

### Stage 2：经营反馈引擎
- 目标：从“静态启发式排序”升级为“结果驱动反馈排序”
- 重点：FeedbackAggregator 升级、style/platform/region/price band prior、negative feedback penalty
- 输出：真实经营结果开始影响 recall 与 ranking

### Stage 3：ERP Lite 商品与供应链核心
- 目标：从“候选商品系统”升级为“SKU 经营系统”
- 重点：ProductMaster / SKU、Supplier / SupplierOffer、PO、Inventory、ProcurementAgent
- 输出：商品、供应商、采购、库存事实层建立

### Stage 4：订单、售后、利润台账
- 目标：从“理论利润”升级为“真实净利”
- 重点：Order、Refund、AfterSale、Settlement、ProfitLedger
- 输出：订单、售后、平台费用、广告费、真实利润统一沉淀

### Stage 5：多平台统一经营中枢
- 目标：让同一 SKU 跨平台统一管理
- 重点：PlatformPolicy、CategoryMapping、PricingRule、Localization、多币种、多地区
- 输出：状态、库存、价格、表现、利润可跨平台统一查看与治理

### Stage 6：自动化经营控制平面
- 目标：从“统一管理”升级为“自动发现问题并自动执行动作”
- 重点：Lifecycle、ActionEngine、AnomalyDetection、Operations Control Plane、Override / Rollback
- 输出：常规经营动作系统自动执行，人只处理例外

---

## 6. 依赖关系总览

### 基础依赖链

```text
Stage 0
  ↓
Stage 1 表现数据回流
  ↓
Stage 2 反馈引擎
  ↓
Stage 3 ERP Lite 商品与供应链核心
  ↓
Stage 4 订单、售后、利润台账
  ↓
Stage 5 多平台统一经营中枢
  ↓
Stage 6 自动化经营控制平面
```

### 关键逻辑说明

- **Stage 1 是 Stage 2 的数据基础**
  - 没有表现数据回流，反馈引擎只能停留在弱先验

- **Stage 2 和 Stage 3 不冲突，但职责不同**
  - Stage 2 负责“把结果变成优化信号”
  - Stage 3 负责“把经营对象变成长期事实实体”

- **Stage 4 是真实经营闭环的关键拐点**
  - 只有订单、退款、费用、净利进入系统，反馈才真正从“表现反馈”升级为“经营反馈”

- **Stage 5 是规模化扩张前提**
  - 没有统一策略层和地区化能力，多平台会把复杂度直接放大

- **Stage 6 必须建立在事实层稳定之上**
  - 没有稳定的商品、库存、利润和异常信号，自动化只会放大错误

---

## 7. 建议执行顺序

### 推荐主路径

1. **先做 Stage 0 / Stage 1**
   - 固化测试基线
   - 让表现数据回流

2. **再做 Stage 2**
   - 让排序和 recall 真正受结果影响

3. **然后做 Stage 3 + Stage 4**
   - 把系统从候选商品逻辑扩展为真实经营事实层
   - 建立订单、退款、利润真相

4. **最后做 Stage 5 + Stage 6**
   - 在事实层稳定后再做多平台统一和自动化经营

### 如果资源有限的最小可行顺序

建议优先投入：
- Stage 0
- Stage 1
- Stage 2
- Stage 3（只做核心商品 / 供应商 / 库存）

这条路径就能让系统形成：

```text
选品 → 上架 → 表现回流 → 排序反馈 → SKU / 库存 / 采购事实层
```

这已经足以支撑一个强可用的 AI Native 卖家操作系统早期版本。

### 如果要按“经营价值释放”来排优先级

推荐顺序是：
1. **Stage 1**：先拿到真实表现结果
2. **Stage 2**：让结果进入选品反馈
3. **Stage 3**：建立 SKU / 供应商 / 库存核心实体
4. **Stage 4**：拿到真实订单、退款、净利真相
5. **Stage 5**：做多平台统一经营
6. **Stage 6**：最后做自动化动作控制平面

---

## 8. 各阶段一句话摘要

| 阶段 | 一句话摘要 |
|------|-----------|
| Stage 0 | 固化基线，确保核心回归稳定可持续开发 |
| Stage 1 | 把平台表现数据回流系统，形成最小结果层 |
| Stage 2 | 把结果反馈到 recall 和 ranking，形成反馈引擎 |
| Stage 3 | 建立 Product / SKU / Supplier / Inventory 事实层 |
| Stage 4 | 建立 Order / Refund / Profit 真实经营损益层 |
| Stage 5 | 让同一 SKU 跨平台统一经营 |
| Stage 6 | 让系统自动识别异常并执行经营动作 |

---

## 9. 使用建议

### 如果要开始实际开发
优先使用：
- `engineering-roadmap-2026.md`
- 本文档
- `stage1-development-backlog.md`
- `stage2-development-backlog.md`
- `stage3-development-backlog.md`
- `stage4-development-backlog.md`

### 如果要做季度规划 / 资源排期
优先使用：
- `product-roadmap-2026.md`
- 本文档
- 各 Stage 实施任务清单中的“退出标准”和“任务分组”

### 如果要做架构评审
优先使用：
- `engineering-roadmap-2026.md`
- `stage2-implementation-tasks.md`
- `stage3-implementation-tasks.md`
- `stage4-implementation-tasks.md`
- 必要时补看对应 development backlog

### 如果要做项目管理看板
建议把各 Stage 文档中的任务直接映射为：
- Epic = Stage
- Feature Group = 分组 A/B/C/D/E
- Story / Task = 每个编号任务（如 A1 / B3 / E2）
- 如果已进入执行阶段，优先使用 development backlog 中的 `Sx-xx` 编号

---

## 10. 当前建议的最近动作

### P0
1. 固化 Stage 0 测试分层与回归入口
2. 按 `stage1-development-backlog.md` 开始 Stage 1 Batch 1
3. 在 Stage 1 稳定后按 `stage2-development-backlog.md` 推进反馈引擎增强

### P1
1. 预先评审 `stage3-development-backlog.md` 中的 Product / SKU / Supplier / Inventory 核心模型
2. 为 `stage4-development-backlog.md` 中的订单 / 利润台账预留实体关系

### P2
1. 平台策略层
2. 本地化内容基础设施
3. 自动动作控制平面

---

## 11. 维护建议

建议后续维护规则：
1. 产品方向变化先更新 `product-roadmap-2026.md`
2. 技术边界变化先更新 `engineering-roadmap-2026.md`
3. 进入具体实施前再更新对应 Stage 的实施清单
4. 进入执行阶段后，新增或维护对应 Stage 的 development backlog
5. 每个 Stage 完成后补一份 verification checklist 或阶段总结
6. 避免在多个文档里维护冲突版本的任务描述
7. 新增 Stage 级文档时，同步更新本总览中的导航和工作量总表

---

**文档版本**: v1.2
**创建时间**: 2026-03-25
**更新时间**: 2026-03-25
**维护者**: Deyes 研发团队
