# FeedbackAggregator 服务文档

## 概述

FeedbackAggregator 是 Deyes 系统的闭环反馈服务，负责从数据库读取历史表现数据，计算种子、店铺、供应商的表现先验，为选品流程提供历史反馈信号。

**位置：** `backend/app/services/feedback_aggregator.py:19`

**核心功能：**
- 90 天历史数据回溯
- 种子表现先验（keyword + seed_type）
- 店铺表现先验（1688 店铺名称）
- 供应商表现先验（supplier_name + supplier_url）
- 高表现种子筛选

---

## 架构设计

### 服务定位

FeedbackAggregator 是一个**轻量级只读服务**，不修改数据库，仅读取历史数据并计算先验评分。

```
┌─────────────────────────────────────────────────────────────┐
│                    FeedbackAggregator                        │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Seed Priors  │  │ Shop Priors  │  │Supplier Priors│     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         High Performing Seeds Cache                   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↑
                            │ refresh()
                            │
┌─────────────────────────────────────────────────────────────┐
│                      PostgreSQL                              │
│                                                              │
│  CandidateProduct  PricingAssessment  RiskAssessment        │
│  SupplierMatch     PlatformListing                          │
└─────────────────────────────────────────────────────────────┘
```

### 数据流

```
1. refresh() 触发
   ↓
2. 从 PostgreSQL 读取 90 天历史数据
   ↓
3. 计算种子/店铺/供应商评分
   ↓
4. 更新内存缓存（_seed_priors, _shop_priors, _supplier_priors）
   ↓
5. 筛选高表现种子（评分 >= 2.0）
   ↓
6. 选品流程调用 get_*_prior() 获取先验
```

---

## 初始化

### 构造函数

```python
def __init__(
    self,
    *,
    lookback_days: int = 90,
    prior_cap: float = 5.0,
):
    self.lookback_days = lookback_days  # 回溯天数
    self.prior_cap = prior_cap          # 评分上限
    self.logger = get_logger(__name__)

    # 内存缓存
    self._seed_priors: dict[tuple[str, str], float] = {}
    self._shop_priors: dict[str, float] = {}
    self._supplier_priors: dict[tuple[str, str], float] = {}
    self._high_performing_seeds: list[tuple[str, str, float]] = []
    self._high_performing_seeds_by_category: dict = {}
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| lookback_days | int | 90 | 历史数据回溯天数 |
| prior_cap | float | 5.0 | 评分上限（防止异常值） |

---

## 核心方法

### 1. refresh() - 刷新缓存

```python
async def refresh(self, db: AsyncSession) -> None:
    """从数据库刷新历史反馈缓存"""
```

#### 执行流程

**步骤 1：计算回溯时间**
```python
cutoff = datetime.now(UTC) - timedelta(days=self.lookback_days)
# 例如：90 天前的时间戳
```

**步骤 2：查询候选商品历史数据**
```python
stmt = (
    select(
        CandidateProduct.id,
        CandidateProduct.category,
        CandidateProduct.normalized_attributes,
        PricingAssessment.profitability_decision,
        PricingAssessment.margin_percentage,
        RiskAssessment.decision,
        func.coalesce(sales_subquery.c.total_sales, 0).label("total_sales"),
    )
    .outerjoin(PricingAssessment, ...)
    .outerjoin(RiskAssessment, ...)
    .outerjoin(sales_subquery, ...)
    .where(CandidateProduct.created_at >= cutoff)
)
```

**步骤 3：计算种子/店铺评分**
```python
for row in rows:
    attrs = row.normalized_attributes or {}
    seed_type = attrs.get("seed_type")
    matched_keyword = attrs.get("matched_keyword")
    shop_name = attrs.get("shop_name")

    # 计算评分
    score = 0.0
    if profitability == PROFITABLE:
        score += 2.0
    elif profitability == MARGINAL:
        score += 0.5

    if risk == PASS:
        score += 1.5
    elif risk == REVIEW:
        score += 0.5

    if margin_percentage:
        score += min(float(margin_percentage) / 10.0, 1.0)

    if total_sales > 0:
        score += min(total_sales / 100.0, 1.0)

    # 记录种子评分
    if seed_type and matched_keyword:
        key = (matched_keyword, seed_type)
        seed_stats[key].append(score)

    # 记录店铺评分
    if shop_name:
        shop_stats[shop_name].append(score)
```

**步骤 4：查询供应商历史数据**
```python
supplier_stmt = (
    select(
        SupplierMatch.supplier_name,
        SupplierMatch.supplier_url,
        PricingAssessment.profitability_decision,
        PricingAssessment.margin_percentage,
        RiskAssessment.decision,
    )
    .join(CandidateProduct, ...)
    .outerjoin(PricingAssessment, ...)
    .outerjoin(RiskAssessment, ...)
    .where(
        and_(
            CandidateProduct.created_at >= cutoff,
            SupplierMatch.selected.is_(True),  # 仅统计被选中的供应商
        )
    )
)
```

**步骤 5：计算平均评分并更新缓存**
```python
self._seed_priors = {
    key: min(sum(scores) / len(scores), self.prior_cap)
    for key, scores in seed_stats.items()
    if scores
}

self._shop_priors = {
    key: min(sum(scores) / len(scores), self.prior_cap)
    for key, scores in shop_stats.items()
    if scores
}

self._supplier_priors = {
    key: min(sum(scores) / len(scores), self.prior_cap)
    for key, scores in supplier_stats.items()
    if scores
}
```

**步骤 6：筛选高表现种子**
```python
self._high_performing_seeds = [
    (seed, seed_type, prior)
    for (seed, seed_type), prior in self._seed_priors.items()
    if prior >= 2.0
]
self._high_performing_seeds.sort(key=lambda x: x[2], reverse=True)
```

---

### 2. get_high_performing_seeds() - 获取高表现种子

```python
def get_high_performing_seeds(
    self,
    category: str | None,
    limit: int
) -> list[str]:
    """返回高表现种子，可选按品类过滤"""
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| category | str \| None | 品类过滤（可选） |
| limit | int | 返回数量限制 |

#### 返回值

```python
["phone case", "wireless charger", "bluetooth speaker", ...]
```

#### 使用示例

```python
# 获取所有品类的 top 20 高表现种子
seeds = aggregator.get_high_performing_seeds(category=None, limit=20)

# 获取电子品类的 top 10 高表现种子
seeds = aggregator.get_high_performing_seeds(category="electronics", limit=10)
```

---

### 3. get_seed_performance_prior() - 获取种子表现先验

```python
def get_seed_performance_prior(self, seed: str, seed_type: str) -> float:
    """返回种子的历史表现先验"""
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| seed | str | 关键词（matched_keyword） |
| seed_type | str | 种子类型（default, sales, factory, image-similar） |

#### 返回值

```python
float  # 0.0 - 5.0
```

#### 使用示例

```python
prior = aggregator.get_seed_performance_prior(
    seed="phone case",
    seed_type="default"
)
# 返回: 3.5
```

---

### 4. get_shop_performance_prior() - 获取店铺表现先验

```python
def get_shop_performance_prior(self, shop_name: str) -> float:
    """返回店铺的历史表现先验"""
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| shop_name | str | 1688 店铺名称 |

#### 返回值

```python
float  # 0.0 - 5.0
```

#### 使用示例

```python
prior = aggregator.get_shop_performance_prior(
    shop_name="深圳市XX电子有限公司"
)
# 返回: 4.0
```

---

### 5. get_supplier_performance_prior() - 获取供应商表现先验

```python
def get_supplier_performance_prior(
    self,
    supplier_name: str,
    supplier_url: str
) -> float:
    """返回供应商的历史表现先验"""
```

#### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| supplier_name | str | 供应商名称 |
| supplier_url | str | 供应商 URL |

#### 返回值

```python
float  # 0.0 - 5.0
```

#### 使用示例

```python
prior = aggregator.get_supplier_performance_prior(
    supplier_name="深圳市XX电子有限公司",
    supplier_url="https://1688.com/offer/123456.html"
)
# 返回: 4.5
```

---

## 评分计算逻辑

### 评分因子

```python
score = 0.0

# 1. 盈利性决策加分
if profitability == ProfitabilityDecision.PROFITABLE:
    score += 2.0
elif profitability == ProfitabilityDecision.MARGINAL:
    score += 0.5

# 2. 风险决策加分
if risk == RiskDecision.PASS:
    score += 1.5
elif risk == RiskDecision.REVIEW:
    score += 0.5

# 3. 利润率加分（最多 +1.0）
if margin_percentage:
    score += min(float(margin_percentage) / 10.0, 1.0)

# 4. 销量加分（最多 +1.0）
if total_sales > 0:
    score += min(total_sales / 100.0, 1.0)

# 5. 上限 5.0
final_score = min(score, 5.0)
```

### 评分示例

**示例 1：优秀候选商品**
```python
profitability = PROFITABLE      # +2.0
risk = PASS                     # +1.5
margin_percentage = 0.40        # +0.4 (40% / 10)
total_sales = 150               # +1.0 (min(150/100, 1.0))

score = 2.0 + 1.5 + 0.4 + 1.0 = 4.9
```

**示例 2：一般候选商品**
```python
profitability = MARGINAL        # +0.5
risk = REVIEW                   # +0.5
margin_percentage = 0.20        # +0.2 (20% / 10)
total_sales = 30                # +0.3 (30 / 100)

score = 0.5 + 0.5 + 0.2 + 0.3 = 1.5
```

**示例 3：较差候选商品**
```python
profitability = UNPROFITABLE    # +0.0
risk = REJECT                   # +0.0
margin_percentage = 0.10        # +0.1 (10% / 10)
total_sales = 5                 # +0.05 (5 / 100)

score = 0.0 + 0.0 + 0.1 + 0.05 = 0.15
```

---

## 使用场景

### 场景 1：选品流程中使用种子先验

```python
# 初始化
aggregator = FeedbackAggregator(lookback_days=90)
await aggregator.refresh(db)

# 获取高表现种子
high_performing_seeds = aggregator.get_high_performing_seeds(
    category="electronics",
    limit=20
)

# 在选品时优先使用高表现种子
for seed in high_performing_seeds:
    products = await source_adapter.fetch_products(
        keywords=[seed],
        category="electronics",
        limit=10,
    )
```

### 场景 2：供应商评分中使用供应商先验

```python
# 获取供应商历史表现先验
supplier_prior = aggregator.get_supplier_performance_prior(
    supplier_name="深圳市XX电子有限公司",
    supplier_url="https://1688.com/offer/123456.html"
)

# 调整供应商评分
if supplier_prior >= 3.0:
    # 历史表现优秀，提升评分
    adjusted_score = base_score * 1.1
elif supplier_prior <= 1.0:
    # 历史表现较差，降低评分
    adjusted_score = base_score * 0.9
else:
    adjusted_score = base_score
```

### 场景 3：定期刷新缓存

```python
# Celery 定时任务
@celery_app.task
async def refresh_feedback_aggregator():
    aggregator = FeedbackAggregator(lookback_days=90)
    async with get_db_session() as db:
        await aggregator.refresh(db)
    logger.info("feedback_aggregator_refreshed")

# 每日凌晨 2:00 刷新
celery_app.conf.beat_schedule = {
    "refresh-feedback-aggregator": {
        "task": "refresh_feedback_aggregator",
        "schedule": crontab(hour=2, minute=0),
    },
}
```

---

## 性能优化

### 1. 内存缓存

FeedbackAggregator 将所有先验评分存储在内存中，避免频繁查询数据库。

```python
# 内存占用估算
# 假设 10,000 个种子，1,000 个店铺，5,000 个供应商
# 每个键值对约 100 字节
# 总内存: (10000 + 1000 + 5000) × 100 = 1.6 MB
```

### 2. 定期刷新

建议每日刷新一次（凌晨 2:00），避免实时查询数据库。

### 3. 查询优化

使用 SQLAlchemy 的 `outerjoin` 和 `func.coalesce` 优化查询性能。

---

## 监控指标

### 日志输出

```python
self.logger.info(
    "feedback_aggregator_refreshed",
    seed_priors=len(self._seed_priors),
    shop_priors=len(self._shop_priors),
    supplier_priors=len(self._supplier_priors),
    high_performing_seeds=len(self._high_performing_seeds),
)
```

### 示例日志

```json
{
  "event": "feedback_aggregator_refreshed",
  "seed_priors": 8523,
  "shop_priors": 1247,
  "supplier_priors": 4891,
  "high_performing_seeds": 342
}
```

---

## 未来优化方向

详见 `docs/architecture/product-selection-optimization-v1.md:1`

**潜在改进：**
1. 引入时间衰减因子（近期数据权重更高）
2. 添加品类特定先验（不同品类分别计算）
3. 引入 A/B 测试结果（实验组 vs 对照组）
4. 添加季节性调整（节假日表现加权）

---

**文档版本：** v1.0
**最后更新：** 2026-03-26
**状态：** 生产就绪
