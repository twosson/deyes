"""Experiment API routes for A/B testing."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ExperimentStatus, TargetPlatform
from app.db.models import Experiment
from app.db.session import get_db
from app.services.experiment_service import ExperimentService

router = APIRouter()


# Request/Response Models
class CreateExperimentRequest(BaseModel):
    """Request model for creating an experiment."""

    candidate_product_id: UUID
    name: str = Field(..., min_length=1, max_length=200)
    metric_goal: str = Field(default="ctr", pattern="^(ctr|cvr|orders|revenue|units_sold|roas)$")
    target_platform: TargetPlatform | None = None
    region: str | None = Field(None, max_length=10)
    notes: str | None = None


class ExperimentResponse(BaseModel):
    """Response model for experiment."""

    id: str
    candidate_product_id: str
    name: str
    status: str
    target_platform: str | None
    region: str | None
    metric_goal: str
    winner_variant_group: str | None
    created_at: str
    updated_at: str


class ListExperimentsResponse(BaseModel):
    """Response model for listing experiments."""

    total: int
    experiments: list[ExperimentResponse]


class SetWinnerRequest(BaseModel):
    """Request model for manually setting winner."""

    variant_group: str


class PromoteWinnerResponse(BaseModel):
    """Response model for promote winner operation."""

    promoted_asset_id: str | None = None
    winner_variant_group: str
    promoted_listing_ids: list[str]
    skipped_listing_ids: list[str]
    updated_association_count: int


# Helper functions
def _experiment_to_response(experiment: Experiment) -> dict:
    """Convert Experiment model to response dict."""
    return {
        "id": str(experiment.id),
        "candidate_product_id": str(experiment.candidate_product_id),
        "name": experiment.name,
        "status": experiment.status.value,
        "target_platform": experiment.target_platform.value if experiment.target_platform else None,
        "region": experiment.region,
        "metric_goal": experiment.metric_goal,
        "winner_variant_group": experiment.winner_variant_group,
        "created_at": experiment.created_at.isoformat(),
        "updated_at": experiment.updated_at.isoformat(),
    }


# Routes
@router.post("/experiments", response_model=ExperimentResponse)
async def create_experiment(
    request: CreateExperimentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new experiment."""
    service = ExperimentService()

    try:
        experiment = await service.create_experiment(
            db,
            candidate_product_id=request.candidate_product_id,
            name=request.name,
            metric_goal=request.metric_goal,
            target_platform=request.target_platform,
            region=request.region,
            notes=request.notes,
        )
        await db.commit()
        return _experiment_to_response(experiment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/experiments", response_model=ListExperimentsResponse)
async def list_experiments(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List experiments with optional filtering."""
    stmt = select(Experiment).order_by(Experiment.created_at.desc())

    if status:
        try:
            status_enum = ExperimentStatus(status)
            stmt = stmt.where(Experiment.status == status_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    # Get total count
    count_stmt = select(Experiment)
    if status:
        count_stmt = count_stmt.where(Experiment.status == status_enum)
    count_result = await db.execute(count_stmt)
    total = len(count_result.scalars().all())

    # Get paginated results
    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    experiments = result.scalars().all()

    return {
        "total": total,
        "experiments": [_experiment_to_response(exp) for exp in experiments],
    }


@router.get("/experiments/{experiment_id}", response_model=ExperimentResponse)
async def get_experiment(
    experiment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get experiment details."""
    experiment = await db.get(Experiment, experiment_id)
    if not experiment:
        raise HTTPException(status_code=404, detail="Experiment not found")

    return _experiment_to_response(experiment)


@router.get("/experiments/{experiment_id}/summary")
async def get_experiment_summary(
    experiment_id: UUID,
    start_date: date | None = None,
    end_date: date | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get experiment performance summary by variant."""
    service = ExperimentService()

    try:
        summary = await service.get_experiment_summary(
            db,
            experiment_id=experiment_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Convert Decimal to float for JSON serialization
        for variant in summary["variants"]:
            variant["ctr"] = float(variant["ctr"]) * 100  # Convert to percentage
            variant["cvr"] = float(variant["cvr"]) * 100  # Convert to percentage
            variant["revenue"] = float(variant["revenue"])
            variant["avg_order_value"] = (
                float(variant["revenue"]) / variant["orders"] if variant["orders"] > 0 else 0.0
            )
            variant["asset_count"] = variant.pop("usage_count", 0)

        # Add experiment_status to response
        experiment = await db.get(Experiment, UUID(summary["experiment_id"]))
        summary["experiment_status"] = experiment.status.value if experiment else "unknown"

        return summary
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/experiments/{experiment_id}/activate", response_model=ExperimentResponse)
async def activate_experiment(
    experiment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Activate an experiment."""
    service = ExperimentService()

    try:
        experiment = await service.activate_experiment(db, experiment_id=experiment_id)
        await db.commit()
        return _experiment_to_response(experiment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/experiments/{experiment_id}/select-winner", response_model=ExperimentResponse)
async def select_winner(
    experiment_id: UUID,
    min_impressions: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """Automatically select the winning variant based on metric goal."""
    service = ExperimentService()

    try:
        winner = await service.select_winner(
            db,
            experiment_id=experiment_id,
            min_impressions=min_impressions,
        )
        await db.commit()

        if winner is None:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient data to select winner (min_impressions={min_impressions})",
            )

        experiment = await db.get(Experiment, experiment_id)
        return _experiment_to_response(experiment)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/experiments/{experiment_id}/set-winner", response_model=ExperimentResponse)
async def set_winner(
    experiment_id: UUID,
    request: SetWinnerRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually set the winning variant."""
    service = ExperimentService()

    try:
        experiment = await service.set_winner(
            db,
            experiment_id=experiment_id,
            winner_variant_group=request.variant_group,
        )
        await db.commit()
        return _experiment_to_response(experiment)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/experiments/{experiment_id}/promote", response_model=PromoteWinnerResponse)
async def promote_winner(
    experiment_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Promote the winning variant to main image for target listings."""
    service = ExperimentService()

    try:
        result = await service.promote_winner(db, experiment_id=experiment_id)
        await db.commit()

        # Get the first promoted asset ID if available
        promoted_asset_id = None
        if result["promoted_listing_ids"]:
            # This is a simplified response - in reality you might want to return
            # the actual asset ID that was promoted
            promoted_asset_id = result["promoted_listing_ids"][0]

        return {
            "promoted_asset_id": promoted_asset_id,
            "winner_variant_group": result["winner_variant_group"],
            "promoted_listing_ids": result["promoted_listing_ids"],
            "skipped_listing_ids": result["skipped_listing_ids"],
            "updated_association_count": result["updated_association_count"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
