# 动态关键词生成服务使用指南

## 概述

动态关键词生成服务（Phase 3 Enhancement）使用 Google Trends (pytrends) 自动发现趋势关键词，并扩展为长尾关键词，用于自动化产品选品。

## 核心功能

1. **趋势关键词生成** - 基于 Google Trends 发现热门关键词
2. **关键词扩展** - 使用相关查���扩展长尾关键词
3. **Redis 缓存** - 24小时缓存，减少 API 调用
4. **定时任务** - 每晚 23:00 UTC 自动执行
5. **品类过滤** - 按品类筛选相关关键词
6. **竞争密度评估** - 启发式评估关键词竞争程度

## 文件结构

```
backend/
├── app/
│   ├── services/
│   │   └── keyword_generator.py          # 关键词生成服务
│   ├── workers/
│   │   ├── celery_app.py                 # Celery 配置（含定时任务）
│   │   └── tasks_keyword_research.py     # 关键词生成任务
│   └── core/
│       └── config.py                     # 配置项
└── tests/
    ├── test_keyword_generator.py         # 服务测试
    └── test_keyword_research_tasks.py    # 任务测试
```

## 配置项

在 `.env` 文件中配置：

```bash
# 关键词生成配置
ENABLE_KEYWORD_GENERATION=true
KEYWORD_GENERATION_CATEGORIES=["electronics", "fashion", "home", "beauty", "sports"]
KEYWORD_GENERATION_REGION=US
KEYWORD_GENERATION_LIMIT_PER_CATEGORY=50
KEYWORD_GENERATION_MIN_TREND_SCORE=20
KEYWORD_GENERATION_CACHE_TTL_SECONDS=86400
KEYWORD_GENERATION_AUTO_TRIGGER_SELECTION=false
```

## 使用方式

### 1. 手动调用服务

```python
from app.services.keyword_generator import KeywordGenerator

# 初始化生成器
generator = KeywordGenerator(
    redis_client=redis_client,  # 可选，用于缓存
    cache_ttl_seconds=86400,    # 24小时
    enable_cache=True,
    min_trend_score=20,         # 最低趋势分数
)

# 生成趋势关键词
keywords = await generator.generate_trending_keywords(
    category="electronics",
    region="US",
    limit=50,
)

# 扩展关键词
related = await generator.expand_keyword(
    keyword="wireless earbuds",
    region="US",
    limit=20,
)
```

### 2. 手动触发 Celery 任务

```python
from app.workers.tasks_keyword_research import generate_trending_keywords

# 触发关键词生成任务
result = generate_trending_keywords.delay(
    categories=["electronics", "fashion"],
    region="US",
    limit=50,
)

# 获取结果
task_result = result.get(timeout=300)
print(task_result)
```

### 3. 自动定时执行

Celery Beat 已配置每晚 23:00 UTC 自动执行：

```python
# celery_app.py 中的配置
beat_schedule={
    "generate-trending-keywords": {
        "task": "tasks.generate_trending_keywords",
        "schedule": crontab(minute=0, hour=23),  # 每晚 23:00 UTC
    },
}
```

启动 Celery Worker 和 Beat：

```bash
# 启动 Worker
celery -A app.workers.celery_app worker --loglevel=info

# 启动 Beat（定时任务调度器）
celery -A app.workers.celery_app beat --loglevel=info
```

## 返回数据结构

### KeywordResult

```python
@dataclass
class KeywordResult:
    keyword: str                    # 关键词
    search_volume: int              # 估算搜索量（月）
    trend_score: int                # 趋势分数（0-100）
    competition_density: str        # 竞争密度（"low", "medium", "high"）
    related_keywords: list[str]     # 相关关键词
    category: str                   # 品类
    region: str                     # 地区
```

### 任务返回结果

```python
{
    "success": True,
    "results": [
        {
            "success": True,
            "category": "electronics",
            "region": "US",
            "base_keywords": [
                {
                    "keyword": "wireless earbuds",
                    "search_volume": 5000,
                    "trend_score": 75,
                    "competition_density": "medium",
                    "related_keywords": ["bluetooth earbuds", "true wireless earbuds"],
                    "category": "electronics",
                    "region": "US"
                }
            ],
            "expanded_keywords": ["bluetooth earbuds", "true wireless earbuds", ...],
            "total_count": 150
        }
    ],
    "total_categories": 5,
    "successful_categories": 5,
    "failed_categories": 0
}
```

## 工作流程

```
1. 每晚 23:00 UTC
   ↓
2. Celery Beat 触发 generate_trending_keywords 任务
   ↓
3. 对每个品类（electronics, fashion, home, beauty, sports）：
   a. 检查 Redis 缓存
   b. 如果缓存未命中，调用 pytrends API
   c. 获取趋势搜索（trending_searches）
   d. 过滤品类相关关键词
   e. 获取每个关键词的兴趣度（interest_over_time）
   f. 获取相关查询（related_queries）
   g. 评估竞争密度（启发式）
   h. 保存到 Redis 缓存（24h TTL）
   ↓
4. 扩展 top 10 关键词
   ↓
5. 返回结果（base_keywords + expanded_keywords）
   ↓
6. （可选）自动触发产品选品任务
```

## 竞争密度评估规则

启发式规则（无需外部 API）：

- **HIGH（高竞争）**
  - 1-2 个词的通用关键词（如 "phone", "laptop"）
  - 包含品牌名（如 "iphone case", "nike shoes"）

- **MEDIUM（中等竞争）**
  - 3-4 个词的具体关键词（如 "wireless phone charger"）

- **LOW（低竞争）**
  - 5+ 个词的长尾关键词（如 "waterproof wireless phone charger for car"）

## 缓存策略

- **缓存键格式**: `keyword_generation:{category_hash}:{region}`
- **TTL**: 24 小时（86400 秒）
- **缓存内容**: 完整的 KeywordResult 列表（JSON 序列化）
- **缓存失效**: 自动过期或手动清除

清除缓存：

```python
import redis.asyncio as redis

redis_client = redis.from_url("redis://localhost:6379/0", decode_responses=True)
await redis_client.delete("keyword_generation:*")
```

## 故障处理

### pytrends 失败

如果 pytrends API 调用失败（网络问题、速率限制等），服务会自动回退到预定义的热门关键词：

```python
fallback_data = {
    "electronics": [
        ("wireless earbuds", 5000, 75, "medium"),
        ("phone case", 8000, 80, "high"),
        ...
    ],
    "fashion": [...],
    "home": [...],
}
```

### Redis 失败

如果 Redis 不可用，服务会跳过缓存，直接调用 pytrends API。

### 速率限制

Google Trends 有速率限制。建议：
- 使用 Redis 缓存（24h TTL）
- 避免频繁手动调用
- 依赖定时任务（每晚一次）

## 监控和日志

关键日志事件：

```python
# 关键词生成开始
logger.info("keyword_generation_started", category=category, region=region, limit=limit)

# 缓存命中
logger.info("keyword_generation_cache_hit", category=category, region=region, count=len(cached_results))

# 关键词生成完成
logger.info("keyword_generation_completed", category=category, region=region, count=len(keywords))

# pytrends 失败
logger.error("pytrends_fetch_failed", category=category, region=region, error=str(e))

# 使用回退关键词
logger.warning("using_fallback_keywords", category=category, region=region)
```

## 测试

运行单元测试：

```bash
# 运行所有测试
pytest tests/test_keyword_generator.py tests/test_keyword_research_tasks.py

# 运行集成测试（需要网络连接）
pytest -m integration tests/test_keyword_generator.py
```

## 下一步集成

### 自动触发产品选品

启用配置项：

```bash
KEYWORD_GENERATION_AUTO_TRIGGER_SELECTION=true
```

修改 `tasks_keyword_research.py`：

```python
# 在 generate_trending_keywords 任务中
if settings.keyword_generation_auto_trigger_selection:
    for result in results:
        if result["success"]:
            # 取 top 20 关键词
            top_keywords = [kw["keyword"] for kw in result["base_keywords"][:20]]

            # 触发产品选品任务
            trigger_keyword_based_selection.delay(
                category=result["category"],
                keywords=top_keywords,
                region=result["region"],
                max_candidates=10,
            )
```

## 常见问题

### Q1: 为什么关键词生成很慢？

A: pytrends API 调用较慢（每个关键词 2-5 秒）。建议：
- 使用 Redis 缓存
- 减少 `limit` 参数
- 依赖定时任务，避免实时调用

### Q2: 如何添加新品类？

A: 修改配置文件：

```bash
KEYWORD_GENERATION_CATEGORIES=["electronics", "fashion", "home", "beauty", "sports", "toys"]
```

并在 `keyword_generator.py` 中添加品类关键词映射：

```python
category_keywords = {
    "toys": ["toy", "game", "puzzle", "doll", "action figure", ...],
}
```

### Q3: 如何支持更多地区？

A: 修改 `_region_to_geo` 和 `_region_to_geo_code` 方法：

```python
region_map = {
    "US": "united_states",
    "UK": "united_kingdom",
    "ES": "spain",  # 新增
    "IT": "italy",  # 新增
    ...
}
```

### Q4: 如何集成 Helium 10 API？

A: 当前实现仅使用 pytrends（免费）。如需 Helium 10：

1. 添加配置：
```bash
DEMAND_VALIDATION_USE_HELIUM10=true
DEMAND_VALIDATION_HELIUM10_API_KEY=your_api_key
```

2. 修改 `keyword_generator.py`，添加 Helium 10 API 调用逻辑。

## 性能指标

- **单品类生成时间**: 30-60 秒（50 个关键词）
- **全品类生成时间**: 3-5 分钟（5 个品类）
- **缓存命中率**: 95%+（24h TTL）
- **API 调用次数**: 每晚 5 次（5 个品类）

## 相关文档

- [产品选品优化计划](../architecture/product-selection-optimization-v1.md)
- [需求验证服务](../services/demand-validator.md)
- [Celery 任务配置](../../app/workers/celery_app.py)
