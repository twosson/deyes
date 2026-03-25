# 平台同步端到端联调清单

## 前置条件

- ✅ 基础服务已启动（postgres, redis, backend, worker, beat）
- ✅ 数据库迁移已完成
- ✅ 至少有一条 `platform_listing_id` 不为空的 listing 记录

---

## 一、准备工作

### 1. 确认服务状态

```bash
cd /data/deyes
docker compose ps backend worker beat postgres redis
```

预期：所有服务都是 `Up` 状态。

### 2. 查看日志（开三个窗口）

```bash
# 窗口 1
docker compose logs -f backend

# 窗口 2
docker compose logs -f worker

# 窗口 3
docker compose logs -f beat
```

### 3. 选择测试 listing

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
SELECT id, platform_listing_id, platform, region, inventory, price, status, last_synced_at
FROM platform_listings
WHERE platform_listing_id IS NOT NULL
LIMIT 10;
"
```

记下一个 `listing_id`，后续用 `<LISTING_ID>` 表示。

---

## 二、联调前快照

### 1. 记录 listing 当前状态

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
SELECT id, platform_listing_id, inventory, price, status, last_synced_at, sync_error
FROM platform_listings
WHERE id = '<LISTING_ID>';
"
```

### 2. 记录当前 metrics

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
SELECT listing_id, metric_date, impressions, clicks, orders, units_sold, revenue
FROM listing_performance_daily
WHERE listing_id = '<LISTING_ID>'
ORDER BY metric_date DESC
LIMIT 10;
"
```

---

## 三、测试链路 A：inventory sync

### 触发方式

**方式 1：通过 API**（如果 API 已实现）
```bash
curl -X POST http://localhost:8000/api/v1/platform-listings/sync-inventory \
  -H "Content-Type: application/json" \
  -d '{"listing_ids": ["<LISTING_ID>"]}'
```

**方式 2：通过 Python shell**
```bash
docker compose exec backend python -c "
import asyncio
from uuid import UUID
from app.db.session import get_db_context
from app.services.platform_sync_service import PlatformSyncService

async def run():
    async with get_db_context() as db:
        service = PlatformSyncService()
        result = await service.sync_listing_inventory(
            db,
            listing_id=UUID('<LISTING_ID>')
        )
        print(result)

asyncio.run(run())
"
```

### 验证点

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
SELECT id, inventory, last_synced_at, sync_error, platform_data->'inventory_sync' as inventory_sync
FROM platform_listings
WHERE id = '<LISTING_ID>';
"
```

**预期结果：**
- `last_synced_at` 更新为最新时间
- `sync_error` 为空
- `platform_data.inventory_sync` 有记录

**对应代码：**
- `backend/app/services/platform_sync_service.py:164`

---

## 四、测试链路 B：status sync

### 触发方式

**通过 Python shell**
```bash
docker compose exec backend python -c "
import asyncio
from uuid import UUID
from app.db.session import get_db_context
from app.services.platform_sync_service import PlatformSyncService

async def run():
    async with get_db_context() as db:
        service = PlatformSyncService()
        result = await service.sync_listing_status(
            db,
            listing_id=UUID('<LISTING_ID>')
        )
        print(result)

asyncio.run(run())
"
```

### 验证点

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
SELECT id, inventory, price, status, last_synced_at, sync_error, platform_data->'status_sync' as status_sync
FROM platform_listings
WHERE id = '<LISTING_ID>';
"
```

**预期结果：**
- 本地 `inventory / price / status` 与远端返回一致
- `platform_data.status_sync` 有原始 payload
- `sync_error` 为空

**特殊情况：**
- 如果远端 `inventory = 0`，本地 `status` 会被映射为 `OUT_OF_STOCK`

**对应代码：**
- `backend/app/services/platform_sync_service.py:101`
- `backend/app/services/platform_sync_service.py:127` (inventory=0 逻辑)

---

## 五、测试链路 C：metrics sync

### 触发方式

**通过 Python shell**
```bash
docker compose exec backend python -c "
import asyncio
from datetime import date
from uuid import UUID
from app.db.session import get_db_context
from app.services.platform_sync_service import PlatformSyncService

async def run():
    async with get_db_context() as db:
        service = PlatformSyncService()
        today = date.today()
        result = await service.sync_listing_metrics(
            db,
            listing_id=UUID('<LISTING_ID>'),
            start_date=today,
            end_date=today
        )
        print(result)

asyncio.run(run())
"
```

### 验证点

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
SELECT listing_id, metric_date, impressions, clicks, orders, units_sold, revenue, raw_payload
FROM listing_performance_daily
WHERE listing_id = '<LISTING_ID>'
ORDER BY metric_date DESC
LIMIT 10;
"
```

**预期结果：**
- 新增一条 `metric_date = 今天` 的记录
- `impressions / clicks / orders / units_sold / revenue` 有值
- `raw_payload` 包含原始 adapter 返回

**特殊情况：**
- 如果远端没有指标，返回 `{"status": "no_data", "synced_days": 0}`
- 不会插入假数据

**对应代码：**
- `backend/app/services/platform_sync_service.py:25`
- `backend/app/services/platform_sync_service.py:73` (只落 end_date 一条)

---

## 六、Agent 级别联调

如果你想测试完整的 agent 编排（包括 `last_synced_at` / `sync_error` 更新），可以通过 agent 入口：

```bash
docker compose exec backend python -c "
import asyncio
from uuid import uuid4
from app.db.session import get_db_context
from app.agents.base.agent import AgentContext
from app.agents.platform_publisher import PlatformSyncAgent

async def run():
    async with get_db_context() as db:
        agent = PlatformSyncAgent()
        context = AgentContext(
            strategy_run_id=uuid4(),
            db=db,
            input_data={
                'sync_type': 'listing_metrics',
                'platform_listing_ids': ['<LISTING_ID>']
            }
        )
        result = await agent.execute(context)
        print(result)

asyncio.run(run())
"
```

**验证点：**
```bash
docker compose exec postgres psql -U deyes -d deyes -c "
SELECT id, last_synced_at, sync_error
FROM platform_listings
WHERE id = '<LISTING_ID>';
"
```

**预期：**
- 成功时 `last_synced_at` 更新，`sync_error` 为空
- 失败时 `sync_error` 有错误信息

**对应代码：**
- `backend/app/agents/platform_publisher.py:508` (last_synced_at)
- `backend/app/agents/platform_publisher.py:517` (sync_error)

---

## 七、通过标准

你可以按这个标准判断联调是否通过：

### inventory sync ✅
- 无报错
- `sync_error` 为空
- `last_synced_at` 更新
- `platform_data.inventory_sync` 有记录

### status sync ✅
- 本地 `inventory / price / status` 与远端一致
- `platform_data.status_sync` 有原始 payload
- `sync_error` 为空

### metrics sync ✅
- `listing_performance_daily` 新增一条记录
- `metric_date = end_date`
- `impressions / clicks / orders / units_sold / revenue` 有值
- 如果远端没指标，明确返回 `no_data`，不写假数据

---

## 八、故障排查

### 问题 1：找不到 listing
```
ValueError: Listing not found: <LISTING_ID>
```
**解决：** 确认 listing_id 正确，且记录存在。

### 问题 2：platform_listing_id 为空
```
ValueError: Listing <LISTING_ID> missing platform_listing_id; cannot sync
```
**解决：** 选择一个 `platform_listing_id` 不为空的 listing。

### 问题 3：adapter 返回空
```
RuntimeError: Failed to fetch status for listing <LISTING_ID>
```
**解决：** 检查 adapter 配置，确认 mock adapter 是否正确初始化。

### 问题 4：metrics 返回 no_data
```
{"status": "no_data", "synced_days": 0}
```
**说明：** 这是正常行为，表示远端没有可用指标，不会插入假数据。

---

## 九、清理

联调完成后，如果需要清理测试数据：

```bash
docker compose exec postgres psql -U deyes -d deyes -c "
DELETE FROM listing_performance_daily WHERE listing_id = '<LISTING_ID>';
"
```

---

## 十、下一步

联调通过后，可以：

1. 验证 Celery Beat 定时任务是否正常触发
2. 测试多 listing 批量同步
3. 测试错误恢复和重试机制
4. 进入 Week 3 的其他 agent 开发

---

**最后更新：** 2026-03-26
**对应实现：** backend/app/services/platform_sync_service.py
