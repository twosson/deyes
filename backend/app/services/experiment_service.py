"""Experiment service for A/B testing content asset variants."""
from __future__ import annotations

from datetime import UTC, datetime, date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ExperimentStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import AssetPerformanceDaily, ContentAsset, Experiment, PlatformListing


class ExperimentService:
    """Service for managing A/B test experiments and winner selection."""

    SUPPORTED_METRICS = {"ctr", "orders", "revenue", "units_sold", "cvr"}

    def __init__(self):
        self.logger = get_logger(__name__)

    async def create_experiment(
        self,
        db: AsyncSession,
        *,
        candidate_product_id: UUID,
        name: str,
        metric_goal: str = "ctr",
        target_platform: TargetPlatform | None = None,
        region: str | None = None,
        notes: str | None = None,
        metadata: dict | None = None,
    ) -> Experiment:
        """Create a draft experiment for a candidate product."""
        self._validate_metric_goal(metric_goal)

        experiment = Experiment(
            id=uuid4(),
            candidate_product_id=candidate_product_id,
            name=name,
            status=ExperimentStatus.DRAFT,
            metric_goal=metric_goal,
            target_platform=target_platform,
            region=region,
            notes=notes,
            metadata_=metadata,
        )
        db.add(experiment)
        await db.flush()

        self.logger.info(
            "experiment_created",
            experiment_id=str(experiment.id),
            candidate_product_id=str(candidate_product_id),
            metric_goal=metric_goal,
        )
        return experiment

    async def activate_experiment(self, db: AsyncSession, *, experiment_id: UUID) -> Experiment:
        """Mark an experiment as active after validating it has variants."""
        experiment = await self._get_experiment_or_raise(db, experiment_id)
        variants = await self.get_experiment_variants(db, experiment_id=experiment_id)
        if len(variants) < 2:
            raise ValueError("Experiment requires at least two variant groups to activate")

        experiment.status = ExperimentStatus.ACTIVE
        await db.flush()

        self.logger.info(
            "experiment_activated",
            experiment_id=str(experiment.id),
            variant_count=len(variants),
        )
        return experiment

    async def get_experiment_variants(self, db: AsyncSession, *, experiment_id: UUID) -> list[dict]:
        """Return participating variant groups and their asset counts."""
        experiment = await self._get_experiment_or_raise(db, experiment_id)

        stmt = (
            select(
                ContentAsset.variant_group,
                func.count(ContentAsset.id).label("asset_count"),
            )
            .where(
                ContentAsset.candidate_product_id == experiment.candidate_product_id,
                ContentAsset.variant_group.is_not(None),
            )
            .group_by(ContentAsset.variant_group)
            .order_by(ContentAsset.variant_group.asc())
        )

        result = await db.execute(stmt)
        rows = result.all()
        return [
            {
                "variant_group": row.variant_group,
                "asset_count": int(row.asset_count),
            }
            for row in rows
        ]

    async def get_experiment_summary(
        self,
        db: AsyncSession,
        *,
        experiment_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict:
        """Aggregate experiment performance by variant group."""
        experiment = await self._get_experiment_or_raise(db, experiment_id)

        stmt = (
            select(
                ContentAsset.variant_group.label("variant_group"),
                func.coalesce(func.sum(AssetPerformanceDaily.impressions), 0).label("impressions"),
                func.coalesce(func.sum(AssetPerformanceDaily.clicks), 0).label("clicks"),
                func.coalesce(func.sum(AssetPerformanceDaily.orders), 0).label("orders"),
                func.coalesce(func.sum(AssetPerformanceDaily.units_sold), 0).label("units_sold"),
                func.coalesce(func.sum(AssetPerformanceDaily.revenue), 0).label("revenue"),
                func.coalesce(func.sum(AssetPerformanceDaily.usage_count), 0).label("usage_count"),
            )
            .join(ContentAsset, ContentAsset.id == AssetPerformanceDaily.asset_id)
            .join(PlatformListing, PlatformListing.id == AssetPerformanceDaily.listing_id)
            .where(
                ContentAsset.candidate_product_id == experiment.candidate_product_id,
                ContentAsset.variant_group.is_not(None),
            )
        )

        if experiment.target_platform is not None:
            stmt = stmt.where(PlatformListing.platform == experiment.target_platform)
        if experiment.region is not None:
            stmt = stmt.where(PlatformListing.region == experiment.region)
        if start_date is not None:
            stmt = stmt.where(AssetPerformanceDaily.metric_date >= start_date)
        if end_date is not None:
            stmt = stmt.where(AssetPerformanceDaily.metric_date <= end_date)

        stmt = stmt.group_by(ContentAsset.variant_group).order_by(ContentAsset.variant_group.asc())

        result = await db.execute(stmt)
        rows = result.all()

        variants = []
        for row in rows:
            impressions = int(row.impressions or 0)
            clicks = int(row.clicks or 0)
            orders = int(row.orders or 0)
            units_sold = int(row.units_sold or 0)
            usage_count = int(row.usage_count or 0)
            revenue = self._to_decimal(row.revenue)

            ctr = Decimal("0.0000")
            if impressions > 0:
                ctr = Decimal(clicks) / Decimal(impressions)

            cvr = Decimal("0.0000")
            if clicks > 0:
                cvr = Decimal(orders) / Decimal(clicks)

            variants.append(
                {
                    "variant_group": row.variant_group,
                    "impressions": impressions,
                    "clicks": clicks,
                    "orders": orders,
                    "units_sold": units_sold,
                    "revenue": revenue,
                    "usage_count": usage_count,
                    "ctr": ctr,
                    "cvr": cvr,
                }
            )

        winner = None
        if experiment.winner_variant_group:
            winner = experiment.winner_variant_group

        return {
            "experiment_id": str(experiment.id),
            "candidate_product_id": str(experiment.candidate_product_id),
            "status": experiment.status.value,
            "metric_goal": experiment.metric_goal,
            "winner_variant_group": winner,
            "variants": variants,
        }

    async def select_winner(
        self,
        db: AsyncSession,
        *,
        experiment_id: UUID,
        min_impressions: int = 100,
    ) -> str | None:
        """Select the best-performing variant and persist it on the experiment."""
        experiment = await self._get_experiment_or_raise(db, experiment_id)
        summary = await self.get_experiment_summary(db, experiment_id=experiment_id)
        variants = summary["variants"]

        eligible = [variant for variant in variants if variant["impressions"] >= min_impressions]
        if not eligible:
            self.logger.info(
                "experiment_winner_not_selected_insufficient_data",
                experiment_id=str(experiment.id),
                min_impressions=min_impressions,
            )
            return None

        metric_goal = experiment.metric_goal
        winner = max(eligible, key=lambda variant: self._variant_metric_value(variant, metric_goal))
        winner_variant_group = winner["variant_group"]

        experiment.winner_variant_group = winner_variant_group
        experiment.winner_selected_at = datetime.now(UTC)
        experiment.status = ExperimentStatus.COMPLETED
        await db.flush()

        self.logger.info(
            "experiment_winner_selected",
            experiment_id=str(experiment.id),
            metric_goal=metric_goal,
            winner_variant_group=winner_variant_group,
        )
        return winner_variant_group

    async def set_winner(
        self,
        db: AsyncSession,
        *,
        experiment_id: UUID,
        winner_variant_group: str,
    ) -> Experiment:
        """Manually set the winning variant group for an experiment."""
        experiment = await self._get_experiment_or_raise(db, experiment_id)
        variants = await self.get_experiment_variants(db, experiment_id=experiment_id)
        allowed_groups = {variant["variant_group"] for variant in variants}
        if winner_variant_group not in allowed_groups:
            raise ValueError(f"Variant group not found in experiment: {winner_variant_group}")

        experiment.winner_variant_group = winner_variant_group
        experiment.winner_selected_at = datetime.now(UTC)
        experiment.status = ExperimentStatus.COMPLETED
        await db.flush()

        self.logger.info(
            "experiment_winner_set_manually",
            experiment_id=str(experiment.id),
            winner_variant_group=winner_variant_group,
        )
        return experiment

    async def _get_experiment_or_raise(self, db: AsyncSession, experiment_id: UUID) -> Experiment:
        experiment = await db.get(Experiment, experiment_id)
        if experiment is None:
            raise ValueError(f"Experiment not found: {experiment_id}")
        return experiment

    def _validate_metric_goal(self, metric_goal: str) -> None:
        if metric_goal not in self.SUPPORTED_METRICS:
            raise ValueError(f"Unsupported metric_goal: {metric_goal}")

    def _variant_metric_value(self, variant: dict, metric_goal: str) -> Decimal:
        if metric_goal in {"ctr", "cvr"}:
            return variant[metric_goal]
        value = variant[metric_goal]
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _to_decimal(self, value) -> Decimal:
        if value is None:
            return Decimal("0.00")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))
