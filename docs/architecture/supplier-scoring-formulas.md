# 供应商评分公式参考文档

## 概述

本文档详细说明 Deyes 系统中供应商评分算法的数学公式��权重配置。

**位置：** `backend/app/services/pricing_service.py:17`

---

## 核心评分公式

```python
total_score = (
    price_component × 0.45 +
    confidence_component × 0.30 +
    moq_component × 0.15 +
    identity_bonus -
    alternative_sku_penalty -
    price_gap_penalty
)
```

**权重分配：**
- 价格得分：45%（最重要）
- 置信度得分：30%
- MOQ 得分：15%
- 身份加分：最多 +0.14
- 惩罚项：最多 -0.25

---

## 1. 价格得分（Price Component）

### 公式

```python
if min_price > 0:
    price_gap = (supplier_price - min_price) / min_price

    if price_gap <= PRICE_GAP_TOLERANCE:  # 0.20 (20%)
        price_component = 1.0 - (price_gap / PRICE_GAP_TOLERANCE)
    else:
        price_component = 0.0
else:
    price_component = 0.5  # 无参考价格时给中等分
```

### 配置参数

```python
SUPPLIER_PRICE_WEIGHT = Decimal("0.45")              # 45% 权重
SUPPLIER_PRICE_GAP_TOLERANCE = Decimal("0.20")       # 20% 容忍度
```

### 计算示例

**场景 1：最低价供应商**
```
min_price = 10.0
supplier_price = 10.0
price_gap = (10.0 - 10.0) / 10.0 = 0.0
price_component = 1.0 - (0.0 / 0.20) = 1.0
```

**场景 2：价格高 10%**
```
min_price = 10.0
supplier_price = 11.0
price_gap = (11.0 - 10.0) / 10.0 = 0.10
price_component = 1.0 - (0.10 / 0.20) = 0.5
```

**场景 3：价格高 20%（临界点）**
```
min_price = 10.0
supplier_price = 12.0
price_gap = (12.0 - 10.0) / 10.0 = 0.20
price_component = 1.0 - (0.20 / 0.20) = 0.0
```

**场景 4：价格高 30%（超出容忍度）**
```
min_price = 10.0
supplier_price = 13.0
price_gap = (13.0 - 10.0) / 10.0 = 0.30
price_component = 0.0  # 超出容忍度，直接归零
```

---

## 2. 置信度得分（Confidence Component）

### 公式

```python
confidence_component = float(confidence_score)  # 0.0 - 1.0
```

### 配置参数

```python
SUPPLIER_CONFIDENCE_WEIGHT = Decimal("0.30")  # 30% 权重
```

### 置信度来源

**1. 直接提取（最高置信度）**
```python
# 从适配器提供的 supplier_candidates 提取
confidence_score = candidate.get("confidence_score") or Decimal("0.80")
```

**2. Payload 提取（中等置信度）**
```python
# 从 raw_payload 提取
confidence_score = Decimal("0.75")
```

**3. Mock 兜底（递减置信度）**
```python
# 模拟数据
confidence_score = Decimal("0.85") - Decimal(i * Decimal("0.10"))
# 第 1 个：0.85
# 第 2 个：0.75
# 第 3 个：0.65
```

---

## 3. MOQ 得分（MOQ Component）

### 公式

```python
if moq <= 50:
    moq_component = 1.0
elif moq <= 100:
    moq_component = 0.7
elif moq <= 200:
    moq_component = 0.4
else:
    moq_component = 0.1
```

### 配置参数

```python
SUPPLIER_MOQ_WEIGHT = Decimal("0.15")  # 15% 权重
```

### 分段说明

| MOQ 范围 | 得分 | 说明 |
|---------|------|------|
| ≤ 50 | 1.0 | 优秀（小单友好） |
| 51-100 | 0.7 | 良好 |
| 101-200 | 0.4 | 一般 |
| > 200 | 0.1 | 较差（起订量过高） |

---

## 4. 身份加分（Identity Bonus）

### 公式

```python
identity_bonus = 0.0

if is_factory_result:
    identity_bonus += SUPPLIER_FACTORY_BONUS  # +0.06

if is_super_factory:
    identity_bonus += SUPPLIER_SUPER_FACTORY_BONUS  # +0.04

if verified_supplier:
    identity_bonus += SUPPLIER_VERIFIED_BONUS  # +0.04
```

### 配置参数

```python
SUPPLIER_FACTORY_BONUS = Decimal("0.06")         # 工厂加分
SUPPLIER_SUPER_FACTORY_BONUS = Decimal("0.04")   # 超级工厂加分
SUPPLIER_VERIFIED_BONUS = Decimal("0.04")        # 认证供应商加分
```

### 身份识别

**工厂标识（is_factory_result）**
```python
# 从 raw_payload 提取
is_factory = raw_payload.get("is_factory") or False
```

**超级工厂标识（is_super_factory）**
```python
# 从 raw_payload 提取
is_super_factory = raw_payload.get("is_super_factory") or False
```

**认证供应商标识（verified_supplier）**
```python
# 从 raw_payload 提取
verified = raw_payload.get("verified_supplier") or False
```

### 最大加分

```python
max_identity_bonus = 0.06 + 0.04 + 0.04 = 0.14
```

---

## 5. 替代 SKU 惩罚（Alternative SKU Penalty）

### 公式

```python
if alternative_sku:
    alternative_sku_penalty = SUPPLIER_ALTERNATIVE_SKU_PENALTY  # 0.05
else:
    alternative_sku_penalty = 0.0
```

### 配置参数

```python
SUPPLIER_ALTERNATIVE_SKU_PENALTY = Decimal("0.05")  # 5% 惩罚
```

### 识别逻辑

```python
# 从 raw_payload 提取
alternative_sku = raw_payload.get("alternative_sku") or False
```

**说明：** 如果供应商提供的是替代 SKU（非原始商品），则扣除 0.05 分。

---

## 6. 价格差距惩罚（Price Gap Penalty）

### 公式

```python
if price_gap > PRICE_GAP_TOLERANCE:  # 0.20
    price_gap_penalty = (price_gap - PRICE_GAP_TOLERANCE) * PRICE_GAP_PENALTY_WEIGHT  # 0.20
else:
    price_gap_penalty = 0.0
```

### 配置参数

```python
SUPPLIER_PRICE_GAP_TOLERANCE = Decimal("0.20")        # 20% 容忍度
SUPPLIER_PRICE_GAP_PENALTY_WEIGHT = Decimal("0.20")   # 惩罚权重
```

### 计算示例

**场景 1：价格差距 10%（在容忍度内）**
```
price_gap = 0.10
price_gap_penalty = 0.0  # 无惩罚
```

**场景 2：价格差距 30%（超出容忍度 10%）**
```
price_gap = 0.30
price_gap_penalty = (0.30 - 0.20) × 0.20 = 0.02
```

**场景 3：价格差距 50%（超出容忍度 30%）**
```
price_gap = 0.50
price_gap_penalty = (0.50 - 0.20) × 0.20 = 0.06
```

---

## 完整评分示例

### 示例 1：优质供应商

**输入：**
```python
supplier_price = 10.0
min_price = 10.0
confidence_score = 0.85
moq = 50
is_factory_result = True
is_super_factory = True
verified_supplier = True
alternative_sku = False
```

**计算：**
```python
# 价格得分
price_gap = (10.0 - 10.0) / 10.0 = 0.0
price_component = 1.0 - (0.0 / 0.20) = 1.0

# 置信度得分
confidence_component = 0.85

# MOQ 得分
moq_component = 1.0  # moq <= 50

# 身份加分
identity_bonus = 0.06 + 0.04 + 0.04 = 0.14

# 惩罚项
alternative_sku_penalty = 0.0
price_gap_penalty = 0.0

# 总分
total_score = (
    1.0 × 0.45 +
    0.85 × 0.30 +
    1.0 × 0.15 +
    0.14 -
    0.0 -
    0.0
) = 0.45 + 0.255 + 0.15 + 0.14 = 0.995
```

**结果：** 0.995（接近满分）

---

### 示例 2：一般供应商

**输入：**
```python
supplier_price = 11.0
min_price = 10.0
confidence_score = 0.75
moq = 100
is_factory_result = False
is_super_factory = False
verified_supplier = False
alternative_sku = False
```

**计算：**
```python
# 价格得分
price_gap = (11.0 - 10.0) / 10.0 = 0.10
price_component = 1.0 - (0.10 / 0.20) = 0.5

# 置信度得分
confidence_component = 0.75

# MOQ 得分
moq_component = 0.7  # 51 <= moq <= 100

# 身份加分
identity_bonus = 0.0

# 惩罚项
alternative_sku_penalty = 0.0
price_gap_penalty = 0.0  # price_gap <= 0.20

# 总分
total_score = (
    0.5 × 0.45 +
    0.75 × 0.30 +
    0.7 × 0.15 +
    0.0 -
    0.0 -
    0.0
) = 0.225 + 0.225 + 0.105 = 0.555
```

**结果：** 0.555（中等）

---

### 示例 3：较差供应商

**输入：**
```python
supplier_price = 13.0
min_price = 10.0
confidence_score = 0.65
moq = 250
is_factory_result = False
is_super_factory = False
verified_supplier = False
alternative_sku = True
```

**计算：**
```python
# 价格得分
price_gap = (13.0 - 10.0) / 10.0 = 0.30
price_component = 0.0  # price_gap > 0.20

# 置信度得分
confidence_component = 0.65

# MOQ 得分
moq_component = 0.1  # moq > 200

# 身份加分
identity_bonus = 0.0

# 惩罚项
alternative_sku_penalty = 0.05
price_gap_penalty = (0.30 - 0.20) × 0.20 = 0.02

# 总分
total_score = (
    0.0 × 0.45 +
    0.65 × 0.30 +
    0.1 × 0.15 +
    0.0 -
    0.05 -
    0.02
) = 0.0 + 0.195 + 0.015 - 0.05 - 0.02 = 0.14
```

**结果：** 0.14（较差）

---

## 评分区间解释

| 总分区间 | 等级 | 说明 |
|---------|------|------|
| 0.80 - 1.00 | 优秀 | 最优供应商，优先选择 |
| 0.60 - 0.79 | 良好 | 可接受供应商 |
| 0.40 - 0.59 | 一般 | 需要权衡 |
| 0.20 - 0.39 | 较差 | 不推荐 |
| 0.00 - 0.19 | 很差 | 应拒绝 |

---

## 配置参数汇总

```python
class PricingConfig:
    # 供应商评分权重
    SUPPLIER_PRICE_WEIGHT = Decimal("0.45")              # 价格权重 45%
    SUPPLIER_CONFIDENCE_WEIGHT = Decimal("0.30")         # 置信度权重 30%
    SUPPLIER_MOQ_WEIGHT = Decimal("0.15")                # MOQ 权重 15%

    # 价格差距配置
    SUPPLIER_PRICE_GAP_TOLERANCE = Decimal("0.20")       # 20% 容忍度
    SUPPLIER_PRICE_GAP_PENALTY_WEIGHT = Decimal("0.20")  # 惩罚权重

    # 身份加分
    SUPPLIER_FACTORY_BONUS = Decimal("0.06")             # 工厂 +0.06
    SUPPLIER_SUPER_FACTORY_BONUS = Decimal("0.04")       # 超级工厂 +0.04
    SUPPLIER_VERIFIED_BONUS = Decimal("0.04")            # 认证 +0.04

    # 惩罚项
    SUPPLIER_ALTERNATIVE_SKU_PENALTY = Decimal("0.05")   # 替代 SKU -0.05
```

---

## 优化建议

详见 `docs/architecture/product-selection-optimization-v1.md:1`

**潜在改进：**
1. 引入历史表现先验（FeedbackAggregator）
2. 添加 1688 跨境信号（热卖榜、复购率、发货周期）
3. 动态调整权重（基于品类特性）
4. 引入供应商竞争集评分

---

**文档版本：** v1.0
**最后更新：** 2026-03-26
**状态：** 生产就绪
