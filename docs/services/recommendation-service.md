# 推荐服务 (Recommendation Service)

> 最后更新: 2026-03-27
> 版本: v2.0（新增用户反馈与数据分析）

## 概述

推荐服务为候选产品提供智能推荐，基于多维度评分帮助用户快速识别最有潜力的产品。

### 核心功能

1. **综合评分** - 基于优先级、利润率、风险、供应商质量的 0-100 分制评分
2. **推荐理由** - 自动生成人类可读的推荐理由
3. **推荐等级** - HIGH/MEDIUM/LOW 三级分类
4. **可解释性** - 透明的分数构成和权重说明
5. **用户反馈** - 接受/拒绝/延后反馈机制（2026-03-27 新增）
6. **数据分析** - 时间趋势、平台对比、反馈统计（2026-03-27 新增）

## 评分算法

### 推荐分数公式

```
recommendation_score (0-100) =
    priority_score * 40 +           # 优先级 40%
    margin_score * 30 +             # 利润率 30%
    risk_score_inverse * 20 +       # 风险反向 20%
    supplier_quality * 10           # 供应商质量 10%
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

## 推荐等级

### 等级划分

| 等级 | 分数范围 | 说明 |
|------|---------|------|
| **HIGH** | ≥ 75 | 强烈推荐，优先上架 |
| **MEDIUM** | 60-74 | 可以考虑，���评估 |
| **LOW** | < 60 | 不建议上架 |

### 典型案例

#### HIGH 级别产品 (77 分)
```
- 优先级评分: 36.0 (0.9 * 40)
- 利润率评分: 13.5 (45% * 30)
- 风险评分: 18.0 ((100-10)/100 * 20)
- 供应商评分: 9.5 (0.95 * 10)
总分: 77.0
```

#### MEDIUM 级别产品 (65 分)
```
- 优先级评分: 28.0 (0.7 * 40)
- 利润率评分: 10.5 (35% * 30)
- 风险评分: 14.0 ((100-30)/100 * 20)
- 供应商评分: 8.0 (0.8 * 10)
总分: 60.5
```

#### LOW 级别产品 (32 分)
```
- 优先级评分: 12.0 (0.3 * 40)
- 利润率评分: 6.0 (20% * 30)
- 风险评分: 8.0 ((100-60)/100 * 20)
- 供应商评分: 6.0 (0.6 * 10)
总分: 32.0
```

## 推荐理由规则

### 利润���理由

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

## API 使用示例

### 1. 获取推荐列表

```bash
GET /api/v1/recommendations?limit=20&min_score=60
```

**参数：**
- `limit` (可选) - 返回数量，默认 20，范围 1-100
- `category` (可选) - 筛选品类
- `min_score` (可选) - 最低推荐分数，默认 60
- `risk_level` (可选) - 筛选风险等级 (PASS/REVIEW/REJECT)

**响应示例：**
```json
{
  "items": [
    {
      "candidate_id": "uuid",
      "title": "Product Title",
      "category": "electronics",
      "source_platform": "temu",
      "platform_price": 50.0,
      "recommendation_score": 77.0,
      "recommendation_level": "HIGH",
      "reasons": [
        "高利润率产品（45.0%）",
        "即将到来的节假日，需求旺盛（+50%）",
        "低竞争蓝海市场",
        "合规风险低，可安全上架",
        "高销量验证（5000单）",
        "高评分产品（4.8星）"
      ],
      "score_breakdown": {
        "priority_component": 36.0,
        "margin_component": 13.5,
        "risk_component": 18.0,
        "supplier_component": 9.5,
        "total_score": 77.0
      },
      "priority_score": 0.9,
      "margin_percentage": 45.0,
      "risk_decision": "PASS",
      "risk_score": 10,
      "created_at": "2026-03-27T10:00:00Z"
    }
  ],
  "count": 1,
  "filters": {
    "category": null,
    "min_score": 60.0,
    "risk_level": null
  }
}
```

### 2. 获取单个候选推荐详情

```bash
GET /api/v1/candidates/{candidate_id}/recommendation
```

**响应示例：**
```json
{
  "candidate_id": "uuid",
  "title": "Product Title",
  "category": "electronics",
  "source_platform": "temu",
  "source_url": "https://...",
  "platform_price": 50.0,
  "sales_count": 5000,
  "rating": 4.8,
  "recommendation": {
    "score": 77.0,
    "level": "HIGH",
    "reasons": [
      "高利润率产品（45.0%）",
      "即将到来的节假日，需求旺盛（+50%）",
      "低竞争蓝海市场",
      "合规风险低，可安全上架",
      "高销量验证（5000单）",
      "高评分产品（4.8星）"
    ],
    "score_breakdown": {
      "total_score": 77.0,
      "components": [
        {
          "name": "priority_score",
          "value": 36.0,
          "weight": "40%",
          "description": "综合优先级（季节性、销量、评分、竞争密度）"
        },
        {
          "name": "margin_score",
          "value": 13.5,
          "weight": "30%",
          "description": "利润率评分"
        },
        {
          "name": "risk_score",
          "value": 18.0,
          "weight": "20%",
          "description": "风险反向评分（风险越低分数越高）"
        },
        {
          "name": "supplier_quality",
          "value": 9.5,
          "weight": "10%",
          "description": "供应商质量评分"
        }
      ]
    }
  },
  "pricing_summary": {
    "margin_percentage": 45.0,
    "profitability_decision": "profitable",
    "recommended_price": 55.0
  },
  "risk_summary": {
    "score": 10,
    "decision": "pass",
    "rule_hits": []
  },
  "best_supplier": {
    "supplier_name": "Supplier Name",
    "supplier_price": 20.0,
    "confidence_score": 0.95,
    "moq": 10
  }
}
```

### 3. 提交用户反馈（2026-03-27 新增）

```bash
POST /api/v1/recommendations/{candidate_id}/feedback
```

**请求体：**
```json
{
  "action": "accepted",  // accepted, rejected, deferred
  "comment": "利润率很好，准备上架"  // 可选
}
```

**响应示例：**
```json
{
  "id": "uuid",
  "candidate_product_id": "uuid",
  "action": "accepted",
  "comment": "利润率很好，准备上架",
  "metadata": {
    "recommendation_score": 77.0,
    "recommendation_level": "HIGH",
    "source_platform": "temu"
  },
  "created_at": "2026-03-27T10:00:00Z"
}
```

### 4. 获取推荐时间趋势（2026-03-27 新增）

```bash
GET /api/v1/recommendations/stats/trends?period=day&days=30&min_score=60
```

**参数：**
- `period` (可选) - 聚合周期：day/week/month，默认 day
- `days` (可选) - 回溯天数，默认 30，范围 1-365
- `min_score` (可选) - 最低推荐分数，默认 60

**响应示例：**
```json
{
  "period": "day",
  "days": 30,
  "min_score": 60.0,
  "data": [
    {
      "date": "2026-03-27",
      "count": 15,
      "average_score": 72.5
    },
    {
      "date": "2026-03-26",
      "count": 12,
      "average_score": 68.3
    }
  ]
}
```

### 5. 获取平台对比分析（2026-03-27 新增）

```bash
GET /api/v1/recommendations/stats/by-platform?min_score=60
```

**参数：**
- `min_score` (可选) - 最低推荐分数，默认 60

**响应示例：**
```json
{
  "min_score": 60.0,
  "data": [
    {
      "platform": "temu",
      "count": 45,
      "average_score": 72.5,
      "high_quality_count": 20,
      "high_quality_percentage": 44.44
    },
    {
      "platform": "amazon",
      "count": 30,
      "average_score": 68.3,
      "high_quality_count": 10,
      "high_quality_percentage": 33.33
    }
  ]
}
```

### 6. 获取用户反馈统计（2026-03-27 新增）

```bash
GET /api/v1/recommendations/stats/feedback?days=30
```

**参数：**
- `days` (可选) - 回溯天数，默认 30，范围 1-365

**响应示例：**
```json
{
  "days": 30,
  "total_feedback": 50,
  "data": [
    {
      "action": "accepted",
      "count": 30
    },
    {
      "action": "rejected",
      "count": 15
    },
    {
      "action": "deferred",
      "count": 5
    }
  ]
}
```

### 7. 获取推荐统计概览

```bash
GET /api/v1/recommendations/stats/overview?min_score=60
```

**参数：**
- `min_score` (可选) - 最低推荐分数，默认 60

**响应示例：**
```json
{
  "total_recommendations": 100,
  "average_score": 70.5,
  "high_quality_count": 35,
  "high_quality_percentage": 35.0,
  "by_level": {
    "HIGH": 35,
    "MEDIUM": 45,
    "LOW": 20
  },
  "by_category": {
    "electronics": 40,
    "home": 30,
    "fashion": 30
  }
}
```

---

## 前端集成

### 推荐页面组件

**位置：** `frontend/src/pages/recommendations/RecommendationsPage.vue`

**功能模块：**

1. **推荐列表**（表格）
   - 推荐等级、分数、产品标题、品类、平台、价格
   - 点击查看详情

2. **推荐详情**（抽屉）
   - 推荐分数分解
   - 推荐理由
   - 定价摘要
   - 风险摘要
   - 最佳供应商
   - **反馈按钮**（接受/拒绝/延后）- line 593

3. **推荐分析看板**（标签页）
   - **时间趋势图表** - line 146
   - **平台对比图表** - line 186
   - **用户反馈统计图表** - line 227

### TanStack Query Hooks

**推荐查询：**
```typescript
import { useRecommendationsQuery } from '@/queries/useRecommendationsQuery'

const filters = ref({
  min_score: 60,
  category: undefined,
  risk_level: undefined,
  limit: 20,
})

const recommendationsQuery = useRecommendationsQuery(filters)
```

**反馈提交：**
```typescript
import { useCreateFeedbackMutation } from '@/queries/useFeedbackMutation'

const createFeedbackMutation = useCreateFeedbackMutation()

async function handleFeedback(action: 'accepted' | 'rejected' | 'deferred', comment?: string) {
  await createFeedbackMutation.mutateAsync({
    candidateId: selectedCandidateId.value,
    payload: { action, comment },
  })
  message.success('反馈已提交')
}
```

**分析查询：**
```typescript
import {
  useRecommendationTrendsQuery,
  useRecommendationsByPlatformQuery,
  useRecommendationFeedbackStatsQuery,
} from '@/queries/useRecommendationsQuery'

const analyticsParams = ref({
  period: 'day' as 'day' | 'week' | 'month',
  days: 30,
  min_score: 60,
})

const trendsQuery = useRecommendationTrendsQuery(analyticsParams)
const platformQuery = useRecommendationsByPlatformQuery(
  computed(() => ({ min_score: analyticsParams.value.min_score })),
)
const feedbackQuery = useRecommendationFeedbackStatsQuery(
  computed(() => ({ days: analyticsParams.value.days })),
)
```

---

## 数据库模型

### RecommendationFeedback 表（2026-03-27 新增）

**位置：** `backend/app/db/models.py:271`

**字段：**
```python
class RecommendationFeedback(Base, TimestampMixin):
    """User feedback on recommendation decisions."""

    id: UUID
    candidate_product_id: UUID  # 外键到 candidate_products
    action: FeedbackAction  # accepted, rejected, deferred
    comment: Optional[str]  # 可选文本评论
    metadata_: Optional[dict]  # 推荐分数、等级、平台等元数据
    created_at: datetime
    updated_at: datetime
```

**索引：**
- `candidate_product_id` - 查询特定候选的反馈
- `action` - 按反馈类型聚合统计

**关联：**
- `candidate: CandidateProduct` - 反向关联到候选产品

---

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
    ) -> tuple[float, dict]:
        """计算推荐分数（0-100）"""

    def generate_recommendation_reasons(
        self,
        margin_percentage: Optional[Decimal],
        seasonal_boost: Optional[float],
        competition_density: Optional[str],
        risk_decision: Optional[RiskDecision],
        sales_count: Optional[int],
        rating: Optional[Decimal],
        profitability_decision: Optional[ProfitabilityDecision],
    ) -> list[str]:
        """生成推荐理由"""

    def get_recommendation_level(self, score: float) -> str:
        """判断推荐等级"""

    def explain_score_breakdown(self, score_breakdown: dict) -> dict:
        """解释分数构成"""
```

### RecommendationFeedbackService（2026-03-27 新增）

**位置：** `backend/app/services/recommendation_feedback_service.py:9`

**核心方法：**
```python
class RecommendationFeedbackService:
    async def create_feedback(
        self,
        db: AsyncSession,
        candidate: CandidateProduct,
        action: str,
        comment: str | None = None,
        metadata: dict | None = None,
    ) -> RecommendationFeedback:
        """创建反馈并记录 RunEvent 审计日志"""
```

---

## 测试

### 单元测试

**推荐服务测试：**
- `backend/tests/test_recommendation_service.py`

**反馈服务测试：**
- `backend/tests/test_recommendation_feedback.py`（2026-03-27 新增）

**需求验证测试：**
- `backend/tests/test_demand_validator.py`

### 前端测试

**推荐查询测试：**
- `frontend/src/queries/useRecommendationsQuery.spec.ts`（2026-03-27 新增）

---

## 更新日志

### v2.0 (2026-03-27)

**新增功能：**
- ✅ 用户反馈机制（接受/拒绝/延后）
- ✅ 反馈 API 端点（POST /recommendations/{id}/feedback）
- ✅ 时间趋势分析 API（GET /recommendations/stats/trends）
- ✅ 平台对比分析 API（GET /recommendations/stats/by-platform）
- ✅ 反馈统计 API（GET /recommendations/stats/feedback）
- ✅ 前端反馈按钮 UI
- ✅ 前端分析看板（ECharts 图表）
- ✅ RecommendationFeedback 数据模型
- ✅ RecommendationFeedbackService 服务层
- ✅ RunEvent 审计日志集成

**代码变更：**
- 19 个文件修改/新增
- +1,012 行代码

### v1.0 (2026-03-20)

**初始功能：**
- ✅ 推荐评分算法
- ✅ 推荐理由生成
- ✅ 推荐等级判断
- ✅ 推荐列表 API
- ✅ 推荐详情 API
- ✅ 推荐概览 API

---

**文档维护**: 本文档应在推荐服务功能更新后同步更新
          "weight": "30%",
          "description": "利润率评分"
        },
        {
          "name": "risk_score_inverse",
          "value": 18.0,
          "weight": "20%",
          "description": "风险反向评分（低风险=高分）"
        },
        {
          "name": "supplier_quality",
          "value": 9.5,
          "weight": "10%",
          "description": "供应商质量评分"
        }
      ]
    }
  },
  "pricing_summary": {
    "margin_percentage": 45.0,
    "profitability_decision": "PROFITABLE",
    "recommended_price": 55.0
  },
  "risk_summary": {
    "score": 10,
    "decision": "PASS",
    "rule_hits": [...]
  },
  "best_supplier": {
    "supplier_name": "Supplier Name",
    "supplier_price": 25.0,
    "confidence_score": 0.95,
    "moq": 100
  },
  "normalized_attributes": {...},
  "created_at": "2026-03-27T10:00:00Z"
}
```

## 评分权重调整指南

### 当前权重配置

```python
# backend/app/services/recommendation_service.py

# 推荐分数权重
PRIORITY_WEIGHT = 40%      # 优先级（季节性、销量、评分、竞争）
MARGIN_WEIGHT = 30%        # 利润率
RISK_WEIGHT = 20%          # 风险反向
SUPPLIER_WEIGHT = 10%      # 供应商质量

# 推荐等级阈值
HIGH_THRESHOLD = 75.0      # HIGH 级别
MEDIUM_THRESHOLD = 60.0    # MEDIUM 级别
```

### 调整场景

#### 场景 1：更重视利润率

如果希望更重视利润率，可以调整权重：

```python
PRIORITY_WEIGHT = 35%      # 降低 5%
MARGIN_WEIGHT = 35%        # 提高 5%
RISK_WEIGHT = 20%          # 保持
SUPPLIER_WEIGHT = 10%      # 保持
```

#### 场景 2：更重视风险控制

如果希望更重视风险控制：

```python
PRIORITY_WEIGHT = 35%      # 降低 5%
MARGIN_WEIGHT = 25%        # 降低 5%
RISK_WEIGHT = 30%          # 提高 10%
SUPPLIER_WEIGHT = 10%      # 保持
```

#### 场景 3：调整推荐等级阈值

如果希望更严格的推荐标准：

```python
HIGH_THRESHOLD = 80.0      # 提高到 80
MEDIUM_THRESHOLD = 65.0    # 提高到 65
```

### 权重调整步骤

1. **修改服务代码**
   ```bash
   vim backend/app/services/recommendation_service.py
   ```

2. **更新测试用例**
   ```bash
   vim backend/tests/test_recommendation_service.py
   ```

3. **运行测试验证**
   ```bash
   cd backend
   pytest tests/test_recommendation_service.py -v
   ```

4. **更新文档**
   ```bash
   vim docs/services/recommendation-service.md
   ```

## 与现有系统集成

### 数据依赖

推荐服务依赖以下数据：

1. **CandidateProduct** - 候选产品基础信息
   - `normalized_attributes["priority_score"]` - 优先级评分
   - `normalized_attributes["seasonal_boost"]` - 季节性加权
   - `normalized_attributes["competition_density"]` - 竞争密度
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

### 工作流集成

推荐服务可以集成到以下工作流：

1. **选品流程** - 在 ProductSelectorAgent 完成后调用
2. **定价流程** - 在 PricingAnalystAgent 完成后调用
3. **风控流程** - 在 RiskControllerAgent 完成后调用
4. **人工审核** - 为审核人员提供推荐参考

### 前端集成

前端可以使用推荐 API 实现：

1. **推荐列表页** - 展示 TOP 推荐产品
2. **产品详情页** - 展示推荐分数和理由
3. **筛选功能** - 按品类、风险等级筛选
4. **排序功能** - 按推荐分数排序

## 性能考虑

### 计算复杂度

- **推荐分数计算** - O(1)，纯数学计算
- **推荐理由生成** - O(1)，规则匹配
- **列表查询** - O(n)，需遍历所有候选

### 优化建议

1. **缓存推荐结果** - 如果候选数据不频繁变化，可以缓存推荐结果
2. **异步计算** - 在后台定时计算推荐分数，存储到数据库
3. **分页查询** - 使用 `limit` 参数限制返回数量

### 扩展性

当候选产品数量增长时：

1. **数据库索引** - 为 `priority_score`、`margin_percentage` 等字段添加索引
2. **物化视图** - 创建推荐分数的物化视图
3. **搜索引擎** - 使用 Elasticsearch 等搜索引擎加速查询

## 监控和调优

### 关键指标

1. **推荐准确率** - 推荐产品的实际上架率
2. **推荐覆盖率** - HIGH/MEDIUM/LOW 级别的分布
3. **API 响应时间** - 推荐 API 的响应时间
4. **用户反馈** - 用户对推荐结果的反馈

### 调优方向

1. **权重调整** - 根据实际效果调整各分量权重
2. **阈值调整** - 根据业务需求调整推荐等级阈值
3. **理由优化** - 根据用户反馈优化推荐理由文案

## 常见问题

### Q1: 为什么我的产品推荐分数很低？

A: 检查以下维度：
- 优先级评分是否偏低（季节性、销量、评分、竞争）
- 利润率是否低于 35%
- 风险评分是否偏高
- 供应商置信度是否偏低

### Q2: 如何提高推荐分数？

A: 可以从以下方面优化：
- 选择季节性需求旺盛的产品
- 提高利润率（优化供应商价格或提高售价）
- 降低风险（避免品牌侵权、选择低竞争市场）
- 选择高置信度的供应商

### Q3: 推荐等级 MEDIUM 的产品是否值得上架？

A: 需要综合评估：
- 查看推荐理由，了解优势和劣势
- 查看分数构成，找出薄弱环节
- 考虑优化空间（如提高利润率、降低风险）

### Q4: 如何批量获取推荐结果？

A: 使用列表 API：
```bash
GET /api/v1/recommendations?limit=100&min_score=0
```

### Q5: 推荐分数会实时更新吗？

A: 推荐分数基于候选产品的当前数据实时计算，当以下数据变化时，推荐分数会自动更新：
- 优先级评分（季节性变化）
- 利润率（定价调整）
- 风险评分（风控规则变化）
- 供应商置信度（供应商匹配更新）

---

**最后更新**: 2026-03-27
**服务版本**: v1.0
**文档状态**: 生产就绪
