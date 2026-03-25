# Stage 1 实施任务清单

> 基于研发路线图 Stage 1：补全"可经营闭环"的结果层
>
> 目标：让系统不仅能选品和上架，还能记录真实经营结果并回流
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 📋 Stage 1 总览

### 核心目标
从"能选品、能上架"升级为"能看结果、能复盘、能持续优化"

### 关键交付物
1. 平台表现数据回流
2. Listing 表现中心
3. 内容 A/B 测试基础
4. 真实平台同步

### 预期成果
- 一个商品从发现到上架后，能拿到真实经营结果
- 能按 listing / 素材 / 平台看表现
- 结果能回流系统，而不是停留在平台后台

---

## 🎯 任务分组

### 分组 A：数据模型与 Schema（优先级 P0）
### 分组 B：平台表现数据回流服务（优先级 P0）
### 分组 C：A/B 测试基础设施（优先级 P1）
### 分组 D：真实平台 API 集成（优先级 P0）
### 分组 E：测试与验证（优先级 P0）

---

## 分组 A：数据模型与 Schema

### A1. 设计 Listing 表现表 Schema

**任务描述**：
设计并实现 `ListingPerformanceDaily` 表，用于记录每个 listing 的每日表现数据。

**具体工作**：
1. 创建 SQLAlchemy 模型定义
2. 设计字段：
   - `id` (UUID, PK)
   - `listing_id` (UUID, FK to platform_listings)
   - `date` (Date, not null)
   - `impressions` (Integer, default 0)
   - `clicks` (Integer, default 0)
   - `ctr` (Decimal, computed)
   - `orders` (Integer, default 0)
   - `units_sold` (Integer, default 0)
   - `gross_revenue` (Decimal)
   - `refund_count` (Integer, default 0)
   - `refund_amount` (Decimal)
   - `created_at` / `updated_at`
3. 添加索引：`(listing_id, date)` unique
4. 添加关系：`listing: Mapped["PlatformListing"]`

**涉及文件**：
- 新增：`backend/app/db/models.py` (追加 `ListingPerformanceDaily` 类)
- 新增：`backend/migrations/versions/006_listing_performance.py`

**验收标准**：
- [ ] 模型定义完成
- [ ] migration 可成功执行
- [ ] 可通过 `PlatformListing.performance_records` 反向查询

**预估工作量**：2-3 小时

---

### A2. 设计 Asset 表现归因表 Schema

**任务描述**：
设计并实现 `AssetPerformanceDaily` 表，用于记录每个素材在特定 listing 上的表现归因。

**具体工作**：
1. 创建 SQLAlchemy 模型定义
2. 设计字段：
   - `id` (UUID, PK)
   - `asset_id` (UUID, FK to content_assets)
   - `listing_id` (UUID, FK to platform_listings)
   - `date` (Date, not null)
   - `impressions` (Integer, default 0)
   - `clicks` (Integer, default 0)
   - `ctr` (Decimal, computed)
   - `orders_attributed` (Integer, default 0)
   - `revenue_attributed` (Decimal)
   - `created_at` / `updated_at`
3. 添加索引：`(asset_id, listing_id, date)` unique
4. 添加关系：`asset` / `listing`

**涉及文件**：
- 修改：`backend/app/db/models.py` (追加 `AssetPerformanceDaily` 类)
- 修改：`backend/migrations/versions/006_listing_performance.py` (同一 migration)

**验收标准**：
- [ ] 模型定义完成
- [ ] migration 可成功执行
- [ ] 可通过 `ContentAsset.performance_records` 反向查询

**预估工作量**：2-3 小时

---

### A3. 扩展 ContentAsset 模型支持 A/B 测试

**任务描述**：
为 `ContentAsset` 增加 `variant_group` 字段，用于标识同一组 A/B 测试变体。

**具体工作**：
1. 在 `ContentAsset` 模型增加字段：
   - `variant_group` (String(50), nullable, index)
2. 创建 migration
3. 更新相关查询逻辑

**涉及文件**：
- 修改：`backend/app/db/models.py:258` (ContentAsset 类)
- 新增：`backend/migrations/versions/007_asset_variant_group.py`

**验收标准**：
- [ ] 字段添加完成
- [ ] migration 可成功执行
- [ ] 现有测试不受影响

**预估工作量**：1-2 小时

---

## 分组 B：平台表现数据回流服务

### B1. 实现 ListingMetricsService 基础框架

**任务描述**：
创建 `ListingMetricsService`，负责从平台拉取表现数据并写入 `ListingPerformanceDaily`。

**具体工作**：
1. 创建服务类框架
2. 实现方法：
   - `ingest_daily_metrics(listing_id, date, metrics_data)`
   - `get_listing_metrics(listing_id, start_date, end_date)`
   - `compute_ctr(impressions, clicks)`
3. 实现幂等性保证（upsert 逻辑）
4. 添加日志和错误处理

**涉及文件**：
- 新增：`backend/app/services/listing_metrics_service.py`

**验收标准**：
- [ ] 服务类可实例化
- [ ] `ingest_daily_metrics` 可正确写入数据
- [ ] 重复调用不会产生重复记录
- [ ] `get_listing_metrics` 可正确查询

**预估工作量**：4-6 小时

---

### B2. 实现 AssetPerformanceService 基础框架

**任务描述**：
创建 `AssetPerformanceService`，负责素材表现归因数据的写入和查询。

**具体工作**：
1. 创建服务类框架
2. 实现方法：
   - `ingest_asset_metrics(asset_id, listing_id, date, metrics_data)`
   - `get_asset_metrics(asset_id, start_date, end_date)`
   - `get_top_performing_assets(listing_id, metric='ctr', limit=10)`
3. 实现幂等性保证
4. 添加日志和错误处理

**涉及文件**：
- 新增：`backend/app/services/asset_performance_service.py`

**验收标准**：
- [ ] 服务类可实例化
- [ ] `ingest_asset_metrics` 可正确写入数据
- [ ] `get_top_performing_assets` 可正确排序

**预估工作量**：4-6 小时

---

### B3. 实现 PlatformSyncService 框架

**任务描述**：
创建 `PlatformSyncService`，负责协调平台数据同步任务。

**具体工作**：
1. 创建服务类框架
2. 实现方法：
   - `sync_listing_status(listing_id)`
   - `sync_listing_inventory(listing_id)`
   - `sync_listing_price(listing_id)`
   - `sync_listing_metrics(listing_id, date)`
3. 实现重试机制（exponential backoff）
4. 实现同步日志记录

**涉及文件**：
- 新增：`backend/app/services/platform_sync_service.py`

**验收标准**：
- [ ] 服务类可实例化
- [ ] 每个 sync 方法有清晰的成功/失败返回
- [ ] 失败时会自动重试
- [ ] 同步日志可追溯

**预估工作量**：6-8 小时

---

## 分组 C：A/B 测试基础设施

### C1. 扩展 ContentAssetManagerAgent 支持多变体生成

**任务描述**：
修改 `ContentAssetManagerAgent`，使其能一次生成多个风格变体。

**具体工作**：
1. 修改 `execute()` 方法，支持 `variant_count` 参数
2. 为每组变体生成唯一 `variant_group` ID
3. 循环生成多个风格变体
4. 更新输出数据结构

**涉及文件**：
- 修改：`backend/app/agents/content_asset_manager.py:61`

**验收标准**：
- [ ] 可指定生成 3-5 个变体
- [ ] 每个变体有相同的 `variant_group`
- [ ] 每个变体有不同的 `style_tags`
- [ ] 输出数据包含所有变体 ID

**预估工作量**：4-6 小时

---

### C2. 实现 ABTestManager Agent 框架

**任务描述**：
创建 `ABTestManager` Agent，负责 A/B 测试的编排和赢家识别。

**具体工作**：
1. 创建 Agent 类框架
2. 实现方法：
   - `create_ab_test(variant_group, listing_ids, duration_days=7)`
   - `check_test_status(variant_group)`
   - `identify_winner(variant_group, metric='ctr')`
   - `promote_winner(variant_group)`
3. 实现测试状态管理
4. 实现赢家识别逻辑（统计显著性检验可选）

**涉及文件**：
- 新增：`backend/app/agents/ab_test_manager.py`

**验收标准**：
- [ ] Agent 可创建 A/B 测试
- [ ] 可查询测试状态
- [ ] 可识别表现最好的变体
- [ ] 可标记赢家并更新 listing

**预估工作量**：8-10 小时

---

### C3. 实现 Winner Promotion 工作流

**任务描述**：
当 A/B 测试识别出赢家后，自动更新所有相关 listing 使用赢家素材。

**具体工作**：
1. 在 `ABTestManager` 中实现 `promote_winner()` 方法
2. 更新 `ListingAssetAssociation` 表
3. 标记输家变体为 `archived`
4. 记录 promotion 日志

**涉及文件**：
- 修改：`backend/app/agents/ab_test_manager.py`
- 可能修改：`backend/app/db/models.py` (ContentAsset 增加 `archived` 字段)

**验收标准**：
- [ ] 赢家素材自动应用到所有 listing
- [ ] 输家素材标记为 archived
- [ ] 操作可追溯

**预估工作量**：4-6 小时

---

## 分组 D：真实平台 API 集成

### D1. Temu 平台适配器从 Mock 向真实 API 演进

**任务描述**：
把 `TemuAdapter` 从 mock 实现升级为真实 API 调用。

**具体工作**：
1. 研究 Temu Seller API 文档
2. 实现 OAuth 认证流程
3. 实现真实 API 调用：
   - `create_listing()`
   - `update_listing()`
   - `sync_inventory()`
   - `sync_price()`
   - `get_listing_metrics()`
4. 实现 rate limit 处理
5. 实现错误重试机制

**涉及文件**：
- 修改：`backend/app/services/platforms/temu.py:97`

**验收标准**：
- [ ] 可成功创建真实 listing
- [ ] 可成功同步库存和价格
- [ ] 可拉取真实表现数据
- [ ] rate limit 不会导致服务崩溃

**预估工作量**：16-20 小时

**依赖**：
- Temu Seller 账号
- API credentials

---

### D2. Amazon SP-API 适配器实现

**任务描述**：
创建 `AmazonAdapter`，实现 Amazon SP-API 集成。

**具体工作**：
1. 研究 Amazon SP-API 文档
2. 实现 LWA (Login with Amazon) 认证
3. 实现 `PlatformAdapter` 接口：
   - `create_listing()`
   - `update_listing()`
   - `sync_inventory()`
   - `sync_price()`
   - `get_listing_metrics()`
4. 支持多 marketplace (US/UK/DE/FR/ES/IT)
5. 实现 throttling 处理

**涉及文件**：
- 新增：`backend/app/services/platforms/amazon.py`

**验收标准**：
- [ ] 可成功创建 Amazon listing
- [ ] 可成功同步 FBA 库存
- [ ] 可拉取 Business Reports 数据
- [ ] 支持至少 2 个 marketplace

**预估工作量**：20-24 小时

**依赖**：
- Amazon Seller 账号
- SP-API credentials

---

### D3. 平台同步 Celery 定时任务

**任务描述**：
创建 Celery 定时任务，定期同步平台数据。

**具体工作**：
1. 创建 Celery task：
   - `sync_all_listings_status()`
   - `sync_all_listings_inventory()`
   - `sync_all_listings_metrics()`
2. 配置定时调度（Celery Beat）
3. 实现任务失败告警
4. 实现任务执行日志

**涉及文件**：
- 新增：`backend/app/tasks/platform_sync_tasks.py`
- 修改：`backend/app/celery_app.py` (配置 beat schedule)

**验收标准**：
- [ ] 定时任务可正常执行
- [ ] 失败时有告警
- [ ] 执行日志可查询

**预估工作量**：6-8 小时

---

## 分组 E：测试与验证

### E1. ListingPerformanceDaily 模型测试

**任务描述**：
为 `ListingPerformanceDaily` 模型编写单元测试。

**具体工作**：
1. 测试模型创建
2. 测试字段约束
3. 测试关系查询
4. 测试 unique 约束

**涉及文件**：
- 新增：`backend/tests/test_listing_performance_model.py`

**验收标准**：
- [ ] 所有测试通过
- [ ] 覆盖率 > 80%

**预估工作量**：2-3 小时

---

### E2. ListingMetricsService 测试

**任务描述**：
为 `ListingMetricsService` 编写单元测试和集成测试。

**具体工作**：
1. 测试 `ingest_daily_metrics` 幂等性
2. 测试 `get_listing_metrics` 查询正确性
3. 测试 CTR 计算逻辑
4. 测试边界情况（空数据、负数等）

**涉及文件**：
- 新增：`backend/tests/test_listing_metrics_service.py`

**验收标准**：
- [ ] 所有测试通过
- [ ] 覆盖率 > 80%

**预估工作量**：4-6 小时

---

### E3. ABTestManager Agent 测试

**任务描述**：
为 `ABTestManager` Agent 编写测试。

**具体工作**：
1. 测试 A/B 测试创建
2. 测试赢家识别逻辑
3. 测试 winner promotion 流程
4. 测试边界情况（所有变体表现相同等）

**涉及文件**：
- 新增：`backend/tests/test_ab_test_manager.py`

**验收标准**：
- [ ] 所有测试通过
- [ ] 覆盖率 > 80%

**预估工作量**：6-8 小时

---

### E4. Temu 平台集成测试

**任务描述**：
为 Temu 真实 API 集成编写集成测试。

**具体工作**：
1. 创建 integration test suite
2. 测试 listing 创建
3. 测试库存同步
4. 测试价格同步
5. 测试表现数据拉取
6. 标记为 `@pytest.mark.integration`

**涉及文件**：
- 新增：`backend/tests/integration/test_temu_real_api.py`

**验收标准**：
- [ ] 集成测试可在有 credentials 的环境执行
- [ ] 测试不阻塞核心回归

**预估工作量**：8-10 小时

---

### E5. Stage 1 端到端验证测试

**任务描述**：
编写端到端测试，验证完整的"选品 -> 上架 -> 表现回流 -> A/B 测试"流程。

**具体工作**：
1. 创建端到端测试场景
2. 模拟完整流程：
   - 创建候选商品
   - 生成多变体素材
   - 上架到平台
   - 模拟表现数据回流
   - 识别赢家
   - 更新 listing
3. 验证数据一致性

**涉及文件**：
- 新增：`backend/tests/test_stage1_e2e.py`

**验收标准**：
- [ ] 端到端测试通过
- [ ] 数据流完整可追溯

**预估工作量**：8-10 小时

---

## 📊 任务优先级与依赖关系

### 第一批（并行）
- A1 + A2 + A3（数据模型）
- B1 + B2（表现数据服务）

### 第二批（依赖第一批）
- B3（平台同步服务）
- C1（多变体生成）
- E1 + E2（模型和服务测试）

### 第三批（依赖第二批）
- C2 + C3（A/B 测试管理）
- D1（Temu 真实 API）
- E3（A/B 测试测试）

### 第四批（依赖第三批）
- D2（Amazon API）
- D3（定时任务）
- E4 + E5（集成测试和端到端测试）

---

## 📈 工作量估算

| 分组 | 任务数 | 预估总工时 | 建议人员 |
|------|--------|-----------|---------|
| A | 3 | 5-8h | 后端 + 数据 |
| B | 3 | 14-20h | 后端 |
| C | 3 | 16-22h | 后端 + Agent |
| D | 3 | 42-52h | 后端 + 平台集成 |
| E | 5 | 28-37h | 测试 + 后端 |
| **总计** | **17** | **105-139h** | **2-3 人** |

按 2 人全职投入，预计 **3-4 周**完成 Stage 1。

---

## ✅ Stage 1 退出标准

### 功能完整性
- [ ] 每个 listing 都能回收到表现数据
- [ ] 每个 asset 都能部分归因到表现
- [ ] 可生成 3-5 个素材变体
- [ ] A/B 测试可自动识别赢家
- [ ] Temu 平台可真实同步

### 数据完整性
- [ ] `ListingPerformanceDaily` 表有真实数据
- [ ] `AssetPerformanceDaily` 表有真实数据
- [ ] `ContentAsset.variant_group` 正确标识变体组

### 测试覆盖
- [ ] 核心回归测试全部通过
- [ ] 新增单元测试覆盖率 > 80%
- [ ] 集成测试可在有 credentials 环境执行
- [ ] 端到端测试验证完整流程

### 可观测性
- [ ] 平台同步任务有日志
- [ ] A/B 测试状态可查询
- [ ] 表现数据可通过 API 查询

---

## 🚀 下一步

完成 Stage 1 后，立即进入 **Stage 2：经营反馈引擎**，把表现数据真正反哺到选品和排序逻辑中。

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
