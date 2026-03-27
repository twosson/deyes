"""Product priority scoring service."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
import math


@dataclass
class ProductScoreInput:
    """优先级评分输入."""
    title: str
    sales_count: Optional[int]
    rating: Optional[Decimal]
    seasonal_boost: float
    competition_density: str  # "low", "medium", "high", "unknown"


@dataclass
class ProductScoreResult:
    """优先级评分结果."""
    total_score: float
    seasonal_component: float
    sales_component: float
    rating_component: float
    competition_component: float


class ProductScoringService:
    """产品优先级评分服务."""

    # 权重
    SEASONAL_WEIGHT = 0.4
    SALES_WEIGHT = 0.3
    RATING_WEIGHT = 0.2
    COMPETITION_WEIGHT = 0.1

    # 竞争密度分数
    COMPETITION_SCORES = {
        "low": 1.0,
        "medium": 0.5,
        "high": 0.0,
        "unknown": 0.3,
    }

    def calculate_priority_score(self, input: ProductScoreInput) -> ProductScoreResult:
        """计算产品优先级分数.

        优先级分数组合:
        - seasonal_boost: 季节性事件加成 (1.0 - 2.0)
        - sales_count: 产品销量 (对数归一化)
        - rating: 产品评分 (0 - 5)
        - competition_density: 市场竞争 (反向)

        Returns:
            ProductScoreResult,总分 0-1 范围,包含各组件分数
        """
        # 1. 季节性加成 (权重: 40%)
        seasonal_component = (input.seasonal_boost - 1.0) * self.SEASONAL_WEIGHT

        # 2. 销量 (权重: 30%)
        sales_component = 0.0
        if input.sales_count and input.sales_count > 0:
            # 对数刻度: 1 → 0, 10 → 0.3, 100 → 0.6, 1000 → 0.9, 10000 → 1.0
            sales_normalized = min(1.0, math.log10(input.sales_count) / 4.0)
            sales_component = sales_normalized * self.SALES_WEIGHT

        # 3. 评分 (权重: 20%)
        rating_component = 0.0
        if input.rating and input.rating > 0:
            rating_normalized = float(input.rating) / 5.0
            rating_component = rating_normalized * self.RATING_WEIGHT

        # 4. 竞争密度 (权重: 10%, 反向)
        competition_score = self.COMPETITION_SCORES.get(input.competition_density, 0.3)
        competition_component = competition_score * self.COMPETITION_WEIGHT

        # 总分
        total_score = (
            seasonal_component +
            sales_component +
            rating_component +
            competition_component
        )

        return ProductScoreResult(
            total_score=total_score,
            seasonal_component=seasonal_component,
            sales_component=sales_component,
            rating_component=rating_component,
            competition_component=competition_component,
        )
