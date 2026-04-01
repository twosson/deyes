# Opportunity-First 选品架构

## 背景

当前 AlphaShop 集成已经替换 Google Trends / TMAPI 的主要调用链，但选品系统主链仍保留 **keyword-first** 假设：

- `category` 会被直接送入 `AlphaShopClient.search_keywords(keyword=category)`。
- `newproduct.report` 需要使用 `keyword.search` 返回的合法 `productKeyword`，不能直接接收泛类目词，否则会触发 `KEYWORD_ILLEGAL`。
- `intelligent_supplier_selection` 更适合做供应链验证与富化，而不是一级冷启动新品发现入口。

这说明问题已经不再是 provider 接入，而是业务主语设计错误：

- `category` 是业务标签，不是最终检索词。
- `keyword` 是市场证据载体，不是最终业务对象。
- 真正应该作为主语的是 **Opportunity（机会）** / **OpportunityCluster（机会簇）**。

## AlphaShop API 职责重定位

### `keyword.search`

定位为 **seed 合法化 / 扩展 / 初筛层**。

职责：
- 将用户词、类目种子词、历史优胜词、季节性词映射为 AlphaShop 可识别的合法关键词。
- 输出搜索量、机会分、竞争度等轻量信号。
- 为 `newproduct.report` 提供合法 `productKeyword`。

不应承担的职责：
- 直接把泛类目当作最终商品机会。
- 直接替代新品深分析。

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

## 新业务对象

### Seed

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

### ValidKeyword

ValidKeyword 是经 `keyword.search` 合法化后、可用于 `newproduct.report` 的关键词。

典型字段：
- `seed`
- `matched_keyword`
- `match_type` (`exact` / `normalized` / `related` / `fallback`)
- `opp_score`
- `search_volume`
- `competition_density`
- `is_valid_for_report`
- `raw`

### Opportunity

Opportunity 是由 `newproduct.report` 产出的市场机会草案。

典型字段：
- `keyword`
- `title`
- `opportunity_score`
- `product_list`
- `keyword_summary`
- `evidence`
- `raw`

## 新主链路

```text
category
  -> seed pool
  -> valid keyword
  -> newproduct report
  -> opportunity
  -> candidate
  -> supplier / pricing / risk / recommendation
```

## 架构原则

1. **纠正冷启动入口**：禁止把一级泛类目直接作为最终 AlphaShop 查询词使用。
2. **合法化优先**：所有 `newproduct.report` 输入都必须来自 `keyword.search` 的合法关键词。
3. **保留稳定下游**：`CandidateProduct` / `SupplierMatch` / `PricingAssessment` / `RiskAssessment` 暂不推翻。
4. **兼容式演进**：`DemandDiscoveryService` 保留 facade 接口，降低对调用方和测试的破坏。
5. **先在线后离线**：先打通在线主链，再扩展 nightly seed / keyword / opportunity 刷新任务。
6. **先无迁移落地**：Phase 1 先把机会数据写入 `demand_discovery_metadata` 与 `normalized_attributes`。

## Phase 1 目标架构

### 在线发现链

1. `SeedPoolBuilderService`
   - 将 `category` 转换为 seed pool。
   - 过滤泛类目词，避免直接查 `newproduct.report`。

2. `KeywordLegitimizerService`
   - 调用 `AlphaShopClient.search_keywords()`。
   - 输出 seed 到合法关键词的映射。

3. `DemandValidator`
   - 对已合法化 keyword 做需求质量判断。
   - 避免 discovery 和 validator 重复承担“生成关键词”职责。

4. `OpportunityDiscoveryService`
   - 对合法 keyword 调 `newproduct.report()`。
   - 规范化为 opportunity drafts。

5. `ProductSelectorAgent`
   - 基于 opportunity 选择 candidate。
   - 下游继续使用现有 supplier / pricing / risk 流程。

### 兼容 Facade

`DemandDiscoveryService` 保留外部接口，但内部改为：

```text
SeedPoolBuilder
  -> KeywordLegitimizer
  -> DemandValidator
```

返回值继续提供 `validated_keywords`，同时新增：
- `seeds`
- `valid_keywords`
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
