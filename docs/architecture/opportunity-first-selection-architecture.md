# Seller-First 选品架构（从 Opportunity-First 演进）

## 背景

当前 AlphaShop 集成已经替换 Google Trends / TMAPI 的主要调用链，但选品系统主链仍保留 **keyword-first** 假设：

- `category` 会被直接送入 `AlphaShopClient.search_keywords(keyword=category)`。
- `newproduct.report` 需要使用 `keyword.search` 返回的合法 `productKeyword`，不能直接接收泛类目词，否则会触发 `KEYWORD_ILLEGAL`。
- `intelligent_supplier_selection` 更适合做供应链验证与富化，而不是一级冷启动新品发现入口。

这说明问题已经不再是 provider 接入，而是业务主语设计错误：

- `category` 是业务标签，不是最终检索词。
- `keyword` 是市场证据载体，不是最终业务对象。
- 真正应该作为主语的是 **SearchIntelligence（市场情报）** 驱动下的 **DemandPocket（需求口袋）** / **ProductHypothesis（产品假设）**，而 **Opportunity** 只是可选增强层。

## AlphaShop API 职责重定位

### `keyword.search`

**原定位**：seed 合法化 / 扩展 / 初筛层。

**新定位**：**关键词情报 / 需求情报资产层**（Keyword Intelligence / Demand Intelligence Layer）。

#### 为什么提升定位

在实际验证中发现：

1. `newproduct.report` 在生产环境中不稳定（`FAIL_SERVER_INTERNAL_ERROR`），不应作为唯一机会发现入口。
2. `keyword.search` 返回的数据已经非常丰富，包含：
   - 搜索量、销量、销售额
   - 机会分、竞争度、增长率
   - 搜索排名、排名趋势
   - 雷达图多维评分（需求分、供给分、销售分、新品分、评价分）
   - 中文关键词（`keywordCn`）可直接用于 1688 供应链召回
3. 从卖家决策视角看，`keyword.search` 已经足够支撑：
   - 需求验证（搜索量、销量、增长率）
   - 变现潜力（销售额、机会分）
   - 可采购性（中文关键词 -> 1688）
   - 风险评估（竞争度、新品分）
   - 趋势判断（排名趋势、增长率）

因此，`keyword.search` 不应仅作为 `newproduct.report` 的前置合法化步骤，而应作为**可独立支撑选品决策的市场情报资产**。

#### 职责

**核心职责**：
- 将用户词、类目种子词、历史优胜词、季节性词映射为 AlphaShop 可识别的合法关键词。
- 输出丰富的市场信号，作为可复用的情报资产。
- 为 `newproduct.report` 提供合法 `productKeyword`（如果 report 可用）。
- 为 1688 供应链召回提供中文关键词（`keywordCn`）。
- 为需求验证、机会评分、趋势判断提供数据基础。

**不应承担的职责**：
- 直接把泛类目当作最终商品机会。
- 替代供应商匹配、定价计算、风控评估等下游服务。

## 关键词情报数据资产设计

### 背景与动机

在生产环境验证中发现：

1. **`keyword.search` 返回数据远比预期丰富**，当前系统只用了其中 10-20% 的信号。
2. **数据被重复抛弃**：`KeywordGenerator`、`DemandValidator`、`KeywordLegitimizer` 都调用 `keyword.search`，但各自只提取少量字段后就丢弃原始响应。
3. **缺少历史追溯**：无法回答"上周这个关键词的机会分是多少？"、"哪些关键词的排名在上升？"
4. **1688 召回能力未充分利用**：`keywordCn` 可直接用于中文供应链召回，但当前只在 legitimizer 的 `raw` 字段里保留，未被下游主动使用。

从卖家决策视角看，`keyword.search` 已经包含完整的"需求-变现-采购-风险-趋势"五维决策信号，应作为**可复用的市场情报资产**管理，而不是一次性消耗品。

### `keyword.search` 返回字段深度分析

基于 AlphaShop 实际响应和卖家决策需求，以下字段具有持久化价值：

#### 核心标识字段

| 字段 | 类型 | 业务价值 | 当前使用情况 | 建议 |
|------|------|----------|-------------|------|
| `keyword` | string | AlphaShop 严格关键词，`newproduct.report` 必需 | ✅ 已用于 `report_keyword` | 持久化 |
| `keywordCn` | string | 中文关键词，可直接用于 1688 供应链召回 | ⚠️ 仅保留在 `raw`，未主动使用 | **持久化并索引** |
| `requestId` | string | AlphaShop 请求追踪 ID | ❌ 未保留 | 持久化用于问题排查 |

#### 需求验证字段

| 字段 | 类型 | 业务价值 | 当前使用情况 | 建议 |
|------|------|----------|-------------|------|
| `searchVolume` | int | 搜索量，需求强度直接指标 | ✅ 已用于需求验证 | 持久化 + 时序分析 |
| `soldCnt30d` | int | 近 30 天销量，真实成交验证 | ⚠️ 部分提取 | **持久化 + 趋势计算** |
| `soldAmt30d` | float | 近 30 天销售额，变现潜力 | ❌ 未使用 | **持久化用于 ROI 预估** |
| `searchRank` | int | 搜索排名，竞争激烈度 | ❌ 未使用 | 持久化 + 排名变化追踪 |

#### 机会评分字段

| 字段 | 类型 | 业务价值 | 当前使用情况 | 建议 |
|------|------|----------|-------------|------|
| `oppScore` | float | AlphaShop 综合机会分 (0-100) | ✅ 已用于过滤和排序 | 持久化 + 历史对比 |
| `oppScoreDesc` | string | 机会分文字描述（高/中/低） | ❌ 未使用 | 持久化用于可解释性 |
| `growthRate` | float | 增长率，趋势方向 | ⚠️ 部分提取 | **持久化 + 趋势预测** |
| `rankTrends` | array | 排名趋势数组 | ❌ 未使用 | **持久化用于趋势可视化** |

#### 雷达图多维评分

| 字段路径 | 类型 | 业务价值 | 当前使用情况 | 建议 |
|---------|------|----------|-------------|------|
| `radar.propertyList[].name` | string | 维度名称（需求分/供给分/销售分/新品分/评价分） | ❌ 未使用 | **持久化** |
| `radar.propertyList[].value` | float | 维���分值 (0-100) | ❌ 未使用 | **持久化 + 多维分析** |

**五维雷达图业务含义**：
- **需求分**：市场需求强度，对应搜索量、关注度
- **供给分**：供应链丰富度，对应竞品数量
- **销售分**：真实成交验证，对应销量、销售额
- **新品分**：新品机会窗口，对应上新速度、市场饱和度
- **评价分**：用户满意度，对应评分、复购率

这五个维度直接对应卖家决策的"需求-变现-采购-风险-趋势"���架。

#### 竞争度字段

| 字段 | 类型 | 业务价值 | 当前使用情况 | 建议 |
|------|------|----------|-------------|------|
| `competitionDensity` | string | 竞争密度（low/medium/high） | ✅ 已用于风控 | 持久化 |
| `searchResultCount` | int | 搜索结果数，竞争激烈度 | ❌ 未使用 | 持久化 |

### 数据资产管理策略

#### 三层数据模型

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: KeywordSearchSession (查询会话)                      │
│ - 记录每次 keyword.search 调用的完整上下文                      │
│ - 用途：问题排查、API 成本追踪、重复调用检测                     │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: KeywordSignalSnapshot (关键词信号快照)                │
│ - 记录每个关键词在特定时间点的完整市场信号                       │
│ - 用途：历史对比、趋势分析、信号复用                             │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: KeywordPocketIntelligence (口袋情报)                 │
│ - 从快照中提取的高频决策信号，预计算并缓存                       │
│ - 用途：快速决策、离线分析、推荐排序                             │
└─────────────────────────────────────────────────────────────┘
```

#### Layer 1: KeywordSearchSession

**用途**：记录每次 API 调用的完整上下文，用于成本追踪和问题排查。

**字段设计**：
```python
{
    "session_id": "uuid",
    "request_time": "2026-04-02T10:30:00Z",
    "seed_term": "wireless charger",
    "seed_source": "user",
    "target_platform": "Amazon",
    "target_region": "US",
    "alphashop_request_id": "req-abc-123",
    "response_keyword_count": 15,
    "api_latency_ms": 450,
    "strategy_run_id": "uuid",  # 关联到具体选品任务
}
```

**持久化策略**：
- Phase 1：写入 `StrategyRun.metadata` 或 `RunEvent.event_payload`
- Phase 2：独立表 `keyword_search_sessions`，保留 30 天

#### Layer 2: KeywordSignalSnapshot

**用途**：记录关键词的完整市场信号快照，支持历史对比和趋势分析。

**字段设计**：
```python
{
    "snapshot_id": "uuid",
    "keyword": "wireless charger",
    "keyword_cn": "无线充电器",
    "snapshot_time": "2026-04-02T10:30:00Z",
    "target_platform": "Amazon",
    "target_region": "US",

    # 需求验证
    "search_volume": 50000,
    "sold_cnt_30d": 12000,
    "sold_amt_30d": 240000.0,
    "search_rank": 15,

    # 机会评分
    "opp_score": 82.5,
    "opp_score_desc": "高",
    "growth_rate": 0.15,
    "rank_trends": [12, 14, 15, 13, 15],  # 最近 5 期排名

    # 雷达图
    "radar_demand_score": 85,
    "radar_supply_score": 60,
    "radar_sales_score": 78,
    "radar_newproduct_score": 72,
    "radar_review_score": 80,

    # 竞争度
    "competition_density": "medium",
    "search_result_count": 3500,

    # 原始响应（用于未来扩展）
    "raw_response": {...},

    # 关联
    "session_id": "uuid",
    "alphashop_request_id": "req-abc-123",
}
```

**持久化策略**：
- Phase 1：写入 `CandidateProduct.demand_discovery_metadata`，每个 candidate 保留其关联的 keyword snapshot
- Phase 2：独立表 `keyword_signal_snapshots`，按 `(keyword, target_platform, target_region, snapshot_time)` 索引

**复用策略**：
- 同一 keyword 在 24 小时内的快照可直接复用，避免重复调用 AlphaShop API
- Redis 热缓存：`keyword_snapshot:{platform}:{region}:{keyword}` TTL=24h

#### Layer 3: KeywordPocketIntelligence

**用途**：预计算的高频决策信号，用于快速决策和离线分析。

**字段设计**：
```python
{
    "keyword": "wireless charger",
    "keyword_cn": "无线充电器",
    "target_platform": "Amazon",
    "target_region": "US",

    # 预计算决策信号
    "demand_strength": "strong",  # strong/medium/weak
    "monetization_potential": "high",  # high/medium/low
    "supply_feasibility": "easy",  # easy/moderate/hard
    "competition_risk": "medium",  # low/medium/high
    "trend_direction": "rising",  # rising/stable/declining

    # 聚合统计（最近 7 天）
    "avg_opp_score_7d": 81.2,
    "opp_score_trend_7d": "+3.5",
    "rank_change_7d": -2,  # 排名上升 2 位

    # 1688 召回提示
    "cn_keyword_available": true,
    "suggested_1688_query": "无线充电器 工厂",

    # 更新时间
    "last_updated": "2026-04-02T10:30:00Z",
    "snapshot_count": 5,  # 基于多少个快照计算
}
```

**持久化策略**���
- Phase 1：不持久化，仅 Redis 缓存
- Phase 2：独立表 `keyword_pocket_intelligence`，每日更新

**生成策略**：
- 由 nightly 任务从 `keyword_signal_snapshots` 聚合生成
- 在线路径优先读取 pocket intelligence，未命中时才调用 `keyword.search`

### Phase 1 实现路径（无 DB Migration）

#### 目标

在不引���新表的前提下，把关键词情报写入现有 metadata 字段，立即提升数据复用能力。

#### 复用现有字段

1. **`StrategyRun.metadata`**：
   - 写入 `keyword_search_sessions` 数组
   - 记录本次选品任务的所有 keyword.search 调用

2. **`RunEvent.event_payload`**：
   - 事件类型：`keyword_search_completed`
   - 写入单次 keyword.search 的完整响应

3. **`CandidateProduct.demand_discovery_metadata`**：
   - 新增 `keyword_signal_snapshot` 字段
   - 保留该 candidate 关联的关键词完整信号

4. **Redis 热缓存**：
   - Key: `keyword_snapshot:{platform}:{region}:{keyword}`
   - Value: 完整 snapshot JSON
   - TTL: 24h

#### 代码改造点

**1. `KeywordLegitimizerService.legitimize_seeds()`**

当前只保留 `raw`，改为保留完整 snapshot：

```python
valid_keywords.append(
    ValidKeyword(
        seed=seed,
        matched_keyword=matched_keyword,
        match_type=match_type,
        opp_score=opp_score,
        search_volume=search_volume,
        competition_density=competition_density,
        is_valid_for_report=is_valid,
        raw=best_match,  # 保留原始 AlphaShop 响应
        report_keyword=report_keyword,
        # 新增：提取关键情报字段
        keyword_cn=best_match.get("keywordCn"),
        sold_cnt_30d=best_match.get("soldCnt30d"),
        sold_amt_30d=best_match.get("soldAmt30d"),
        search_rank=best_match.get("searchRank"),
        growth_rate=best_match.get("growthRate"),
        rank_trends=best_match.get("rankTrends"),
        radar_scores=self._extract_radar_scores(best_match),
    )
)
```

**2. `DemandDiscoveryService.discover_keywords()`**

在返回 `DemandDiscoveryResult` 时，补充 `keyword_signal_snapshots`：

```python
return DemandDiscoveryResult(
    validated_keywords=validated,
    rejected_keywords=rejected,
    discovery_mode="seed_pool",
    fallback_used=False,
    degraded=False,
    seeds=seeds_payload,
    valid_keywords=valid_keywords_payload,
    seed_to_keyword_mapping=mapping_payload,
    # 新增：关键词信号快照
    keyword_signal_snapshots=[
        self._build_snapshot(vk) for vk in valid_keywords
    ],
)
```

**3. `ProductSelectorAgent.execute()`**

写入 `CandidateProduct.demand_discovery_metadata`：

```python
demand_metadata = {
    **demand_discovery_payload,
    "keyword_signal_snapshots": demand_discovery_payload.get("keyword_signal_snapshots", []),
}
```

**4. Redis 缓存层**

在 `KeywordLegitimizerService` 中新增缓存逻辑：

```python
async def legitimize_seeds(self, seeds, region, platform):
    results = []
    for seed in seeds:
        # 先查缓存
        cache_key = f"keyword_snapshot:{platform}:{region}:{seed.term}"
        cached = await self.redis.get(cache_key)
        if cached:
            results.append(self._snapshot_to_valid_keyword(cached, seed))
            continue

        # 未命中，调用 AlphaShop
        response = await client.search_keywords(...)
        snapshot = self._build_snapshot(response, seed, region, platform)

        # 写缓存
        await self.redis.setex(cache_key, 86400, json.dumps(snapshot))

        results.append(self._snapshot_to_valid_keyword(snapshot, seed))
    return results
```

#### 预期收益

- ✅ **API 成本降低 60-80%**：24h 内重复查询直接命中缓存
- ✅ **1688 召回能力提升**：`keywordCn` 可直接用于中文供应链查询
- ✅ **需求验证更精准**：`soldCnt30d`、`soldAmt30d` 补充真实成交数据
- ✅ **趋势判断可用**：`rankTrends`、`growthRate` 支持趋势分析
- ✅ **可解释性增强**：雷达图五维评分可用于推荐理由生成

### Phase 2+ 正式持久化

#### 新增表结构

**`keyword_search_sessions`**：
```sql
CREATE TABLE keyword_search_sessions (
    id UUID PRIMARY KEY,
    request_time TIMESTAMP NOT NULL,
    seed_term VARCHAR(255) NOT NULL,
    seed_source VARCHAR(50),
    target_platform VARCHAR(50),
    target_region VARCHAR(10),
    alphashop_request_id VARCHAR(255),
    response_keyword_count INT,
    api_latency_ms INT,
    strategy_run_id UUID REFERENCES strategy_runs(id),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_sessions_strategy ON keyword_search_sessions(strategy_run_id);
CREATE INDEX idx_sessions_time ON keyword_search_sessions(request_time);
```

**`keyword_signal_snapshots`**：
```sql
CREATE TABLE keyword_signal_snapshots (
    id UUID PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    keyword_cn VARCHAR(255),
    snapshot_time TIMESTAMP NOT NULL,
    target_platform VARCHAR(50) NOT NULL,
    target_region VARCHAR(10) NOT NULL,

    search_volume INT,
    sold_cnt_30d INT,
    sold_amt_30d DECIMAL(12,2),
    search_rank INT,

    opp_score DECIMAL(5,2),
    opp_score_desc VARCHAR(20),
    growth_rate DECIMAL(5,4),
    rank_trends JSONB,

    radar_demand_score INT,
    radar_supply_score INT,
    radar_sales_score INT,
    radar_newproduct_score INT,
    radar_review_score INT,

    competition_density VARCHAR(20),
    search_result_count INT,

    raw_response JSONB,
    session_id UUID REFERENCES keyword_search_sessions(id),
    alphashop_request_id VARCHAR(255),

    created_at TIMESTAMP DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_snapshots_unique ON keyword_signal_snapshots(
    keyword, target_platform, target_region, snapshot_time
);
CREATE INDEX idx_snapshots_keyword ON keyword_signal_snapshots(keyword);
CREATE INDEX idx_snapshots_time ON keyword_signal_snapshots(snapshot_time);
```

**`keyword_pocket_intelligence`**：
```sql
CREATE TABLE keyword_pocket_intelligence (
    keyword VARCHAR(255) NOT NULL,
    keyword_cn VARCHAR(255),
    target_platform VARCHAR(50) NOT NULL,
    target_region VARCHAR(10) NOT NULL,

    demand_strength VARCHAR(20),
    monetization_potential VARCHAR(20),
    supply_feasibility VARCHAR(20),
    competition_risk VARCHAR(20),
    trend_direction VARCHAR(20),

    avg_opp_score_7d DECIMAL(5,2),
    opp_score_trend_7d VARCHAR(10),
    rank_change_7d INT,

    cn_keyword_available BOOLEAN,
    suggested_1688_query VARCHAR(255),

    last_updated TIMESTAMP NOT NULL,
    snapshot_count INT,

    PRIMARY KEY (keyword, target_platform, target_region)
);
CREATE INDEX idx_pocket_updated ON keyword_pocket_intelligence(last_updated);
```

#### Nightly 聚合任务

新增 `tasks_keyword_intelligence.py`：

```python
@celery_app.task(name="aggregate_keyword_pocket_intelligence")
def aggregate_keyword_pocket_intelligence():
    """从快照聚合生成口袋情报."""
    # 1. 读取最近 7 天的 snapshots
    # 2. 按 (keyword, platform, region) 分组
    # 3. 计算聚合指标
    # 4. 写入 keyword_pocket_intelligence
    pass
```

### 验证标准

#### Phase 1 验证

1. **缓存命中率**：
   - 同一 keyword 在 24h 内第二次查询应命中 Redis 缓存
   - 目标：缓存命中率 > 60%

2. **Metadata 完整性**：
   - `CandidateProduct.demand_discovery_metadata` 应包含 `keyword_signal_snapshots`
   - 快照应包含 `keywordCn`、`soldCnt30d`、`radar_scores` 等扩展字段

3. **1688 召回能力**：
   - `keywordCn` 非空率 > 80%（针对有中文市场的关键词）
   - 可用于 `AlphaShop1688Adapter` 的中文查询

#### Phase 2 验证

1. **历史追溯**：
   - 可查询"上周这个关键词的机会分是多少？"
   - 可生成关键词排名趋势图

2. **趋势分析**：
   - 可识别"排名上��最快的 10 个关键词"
   - 可识别"机会分持续下降的关键词"

3. **口袋情报准确性**：
   - `demand_strength` 与实际搜索量/销量的相关性 > 0.8
   - `trend_direction` 与 7 天排名变化的一致性 > 85%


### `newproduct.report`

定位为 **新品机会深分析层**。

职责：
- 仅接收来自 `keyword.search` 的合法关键词。
- 输出新品机会清单、市场摘要、机会分及原始 evidence。
- 作为 Opportunity 发现的核心 API。

不应承担的职责：
- 冷启动关键词生成。
- 类目级泛查询。

### `intelligent_supplier_selection`

定位为 **供应链可行性验证 / 富化层**。

职责：
- 针对已选中的 opportunity / candidate 做 1688 召回。
- 提供供应商、MOQ、价格、店铺等信息。

不应承担的职责：
- 一级新品发现入口。

## 卖家视角的业务逻辑重构

### 当前问题：业务主语错误

当前系统的核心问题不是"接哪个 provider"，而是**业务主语和决策链错误**：

1. **`keyword` 不是业务对象，是市场语言**
   - 卖家不"经营关键词"，卖家经营的是"需求口袋"（demand pockets）
   - `keyword.search` 返回的数据是市场情报，不是最终产物
   - `keywordCn` 是供应链召回的桥梁，不是附属字段

2. **`newproduct.report` 不应是硬性闸门**
   - 当前 1688 路径：无 `newproduct.report` = 无法继续
   - 卖家视角：有搜索量 + 有供应商 = 可以尝试
   - `newproduct.report` 应是增强层，不是存在性判断

3. **供应链验证应该是主链的一部分，不是下游富化**
   - 当前：opportunity -> candidate -> supplier
   - 卖家视角：search intelligence -> supply validation -> product hypothesis

### 卖家决策的真实流程

从卖家视角看，选品决策是这样的：

```
1. 市场语言理解（Search Intelligence）
   - 用户在搜什么？（searchVolume, soldCnt30d）
   - 市场在增长吗？（growthRate, rankTrends）
   - 竞争激烈吗？（competitionDensity, oppScore）
   - 中文怎么说？（keywordCn -> 1688 召回）

2. 需求口袋识别（Demand Pocket）
   - 相关关键词聚类
   - 需求强度评估（radar.demandScore）
   - 变现潜力评估（soldAmt30d, radar.salesScore）

3. 产品假设（Product Hypothesis）
   - 基于需求口袋，我应该卖什么？
   - 可以从哪里采购？（keywordCn -> 1688）
   - 定价空间多大？（soldAmt30d / soldCnt30d）

4. 供应链验证（Supply Validation）
   - 1688 有货吗？（intelligent_supplier_selection）
   - MOQ 可接受吗？
   - 价格有利润吗？

5. 机会增强（Opportunity Enhancement，可选）
   - newproduct.report 提供的产品列表
   - 竞品分析
   - 市场摘要
```

### 新业务对象

#### Seed

Seed 是冷启动阶段的候选检索意图。

可能来源：
1. 用户提供关键词
2. 类目静态种子词
3. 历史优胜词（FeedbackAggregator）
4. 季节性/事件词（SeasonalCalendar）

典型字段：
- `term`
- `source`
- `confidence`
- `category`
- `region`
- `platform`

#### SearchIntelligence（扩展后的 ValidKeyword）

SearchIntelligence 是经 `keyword.search` 返回的完整市场情报，不仅仅是"合法关键词"。

**核心字段**：
- `seed`: 原始种子
- `matched_keyword`: 匹配的关键词
- `match_type`: 匹配类型
- `report_keyword`: 严格的 report-safe keyword（用于 `newproduct.report`）
- `is_valid_for_report`: 是否可用于 report

**市场情报字段**（新增）：
- `keyword_cn`: 中文关键词，用于 1688 供应链召回
- `search_volume`: 搜索量
- `sold_cnt_30d`: 近 30 天销量
- `sold_amt_30d`: 近 30 天销售额
- `search_rank`: 搜索排名
- `opp_score`: 机会分
- `growth_rate`: 增长率
- `rank_trends`: 排名趋势数组
- `competition_density`: 竞争密度
- `radar_scores`: 雷达图五维评分
  - `demand_score`: 需求分
  - `supply_score`: 供给分
  - `sales_score`: 销售分
  - `newproduct_score`: 新品分
  - `review_score`: 评价分

**业务语义**：
- 这不是"关键词验证结果"，而是"市场情报快照"
- `keywordCn` 不是附属字段，而是供应链召回的核心桥梁
- `soldCnt30d` / `soldAmt30d` 直接支撑变现潜力评估
- 雷达图五维评分对应卖家决策的"需求-变现-采购-风险-趋势"框架

#### DemandPocket（Phase 2+）

DemandPocket 是相关 SearchIntelligence 的聚类，代表一个需求口袋。

典型字段：
- `primary_keyword`: 主关键词
- `related_keywords`: 相关关键词列表
- `total_search_volume`: 总搜索量
- `avg_opp_score`: 平均机会分
- `demand_strength`: 需求强度（strong/medium/weak）
- `monetization_potential`: 变现潜力（high/medium/low）
- `supply_feasibility`: 供应链可行性（easy/moderate/hard）

#### ProductHypothesis（Phase 2+）

ProductHypothesis 是基于 DemandPocket 和供应链验证的产品假设。

典型字段：
- `demand_pocket`: 关联的需求口袋
- `search_intelligence`: 关联的市场情报
- `supply_candidates`: 1688 供应商候选
- `hypothesis_score`: 假设评分
- `pricing_estimate`: 定价估算
- `risk_flags`: 风险标记

#### Opportunity（降级为可选增强）

Opportunity 是由 `newproduct.report` 产出的市场机会草案，作为 ProductHypothesis 的增强信息。

典型字段：
- `keyword`
- `title`
- `opportunity_score`
- `product_list`
- `keyword_summary`
- `evidence`
- `raw`

**重要变化**：
- Opportunity 不再是 candidate 的必需来源
- 它是可选的增强层，提供竞品分析和市场摘要
- 当 `newproduct.report` 不可用时，系统仍可基于 SearchIntelligence + Supply Validation 继续

## 新主链路（卖家视角）

### Phase 1 主链（当前实现目标）

```text
category / user keywords
  -> seed pool
  -> keyword.search (SearchIntelligence)
  -> supply validation (1688 via keywordCn)
  -> product hypothesis
  -> candidate
  -> pricing / risk / recommendation
```

**关键变化**：
1. `keyword.search` 返回完整市场情报，不仅仅是"合法关键词"
2. `keywordCn` 直接用于 1688 供应链召回
3. 供应链验证不再依赖 `newproduct.report`
4. `newproduct.report` 变成可选增强层

### Phase 1 可选增强路径

```text
SearchIntelligence (report-safe)
  -> newproduct.report
  -> opportunity products
  -> merge into candidates
```

**语义**：
- 当 `is_valid_for_report=True` 且 `report_keyword` 存在时，可调用 `newproduct.report`
- 返回的 `product_list` 作为额外候选，与主链候选合并
- 但主链不依赖 report 成功

### Phase 2+ 完整链路

```text
category / user keywords
  -> seed pool
  -> keyword.search (SearchIntelligence)
  -> demand pocket clustering
  -> product hypothesis generation
  -> supply validation (1688 via keywordCn)
  -> opportunity enhancement (optional newproduct.report)
  -> candidate ranking
  -> pricing / risk / recommendation
```

## 架构原则（卖家视角）

1. **市场情报优先**：`keyword.search` 是市场情报资产，不是简单的合法化步骤。
2. **供应链验证是主链**：有搜索量 + 有供应商 = 可以尝试，不依赖 `newproduct.report`。
3. **`keywordCn` 是一等公民**：中文关键词是 1688 召回的核心桥梁，不是附属字段。
4. **`newproduct.report` 是增强层**：提供竞品分析和市场摘要，但不是硬性闸门。
5. **保留稳定下游**：`CandidateProduct` / `SupplierMatch` / `PricingAssessment` / `RiskAssessment` 暂不推翻。
6. **兼容式演进**：`DemandDiscoveryService` 保留 facade 接口，降低对调用方和测试的破坏。
7. **先在线后离线**：先打通在线主链，再扩展 nightly seed / keyword / opportunity 刷新任务。
8. **先无迁移落地**：Phase 1 先把市场情报写入 `demand_discovery_metadata` 与 `normalized_attributes`。

## Phase 1 目标架构（卖家视角）

### 在线发现链

1. `SeedPoolBuilderService`
   - 将 `category` 转换为 seed pool。
   - 过滤泛类目词，避免直接查 `newproduct.report`。

2. `KeywordLegitimizerService` -> `SearchIntelligenceService`
   - 调用 `AlphaShopClient.search_keywords()`。
   - 输出完整市场情报（SearchIntelligence），不仅仅是”合法关键词”。
   - 提取并保留：`keywordCn`, `soldCnt30d`, `soldAmt30d`, `searchRank`, `growthRate`, `rankTrends`, 雷达图评分。

3. `DemandValidator`
   - 对已合法化 keyword 做需求质量判断。
   - 复用 SearchIntelligence 中的市场信号，避免重复调用。

4. `AlphaShop1688Adapter` -> 供应链验证主路径
   - 使用 `keywordCn` 调用 `intelligent_supplier_selection`。
   - 不再依赖 `newproduct.report` 作为一级发现入口。
   - 返回供应商候选，支撑 ProductHypothesis 生成。

5. `OpportunityDiscoveryService`（可选增强）
   - 对 report-safe keyword 调 `newproduct.report()`。
   - 规范化为 opportunity drafts。
   - 当 report 不可用时，主链仍可继续。

6. `ProductSelectorAgent`
   - 基于 SearchIntelligence + Supply Validation 生成 candidate。
   - 可选：合并 opportunity products 作为额外候选。
   - 下游继续使用现有 supplier / pricing / risk 流程。

### 兼容 Facade

`DemandDiscoveryService` 保留外部接口，但内部改为：

```text
SeedPoolBuilder
  -> KeywordLegitimizer (SearchIntelligence)
  -> DemandValidator
```

返回值继续提供 `validated_keywords`，同时新增：
- `seeds`
- `valid_keywords`（现在包含完整市场情报）
- `seed_to_keyword_mapping`
- `degraded_reason`

## 与现有模块的关系

以下模块继续复用：

- `backend/app/services/feedback_aggregator.py`：历史优胜词 / 反馈先验
- `backend/app/core/seasonal_calendar.py`：季节性种子
- `backend/app/services/supplier_matcher.py`：供应商提取与 fallback
- `backend/app/services/pricing_service.py`：利润评估
- `backend/app/services/risk_rules.py`：风控
- `backend/app/db/models.py` 中的 `CandidateProduct.demand_discovery_metadata`
- `backend/app/workers/` + Redis：nightly 与缓存基础设施

## 持久化策略

### Phase 1

不强依赖数据库迁移，复用：
- `CandidateProduct.demand_discovery_metadata`
- `CandidateProduct.normalized_attributes`

写入内容包括：
- seed pool
- valid keyword list
- chosen `productKeyword`
- `newproduct.report` 摘要
- opportunity score / evidence

### Phase 2+

主链稳定后再引入：
- `OpportunityRecord`
- `OpportunityClusterRecord`

## 风险与控制

### 风险 1：兼容性破坏

控制：
- `DemandDiscoveryService` 保持原有对外接口。
- `KeywordGenerator` 保留兼容方法，改为离线扩展器角色。
- `AlphaShop1688Adapter.fetch_products()` 接口不变。

### 风险 2：下游 candidate / pricing / risk 被入口变更破坏

控制：
- 下游继续消费 candidate 结构。
- opportunity 元数据通过 `demand_discovery_metadata` 和 `normalized_attributes` 透传。

### 风险 3：在线 API 成本升高

控制：
- 优先限制 seed 数量。
- 对合法 keyword 和 opportunity 做缓存。
- 后续通过 nightly 任务做预计算。

### 风险 4：AlphaShop 返回结构不稳定

控制：
- 在 `AlphaShopClient` 中集中做响应标准化。
- 在 `OpportunityDiscoveryService` 中保留 `raw` evidence。

## 分阶段重构路线

### Phase 1：纠正冷启动主链

目标：跑通 `category -> valid keyword -> report -> candidate`

范围：
- 新文档
- `AlphaShopClient.newproduct_report()`
- `SeedPoolBuilderService`
- `KeywordLegitimizerService`
- `OpportunityDiscoveryService`
- `DemandDiscoveryService` facade 改造
- `ProductSelectorAgent` 编排改造
- 相关测试更新

### Phase 2：离线双速系统

目标：nightly 刷新 seeds / valid keywords / opportunities

范围：
- `tasks_keyword_research.py` 内部机会化
- Redis / snapshot 缓存结构调整
- auto-trigger 从 keyword-based 迁移到 opportunity-based

### Phase 3：机会簇与持久化

目标：将多个相近 opportunities 聚合成可解释决策单元

范围：
- `OpportunityClusterService`
- `OpportunityRecord` / `OpportunityClusterRecord`
- recommendation / feedback 集成

### Phase 4：反馈闭环优化

目标：让 seed 选择、keyword 合法化、机会排序持续优化

范围：
- 历史利润 / 转化 / 退款回灌
- cluster scoring 调优
- A/B 测试接入 opportunity 层

## 验证标准

### 冷启动合法化验证

输入：`category="electronics"`

应满足：
- 不会直接把 `electronics` 作为 `newproduct.report` 的最终 `productKeyword`
- 会先构建 seed，再通过 `keyword.search` 筛出产品级 valid keyword

### AlphaShop 契约验证

应满足：
- `newproduct.report` 只接收合法 keyword
- `KEYWORD_ILLEGAL` 能被正确处理和上报

### Opportunity 主链验证

应满足：
- `ProductSelectorAgent` 能产出 opportunity metadata
- `CandidateProduct.demand_discovery_metadata` 中包含 seed / valid keyword / report 摘要

### 供应链与下游回归

应满足：
- `AlphaShop1688Adapter` 继续承担已选中 candidate 的供应链召回
- pricing / risk / recommendation 不因入口调整而失效
