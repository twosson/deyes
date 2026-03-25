# Stage 2 实施任务清单

> 基于研发路线图 Stage 2：把 Phase 6 升级为经营反馈引擎
>
> 目标：让反馈不只作用于 seed / shop / supplier，还能作用于 style、asset pattern、platform、region、price band，并形成可解释的经营闭环。
>
> 版本: v1.0
> 创建时间: 2026-03-25

---

## 📋 Stage 2 总览

### 核心目标
从“历史先验加分”升级为“经营结果驱动的反馈引擎”。

### 关键交付物
1. FeedbackAggregator 升级
2. 风格 / 平台 / 地区 / 价格带 prior
3. 负反馈降权机制
4. Adapter 注入增强与解释性输出
5. 反馈特征聚合服务与测试体系

### 预期成果
- 新一轮候选排序能显著受到真实经营结果影响
- 系统能解释为什么偏爱某类 seed / supplier / style / platform-region 组合
- 高退款 / 高风险 / 低转化组合会被显式降权
- 反馈机制不破坏 Phase 1-5 已有语义

---

## 🎯 任务分组

### 分组 A：反馈数据模型与聚合口径（优先级 P0）
### 分组 B：FeedbackAggregator 扩展（优先级 P0）
### 分组 C：1688 Adapter 注入增强（优先级 P0）
### 分组 D：解释性输出与可观测性（优先级 P1）
### 分组 E：测试与验证（优先级 P0）

---

## 分组 A：反馈数据模型与聚合口径

### A1. 定义反馈聚合口径规范

**任务描述**：
编写 Stage 2 的反馈聚合口径，确保 style / platform / region / price band prior 的计算方式一致且可复现。

**具体工作**：
1. 定义基础输入源：
   - `ListingPerformanceDaily`
   - `AssetPerformanceDaily`
   - `PricingAssessment`
   - `RiskAssessment`
   - `PlatformListing`
   - `SupplierMatch`
2. 定义统一指标：
   - CTR
   - CVR
   - gross revenue
   - refund rate
   - profitability bucket
   - risk bucket
3. 定义 lookback 范围（默认 90 天）
4. 定义最小样本阈值（避免小样本噪音）
5. 定义 prior 上限和归一化规则

**涉及文件**：
- 新增：`docs/roadmap/stage2-feedback-spec.md`
- 参考：`backend/app/services/feedback_aggregator.py`

**验收标准**：
- [ ] 聚合指标有明确定义
- [ ] 每类 prior 的输入字段和计算逻辑清晰
- [ ] 小样本和缺失值策略明确

**预估工作量**：2-4 小时

---

### A2. 增加价格带划分工具

**任务描述**：
为反馈聚合新增 price band 归类工具，用于在不同类目下识别有效价格带。

**具体工作**：
1. 定义 price band 分类方法：
   - 固定分段（如 0-10 / 10-20 / 20-50）或类目分位数
2. 实现 price band 解析函数：
   - `resolve_price_band(category, platform_price)`
3. 设计统一返回值格式（如 `low`, `mid`, `high`, `premium`）
4. 增加类目缺失时的 fallback 逻辑

**涉及文件**：
- 新增：`backend/app/services/price_band_service.py`

**验收标准**：
- [ ] 不同价格都能映射到 band
- [ ] 同一类目的 band 计算稳定
- [ ] 缺失 category 时不会报错

**预估工作量**：3-5 小时

---

### A3. 定义 style 与 asset pattern 抽象规范

**任务描述**：
为 ContentAsset 和未来 A/B 测试结果建立统一的 style / asset pattern 语义层。

**具体工作**：
1. 统一 `style_tags` 的枚举和清洗规则
2. 定义 `asset_pattern` 抽象：
   - minimalist
   - luxury
   - tech
   - natural
   - seasonal
   - promo_text_overlay 等
3. 编写 style / asset pattern 解析工具
4. 定义多标签资产的聚合优先级

**涉及文件**：
- 新增：`backend/app/services/style_taxonomy_service.py`

**验收标准**：
- [ ] style_tags 可统一清洗
- [ ] asset_pattern 可从内容资产稳定提取
- [ ] 多标签时聚合规则明确

**预估工作量**：4-6 小时

---

## 分组 B：FeedbackAggregator 扩展

### B1. 扩展 style performance prior

**任务描述**：
在 `FeedbackAggregator` 中新增 style prior 查询能力。

**具体工作**：
1. 新增接口：
   - `get_style_performance_prior(style: str, category: str | None) -> float`
2. 聚合输入：
   - `ContentAsset.style_tags`
   - `AssetPerformanceDaily`
   - `PlatformListing` / `PricingAssessment` / `RiskAssessment`
3. 计算维度：
   - style CTR
   - style CVR
   - style refund risk
   - style profitability bias
4. 设置 prior cap 和最小样本阈值

**涉及文件**：
- 修改：`backend/app/services/feedback_aggregator.py`

**验收标准**：
- [ ] 可查询 style prior
- [ ] 无数据时返回 0 或 neutral prior
- [ ] prior 在上限内可控

**预估工作量**：6-8 小时

---

### B2. 扩展 platform-region prior

**任务描述**：
新增平台 + 地区 + 类目组合的历史表现先验。

**具体工作**：
1. 新增接口：
   - `get_platform_region_prior(platform: str, region: str, category: str | None) -> float`
2. 聚合输入：
   - `PlatformListing.platform`
   - `PlatformListing.region`
   - `ListingPerformanceDaily`
3. 计算维度：
   - 该平台地区组合的平均 CTR / CVR / refund rate / profitability
4. 增加 category 维度过滤和 fallback

**涉及文件**：
- 修改：`backend/app/services/feedback_aggregator.py`

**验收标准**：
- [ ] 可查询 platform-region prior
- [ ] category 有值和无值两种路径均可工作
- [ ] small sample 会自动回退

**预估工作量**：6-8 小时

---

### B3. 扩展 price band prior

**任务描述**：
新增价格带表现先验，用于辅助 business score 调整。

**具体工作**：
1. 新增接口：
   - `get_price_band_prior(category: str | None, price_band: str) -> float`
2. 结合 `PriceBandService` 进行 band 分类
3. 聚合价格带的 CTR / CVR / gross revenue / refund rate / profitability
4. 处理样本稀疏问题

**涉及文件**：
- 修改：`backend/app/services/feedback_aggregator.py`
- 依赖：`backend/app/services/price_band_service.py`

**验收标准**：
- [ ] 可查询 price band prior
- [ ] 与 style / supplier prior 共存不冲突
- [ ] 输出有上限和稳定 fallback

**预估工作量**：5-7 小时

---

### B4. 新增负反馈降权聚合

**任务描述**：
实现针对高退款 / 高风险 / 低转化组合的负反馈降权机制。

**具体工作**：
1. 新增接口：
   - `get_negative_feedback_penalty(...)`
2. 支持维度：
   - seed
   - supplier
   - style
   - platform-region
   - price band
3. 规则示例：
   - refund rate 高于阈值 -> penalty
   - risk REVIEW/REJECT 比例高 -> penalty
   - CVR 长期过低 -> penalty
4. 设置 penalty cap

**涉及文件**：
- 修改：`backend/app/services/feedback_aggregator.py`

**验收标准**：
- [ ] 负反馈会输出 penalty
- [ ] penalty 不会无限放大
- [ ] 能和正向 prior 一起组合

**预估工作量**：6-8 小时

---

### B5. 抽离聚合特征服务

**任务描述**：
将复杂聚合逻辑从 `FeedbackAggregator` 抽离到独立服务，避免其演变为臃肿特征仓库。

**具体工作**：
1. 新增 `PerformanceAggregatorService`
2. 新增方法：
   - `aggregate_seed_features()`
   - `aggregate_style_features()`
   - `aggregate_supplier_features()`
   - `aggregate_platform_region_features()`
   - `aggregate_price_band_features()`
3. `FeedbackAggregator` 改为面向 prior 接口的轻量 facade

**涉及文件**：
- 新增：`backend/app/services/performance_aggregator_service.py`
- 修改：`backend/app/services/feedback_aggregator.py`

**验收标准**：
- [ ] 聚合逻辑不再全部堆在 FeedbackAggregator 内
- [ ] FeedbackAggregator 只保留对外 prior API
- [ ] 单元测试可分别覆盖 aggregation 与 prior 映射

**预估工作量**：8-10 小时

---

## 分组 C：1688 Adapter 注入增强

### C1. 扩展 historical feedback score 注入点

**任务描述**：
在 1688 adapter 中把 Stage 2 prior 注入 recall 和 ranking。

**具体工作**：
1. 保持现有 recall 注入点：`_get_historical_high_performing_seeds(...)`
2. 扩展 scoring helper：
   - seed prior
   - shop prior
   - supplier prior
   - style prior
   - platform-region prior
   - price band prior
   - negative feedback penalty
3. 输出总的 `historical_feedback_score`

**涉及文件**：
- 修改：`backend/app/services/alibaba_1688_adapter.py`

**验收标准**：
- [ ] 新 prior 已进入 business score
- [ ] negative penalty 会影响最终反馈分数
- [ ] final_score 语义不变（仍为 discovery + business）

**预估工作量**：8-10 小时

---

### C2. 为 candidate 补充 style / price band 推断

**任务描述**：
为候选商品推断可参与反馈的 style 和 price band 特征。

**具体工作**：
1. 从候选内容 / normalized_attributes / raw_payload 推导 style 候选
2. 通过 `PriceBandService` 推导 price band
3. 将推导出的特征注入 `normalized_attributes`

**涉及文件**：
- 修改：`backend/app/services/alibaba_1688_adapter.py`

**验收标准**：
- [ ] candidate 可输出 style / price_band 派生特征
- [ ] 缺失值时有 fallback
- [ ] 不引入 schema 变更

**预估工作量**：4-6 小时

---

### C3. 实现降权不淘汰的排序策略

**任务描述**：
设计 Stage 2 的负反馈排序策略，确保系统优先降权，而不是过早把候选完全过滤掉。

**具体工作**：
1. 明确 penalty 应用于 business score 的方式
2. 设置下限，避免极端 penalty 导致 recall 失真
3. 为低样本的负反馈增加置信度折扣

**涉及文件**：
- 修改：`backend/app/services/alibaba_1688_adapter.py`
- 修改：`backend/app/services/feedback_aggregator.py`

**验收标准**：
- [ ] 高风险组合下移但不会全部消失
- [ ] 低样本噪音不会导致严重误杀
- [ ] 排序结果更符合经营反馈直觉

**预估工作量**：4-6 小时

---

## 分组 D：解释性输出与可观测性

### D1. 扩展 normalized_attributes 调试信号

**任务描述**：
把 Stage 2 的关键 prior 和 penalty 输出到 `normalized_attributes`，便于 API / 测试 / 人工验证。

**建议字段**：
- `historical_style_prior`
- `historical_platform_region_prior`
- `historical_price_band_prior`
- `historical_negative_feedback_penalty`
- `historical_feedback_score_breakdown`

**涉及文件**：
- 修改：`backend/app/services/alibaba_1688_adapter.py:1823`

**验收标准**：
- [ ] 关键 prior / penalty 可观测
- [ ] breakdown 字段结构稳定
- [ ] 不污染与业务无关的字段

**预估工作量**：3-4 小时

---

### D2. 新增反馈解释器服务

**任务描述**：
创建 `FeedbackExplanationService`，统一输出“为什么这个 candidate 被加分/降权”。

**具体工作**：
1. 新增解释器服务
2. 实现方法：
   - `build_candidate_feedback_explanation(...)`
   - `build_seed_feedback_explanation(...)`
   - `build_supplier_feedback_explanation(...)`
3. 输出结构化 explanation payload

**涉及文件**：
- 新增：`backend/app/services/feedback_explanation_service.py`

**验收标准**：
- [ ] explanation payload 可序列化
- [ ] 能准确反映 prior 和 penalty 来源
- [ ] 可供 API / UI 复用

**预估工作量**：5-7 小时

---

### D3. 新增反馈调试 API（可选）

**任务描述**：
提供只读调试 API，查询某个 seed / supplier / style / price band 的反馈 prior。

**具体工作**：
1. 设计只读路由
2. 提供查询接口：
   - `/feedback/seed/{seed}`
   - `/feedback/style/{style}`
   - `/feedback/supplier/{supplier}`
3. 返回 prior / penalty / sample size / breakdown

**涉及文件**：
- 新增：`backend/app/api/routes_feedback_debug.py`

**验收标准**：
- [ ] API 可返回结构化调试数据
- [ ] 不暴露敏感信息
- [ ] 可在测试环境验证

**预估工作量**：6-8 小时

---

## 分组 E：测试与验证

### E1. 扩展 FeedbackAggregator 单元测试

**任务描述**：
扩展现有 `test_feedback_aggregator.py`，覆盖 style / platform-region / price band / penalty 场景。

**具体工作**：
新增测试：
- `test_get_style_performance_prior_returns_bounded_score`
- `test_get_platform_region_prior_returns_bounded_score`
- `test_get_price_band_prior_returns_bounded_score`
- `test_negative_feedback_penalty_is_applied_for_high_refund_rate`
- `test_feedback_aggregator_respects_min_sample_threshold`

**涉及文件**：
- 修改：`backend/tests/test_feedback_aggregator.py`

**验收标准**：
- [ ] 新增测试全部通过
- [ ] prior 和 penalty 都有边界验证

**预估工作量**：6-8 小时

---

### E2. 扩展 1688 Adapter 聚焦测试

**任务描述**：
扩展 `test_alibaba_1688_adapter_tmapi.py`，验证新的 Stage 2 prior 已经进入 recall / ranking / normalized_attributes。

**具体工作**：
新增测试：
- `test_style_prior_boosts_business_score`
- `test_platform_region_prior_boosts_business_score`
- `test_price_band_prior_boosts_business_score`
- `test_negative_feedback_penalty_reduces_business_score`
- `test_stage2_feedback_signals_are_visible_in_normalized_attributes`

**涉及文件**：
- 修改：`backend/tests/test_alibaba_1688_adapter_tmapi.py`

**验收标准**：
- [ ] 新增测试全部通过
- [ ] Phase 1-6 原逻辑不回退

**预估工作量**：6-8 小时

---

### E3. 新增反馈解释器测试

**任务描述**：
为 `FeedbackExplanationService` 编写单元测试。

**具体工作**：
1. 测试 explanation payload 结构
2. 测试正向 prior explanation
3. 测试 penalty explanation
4. 测试无历史数据场景

**涉及文件**：
- 新增：`backend/tests/test_feedback_explanation_service.py`

**验收标准**：
- [ ] explanation 测试通过
- [ ] payload 字段稳定

**预估工作量**：3-5 小时

---

### E4. Stage 2 回归验证套件

**任务描述**：
建立 Stage 2 的目标回归命令和验证 checklist。

**建议命令**：
```bash
python -m pytest backend/tests/test_feedback_aggregator.py -v
python -m pytest backend/tests/test_alibaba_1688_adapter_tmapi.py -k "feedback or historical or stage2" -v
python -m pytest backend/tests/test_phase1_mvp.py -v
```

**涉及文件**：
- 新增：`docs/roadmap/stage2-verification-checklist.md`

**验收标准**：
- [ ] 核心回归命令明确
- [ ] 手工验证 checklist 明确
- [ ] 人工和自动验证路径一致

**预估工作量**：2-3 小时

---

## 📊 任务优先级与依赖关系

### 第一批（并行）
- A1（反馈口径规范）
- A2（价格带服务）
- A3（style taxonomy）
- B1（style prior）

### 第二批（依赖第一批）
- B2（platform-region prior）
- B3（price band prior）
- B4（negative penalty）
- D1（normalized_attributes 扩展）

### 第三批（依赖第二批）
- B5（聚合逻辑抽离）
- C1（adapter 注入增强）
- C2（candidate 特征推断）
- E1 / E2（核心测试）

### 第四批（依赖第三批）
- C3（降权不淘汰策略）
- D2（反馈解释器）
- D3（调试 API，可选）
- E3 / E4（补充测试与验证文档）

---

## 📈 工作量估算

| 分组 | 任务数 | 预估总工时 | 建议人员 |
|------|--------|-----------|---------|
| A | 3 | 9-15h | 后端 + 数据 |
| B | 5 | 31-41h | 后端 |
| C | 3 | 16-22h | 后端 + 算法 |
| D | 3 | 14-19h | 后端 |
| E | 4 | 17-24h | 测试 + 后端 |
| **总计** | **18** | **87-121h** | **2 人** |

按 2 人并行投入，Stage 2 可作为下一阶段主开发包推进。

---

## ✅ Stage 2 退出标准

### 功能完整性
- [ ] style prior 已可查询和使用
- [ ] platform-region prior 已可查询和使用
- [ ] price band prior 已可查询和使用
- [ ] negative feedback penalty 已可查询和使用
- [ ] 1688 adapter 已接入 Stage 2 反馈信号

### 可解释性
- [ ] normalized_attributes 中可看到新增反馈信号
- [ ] explanation payload 可说明加分/降权原因
- [ ] 调试 API（如启用）可查询 prior / penalty

### 稳定性
- [ ] prior / penalty 均有 cap，不会无限放大
- [ ] 小样本不会产生极端偏差
- [ ] Phase 1-6 原语义不退化

### 测试覆盖
- [ ] FeedbackAggregator 扩展测试全部通过
- [ ] 1688 Adapter Stage 2 聚焦测试全部通过
- [ ] Phase 1 MVP 回归不受影响

---

## 🚀 下一步

完成 Stage 2 后，下一步进入 **Stage 3：建立 ERP Lite 商品与供应链核心**，把反馈引擎真正落到 SKU、Supplier、Inventory、PurchaseOrder 的长期经营事实层上。

---

**文档版本**: v1.0
**创建时间**: 2026-03-25
**维护者**: Deyes 研发团队
