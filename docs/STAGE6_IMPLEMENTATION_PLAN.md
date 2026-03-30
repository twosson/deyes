# Stage 6 实施规划

**创建日期**: 2026-03-30
**状态**: 规划中
**预计工期**: 84-121h (2-3 人，2-3 周)

---

## 一、Stage 6 目标

### 核心目标
从"统一管理与分析"升级为"系统驱动动作、人只处理例外"的自动化经营控制平面。

### 关键交付物
1. SKU 生命周期引擎（DISCOVERING → TESTING → SCALING → STABLE → DECLINING → CLEARANCE → RETIRED）
2. 自动动作规则与执行日志（调价、补货、换素材、扩平台、下架）
3. ManualOverride / rollback 机制
4. 经营控制台 API 与异常检测服务
5. 自动化动作的可追踪、可解释、可回滚基础设施

### 预期成果
- 系统可自动识别值得加码、需要清退、需要补货、需要调价、需要换素材的 SKU
- 常规经营动作不再完全依赖人工触发
- 每次自动动作都有规则来源、执行结果和回滚入口
- 人工只处理异常、审批和策略修正

---

## 二、实施策略

### 2.1 分阶段实施

**Phase 1: 基础设施层（A1, B1, D1）** - 5-7 天
- 生命周期 Schema
- 动作规则与执行日志 Schema
- ManualOverride Schema
- 数据库迁移

**Phase 2: 核心服务层（A2, A3, B2, C1, D2）** - 7-10 天
- LifecycleEngineService
- 生命周期信号聚合
- ActionEngineService
- AnomalyDetectionService
- OverrideService

**Phase 3: 集成与控制层（B3, B4, C2, C3）** - 5-7 天
- 安全阈值与降级策略
- 关键自动动作接入
- 经营控制台聚合服务
- 控制台只读 API

**Phase 4: 审批与回滚（C4, D3）** - 3-5 天
- 动作审批入口（可选）
- 动作回滚机制

**Phase 5: 测试与验证（E1-E5）** - 5-7 天
- 生命周期引擎测试
- 动作引擎测试
- 异常检测与控制台测试
- override 与审计测试
- 回归验证

### 2.2 并行工作策略

**第一批（并行）**:
- A1（生命周期 Schema）
- B1（动作规则与执行日志 Schema）
- D1（ManualOverride Schema）
- C1（异常检测服务）

**第二批（依赖第一批）**:
- A2（LifecycleEngineService）
- A3（生命周期信号快照）
- B2（ActionEngineService）
- D2（OverrideService）

**第三批（依赖第二批）**:
- B3（降级执行策略与安全阈值）
- B4（关键自动动作接入）
- C2（经营控制台聚合服务）
- C3（控制台只读 API）
- E1 / E2（生命周期与动作引擎测试）

**第四批（依赖第三批）**:
- C4（动作审批入口，可选）
- D3（动作回滚机制）
- E3 / E4（异常检测、override、审计测试）
- E5（回归验证）

---

## 三、详细任务清单

### Phase 1: 基础设施层（5-7 天）

#### A1. 生命周期 Schema ✅
**工作量**: 5-7h
**负责人**: 后端
**输出**:
- `SkuLifecycleState` 模型
- `LifecycleRule` 模型
- `LifecycleTransitionLog` 模型
- 生命周期状态枚举（DISCOVERING, TESTING, SCALING, STABLE, DECLINING, CLEARANCE, RETIRED）
- 数据库迁移 `00x_lifecycle_engine.py`

#### B1. 动作规则与执行日志 Schema ✅
**工作量**: 4-6h
**负责人**: 后端
**输出**:
- `ActionRule` 模型
- `ActionExecutionLog` 模型
- 动作类型枚举（repricing, replenish, swap_content, expand_platform, delist, retire）
- 数据库迁移 `00x_action_engine.py`

#### D1. ManualOverride Schema ✅
**工作量**: 3-5h
**负责人**: 后端
**输出**:
- `ManualOverride` 模型
- override 类型枚举（lifecycle_state_override, action_skip, action_force_execute, strategy_freeze）
- 数据库迁移 `00x_manual_override.py`

---

### Phase 2: 核心服务层（7-10 天）

#### A2. LifecycleEngineService ✅
**工作量**: 6-8h
**负责人**: 后端
**输出**:
- `LifecycleEngineService` 服务
- `evaluate_state(product_variant_id)` 方法
- `apply_transition(product_variant_id, target_state, reason)` 方法
- `get_current_state(product_variant_id)` 方法
- `load_rules()` 方法

#### A3. 生命周期信号聚合 ✅
**工作量**: 4-6h
**负责人**: 后端
**输出**:
- `get_lifecycle_signal_snapshot(product_variant_id)` 方法
- 聚合 sales trend, refund trend, profit margin trend, inventory coverage days, supplier risk signal, content performance signal

#### B2. ActionEngineService ✅
**工作量**: 6-8h
**负责人**: 后端
**输出**:
- `ActionEngineService` 服务
- `evaluate_actions(product_variant_id)` 方法
- `execute_action(action_type, payload)` 方法
- `log_action_execution(...)` 方法
- `get_pending_actions(...)` 方法

#### C1. AnomalyDetectionService ✅
**工作量**: 5-7h
**负责人**: 后端
**输出**:
- `AnomalyDetectionService` 服务
- `detect_sku_anomalies(product_variant_id)` 方法
- `detect_listing_anomalies(listing_id)` 方法
- `detect_supplier_anomalies(supplier_id)` 方法
- `detect_global_anomalies()` 方法

#### D2. OverrideService ✅
**工作量**: 4-6h
**负责人**: 后端
**输出**:
- `OverrideService` 服务
- `create_override(...)` 方法
- `get_active_overrides(target_type, target_id)` 方法
- `resolve_override_decision(...)` 方法
- `expire_override(...)` 方法

---

### Phase 3: 集成与控制层（5-7 天）

#### B3. 降级执行策略与安全阈值 ✅
**工作量**: 4-6h
**负责人**: 后端
**输出**:
- 最大调价幅度限制
- 最大补货量限制
- 自动下架前的最低证据阈值
- 自动扩平台前的最小利润和稳定性要求
- dry-run / suggest-only 模式

#### B4. 关键自动动作接入 ✅
**工作量**: 6-8h
**负责人**: 后端
**输出**:
- 调价动作接入
- 补货动作接入
- 素材替换动作接入
- listing 下架 / 平台扩展动作接入

#### C2. 经营控制台聚合服务 ✅
**工作量**: 5-7h
**负责人**: 后端
**输出**:
- `OperationsControlPlaneService` 服务
- `get_daily_exceptions()` 方法
- `get_scaling_candidates()` 方法
- `get_clearance_candidates()` 方法
- `get_pending_action_approvals()` 方法

#### C3. 控制台只读 API ✅
**工作量**: 4-6h
**负责人**: 后端
**输出**:
- `/operations/exceptions` 路由
- `/operations/scaling-candidates` 路由
- `/operations/clearance-candidates` 路由
- `/operations/pending-actions` 路由

---

### Phase 4: 审批与回滚（3-5 天）

#### C4. 动作审批入口（可选）✅
**工作量**: 4-6h
**负责人**: 后端
**输出**:
- 审批动作接口（approve, reject, defer）
- 审批意见记录

#### D3. 动作回滚机制 ✅
**工作量**: 4-6h
**负责人**: 后端
**输出**:
- 调价回滚
- 内容版本回滚
- 状态回滚
- `rollback_action(action_execution_id)` 方法

---

### Phase 5: 测试与验证（5-7 天）

#### E1. 生命周期引擎测试 ✅
**工作量**: 4-6h
**负责人**: 测试 + 后端
**输出**:
- `test_lifecycle_engine_service.py`
- 4+ 测试用例

#### E2. 动作引擎与安全阈值测试 ✅
**工作量**: 5-7h
**负责人**: 测试 + 后端
**输出**:
- `test_action_engine_service.py`
- 5+ 测试用例

#### E3. 异常检测与控制台测试 ✅
**工作量**: 5-7h
**负责人**: 测试 + 后端
**输出**:
- `test_anomaly_detection_service.py`
- `test_operations_control_plane_service.py`
- `test_routes_operations.py`
- 4+ 测试用例

#### E4. override 与审计测试 ✅
**工作量**: 4-6h
**负责人**: 测试 + 后端
**输出**:
- `test_override_service.py`
- 4+ 测试用例

#### E5. Stage 6 回归验证 ✅
**工作量**: 2-3h
**负责人**: 测试 + 后端
**输出**:
- `docs/roadmap/stage6-verification-checklist.md`
- 回归测试命令

---

## 四、技术设计要点

### 4.1 生命周期状态机

```
DISCOVERING → TESTING → SCALING → STABLE → DECLINING → CLEARANCE → RETIRED
     ↓           ↓          ↓         ↓          ↓           ↓
     └───────────┴──────────┴─────────┴──────────┴───────────┘
                    (可回退，需记录原因)
```

**状态定义**:
- **DISCOVERING**: 新 SKU，尚未上架或刚上架
- **TESTING**: 测试期，小批量验证市场反应
- **SCALING**: 放量期，表现良好，加大投入
- **STABLE**: 稳定期，持续盈利
- **DECLINING**: 衰退期，表现下滑
- **CLEARANCE**: 清退期，准备下架
- **RETIRED**: 已退市

**迁移信号**:
- revenue trend (7d, 30d)
- refund trend (7d, 30d)
- profit margin trend (7d, 30d)
- inventory coverage days
- supplier risk signal
- content performance signal

### 4.2 自动动作类型

| 动作类型 | 触发条件 | 执行逻辑 | 回滚支持 |
|---------|---------|---------|---------|
| repricing | 利润率下降 / 竞争压力 | PricingService.calculate_pricing() | ✅ |
| replenish | 库存低于阈值 | ProcurementService.create_purchase_order() | ❌ |
| swap_content | CTR 下降 / A/B 测试输家 | ContentAssetManager.swap_asset() | ✅ |
| expand_platform | 稳定期 + 高利润 | UnifiedListingService.create_listing() | ❌ |
| delist | 衰退期 + 低利润 | UnifiedListingService.update_listing(status=INACTIVE) | ✅ |
| retire | 清退期 | ProductVariant.status = RETIRED | ❌ |

### 4.3 安全阈值

| 动作类型 | 安全阈值 | 降级策略 |
|---------|---------|---------|
| repricing | 最大调价幅度 ±20% | 超过阈值 → suggest-only |
| replenish | 最大补货量 = 30 天销量 | 超过阈值 → 需审批 |
| swap_content | 最小 CTR 下降 > 20% | 不满足 → suggest-only |
| expand_platform | 最小利润率 > 30%, 稳定期 > 30 天 | 不满足 → suggest-only |
| delist | 最小衰退期 > 14 天 | 不满足 → suggest-only |

### 4.4 ManualOverride 优先级

```
ManualOverride (最高优先级)
    ↓
ActionRule (自动规则)
    ↓
Default Behavior (默认行为)
```

**Override 类型**:
- `lifecycle_state_override`: 强制 SKU 保持某个生命周期状态
- `action_skip`: 跳过某个自动动作
- `action_force_execute`: 强制执行某个动作（即使不满足条件）
- `strategy_freeze`: 冻结所有自动动作

---

## 五、风险与缓解

### 5.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 自动动作放大错误 | 高 | 安全阈值 + dry-run 模式 + 审批流 |
| 生命周期判断不准确 | 中 | ManualOverride + 人工审核 + 规则迭代 |
| 回滚机制不完善 | 中 | 明确标注不可回滚动作 + 审计日志 |
| 异常检测误报 | 低 | 阈值调优 + 人工确认 |

### 5.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 自动调价导致利润下降 | 高 | 最大调价幅度限制 + 利润率下限 |
| 自动补货导致库存积压 | 中 | 最大补货量限制 + 库存周转率监控 |
| 自动下架导致销售损失 | 中 | 最小衰退期要求 + 人工审批 |

---

## 六、成功标准

### 6.1 功能完整性
- [ ] SKU 生命周期状态可自动评估和迁移
- [ ] 自动动作引擎可生成并执行关键经营动作
- [ ] 异常检测服务可识别核心经营异常
- [ ] 控制台 API 可输出例外、加码、清退、待审批动作
- [ ] ManualOverride / 回滚 / 审计链路可工作

### 6.2 自动化成熟度
- [ ] 常规经营动作可自动执行或自动建议
- [ ] 高风险动作有审批或安全阈值保护
- [ ] 人工覆盖优先级明确
- [ ] 每次动作都有日志和结果记录

### 6.3 可控性
- [ ] 自动动作可解释来源规则
- [ ] 关键动作具备回滚能力或显式不可回滚标注
- [ ] 控制台能集中查看异常和待处理事项
- [ ] 自动化不会绕过 Stage 3-5 的事实层边界

### 6.4 测试覆盖
- [ ] 生命周期测试全部通过
- [ ] 动作引擎测试全部通过
- [ ] 异常检测与控制台测试全部通过
- [ ] override / 审计测试全部通过
- [ ] Stage 1-5 核心回归不受影响

---

## 七、下一步行动

### 立即行动（P0）
1. 创建 Stage 6 开发分支
2. 启动 Phase 1: 基础设施层
   - A1: 生命周期 Schema
   - B1: 动作规则与执行日志 Schema
   - D1: ManualOverride Schema
3. 并行启动 C1: AnomalyDetectionService

### 近期行动（P1）
1. Phase 2: 核心服务层
   - A2: LifecycleEngineService
   - A3: 生命周期信号聚合
   - B2: ActionEngineService
   - D2: OverrideService

### 中期行动（P2）
1. Phase 3: 集成与控制层
2. Phase 4: 审批与回滚
3. Phase 5: 测试与验证

---

**文档版本**: v1.0
**创建时间**: 2026-03-30
**维护者**: Deyes 研发团队
