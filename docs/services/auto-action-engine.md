# Auto Action Engine
 使用指南

> 最后更新: 2026-03-27
> 版本: v1.1 (新增 Temu RPA Fallback Phase 1)

---

## 概述

AutoActionEngine 是 Deyes 自动化经营系统的核心引擎，实现了从"推荐分析"到"自动执行"的战略转向。

### 核心功能

1. **自动上架** (`auto_publish`) - 自动将高质量候选发布到平台
   - **API-first, RPA-second**: 优先使用平台 API，失败后自动 fallback 到 RPA
   - **Temu RPA Fallback (Phase 1)**: Temu API 失败时异步 Celery fallback，challenge 转人工介入
2. **自动调价** (`auto_reprice`) - 基于 ROI 自动调整价格
3. **自动暂停** (`auto_pause`) - 暂停低效商品
4. **自动换素材** (`auto_asset_switch`) - 切换到更高 CTR 的素材
5. **审批边界** - 高风险操作需要人工审批

---

## Temu RPA Fallback (Phase 1) 🆕

### 功能范围

**第一期仅支持**:
- ✅ **平台**: Temu only
- ✅ **操作**: publish fallback only (reprice/pause/asset-switch 暂不支持)
- ✅ **触发**: Temu API 失败后自动异步 Celery fallback
- ✅ **Challenge 处理**: 验证码/短信/邮箱验证 → 转人工介入 (`MANUAL_INTERVENTION_REQUIRED`)
- ❌ **不支持**: 自动打码、自动短信验证、Amazon/AliExpress RPA

### 状态流转

```
Temu API 成功:
  PUBLISHING → ACTIVE

Temu API 失败:
  PUBLISHING → FALLBACK_QUEUED → FALLBACK_RUNNING → ACTIVE / MANUAL_INTERVENTION_REQUIRED / REJECTED

非 Temu 平台 API 失败:
  PUBLISHING → REJECTED (保持原有行为)
```

### 新增状态

- `FALLBACK_QUEUED`: RPA fallback 已入队，等待 Celery worker 执行
- `FALLBACK_RUNNING`: RPA fallback 正在执行中
- `MANUAL_INTERVENTION_REQUIRED`: 需要人工介入（缺前置条件 / 遇到 challenge）

### 前置条件

RPA fallback 执行前会验证以下前置条件，缺失时直接标记 `MANUAL_INTERVENTION_REQUIRED`:

**配置项**:
- `TEMU_RPA_ENABLED=true`
- `TEMU_RPA_LOGIN_URL`
- `TEMU_RPA_PUBLISH_URL`
- `TEMU_RPA_USERNAME`
- `TEMU_RPA_PASSWORD`

**Payload 必填字段**:
- `title`, `price`, `currency`, `inventory`
- `main_image_url`, `category`, `leaf_category`
- `core_attributes`, `logistics_template`, `description`

### Challenge 检测

以下场景会自动转人工介入:
- 验证码 (captcha)
- 短信验证 (SMS verification)
- 邮箱验证 (email verification)
- 风控弹窗 (security check / unusual traffic)

### 元数据追踪

`auto_action_metadata` 新增字段:
- `publish_attempts.api.count`: API 尝试次数
- `publish_attempts.rpa.count`: RPA 尝试次数
- `last_publish_channel`: 最近发布通道 (`api` / `rpa`)
- `last_error_stage`: 最近错误阶段 (`api_publish` / `rpa_prerequisite_check` / `rpa_manual_intervention` / `rpa_publish`)
- `last_celery_task_id`: 最近 Celery 任务 ID
- `manual_intervention_reason`: 人工介入原因
- `missing_fields`: 缺失字段列表

### 事件类型

新增 RunEvent 事件:
- `temu_api_publish_failed`: Temu API 发布失败
- `temu_rpa_fallback_queued`: RPA fallback 已入队
- `temu_rpa_fallback_started`: RPA fallback 开始执行
- `temu_rpa_prerequisite_missing`: 前置条件缺失
- `temu_rpa_publish_succeeded`: RPA 发布成功
- `temu_rpa_publish_failed`: RPA 发布失败
- `temu_manual_intervention_required`: 需要人工介入

---

## 快速开始

### 1. 运行数据库迁移

```bash
cd backend
psql -U deyes -d deyes < migrations/003_auto_action_engine.sql
```

### 2. 配置环境变量

在 `.env` 文件中添加：

```bash
# Auto Action Engine
ENABLE_AUTO_ACTIONS=true

# Auto Publish Rules
AUTO_PUBLISH_REQUIRE_APPROVAL_FIRST_TIME=true
AUTO_PUBLISH_REQUIRE_APPROVAL_HIGH_RISK=true
AUTO_PUBLISH_REQUIRE_APPROVAL_PRICE_ABOVE=100.0
AUTO_PUBLISH_REQUIRE_APPROVAL_MARGIN_BELOW=0.25
AUTO_PUBLISH_AUTO_EXECUTE_SCORE_ABOVE=75.0
AUTO_PUBLISH_AUTO_EXECUTE_RISK_BELOW=30
AUTO_PUBLISH_AUTO_EXECUTE_MARGIN_ABOVE=0.35

# Auto Reprice Rules
AUTO_REPRICE_ENABLE=true
AUTO_REPRICE_TARGET_ROI=0.30
AUTO_REPRICE_LOW_ROI_THRESHOLD=0.24
AUTO_REPRICE_HIGH_ROI_THRESHOLD=0.36
AUTO_REPRICE_DECREASE_PERCENTAGE=0.08
AUTO_REPRICE_INCREASE_PERCENTAGE=0.04
AUTO_REPRICE_MAX_CHANGE_PERCENTAGE=0.10
AUTO_REPRICE_LOOKBACK_DAYS=7

# Auto Pause Rules
AUTO_PAUSE_ENABLE=true
AUTO_PAUSE_ROI_THRESHOLD=0.10
AUTO_PAUSE_LOOKBACK_DAYS=7
AUTO_PAUSE_MIN_DATA_POINTS=7

# Auto Asset Switch Rules
AUTO_ASSET_SWITCH_ENABLE=true
AUTO_ASSET_SWITCH_CTR_THRESHOLD=0.80
AUTO_ASSET_SWITCH_LOOKBACK_DAYS=7

# Platform API Configuration
TEMU_API_BASE_URL=https://api-sg.temu.com
TEMU_USE_MOCK=true  # Set to false in production

# Temu RPA Fallback (Phase 1)
RPA_ENABLE=true
TEMU_RPA_ENABLED=true
TEMU_RPA_LOGIN_URL=https://seller.temu.example/login
TEMU_RPA_PUBLISH_URL=https://seller.temu.example/publish
TEMU_RPA_USERNAME=your-temu-seller-username
TEMU_RPA_PASSWORD=your-temu-seller-password
RPA_MANUAL_INTERVENTION_ON_CHALLENGE=true
RPA_TIMEOUT=300000
```

### 3. 启动服务

```bash
cd backend
uvicorn app.main:app --reload
```

### 4. 访问 API 文档

打开浏览器访问：`http://localhost:8000/docs`

---

## API 使用示例

### 1. 自动上架

**重要变更 (2026-03-27)**:
- `recommendation_score`, `risk_score`, `margin_percentage` 参数已废弃
- 服务端会从数据库重新计算这些值（source-of-truth）
- 客户端仍需传递这些字段以保持向后兼容，但值会被忽略
- 审批决策基于 `PricingAssessment`, `RiskAssessment`, `CandidateProduct.normalized_attributes`

```bash
curl -X POST http://localhost:8000/api/v1/auto-actions/publish \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_id": "550e8400-e29b-41d4-a716-446655440000",
    "platform": "temu",
    "region": "US",
    "price": 50.0,
    "currency": "USD",
    "recommendation_score": 80.0,
    "risk_score": 20,
    "margin_percentage": 40.0
  }'
```

**注意**: 上述 `recommendation_score`, `risk_score`, `margin_percentage` 会被服务端忽略并重新计算。

**响应示例**：

```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "candidate_product_id": "550e8400-e29b-41d4-a716-446655440000",
  "platform": "temu",
  "region": "US",
  "price": 50.0,
  "currency": "USD",
  "status": "pending_approval",
  "approval_required": true,
  "approval_reason": "first_time_product",
  "auto_action_metadata": {
    "recommendation_score": 72.0,
    "risk_score": 80,
    "margin_percentage": 20.0,
    "created_by": "auto_action_engine"
  }
}
```

**注意**: `auto_action_metadata` 中的分数是服务端根据数据库真实数据重新计算的结果，不是客户端请求中传入的值。

### 2. 获取待审批列表

```bash
curl http://localhost:8000/api/v1/auto-actions/pending-approval?limit=20
```

**响应示例**：

```json
{
  "items": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440001",
      "candidate_product_id": "550e8400-e29b-41d4-a716-446655440000",
      "platform": "temu",
      "status": "pending_approval",
      "approval_required": true,
      "approval_reason": "first_time_product"
    }
  ],
  "count": 1
}
```

### 3. 审批通过

```bash
curl -X POST http://localhost:8000/api/v1/auto-actions/approve/660e8400-e29b-41d4-a716-446655440001 \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "admin@example.com"
  }'
```

### 4. 审批拒绝

```bash
curl -X POST http://localhost:8000/api/v1/auto-actions/reject/660e8400-e29b-41d4-a716-446655440001 \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "admin@example.com",
    "reason": "Low quality product"
  }'
```

### 5. 触发自动调价

```bash
curl -X POST http://localhost:8000/api/v1/auto-actions/reprice/660e8400-e29b-41d4-a716-446655440001
```

### 6. 触发自动暂停

```bash
curl -X POST http://localhost:8000/api/v1/auto-actions/pause/660e8400-e29b-41d4-a716-446655440001
```

### 7. 触发自动换素材

```bash
curl -X POST http://localhost:8000/api/v1/auto-actions/switch-asset/660e8400-e29b-41d4-a716-446655440001
```

---

## 审批边界说明

### 自动执行（无需审批）

以下情况会自动执行，无需人工审批：

- 推荐分数 ≥ 75
- 风险分数 < 30
- 利润率 ≥ 35%
- 价格调整 ≤ 10%
- 素材切换（基于 CTR）
- 暂停低效商品（ROI < 10%）

### 需要审批

以下情况需要人工审批：

- 首次上架新商品
- 高风险品类（风险分数 ≥ 50）
- 高价商品（价格 > $100）
- 低利润率（< 25%）
- 大幅调价（> 10%）
- 下架商品

### 配置审批边界

可以通过环境变量调整审批边界：

```bash
# 首次上架是否需要审批
AUTO_PUBLISH_REQUIRE_APPROVAL_FIRST_TIME=true

# 高风险是否需要审批
AUTO_PUBLISH_REQUIRE_APPROVAL_HIGH_RISK=true

# 价格阈值（超过此价格需要审批）
AUTO_PUBLISH_REQUIRE_APPROVAL_PRICE_ABOVE=100.0

# 利润率阈值（低于此利润率需要审批）
AUTO_PUBLISH_REQUIRE_APPROVAL_MARGIN_BELOW=0.25

# 自动执行的推荐分数阈值
AUTO_PUBLISH_AUTO_EXECUTE_SCORE_ABOVE=75.0

# 自动执行的风险分数阈值
AUTO_PUBLISH_AUTO_EXECUTE_RISK_BELOW=30

# 自动执行的利润率阈值
AUTO_PUBLISH_AUTO_EXECUTE_MARGIN_ABOVE=0.35
```

---

## 定时任务配置

### Celery Beat 配置

在 `backend/app/workers/celery_app.py` 中添加：

```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    # 每天凌晨 2:00 执行自动调价
    'auto-reprice-daily': {
        'task': 'tasks.auto_reprice_all_listings',
        'schedule': crontab(hour=2, minute=0),
    },
    # 每天凌晨 3:00 执行自动暂停
    'auto-pause-daily': {
        'task': 'tasks.auto_pause_all_listings',
        'schedule': crontab(hour=3, minute=0),
    },
    # 每天凌晨 4:00 执行自动换素材
    'auto-asset-switch-daily': {
        'task': 'tasks.auto_asset_switch_all_listings',
        'schedule': crontab(hour=4, minute=0),
    },
}
```

### 启动 Celery Worker 和 Beat

```bash
# 启动 Worker
celery -A app.workers.celery_app worker --loglevel=info

# 启动 Beat（定时任务调度器）
celery -A app.workers.celery_app beat --loglevel=info
```

---

## 故障排查

### 问题 1: Temu 自动上架失败

**症状 A**：listing 状态为 `fallback_queued`

说明 Temu API 发布失败，系统已经自动入队异步 RPA fallback。这是一期设计内的正常路径，不是最终失败。

**排查步骤**：

1. 检查 worker 是否正常消费任务：`celery -A app.workers.celery_app inspect active`
2. 检查 `auto_action_metadata.last_celery_task_id`
3. 检查 RunEvent 是否有：
   - `temu_api_publish_failed`
   - `temu_rpa_fallback_queued`
   - `temu_rpa_fallback_started`
4. 查看 worker 日志中 `temu_rpa_publish_fallback` 任务执行情况

**症状 B**：listing 状态为 `manual_intervention_required`

说明一期 RPA fallback 因前置条件缺失或 challenge 场景转人工处理。

**排查步骤**：

1. 检查 `auto_action_metadata.manual_intervention_reason`
2. 检查 `auto_action_metadata.missing_fields`
3. 核对以下 RPA 配置是否完整：
   - `TEMU_RPA_LOGIN_URL`
   - `TEMU_RPA_PUBLISH_URL`
   - `TEMU_RPA_USERNAME`
   - `TEMU_RPA_PASSWORD`
4. 如果是 challenge，查看页面是否出现 captcha / 短信验证 / 邮箱验证 / 风控弹窗

**症状 C**：listing 状态为 `rejected`

说明 API 和 RPA 自动路径都已走尽，或非 Temu 平台仍按原逻辑直接失败。

**排查步骤**：

1. 检查 `last_error_stage` 是否为 `rpa_publish`
2. 检查 `publish_attempts.api.count` 和 `publish_attempts.rpa.count`
3. 查看 RunEvent 中的 `temu_rpa_publish_failed`

### 问题 2: 审批列表为空

**症状**：`/pending-approval` 返回空列表

**排查步骤**：

1. 检查是否有 `pending_approval` 状态的 listing
2. 检查审批边界配置是否过于宽松（所有商品都自动执行）
3. 查询数据库：`SELECT * FROM platform_listings WHERE status = 'pending_approval';`

### 问题 3: 自动调价不生效

**症状**：`auto_reprice` 返回 `success: false`

**排查步骤**：

1. 检查 `AUTO_REPRICE_ENABLE` 是否为 `true`
2. 检查 listing 是否有性能数据（`listing_performance_daily` 表）
3. 检查 ROI 是否在目标范围内（不需要调价）
4. 查看日志：`grep "auto_reprice" backend/logs/app.log`

### 问题 4: RunEvent 记录失败

**症状**：日志中有 `strategy_run_id` 相关错误

**排查步骤**：

1. 检查 candidate 是否有有效的 `strategy_run_id`
2. 检查 `strategy_runs` 表是否存在对应记录
3. 如果是测试环境，确保创建了 `sample_strategy_run` fixture

---

## 最佳实践

### 1. 渐进式启用

建议按以下顺序逐步启用自动化功能：

1. **第一周**：只启用自动上架，所有操作都需要审批
2. **第二周**：启用自动调价，观察效果
3. **第三周**：启用自动暂停
4. **第四周**：启用自动换素材

### 2. 监控关键指标

定期监控以下指标：

- 自动执行成功率
- 人工审批通过率
- 平均 ROI 变化
- 暂停商品数量
- 素材切换效果

### 3. 调整审批边界

根据实际运营情况调整审批边界：

- 如果人工审批负担过重，提高自动执行阈值
- 如果自动执行错误率过高，降低自动执行阈值

### 4. 定期回顾

每月回顾自动化效果：

- 哪些商品被自动暂停了？是否合理？
- 自动调价是否提高了 ROI？
- 自动换素材是否提高了 CTR？

---

## 相关文档

- [项目状态报告](../PROJECT_STATUS.md) - 战略转向说明
- [核心业务流程](../workflows/core-business-flows.md) - 自动化经营流程
- [研发路线图](../roadmap/engineering-roadmap-2026.md) - 技术实现路线

---

**文档维护**: 本文档应在 AutoActionEngine 功能更新后同步更新
