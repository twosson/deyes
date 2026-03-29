# 推荐服务 (Recommendation Service)

> 最后更新: 2026-03-29
> 版本: v3.0（需求上下文集成）
> 定位: 内部决策服务（已降级，不再作为主产品形态）

## 概述

推荐服务为候选产品提供智能推荐分数，作为内部决策引擎驱动候选排序与自动上架判断。

**核心功能：**
1. **综合评分** - 基于优先级、利润率、风险、供应商质量、需求上下文的 0-100 分制评分
2. **推荐理由** - 自动生成人类可读的推荐理由（含需求发现来源说明）
3. **推荐等级** - HIGH/MEDIUM/LOW 三级分类
4. **可解释性** - 透明的分数构成和权重说明

## 评分算法

### 推荐分数公式

```
recommendation_score (0-100) =
    priority_score * 40 +           # 优先级 40%
    margin_score * 30 +             # 利润率 30%
    risk_score_inverse * 20 +       # 风险反向 20%
    supplier_quality * 10 +         # 供应商质量 10%
    demand_adjustment               # 需求上下文调整 (-6 至 +3)
```

### 各分量说明

#### 1. 优先级评分 (40%)

来源：`CandidateProduct.normalized_attributes["priority_score"]`

已包含：
- **季节性加权** (40%) - 即将到来的节假日需求
- **销量** (30%) - 产品销量验证
- **评分** (20%) - 产品质量评分
- **竞争密度** (10%) - 市场竞争程度

计算：`priority_score (0-1) * 40`

#### 2. 利润率评分 (30%)

来源：`PricingAssessment.margin_percentage`

计算：`min(margin_percentage / 100, 1.0) * 30`

示例：
- 45% 利润率 → 13.5 分
- 35% 利润率 → 10.5 分
- 20% 利润率 → 6.0 分

#### 3. 风险反向评分 (20%)

来源：`RiskAssessment.score`

计算：`(100 - risk_score) / 100 * 20`

说明：风险越低，分数越高

示例：
- 风险 10 分 → 18.0 分
- 风险 40 分 → 12.0 分
- 风险 80 分 → 4.0 分

#### 4. 供应商质量评分 (10%)

来源：`SupplierMatch.confidence_score` (取最高值)

计算：`confidence_score (0-1) * 10`

示例：
- 95% 置信度 → 9.5 分
- 70% 置信度 → 7.0 分
- 30% 置信度 → 3.0 分

#### 5. 需求上下文调整（v3.0 新增）

来源：`CandidateProduct.demand_discovery_metadata`

| discovery_mode | adjustment |
|----------------|------------|
| user | +3.0 |
| generated | +1.0 |
| fallback | -4.0 |
| none | -6.0 |

附加调整：
- `degraded=True`: -2.0
- `fallback_used=True` (非 fallback 模式): -1.0

## 推荐等级

### 等级划分

| 等级 | 分数范围 | 说明 |
|------|---------|------|
| **HIGH** | ≥ 75 | 强烈推荐，优先上架 |
| **MEDIUM** | 60-74 | 可以考虑，需评估 |
| **LOW** | < 60 | 不建议上架 |

### 典型案例

#### HIGH 级别产品 (80 分)
```
- 优先级评分: 36.0 (0.9 * 40)
- 利润率评分: 13.5 (45% * 30)
- 风险评分: 18.0 ((100-10)/100 * 20)
- 供应商评分: 9.5 (0.95 * 10)
- 需求上下文: +3.0 (user 模式)
总分: 80.0
```

#### MEDIUM 级别产品 (61 分)
```
- 优先级评分: 28.0 (0.7 * 40)
- 利润率评分: 10.5 (35% * 30)
- 风险评分: 14.0 ((100-30)/100 * 20)
- 供应商评分: 8.0 (0.8 * 10)
- 需求上下文: +1.0 (generated 模式)
总分: 61.5
```

#### LOW 级别产品 (24 分)
```
- 优先级评分: 12.0 (0.3 * 40)
- 利润率评分: 6.0 (20% * 30)
- 风险评分: 8.0 ((100-60)/100 * 20)
- 供应商评分: 6.0 (0.6 * 10)
- 需求上下文: -8.0 (fallback 模式 -4, degraded -2, fallback_used -1, lower clamp applied in implementation if needed)
总分: 24.0
```

## 推荐理由规则

### 利润率理由

| 条件 | 理由 |
|------|------|
| 利润率 ≥ 40% | "高利润率产品（XX%）" |
| 利润率 ≥ 35% | "良好利润率（XX%）" |
| 边际利润 | "边际利润率（XX%），需优化定价" |
| 不盈利 | "利润率偏低（XX%），不建议上架" |

### 季节性理由

| 条件 | 理由 |
|------|------|
| 季节性加权 ≥ 1.3 | "即将到来的节假日，需求旺盛（+XX%）" |
| 季节性加权 ≥ 1.1 | "季节性需求增长（+XX%）" |

### 竞争密度理由

| 条件 | 理由 |
|------|------|
| LOW | "低竞争蓝海市场" |
| MEDIUM | "中等竞争市场" |
| HIGH | "高竞争红海市场，需谨慎评估" |

### 需求发现理由（v3.0 新增）

| 条件 | 理由 |
|------|------|
| user | "需求关键词已人工确认" |
| generated | "基于生成关键词完成需求发现" |
| fallback | "使用回退关键词发现候选，建议谨慎验证" |
| none | "缺少有效需求关键词支撑，建议人工复核" |
| degraded=True | "需求发现过程存在降级，建议补充验证" |
| fallback_used=True | "需求发现使用了部分回退信号" |

### 风险理由

| 条件 | 理由 |
|------|------|
| PASS | "合规风险低，可安全上架" |
| REVIEW | "需人工审核风险" |
| REJECT | "高风险产品，不建议上架" |

### 销量理由

| 条件 | 理由 |
|------|------|
| 销量 ≥ 5000 | "高销量验证（XX单）" |
| 销量 ≥ 1000 | "中等销量（XX单）" |
| 销量 ≥ 100 | "有一定销量基础（XX单）" |

### 评分理由

| 条件 | 理由 |
|------|------|
| 评分 ≥ 4.5 | "高评分产品（X.X星）" |
| 评分 ≥ 4.0 | "良好评分（X.X星）" |
| 评分 < 3.5 | "评分偏低（X.X星），需注意质量" |

## 服务实现

### RecommendationService

**位置：** `backend/app/services/recommendation_service.py:39`

**核心方法：**
```python
class RecommendationService:
    def calculate_recommendation_score(
        self,
        priority_score: Optional[float],
        margin_percentage: Optional[Decimal],
        risk_score: Optional[int],
        supplier_confidence: Optional[Decimal],
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
        fallback_used: bool = False,
    ) -> tuple[float, dict]:
        """计算推荐分数（0-100），包含需求上下文调整"""

    def generate_recommendation_reasons(
        self,
        margin_percentage: Optional[Decimal],
        seasonal_boost: Optional[float],
        competition_density: Optional[str],
        risk_decision: Optional[RiskDecision],
        sales_count: Optional[int],
        rating: Optional[Decimal],
        profitability_decision: Optional[ProfitabilityDecision],
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
        fallback_used: bool = False,
    ) -> list[str]:
        """生成推荐理由，包含需求发现来源说明"""

    def get_recommendation_level(self, score: float) -> str:
        """判断推荐等级：HIGH (≥75), MEDIUM (60-74), LOW (<60)"""

    def explain_score_breakdown(self, score_breakdown: dict) -> dict:
        """解释分数构成"""
```

### API 调用入口

**位置：** `backend/app/api/routes_recommendations.py`

所有推荐 API 端点均从 `CandidateProduct.demand_discovery_metadata` 提取需求上下文，并传入 RecommendationService：

```python
demand_metadata = candidate.demand_discovery_metadata or {}

score, breakdown = recommendation_service.calculate_recommendation_score(
    priority_score=normalized_attrs.get("priority_score"),
    margin_percentage=pricing.margin_percentage if pricing else None,
    risk_score=risk.score if risk else None,
    supplier_confidence=best_supplier.confidence_score if best_supplier else None,
    discovery_mode=demand_metadata.get("discovery_mode"),
    degraded=bool(demand_metadata.get("degraded", False)),
    fallback_used=bool(demand_metadata.get("fallback_used", False)),
)

reasons = recommendation_service.generate_recommendation_reasons(
    margin_percentage=pricing.margin_percentage if pricing else None,
    seasonal_boost=normalized_attrs.get("seasonal_boost"),
    competition_density=normalized_attrs.get("competition_density"),
    risk_decision=risk.decision if risk else None,
    sales_count=candidate.sales_count,
    rating=candidate.rating,
    profitability_decision=pricing.profitability_decision if pricing else None,
    discovery_mode=demand_metadata.get("discovery_mode"),
    degraded=bool(demand_metadata.get("degraded", False)),
    fallback_used=bool(demand_metadata.get("fallback_used", False)),
)
```

## 数据依赖

### 输入字段

推荐服务依赖以下数据：

1. **CandidateProduct** - 候选产品基础信息
   - `normalized_attributes["priority_score"]` - 优先级评分
   - `normalized_attributes["seasonal_boost"]` - 季节性加权
   - `normalized_attributes["competition_density"]` - 竞争密度
   - `demand_discovery_metadata["discovery_mode"]` - 需求发现模式
   - `demand_discovery_metadata["degraded"]` - 是否降级
   - `demand_discovery_metadata["fallback_used"]` - 是否使用回退
   - `sales_count` - 销量
   - `rating` - 评分

2. **PricingAssessment** - 定价评估
   - `margin_percentage` - 利润率
   - `profitability_decision` - 盈利性决策

3. **RiskAssessment** - 风险评估
   - `score` - 风险评分
   - `decision` - 风险决策

4. **SupplierMatch** - 供应商匹配
   - `confidence_score` - 置信度评分

## 测试

### 单元测试

**推荐服务测试：**
- `backend/tests/test_recommendation_service.py`
  - 推荐分数计算测试（高/中/低质量产品）
  - 推荐理由生成测试（含需求发现理由）
  - 需求上下文调整测试
  - 推荐等级判断测试
  - 分数分解解释测试

**风控规则测试：**
- `backend/tests/test_risk_rules.py`（合规规则基线）
- `backend/tests/test_competition_risk.py`（竞争密度 + 需求发现质量规则）

## 更新日志

### v3.0 (2026-03-29)

**核心变更：**
- ✅ 评分公式新增 `demand_adjustment` 分量（-6 至 +3）
- ✅ `calculate_recommendation_score()` 新增 `discovery_mode`、`degraded`、`fallback_used` 参数
- ✅ `generate_recommendation_reasons()` 新增需求发现相关理由
- ✅ 所有推荐 API 端点传入需求上下文
- ✅ 推荐理由包含需求发现来源与降级说明

**定位变更：**
- 推荐服务降级为内部决策引擎
- 推荐 API 保留用于审批工作台与监控面板

### v2.0 (2026-03-27)

**新增功能：**
- ✅ 用户反馈机制（接受/拒绝/延后）
- ✅ 时间趋势分析 API
- ✅ 平台对比分析 API
- ✅ 反馈统计 API

### v1.0 (2026-03-20)

**初始功能：**
- ✅ 推荐评分算法
- ✅ 推荐理由生成
- ✅ 推荐等级判断
- ✅ 推荐列表/详情 API

---

**最后更新**: 2026-03-29
**服务版本**: v3.0
**文档状态**: 已同步最新代码
