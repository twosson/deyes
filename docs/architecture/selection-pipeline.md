# 产品选品流程详细文档

## 概述

Deyes 产品选品系统采用 4 阶段流程，结合 1688 多路召回策略和闭环反馈机制，实现自动化选品。

**核心流程：**
1. ProductSelectorAgent - 抓取平台商品，匹配 1688 供应商
2. PricingAnalystAgent - 选择最优供应商，计算利润率
3. RiskControllerAgent - 基于规则的风险评估
4. MultilingualCopywriterAgent - 生成多语言文案

**关键特性：**
- 1688 多路召回（默认、销量、工厂、图像相似）
- 供应商竞争集评分（多维度加权）
- 历史反馈先验（种子、店铺、供应商）
- 闭环优化（90 天回溯）

---

## 阶段 1: ProductSelectorAgent

**位置：** `backend/app/agents/product_selector.py:14`

### 职责

1. 从目标平台抓取热销商品（Temu, Amazon, AliExpress 等）
2. 在 1688 匹配供应商（多路召回）
3. 创建候选商品记录（CandidateProduct）
4. 创建供应商匹配记录（SupplierMatch）

### 输入参数

```python
context.input_data = {
    "platform": "temu",              # 目标平台
    "category": "electronics",       # 品类
    "keywords": ["phone case"],      # 关键词列表
    "region": "US",                  # 地区
    "price_min": 10.0,               # 最低价格
    "price_max": 50.0,               # 最高价格
    "max_candidates": 10,            # 最大候选数
}
```

### 执行流程

```python
# 1. 初始化平台适配器
if settings.use_real_scrapers:
    if platform == SourcePlatform.TEMU:
        self.source_adapter = TemuSourceAdapterV2()
    elif platform == SourcePlatform.ALIBABA_1688:
        self.source_adapter = Alibaba1688Adapter()
else:
    self.source_adapter = MockSourceAdapter(platform)

# 2. 抓取平台商品
products = await self.source_adapter.fetch_products(
    category=category,
    keywords=keywords,
    price_min=price_min,
    price_max=price_max,
    limit=max_candidates,
    region=region,
)

# 3. 为每个商品匹配 1688 供应商
for product in products:
    # 创建候选商品记录
    candidate = CandidateProduct(
        source_platform=product.source_platform,
        source_product_id=product.source_product_id,
        title=product.title,
        platform_price=product.platform_price,
        sales_count=product.sales_count,
        rating=product.rating,
        main_image_url=product.main_image_url,
        status=CandidateStatus.DISCOVERED,
    )

    # 匹配供应商（多路召回）
    suppliers = await self.supplier_matcher.find_suppliers(
        product_title=product.title,
        product_category=product.category,
        limit=5,
        source_platform=product.source_platform,
        supplier_candidates=product.supplier_candidates,
    )

    # 创建供应商匹配记录
    for supplier in suppliers:
        supplier_match = SupplierMatch(
            candidate_product_id=candidate.id,
            supplier_name=supplier.supplier_name,
            supplier_url=supplier.supplier_url,
            supplier_sku=supplier.supplier_sku,
            supplier_price=supplier.supplier_price,
            moq=supplier.moq,
            confidence_score=supplier.confidence_score,
            selected=False,
        )
        context.db.add(supplier_match)
```

### 输出

```python
{
    "candidate_ids": ["uuid1", "uuid2", ...],
    "count": 10,
}
```

---

## 1688 多路召回策略

**位置：** `backend/app/services/supplier_matcher.py:39`

### 召回路径优先级

1. **直接提取路径** - 从平台适配器提供的 `supplier_candidates` 提取
2. **Payload 提取路径** - 从 `raw_payload` 中提取 1688 供应商信息
3. **Mock 兜底路径** - 生成模拟供应商数据（非 1688 平台或无数据时）

### 路径 1: 直接提取（优先）

```python
def _extract_from_supplier_candidates(
    self,
    supplier_candidates: list[dict],
    limit: int,
) -> list[SupplierMatch]:
    """从适配器提供的候选供应商列表提取"""
    matches = []
    for candidate in supplier_candidates[:limit]:
        supplier_name = candidate.get("supplier_name") or candidate.get("company_name")
        supplier_url = candidate.get("supplier_url") or candidate.get("detail_url")
        supplier_sku = candidate.get("supplier_sku") or candidate.get("item_id")

        matches.append(SupplierMatch(
            supplier_name=supplier_name,
            supplier_url=supplier_url,
            supplier_sku=str(supplier_sku),
            supplier_price=self._coerce_decimal(candidate.get("supplier_price")),
            moq=self._coerce_int(candidate.get("moq")),
            confidence_score=self._coerce_decimal(candidate.get("confidence_score")) or Decimal("0.80"),
            raw_payload=candidate,
        ))
    return matches
```

### 路径 2: Payload 提取（兜底）

```python
def _extract_from_1688_payload(self, raw_payload: dict) -> list[SupplierMatch]:
    """从原始 1688 数据中提取供应商信息"""
    detail_payload = raw_payload.get("detail_payload") or {}

    supplier_name = (
        detail_payload.get("company_name") or
        detail_payload.get("shop_name") or
        raw_payload.get("company_name")
    )

    supplier_url = (
        detail_payload.get("detail_url") or
        raw_payload.get("source_url")
    )

    supplier_sku = (
        detail_payload.get("num_iid") or
        raw_payload.get("source_product_id")
    )

    supplier_price = self._coerce_decimal(
        raw_payload.get("price_cny") or detail_payload.get("price")
    )

    moq = self._coerce_int(
        raw_payload.get("moq") or detail_payload.get("min_num")
    )

    return [SupplierMatch(
        supplier_name=supplier_name,
        supplier_url=supplier_url,
        supplier_sku=str(supplier_sku),
        supplier_price=supplier_price,
        moq=moq,
        confidence_score=Decimal("0.75"),
    )]
```

### 路径 3: Mock 兜底

```python
def _build_mock_suppliers(self, product_title: str, limit: int) -> list[SupplierMatch]:
    """生成模拟供应商数据（非 1688 或无数据时）"""
    suppliers = []
    for i in range(min(limit, 3)):
        base_price = Decimal("10.00") + Decimal(i * 5)
        confidence = Decimal("0.85") - Decimal(i * Decimal("0.10"))
        suppliers.append(SupplierMatch(
            supplier_name=f"Mock Supplier {i + 1}",
            supplier_url=f"https://1688.com/offer/{uuid4().hex[:12]}.html",
            supplier_sku=f"SKU-{uuid4().hex[:8].upper()}",
            supplier_price=base_price,
            moq=50 + (i * 50),
            confidence_score=confidence,
            raw_payload={"mock": True},
        ))
    return suppliers
```

---

## 阶段 2: PricingAnalystAgent

**位置：** `backend/app/agents/pricing_analyst.py:14`

### 职责

1. 为每个候选商品选择最优供应商
2. 计算利润率和成本结构
3. 做出盈利性决策（PROFITABLE / MARGINAL / UNPROFITABLE）

### 供应商评分公式

**位置：** `backend/app/services/pricing_service.py:42`

```python
# 多维度加权评分
total_score = (
    price_component * 0.45 +           # 价格得分（45%）
    confidence_component * 0.30 +      # 置信度得分（30%）
    moq_component * 0.15 +             # MOQ 得分（15%）
    identity_bonus -                   # 身份加分
    alternative_sku_penalty -          # 替代 SKU 惩罚
    price_gap_penalty                  # 价格差距惩罚
)
```

#### 价格得分计算

```python
# 价格越低，得分越高
if min_price > 0:
    price_gap = (supplier_price - min_price) / min_price
    if price_gap <= PRICE_GAP_TOLERANCE:  # 20%
        price_component = 1.0 - (price_gap / PRICE_GAP_TOLERANCE)
    else:
        price_component = 0.0
else:
    price_component = 0.5
```

#### 置信度得分

```python
# 直接使用置信度分数（0-1）
confidence_component = float(confidence_score)
```

#### MOQ 得分

```python
# MOQ 越低，得分越高
if moq <= 50:
    moq_component = 1.0
elif moq <= 100:
    moq_component = 0.7
elif moq <= 200:
    moq_component = 0.4
else:
    moq_component = 0.1
```

#### 身份加分

```python
identity_bonus = 0.0

if is_factory_result:
    identity_bonus += FACTORY_BONUS  # +0.06

if is_super_factory:
    identity_bonus += SUPER_FACTORY_BONUS  # +0.04

if verified_supplier:
    identity_bonus += VERIFIED_BONUS  # +0.04
```

#### 惩罚项

```python
# 替代 SKU 惩罚
if alternative_sku:
    alternative_sku_penalty = ALTERNATIVE_SKU_PENALTY  # 0.05
else:
    alternative_sku_penalty = 0.0

# 价格差距惩罚
if price_gap > PRICE_GAP_TOLERANCE:
    price_gap_penalty = (price_gap - PRICE_GAP_TOLERANCE) * PRICE_GAP_PENALTY_WEIGHT  # 0.20
else:
    price_gap_penalty = 0.0
```

### 利润率计算

```python
# 总成本
total_cost = (
    supplier_price +
    shipping_cost +
    platform_commission +
    payment_fee +
    return_cost
)

# 利润率
margin_ratio = (platform_price - total_cost) / platform_price

# 盈利性决策
if margin_ratio >= PROFITABLE_THRESHOLD:  # 30%
    decision = ProfitabilityDecision.PROFITABLE
elif margin_ratio >= MARGINAL_THRESHOLD:  # 15%
    decision = ProfitabilityDecision.MARGINAL
else:
    decision = ProfitabilityDecision.UNPROFITABLE
```

---

## 阶段 3: RiskControllerAgent

**位置：** `backend/app/agents/risk_controller.py:14`

### 职责

1. 基于规则的风险评估
2. 计算风险评分（0-100）
3. 做出风险决策（PASS / REVIEW / REJECT）

### 风险评估规则

```python
# 当前仅支持合规风险
# 未来将添加竞争密度风险（见优化计划）

risk_score = 0

# 规则 1: 品牌侵权检测
if contains_brand_keywords(title):
    risk_score += 30

# 规则 2: 禁售品类检测
if category in FORBIDDEN_CATEGORIES:
    risk_score += 50

# 规则 3: 目标市场合规检测
if not compliant_with_market_regulations(product, market):
    risk_score += 20

# 风险决策
if risk_score >= 70:
    decision = RiskDecision.REJECT
elif risk_score >= 40:
    decision = RiskDecision.REVIEW
else:
    decision = RiskDecision.PASS
```

---

## 阶段 4: MultilingualCopywriterAgent

**位置：** `backend/app/agents/multilingual_copywriter.py:14`

### 职责

1. 生成多语言商品标题（5 种语言）
2. 生成多语言商品描述
3. 生成卖点 bullet points
4. 生成 HTML 详情页

### 目标语言

- 英语（en）
- 西班牙语（es）
- 日语（ja）
- 俄语（ru）
- 葡萄牙语（pt）

---

## 闭环反馈机制

**位置：** `backend/app/services/feedback_aggregator.py:19`

### FeedbackAggregator 服务

#### 职责

1. 从数据库读取历史表现数据（90 天回溯）
2. 计算种子、店铺、供应商的表现先验
3. 为选品流程提供历史反馈信号

#### 先验类型

**1. 种子表现先验（Seed Performance Prior）**

```python
# 键：(matched_keyword, seed_type)
# 值：历史表现评分（0-5.0）

seed_priors = {
    ("phone case", "default"): 3.5,
    ("wireless charger", "sales"): 4.2,
    ("bluetooth speaker", "factory"): 2.8,
}
```

**2. 店铺表现先验（Shop Performance Prior）**

```python
# 键：shop_name
# 值：历史表现评分（0-5.0）

shop_priors = {
    "深圳市XX电子有限公司": 4.0,
    "广州YY贸易有限公司": 3.2,
}
```

**3. 供应商表现先验（Supplier Performance Prior）**

```python
# 键：(supplier_name, supplier_url)
# 值：历史表现评分（0-5.0）

supplier_priors = {
    ("深圳市XX电子有限公司", "https://1688.com/..."): 4.5,
    ("广州YY贸易有限公司", "https://1688.com/..."): 3.0,
}
```

#### 评分计算

```python
score = 0.0

# 盈利性决策加分
if profitability == PROFITABLE:
    score += 2.0
elif profitability == MARGINAL:
    score += 0.5

# 风险决策加分
if risk == PASS:
    score += 1.5
elif risk == REVIEW:
    score += 0.5

# 利润率加分（最多 +1.0）
if margin_percentage:
    score += min(margin_percentage / 10.0, 1.0)

# 销量加分（最多 +1.0）
if total_sales > 0:
    score += min(total_sales / 100.0, 1.0)

# 最终评分上限 5.0
final_score = min(score, 5.0)
```

#### 高表现种子

```python
# 筛选评分 >= 2.0 的种子
high_performing_seeds = [
    (seed, seed_type, prior)
    for (seed, seed_type), prior in seed_priors.items()
    if prior >= 2.0
]

# 按评分降序排序
high_performing_seeds.sort(key=lambda x: x[2], reverse=True)
```

#### 使用方式

```python
# 初始化
aggregator = FeedbackAggregator(lookback_days=90, prior_cap=5.0)

# 刷新缓存
await aggregator.refresh(db)

# 获取高表现种子
seeds = aggregator.get_high_performing_seeds(category="electronics", limit=20)

# 获取种子表现先验
prior = aggregator.get_seed_performance_prior(seed="phone case", seed_type="default")

# 获取店铺表现先验
prior = aggregator.get_shop_performance_prior(shop_name="深圳市XX电子有限公司")

# 获取供应商表现先验
prior = aggregator.get_supplier_performance_prior(
    supplier_name="深圳市XX电子有限公司",
    supplier_url="https://1688.com/...",
)
```

---

## 完整流程示例

```python
# 1. ProductSelectorAgent
candidate_ids = await product_selector.execute(context)
# 输出: ["uuid1", "uuid2", ...]

# 2. PricingAnalystAgent
for candidate_id in candidate_ids:
    pricing_result = await pricing_analyst.execute(context)
    # 输出: {
    #   "selected_supplier_id": "uuid",
    #   "profitability_decision": "PROFITABLE",
    #   "margin_percentage": 0.35,
    # }

# 3. RiskControllerAgent
for candidate_id in candidate_ids:
    risk_result = await risk_controller.execute(context)
    # 输出: {
    #   "risk_decision": "PASS",
    #   "risk_score": 20,
    # }

# 4. MultilingualCopywriterAgent
for candidate_id in candidate_ids:
    if profitability == PROFITABLE and risk == PASS:
        copy_result = await copywriter.execute(context)
        # 输出: {
        #   "copies": {
        #     "en": {"title": "...", "description": "...", "bullets": [...]},
        #     "es": {"title": "...", "description": "...", "bullets": [...]},
        #     ...
        #   }
        # }
```

---

## 性能指标

**单个候选商品处理时间：**
- ProductSelectorAgent: 2-3 秒（抓取 + 匹配供应商）
- PricingAnalystAgent: 0.5-1 秒（评分 + 利润计算）
- RiskControllerAgent: 0.2-0.5 秒（规则评估）
- MultilingualCopywriterAgent: 3-5 秒（LLM 生成文案）

**总计：** 6-10 秒/候选商品

**并发能力：**
- 图像生成瓶颈：4 张/秒（4 卡 GPU）
- LLM 推理瓶颈：20-25 个并发请求
- 理论产能：2,400-2,800 套/天

---

## 优化方向

详见 `docs/architecture/product-selection-optimization-v1.md:1`

**关键改进：**
1. 需求优先验证（在抓取前验证海外需求）
2. 竞争密度评估（量化市场饱和风险）
3. 提高利润阈值（30% → 35%）
4. 动态关键词生成（自动发现趋势关键词）
5. 季节性日历（事件驱动选品）

---

**文档版本：** v1.0
**最后更新：** 2026-03-26
**状态：** 生产就绪
