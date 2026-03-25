# Stage 6 实施任务清单

> 基于研发路线图 Stage 6：自动化经营控制平面
>
> 目标：把系统从“统一管理与分析”升级为“系统驱动动作、人只处理例外”的自动化经营控制平面。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 📋 Stage 6 总览

### 核心目标
从“能统一查看和管理 SKU / listing / inventory / profit”升级为“能自动识别问题、执行经营动作、记录审计链路并支持人工覆盖”。

### 关键交付物
1. SKU 生命周期引擎
2. 自动动作规则与执行日志
3. ManualOverride / rollback 机制
4. 经营控制台 API 与异常检测服务
5. 自动化动作的可追踪、可解释、可回滚基础设施

### 预期成果
- 系统可自动识别值得加码、需要清退、需要补货、需要调价、需要换素材的 SKU
- 常规经营动作不再完全依赖人工触发
- 每次自动动作都有规则来源、执行结果和回滚入口
- 人工只处理异常、审批和策略修正

---

## 🎯 任务分组

### 分组 A：SKU 生命周期引擎（优先级 P0）
### 分组 B：自动动作引擎（优先级 P0）
### 分组 C：异常检测与经营控制台（优先级 P0）
### 分组 D：人工覆盖、审计与回滚（优先级 P1）
### 分组 E：测试与验证（优先级 P0）

---

## 分组 A：SKU 生命周期引擎

### A1. 设计 SkuLifecycleState / LifecycleRule / LifecycleTransitionLog Schema

**任务描述**：
建立 SKU 生命周期模型，为测试期、放量期、稳定期、衰退期、清退期等经营阶段提供统一事实层。

**具体工作**：
1. 设计 `SkuLifecycleState`：
   - `id`
   - `product_variant_id`
   - `current_state`
   - `entered_at`
   - `reason`
   - `confidence_score`
2. 设计 `LifecycleRule`：
   - `rule_name`
   - `from_state`
   - `to_state`
   - `rule_payload`
   - `enabled`
3. 设计 `LifecycleTransitionLog`：
   - `product_variant_id`
   - `from_state`
   - `to_state`
   - `trigger_source`
   - `trigger_payload`
   - `executed_at`
4. 定义基础生命周期状态：
   - `DISCOVERING`
   - `TESTING`
   - `SCALING`
   - `STABLE`
   - `DECLINING`
   - `CLEARANCE`
   - `RETIRED`

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_lifecycle_engine.py`
- 修改：`backend/app/core/enums.py` 或相关枚举文件

**验收标准**：
- [ ] 生命周期状态与规则模型定义完成
- [ ] 可记录状态迁移日志
- [ ] migration 可成功执行

**预估工作量**：5-7 小时

---

### A2. 实现 LifecycleEngineService

**任务描述**：
创建生命周期引擎服务，根据经营结果和规则判断 SKU 当前所处阶段。

**具体工作**：
1. 新增 `LifecycleEngineService`
2. 实现方法：
   - `evaluate_state(product_variant_id)`
   - `apply_transition(product_variant_id, target_state, reason)`
   - `get_current_state(product_variant_id)`
   - `load_rules()`
3. 输入信号包括：
   - revenue trend
   - refund trend
   - inventory pressure
   - profit trend
   - content performance trend
4. 保持规则型判断，不引入复杂模型

**涉及文件**：
- 新增：`backend/app/services/lifecycle_engine_service.py`

**验收标准**：
- [ ] 可评估 SKU 当前生命周期状态
- [ ] 可触发状态迁移并写日志
- [ ] 规则加载和应用路径清晰

**预估工作量**：6-8 小时

---

### A3. 建立生命周期信号聚合接口

**任务描述**：
为生命周期引擎准备统一输入信号，避免规则直接耦合多个底层服务。

**具体工作**：
1. 实现 `get_lifecycle_signal_snapshot(product_variant_id)`
2. 聚合内容：
   - sales trend
   - refund trend
   - profit margin trend
   - inventory coverage days
   - supplier risk signal
   - content performance signal
3. 统一返回结构
4. 与 `OperatingMetricsService`、`FeedbackAggregator` 复用衔接

**涉及文件**：
- 修改：`backend/app/services/operating_metrics_service.py`
- 可能新增：`backend/app/services/lifecycle_signal_service.py`

**验收标准**：
- [ ] 生命周期信号快照可查询
- [ ] 输入指标结构稳定
- [ ] 可供规则引擎复用

**预估工作量**：4-6 小时

---

## 分组 B：自动动作引擎

### B1. 设计 ActionRule / ActionExecutionLog Schema

**任务描述**：
建立自动动作规则和执行日志，为调价、补货、换素材、下架清退等动作提供统一规则层与审计层。

**具体工作**：
1. 设计 `ActionRule`：
   - `id`
   - `rule_name`
   - `action_type`
   - `trigger_payload`
   - `target_scope`
   - `enabled`
2. 设计 `ActionExecutionLog`：
   - `id`
   - `action_rule_id`
   - `product_variant_id` (nullable)
   - `platform_listing_id` (nullable)
   - `action_type`
   - `status`
   - `request_payload`
   - `result_payload`
   - `executed_at`
3. 定义基础动作类型：
   - repricing
   - replenish
   - swap_content
   - expand_platform
   - delist
   - retire
4. 明确规则与执行日志的关系

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_action_engine.py`

**验收标准**：
- [ ] 动作规则与执行日志模型定义完成
- [ ] 可表达多个动作类型
- [ ] migration 可成功执行

**预估工作量**：4-6 小时

---

### B2. 实现 ActionEngineService

**任务描述**：
创建动作引擎服务，根据规则和当前信号生成待执行动作并记录执行结果。

**具体工作**：
1. 新增 `ActionEngineService`
2. 实现方法：
   - `evaluate_actions(product_variant_id)`
   - `execute_action(action_type, payload)`
   - `log_action_execution(...)`
   - `get_pending_actions(...)`
3. 动作引擎调度以下能力：
   - `PricingService`
   - `InventoryAllocator` / `ProcurementService`
   - `LocalizationService` / content service
   - `UnifiedListingService`
4. 保持引擎只负责规则评估与编排，不接管事实计算

**涉及文件**：
- 新增：`backend/app/services/action_engine_service.py`

**验收标准**：
- [ ] 可生成和执行自动动作
- [ ] 每个动作执行都会记录日志
- [ ] 行为边界清晰

**预估工作量**：6-8 小时

---

### B3. 建立降级执行策略与安全阈值

**任务描述**：
为自动动作引擎增加安全阈值和降级机制，避免系统自动放大错误。

**具体工作**：
1. 定义高风险动作必须满足的约束
2. 增加安全规则：
   - 最大调价幅度
   - 最大补货量
   - 自动下架前的最低证据阈值
   - 自动扩平台前的最小利润和稳定性要求
3. 增加 dry-run / suggest-only 模式
4. 将被拒绝的动作也写入日志

**涉及文件**：
- 修改：`backend/app/services/action_engine_service.py`
- 可能修改：`backend/app/core/config.py`

**验收标准**：
- [ ] 高风险动作有安全阈值
- [ ] dry-run / suggest-only 模式可工作
- [ ] 被拒绝动作也有审计记录

**预估工作量**：4-6 小时

---

### B4. 接入关键自动动作执行路径

**任务描述**：
把生命周期状态和动作引擎与关键经营动作打通。

**具体工作**：
1. 接入调价动作
2. 接入补货动作
3. 接入素材替换动作
4. 接入 listing 下架 / 平台扩展动作
5. 明确哪些动作默认自动执行，哪些只建议不执行

**涉及文件**：
- 修改：
  - `backend/app/services/action_engine_service.py`
  - `backend/app/services/pricing_service.py`
  - `backend/app/services/procurement_service.py`
  - `backend/app/services/unified_listing_service.py`
  - 相关内容服务

**验收标准**：
- [ ] 至少 3 类经营动作可接入统一引擎
- [ ] 自动动作与建议动作边界明确
- [ ] 行为可追踪

**预估工作量**：6-8 小时

---

## 分组 C：异常检测与经营控制台

### C1. 实现 AnomalyDetectionService

**任务描述**：
创建异常检测服务，识别 CTR 异常下降、退款异常上升、库存断货风险、供应商履约异常等经营问题。

**具体工作**：
1. 新增 `AnomalyDetectionService`
2. 实现方法：
   - `detect_sku_anomalies(product_variant_id)`
   - `detect_listing_anomalies(listing_id)`
   - `detect_supplier_anomalies(supplier_id)`
   - `detect_global_anomalies()`
3. 规则包括：
   - sales drop
   - refund spike
   - margin collapse
   - stockout risk
   - supplier delay risk
4. 输出结构化异常 payload

**涉及文件**：
- 新增：`backend/app/services/anomaly_detection_service.py`

**验收标准**：
- [ ] 可识别核心经营异常
- [ ] 异常结果结构稳定
- [ ] 可供控制台和动作引擎复用

**预估工作量**：5-7 小时

---

### C2. 创建经营控制台聚合服务

**任务描述**：
建立控制台聚合服务，输出“今日异常、值得加码 SKU、应清退 SKU、待审批动作”等统一视图。

**具体工作**：
1. 新增 `OperationsControlPlaneService`
2. 实现方法：
   - `get_daily_exceptions()`
   - `get_scaling_candidates()`
   - `get_clearance_candidates()`
   - `get_pending_action_approvals()`
3. 汇总生命周期、动作引擎、异常检测、利润与库存快照
4. 返回控制台友好的结构化 payload

**涉及文件**：
- 新增：`backend/app/services/operations_control_plane_service.py`

**验收标准**：
- [ ] 控制台核心视图可查询
- [ ] 能输出例外、加码、清退、审批列表
- [ ] 聚合结构清晰稳定

**预估工作量**：5-7 小时

---

### C3. 新增经营控制台只读 API

**任务描述**：
为自动化经营阶段提供只读 API，支持 UI、调试和运营使用。

**具体工作**：
1. 新增只读路由：
   - `/operations/exceptions`
   - `/operations/scaling-candidates`
   - `/operations/clearance-candidates`
   - `/operations/pending-actions`
2. 调用 `OperationsControlPlaneService`
3. 支持过滤条件：
   - platform
   - region
   - lifecycle state
4. 确保返回结构稳定、无敏感数据泄露

**涉及文件**：
- 新增：`backend/app/api/routes_operations.py`

**验收标准**：
- [ ] 控制台 API 可返回结构化数据
- [ ] 支持基础过滤
- [ ] 可在测试环境验证

**预估工作量**：4-6 小时

---

### C4. 建立自动动作审批入口（可选）

**任务描述**：
为高风险自动动作建立人工审批入口，让系统从“建议”平滑过渡到“自动执行”。

**具体工作**：
1. 设计审批动作接口：
   - approve
   - reject
   - defer
2. 对接 `ActionExecutionLog`
3. 明确审批后动作的执行路径
4. 支持审批意见记录

**涉及文件**：
- 修改：`backend/app/api/routes_operations.py`
- 可能修改：`backend/app/services/action_engine_service.py`

**验收标准**：
- [ ] 高风险动作可进入审批流
- [ ] 审批结果可追踪
- [ ] 审批后执行路径清晰

**预估工作量**：4-6 小时

---

## 分组 D：人工覆盖、审计与回滚

### D1. 设计 ManualOverride Schema

**任务描述**：
建立人工覆盖记录模型，允许运营人员覆盖生命周期判断或自动动作结果。

**具体工作**：
1. 设计 `ManualOverride`：
   - `id`
   - `target_type`
   - `target_id`
   - `override_type`
   - `override_payload`
   - `reason`
   - `created_by`
   - `expires_at`
2. 明确 override 适用场景：
   - lifecycle state override
   - action skip
   - action force execute
   - strategy freeze
3. 设计优先级规则：人工覆盖优先于自动规则
4. 为后续 UI / API 提供稳定结构

**涉及文件**：
- 修改：`backend/app/db/models.py`
- 新增：`backend/migrations/versions/00x_manual_override.py`

**验收标准**：
- [ ] ManualOverride 模型定义完成
- [ ] 可表达常见人工覆盖场景
- [ ] migration 可成功执行

**预估工作量**：3-5 小时

---

### D2. 实现 OverrideService 与优先级规则

**任务描述**：
创建人工覆盖服务，并在生命周期引擎和动作引擎中消费 override 规则。

**具体工作**：
1. 新增 `OverrideService`
2. 实现方法：
   - `create_override(...)`
   - `get_active_overrides(target_type, target_id)`
   - `resolve_override_decision(...)`
   - `expire_override(...)`
3. 在生命周期评估前读取 override
4. 在动作执行前读取 override

**涉及文件**：
- 新增：`backend/app/services/override_service.py`
- 修改：
  - `backend/app/services/lifecycle_engine_service.py`
  - `backend/app/services/action_engine_service.py`

**验收标准**：
- [ ] 可创建和读取人工覆盖
- [ ] 生命周期与动作引擎会尊重 override
- [ ] override 过期规则明确

**预估工作量**：4-6 小时

---

### D3. 建立动作回滚机制

**任务描述**：
为关键自动动作提供最小可用回滚能力，降低自动化经营的不可逆风险。

**具体工作**：
1. 明确哪些动作支持回滚：
   - 调价回滚
   - 内容版本回滚
   - 状态回滚
2. 在 `ActionExecutionLog` 中记录回滚前状态
3. 实现 `rollback_action(action_execution_id)`
4. 对不支持回滚的动作明确标注

**涉及文件**：
- 修改：`backend/app/services/action_engine_service.py`
- 可能修改：相关 service

**验收标准**：
- [ ] 至少部分关键动作支持回滚
- [ ] 回滚会留下审计日志
- [ ] 不可回滚动作会明确标注

**预估工作量**：4-6 小时

---

## 分组 E：测试与验证

### E1. 新增生命周期引擎测试

**任务描述**：
验证生命周期状态判断、规则迁移与日志记录行为。

**具体工作**：
新增测试：
- `test_evaluate_state_returns_testing_for_new_sku`
- `test_lifecycle_engine_moves_sku_to_scaling_when_signals_are_strong`
- `test_lifecycle_transition_log_is_written`
- `test_manual_override_can_block_lifecycle_transition`

**涉及文件**：
- 新增：`backend/tests/test_lifecycle_engine_service.py`

**验收标准**：
- [ ] 生命周期测试全部通过
- [ ] 状态迁移和 override 被覆盖

**预估工作量**：4-6 小时

---

### E2. 新增动作引擎与安全阈值测试

**任务描述**：
验证动作评估、执行、dry-run、安全阈值与回滚逻辑。

**具体工作**：
新增测试：
- `test_action_engine_generates_repricing_action`
- `test_action_engine_blocks_action_when_safety_threshold_is_exceeded`
- `test_action_engine_supports_dry_run_mode`
- `test_rejected_action_is_logged`
- `test_supported_action_can_be_rolled_back`

**涉及文件**：
- 新增：`backend/tests/test_action_engine_service.py`

**验收标准**：
- [ ] 动作引擎测试全部通过
- [ ] 安全阈值与回滚逻辑被覆盖

**预估工作量**：5-7 小时

---

### E3. 新增异常检测与控制台测试

**任务描述**：
验证异常检测服务、控制台聚合服务与只读 API 的核心行为。

**具体工作**：
新增测试：
- `test_detect_sku_anomalies_returns_refund_spike`
- `test_operations_control_plane_returns_scaling_candidates`
- `test_operations_api_returns_daily_exceptions`
- `test_pending_action_approvals_are_visible_when_required`

**涉及文件**：
- 新增：`backend/tests/test_anomaly_detection_service.py`
- 新增：`backend/tests/test_operations_control_plane_service.py`
- 新增：`backend/tests/test_routes_operations.py`

**验收标准**：
- [ ] 异常检测与控制台测试全部通过
- [ ] API 响应结构稳定

**预估工作量**：5-7 小时

---

### E4. 新增人工覆盖与审计测试

**任务描述**：
验证 ManualOverride、审批流和审计日志在关键路径中的作用。

**具体工作**：
新增测试：
- `test_create_manual_override_for_action_skip`
- `test_override_service_takes_precedence_over_action_rule`
- `test_high_risk_action_can_require_approval`
- `test_rollback_writes_audit_log`

**涉及文件**：
- 新增：`backend/tests/test_override_service.py`
- 修改：`backend/tests/test_action_engine_service.py`

**验收标准**：
- [ ] override 与审计测试全部通过
- [ ] 审批与回滚路径被覆盖

**预估工作量**：4-6 小时

---

### E5. Stage 6 回归验证套件

**任务描述**：
建立 Stage 6 的回归命令与验证 checklist。

**建议命令**：
```bash
python -m pytest backend/tests/test_lifecycle_engine_service.py -v
python -m pytest backend/tests/test_action_engine_service.py -v
python -m pytest backend/tests/test_anomaly_detection_service.py -v
python -m pytest backend/tests/test_operations_control_plane_service.py -v
python -m pytest backend/tests/test_override_service.py -v
python -m pytest backend/tests/test_routes_operations.py -v
```

**涉及文件**：
- 新增：`docs/roadmap/stage6-verification-checklist.md`

**验收标准**：
- [ ] 核心回归命令明确
- [ ] 手工验证 checklist 明确
- [ ] Stage 1-5 主链路不回退

**预估工作量**：2-3 小时

---

## 📊 任务优先级与依赖关系

### 第一批（并行）
- A1（生命周期 Schema）
- B1（动作规则与执行日志 Schema）
- C1（异常检测服务）
- D1（ManualOverride Schema）

### 第二批（依赖第一批）
- A2（LifecycleEngineService）
- A3（生命周期信号快照）
- B2（ActionEngineService）
- D2（OverrideService）

### 第三批（依赖第二批）
- B3（降级执行策略与安全阈值）
- B4（关键自动动作接入）
- C2（经营控制台聚合服务）
- C3（控制台只读 API）
- E1 / E2（生命周期与动作引擎测试）

### 第四批（依赖第三批）
- C4（动作审批入口，可选）
- D3（动作回滚机制）
- E3 / E4（异常检测、override、审计测试）
- E5（回归验证）

---

## 📈 工作量估算

| 分组 | 任务数 | 预估总工时 | 建议人员 |
|------|--------|-----------|---------|
| A | 3 | 15-21h | 后端 |
| B | 4 | 20-28h | 后端 |
| C | 4 | 18-26h | 后端 |
| D | 3 | 11-17h | 后端 |
| E | 5 | 20-29h | 测试 + 后端 |
| **总计** | **19** | **84-121h** | **2-3 人** |

按 2-3 人并行投入，Stage 6 可作为从“多平台统一经营中枢”升级到“自动化经营控制平面”的主开发包推进。

---

## ✅ Stage 6 退出标准

### 功能完整性
- [ ] SKU 生命周期状态可自动评估和迁移
- [ ] 自动动作引擎可生成并执行关键经营动作
- [ ] 异常检测服务可识别核心经营异常
- [ ] 控制台 API 可输出例外、加码、清退、待审批动作
- [ ] ManualOverride / 回滚 / 审计链路可工作

### 自动化成熟度
- [ ] 常规经营动作可自动执行或自动建议
- [ ] 高风险动作有审批或安全阈值保护
- [ ] 人工覆盖优先级明确
- [ ] 每次动作都有日志和结果记录

### 可控性
- [ ] 自动动作可解释来源规则
- [ ] 关键动作具备回滚能力或显式不可回滚标注
- [ ] 控制台能集中查看异常和待处理事项
- [ ] 自动化不会绕过 Stage 3-5 的事实层边界

### 测试覆盖
- [ ] 生命周期测试全部通过
- [ ] 动作引擎测试全部通过
- [ ] 异常检测与控制台测试全部通过
- [ ] override / 审计测试全部通过
- [ ] Stage 1-5 核心回归不受影响

---

## 🚀 下一步

完成 Stage 6 后，系统将具备“事实层 + 反馈层 + 多平台统一经营 + 自动动作控制平面”的完整骨架。后续可按业务优先级继续推进视频/3D 内容、广告优化、需求预测、多仓协同等高级能力。

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
