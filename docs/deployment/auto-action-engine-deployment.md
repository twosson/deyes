# AutoActionEngine 服务器部署指南

> 专项部署指南 - AutoActionEngine 自动化经营引擎
>
> 最后更新: 2026-03-27
> 版本: v1.1 (新增 Temu RPA Fallback Phase 1)

---

## 概述

本文档提供 AutoActionEngine 在服务器上的完整部署流程。AutoActionEngine 是 Deyes 自动化经营系统的核心引擎，实现从"推荐分析"到"自动执行"的战略转向。

**前置条件**: 已按照根目录 `DEPLOYMENT.md` 完成基础服务部署。

### Temu RPA Fallback Phase 1 🆕

**第一期仅支持**:
- ✅ **平台**: Temu only
- ✅ **操作**: publish fallback only
- ✅ **触发**: Temu API 失败后自动异步 Celery fallback
- ✅ **Challenge 处理**: 验证码/短信/邮箱验证 → 转人工介入
- ❌ **不支持**: 自动打码、自动短信验证、Amazon/AliExpress RPA

---

## 1. 部署前检查

### 1.1 确认基础服务运行正常

```bash
cd ~/deyes
docker compose ps
```

确认以下服务状态为 `Up`:
- `deyes-postgres` (healthy)
- `deyes-redis`
- `deyes-backend`
- `deyes-worker`
- `deyes-beat`

### 1.2 确认 API 可访问

```bash
curl http://127.0.0.1:8000/api/v1/health
```

预期响应:
```json
{"status": "ok"}
```

---

## 2. 代码部署

### 2.1 拉取最新代码

```bash
cd ~/deyes
git pull origin main
```

### 2.2 确认 AutoActionEngine 文件存在

```bash
ls -la backend/app/services/auto_action_engine.py
ls -la backend/app/api/routes_auto_actions.py
ls -la backend/app/clients/temu_api.py
ls -la backend/app/workers/tasks_auto_actions.py
ls -la backend/migrations/003_auto_action_engine.sql
```

---

## 3. 环境配置

### 3.1 备份现有 .env

```bash
cp backend/.env backend/.env.backup.$(date +%Y%m%d_%H%M%S)
```

### 3.2 添加 AutoActionEngine 配置

编辑 `backend/.env`,添加以下配置:

```bash
# Auto Action Engine (2026-03-27)
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
TEMU_USE_MOCK=true

# Temu RPA Fallback (Phase 1) 🆕
RPA_ENABLE=true
TEMU_RPA_ENABLED=true
TEMU_RPA_LOGIN_URL=https://seller.temu.example/login
TEMU_RPA_PUBLISH_URL=https://seller.temu.example/publish
TEMU_RPA_USERNAME=your-temu-seller-username
TEMU_RPA_PASSWORD=your-temu-seller-password
RPA_MANUAL_INTERVENTION_ON_CHALLENGE=true
RPA_TIMEOUT=300000
```

### 3.3 验证配置

```bash
grep "ENABLE_AUTO_ACTIONS" backend/.env
grep "AUTO_PUBLISH_" backend/.env | head -5
grep "TEMU_RPA_" backend/.env
grep "RPA_MANUAL_INTERVENTION_ON_CHALLENGE" backend/.env
```

确认以下配置不为空:
- `TEMU_RPA_LOGIN_URL`
- `TEMU_RPA_PUBLISH_URL`
- `TEMU_RPA_USERNAME`
- `TEMU_RPA_PASSWORD`

---

## 4. 数据库迁移

### 4.1 执行迁移脚本

```bash
cd ~/deyes
docker compose exec postgres psql -U deyes -d deyes -f /tmp/003_auto_action_engine.sql
```

**注意**: 需要先将迁移文件复制到容器内:

```bash
docker cp backend/migrations/003_auto_action_engine.sql deyes-postgres:/tmp/
docker compose exec postgres psql -U deyes -d deyes -f /tmp/003_auto_action_engine.sql
```

### 4.2 验证迁移结果

检查新增字段:

```bash
docker compose exec postgres psql -U deyes -d deyes -c "\d platform_listings"
```

确认以下字段存在:
- `approval_required` (boolean)
- `approval_reason` (text)
- `auto_action_metadata` (jsonb)
- `approved_at` (timestamp)
- `approved_by` (text)
- `rejected_at` (timestamp)
- `rejected_by` (text)
- `rejection_reason` (text)
- `last_auto_action_at` (timestamp)

检查新增表:

```bash
docker compose exec postgres psql -U deyes -d deyes -c "\dt price_history"
```

### 4.3 验证索引

```bash
docker compose exec postgres psql -U deyes -d deyes -c "\di idx_platform_listings_approval"
```

---

## 5. 重启服务

### 5.1 重启 Backend

```bash
docker compose restart backend
```

### 5.2 重启 Worker

```bash
docker compose restart worker
```

### 5.3 重启 Beat (定时任务调度器)

```bash
docker compose restart beat
```

### 5.4 查看启动日志

```bash
docker compose logs -f backend | grep -i "auto_action"
docker compose logs -f worker | grep -i "celery"
docker compose logs -f beat | grep -i "beat"
```

---

## 6. 验证部署

### 6.1 检查 API 端点

访问 Swagger 文档:

```bash
curl http://127.0.0.1:8000/docs
```

或在浏览器打开: `http://<server-ip>:8000/docs`

确认以下端点存在:
- `POST /api/v1/auto-actions/publish`
- `GET /api/v1/auto-actions/pending-approval`
- `POST /api/v1/auto-actions/approve/{listing_id}`
- `POST /api/v1/auto-actions/reject/{listing_id}`
- `POST /api/v1/auto-actions/reprice/{listing_id}`
- `POST /api/v1/auto-actions/pause/{listing_id}`
- `POST /api/v1/auto-actions/switch-asset/{listing_id}`

### 6.2 测试自动上架 API

**重要变更 (2026-03-27)**:
- `recommendation_score`, `risk_score`, `margin_percentage` 参数已废弃
- 服务端会从数据库重新计算这些值（source-of-truth）
- 客户端仍需传递这些字段以保持向后兼容，但值会被忽略

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auto-actions/publish \
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

**注意**:
- 需要先创建一个有效的 candidate_id,或使用数据库中已有的 ID
- 上述 `recommendation_score`, `risk_score`, `margin_percentage` 会被服务端忽略并重新计算

### 6.3 查看待审批列表

```bash
curl http://127.0.0.1:8000/api/v1/auto-actions/pending-approval?limit=20
```

### 6.4 验证 Temu RPA Fallback 状态流转 🆕

检查 listing 状态是否包含新增的 fallback 状态:

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
  SELECT DISTINCT status
  FROM platform_listings
  WHERE platform = 'temu'
  ORDER BY status;
"
```

预期包含:
- `fallback_queued`
- `fallback_running`
- `manual_intervention_required`

### 6.5 验证 RunEvent 事件类型 🆕

检查是否有 Temu RPA fallback 相关事件:

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
  SELECT DISTINCT event_type
  FROM run_events
  WHERE event_type LIKE 'temu_%'
  ORDER BY event_type;
"
```

预期包含:
- `temu_api_publish_failed`
- `temu_rpa_fallback_queued`
- `temu_rpa_fallback_started`
- `temu_rpa_prerequisite_missing`
- `temu_rpa_publish_succeeded`
- `temu_rpa_publish_failed`
- `temu_manual_intervention_required`

### 6.6 验证 Celery 定时任务

检查 Beat 是否注册了定时任务:

```bash
docker compose logs beat | grep -i "auto_reprice_all_listings"
docker compose logs beat | grep -i "auto_pause_all_listings"
docker compose logs beat | grep -i "auto_asset_switch_all_listings"
```

### 6.7 浏览器 / Worker 烟雾验证 🆕

当 `TEMU_USE_MOCK=false` 且配置了真实 Temu 卖家后台地址后，进行以下烟雾验证:

1. 触发一次 Temu publish，确认 API 失败后 listing 进入 `fallback_queued`
2. 查看 worker 日志，确认执行了 `tasks.temu_rpa_publish_fallback`
3. 观察 listing 是否继续流转为:
   - `active`（RPA 成功）
   - `manual_intervention_required`（遇到 challenge / 缺前置条件）
   - `rejected`（RPA 普通失败）
4. 检查 `auto_action_metadata` 是否写入:
   - `last_celery_task_id`
   - `last_publish_channel`
   - `last_error_stage`
   - `manual_intervention_reason`
   - `missing_fields`

可使用以下 SQL 检查最新 Temu listing:

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
  SELECT id, status, sync_error, auto_action_metadata
  FROM platform_listings
  WHERE platform = 'temu'
  ORDER BY created_at DESC
  LIMIT 5;
"
```

---

## 7. 配置定时任务 (可选)

### 7.1 当前定时任务配置

定时任务已在 `backend/app/workers/celery_app.py` 中配置:

- **每天凌晨 2:00** - 自动调价 (`auto_reprice_all_listings`)
- **每天凌晨 3:00** - 自动暂停 (`auto_pause_all_listings`)
- **每天凌晨 4:00** - 自动换素材 (`auto_asset_switch_all_listings`)

### 7.2 手动触发定时任务 (测试)

```bash
# 手动触发自动调价
docker compose exec worker celery -A app.workers.celery_app call tasks.auto_reprice_all_listings

# 手动触发自动暂停
docker compose exec worker celery -A app.workers.celery_app call tasks.auto_pause_all_listings

# 手动触发自动换素材
docker compose exec worker celery -A app.workers.celery_app call tasks.auto_asset_switch_all_listings
```

### 7.3 查看任务执行结果

```bash
docker compose logs worker | grep -i "task_completed"
```

---

## 8. 监控与日志

### 8.1 实时监控 AutoActionEngine 日志

```bash
docker compose logs -f backend | grep -i "auto_action"
```

### 8.2 查看 RunEvent 审计日志

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
  SELECT event_type, event_payload, created_at
  FROM run_events
  WHERE event_type LIKE 'auto_%' OR event_type LIKE 'temu_%'
  ORDER BY created_at DESC
  LIMIT 10;
"
```

### 8.3 查看 PriceHistory

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
  SELECT listing_id, old_price, new_price, reason, changed_at
  FROM price_history
  ORDER BY changed_at DESC
  LIMIT 10;
"
```

### 8.4 查看待审批 Listing

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
  SELECT id, platform, region, price, status, approval_reason
  FROM platform_listings
  WHERE status = 'pending_approval'
  ORDER BY created_at DESC;
"
```

---

## 9. 故障排查

### 9.1 Temu API 失败后未进入 fallback_queued 🆕

**症状**: Temu listing 在 API 失败后直接进入 `rejected`，而不是 `fallback_queued`

**排查步骤**:

1. 确认 `TEMU_RPA_ENABLED` 配置:
   ```bash
   grep "TEMU_RPA_ENABLED" backend/.env
   ```

2. 确认 `RPA_ENABLE` 配置:
   ```bash
   grep "RPA_ENABLE" backend/.env
   ```

3. 查看 backend 日志中是否有 fallback 入队记录:
   ```bash
   docker compose logs backend | grep -i "temu_rpa_fallback_queued"
   ```

4. 检查 `auto_action_metadata` 中的 `last_error_stage`:
   ```bash
   docker compose exec postgres psql -U deyes -d deyes -c "
     SELECT id, status, auto_action_metadata->'last_error_stage' AS last_error_stage
     FROM platform_listings
     WHERE platform = 'temu' AND status = 'rejected'
     ORDER BY created_at DESC
     LIMIT 5;
   "
   ```

### 9.2 Listing 停留在 fallback_queued 🆕

**症状**: listing 状态为 `fallback_queued`，长时间未流转

**排查步骤**:

1. 确认 worker 容器运行正常:
   ```bash
   docker compose ps worker
   docker compose logs worker | tail -50
   ```

2. 检查 worker 是否消费任务:
   ```bash
   docker compose exec worker celery -A app.workers.celery_app inspect active
   ```

3. 检查 `last_celery_task_id`:
   ```bash
   docker compose exec postgres psql -U deyes -d deyes -c "
     SELECT id, status, auto_action_metadata->'last_celery_task_id' AS task_id
     FROM platform_listings
     WHERE status = 'fallback_queued'
     ORDER BY created_at DESC;
   "
   ```

4. 查看 worker 日志中该任务执行情况:
   ```bash
   docker compose logs worker | grep "temu_rpa_publish_fallback"
   ```

### 9.3 Listing 进入 manual_intervention_required 🆕

**症状**: listing 状态为 `manual_intervention_required`

**排查步骤**:

1. 检查 `manual_intervention_reason`:
   ```bash
   docker compose exec postgres psql -U deyes -d deyes -c "
     SELECT id, status,
            auto_action_metadata->'manual_intervention_reason' AS reason,
            auto_action_metadata->'missing_fields' AS missing_fields
     FROM platform_listings
     WHERE status = 'manual_intervention_required'
     ORDER BY created_at DESC
     LIMIT 5;
   "
   ```

2. 如果是前置条件缺失，核对以下配置:
   ```bash
   grep "TEMU_RPA_LOGIN_URL" backend/.env
   grep "TEMU_RPA_PUBLISH_URL" backend/.env
   grep "TEMU_RPA_USERNAME" backend/.env
   grep "TEMU_RPA_PASSWORD" backend/.env
   ```

3. 如果是 challenge 场景，查看 RunEvent:
   ```bash
   docker compose exec postgres psql -U deyes -d deyes -c "
     SELECT event_type, event_payload
     FROM run_events
     WHERE event_type = 'temu_manual_intervention_required'
     ORDER BY created_at DESC
     LIMIT 5;
   "
   ```

4. 如果是 payload 字段缺失，检查 candidate 数据:
   ```bash
   docker compose exec postgres psql -U deyes -d deyes -c "
     SELECT id, title, main_image_url, category, raw_payload
     FROM candidate_products
     WHERE id = '<candidate_id>';
   "
   ```

### 9.4 API 端点不存在

**症状**: 访问 `/api/v1/auto-actions/*` 返回 404

**排查步骤**:

1. 确认代码已拉取:
   ```bash
   ls -la backend/app/api/routes_auto_actions.py
   ```

2. 确认路由已注册:
   ```bash
   grep "auto_actions" backend/app/main.py
   ```

3. 重启 backend:
   ```bash
   docker compose restart backend
   docker compose logs -f backend
   ```

### 9.5 数据库字段不存在

**症状**: 日志中出现 `column "approval_required" does not exist`

**排查步骤**:

1. 确认迁移脚本已执行:
   ```bash
   docker compose exec postgres psql -U deyes -d deyes -c "\d platform_listings"
   ```

2. 手动执行迁移:
   ```bash
   docker cp backend/migrations/003_auto_action_engine.sql deyes-postgres:/tmp/
   docker compose exec postgres psql -U deyes -d deyes -f /tmp/003_auto_action_engine.sql
   ```

3. 重启 backend 和 worker:
   ```bash
   docker compose restart backend worker
   ```

### 9.6 RunEvent 记录失败

**症状**: 日志中出现 `strategy_run_id` 相关错误

**排查步骤**:

1. 确认 candidate 有有效的 `strategy_run_id`:
   ```bash
   docker compose exec postgres psql -U deyes -d deyes -c "
     SELECT id, strategy_run_id
     FROM candidate_products
     WHERE strategy_run_id IS NOT NULL
     LIMIT 5;
   "
   ```

2. 如果是测试环境,确保创建了 `strategy_run`:
   ```bash
   docker compose exec postgres psql -U deyes -d deyes -c "
     INSERT INTO strategy_runs (id, status, platform, region, created_at, updated_at)
     VALUES (
       '00000000-0000-0000-0000-000000000000',
       'completed',
       'temu',
       'US',
       NOW(),
       NOW()
     )
     ON CONFLICT (id) DO NOTHING;
   "
   ```

### 9.7 Celery 定时任务不执行

**症状**: 定时任务到点不执行

**排查步骤**:

1. 确认 Beat 容器运行正常:
   ```bash
   docker compose ps beat
   docker compose logs beat | tail -50
   ```

2. 确认定时任务已注册:
   ```bash
   docker compose logs beat | grep -i "schedule"
   ```

3. 手动触发测试:
   ```bash
   docker compose exec worker celery -A app.workers.celery_app call tasks.auto_reprice_all_listings
   ```

### 9.8 平台 API 调用失败

**症状 A**: Temu listing 状态为 `fallback_queued`

说明 Temu API 失败后已进入一期设计内的异步 RPA fallback，不是最终失败。

**排查步骤**:

1. 检查 worker 是否继续处理
2. 检查 `auto_action_metadata.last_celery_task_id`
3. 查看 `temu_api_publish_failed` / `temu_rpa_fallback_queued` / `temu_rpa_fallback_started` 事件

**症状 B**: 非 Temu 或最终状态为 `rejected`

**排查步骤**:

1. 确认 `TEMU_USE_MOCK` 配置:
   ```bash
   grep "TEMU_USE_MOCK" backend/.env
   ```

2. 开发环境应设置为 `true`:
   ```bash
   echo "TEMU_USE_MOCK=true" >> backend/.env
   docker compose restart backend worker
   ```

3. 查看详细错误日志:
   ```bash
   docker compose logs backend | grep -i "platform_api"
   ```

---

## 10. 生产环境配置建议

### 10.1 调整审批边界

**重要**: 审批决策基于服务端从数据库重算的真实值，不依赖客户端传入的分数。

根据实际运营情况调整 `.env` 中的阈值:

```bash
# 提高自动执行门槛 (更保守)
AUTO_PUBLISH_AUTO_EXECUTE_SCORE_ABOVE=85.0
AUTO_PUBLISH_AUTO_EXECUTE_RISK_BELOW=20
AUTO_PUBLISH_AUTO_EXECUTE_MARGIN_ABOVE=0.40

# 或降低门槛 (更激进)
AUTO_PUBLISH_AUTO_EXECUTE_SCORE_ABOVE=70.0
AUTO_PUBLISH_AUTO_EXECUTE_RISK_BELOW=40
AUTO_PUBLISH_AUTO_EXECUTE_MARGIN_ABOVE=0.30
```

### 10.2 启用真实平台 API

```bash
# 关闭 Mock 模式
TEMU_USE_MOCK=false

# 配置真实 API 凭证
TEMU_API_BASE_URL=https://api-sg.temu.com
TEMU_API_KEY=your-real-api-key
TEMU_API_SECRET=your-real-api-secret
```

### 10.3 调整定时任务时间

编辑 `backend/app/workers/celery_app.py`:

```python
celery_app.conf.beat_schedule = {
    'auto-reprice-daily': {
        'task': 'tasks.auto_reprice_all_listings',
        'schedule': crontab(hour=2, minute=0),  # 修改为合适的时间
    },
    # ...
}
```

重启 Beat:

```bash
docker compose restart beat
```

---

## 11. 回滚方案

### 11.1 回滚代码

```bash
cd ~/deyes
git log --oneline | head -10  # 查看最近提交
git checkout <previous-commit-hash>
docker compose restart backend worker beat
```

### 11.2 回滚数据库

```bash
# 备份当前数据
docker compose exec postgres pg_dump -U deyes deyes > backup_before_rollback.sql

# 删除新增字段 (谨慎操作)
docker compose exec postgres psql -U deyes -d deyes -c "
  ALTER TABLE platform_listings
  DROP COLUMN IF EXISTS approval_required,
  DROP COLUMN IF EXISTS approval_reason,
  DROP COLUMN IF EXISTS auto_action_metadata,
  DROP COLUMN IF EXISTS approved_at,
  DROP COLUMN IF EXISTS approved_by,
  DROP COLUMN IF EXISTS rejected_at,
  DROP COLUMN IF EXISTS rejected_by,
  DROP COLUMN IF EXISTS rejection_reason,
  DROP COLUMN IF EXISTS last_auto_action_at;
"

# 删除新增表
docker compose exec postgres psql -U deyes -d deyes -c "DROP TABLE IF EXISTS price_history;"
```

### 11.3 恢复配置

```bash
cp backend/.env.backup.<timestamp> backend/.env
docker compose restart backend worker beat
```

---

## 12. 相关文档

- [AutoActionEngine 使用指南](../services/auto-action-engine.md) - API 使用示例、配置说明
- [统一部署指南](../../DEPLOYMENT.md) - 基础服务部署
- [项目状态报告](../PROJECT_STATUS.md) - 战略转向说明
- [核心业务流程](../workflows/core-business-flows.md) - 自动化经营流程

---

**最后更新**: 2026-03-27
**状态**: 生产就绪
**维护者**: Deyes 开发团队
