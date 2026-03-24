"""Agent run API routes."""
from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.enums import AgentRunStatus, SourcePlatform, StrategyRunStatus, TriggerType
from app.core.logging import get_logger
from app.db.models import AgentRun, CandidateProduct, StrategyRun
from app.db.session import get_db
from app.schemas.strategy import (
    CreateStrategyRunRequest,
    StrategyRunResponse,
    StrategyRunStatusResponse,
)
from app.workers.tasks_agent_pipeline import start_discovery_pipeline

logger = get_logger(__name__)
router = APIRouter()
TOTAL_PIPELINE_STEPS = 4
settings = get_settings()


class StrategyRunListItem(BaseModel):
    """Strategy run summary for monitoring lists."""

    run_id: UUID
    status: str
    source_platform: str
    region: str | None = None
    category: str | None = None
    keywords: list[str] | None = None
    max_candidates: int
    current_step: str | None = None
    completed_steps: int
    total_steps: int
    candidates_discovered: int
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class ListStrategyRunsResponse(BaseModel):
    """Paginated strategy run summaries."""

    total: int
    runs: list[StrategyRunListItem]


class AgentRunStepResponse(BaseModel):
    """Detailed pipeline step execution record."""

    id: UUID
    step_name: str
    agent_name: str
    status: str
    attempt: int
    error_message: str | None = None
    started_at: str
    completed_at: str | None = None
    latency_ms: int | None = None


class ListAgentRunStepsResponse(BaseModel):
    """Detailed steps for a strategy run."""

    run_id: UUID
    steps: list[AgentRunStepResponse]


def _serialize_strategy_run_summary(
    strategy_run: StrategyRun,
    *,
    candidates_count: int,
    completed_steps: int,
    current_step: str | None,
) -> StrategyRunListItem:
    return StrategyRunListItem(
        run_id=strategy_run.id,
        status=strategy_run.status.value,
        source_platform=strategy_run.source_platform.value,
        region=strategy_run.region,
        category=strategy_run.category,
        keywords=strategy_run.keywords,
        max_candidates=strategy_run.max_candidates,
        current_step=current_step,
        completed_steps=completed_steps,
        total_steps=TOTAL_PIPELINE_STEPS,
        candidates_discovered=candidates_count,
        created_at=strategy_run.created_at.isoformat() if strategy_run.created_at else "",
        started_at=strategy_run.started_at.isoformat() if strategy_run.started_at else None,
        completed_at=strategy_run.completed_at.isoformat() if strategy_run.completed_at else None,
    )


async def _build_strategy_run_summary(
    strategy_run: StrategyRun,
    db: AsyncSession,
) -> StrategyRunListItem:
    candidates_count_result = await db.execute(
        select(func.count(CandidateProduct.id)).where(CandidateProduct.strategy_run_id == strategy_run.id)
    )
    candidates_count = candidates_count_result.scalar() or 0

    completed_steps_result = await db.execute(
        select(func.count(AgentRun.id)).where(
            AgentRun.strategy_run_id == strategy_run.id,
            AgentRun.status == AgentRunStatus.COMPLETED,
        )
    )
    completed_steps = completed_steps_result.scalar() or 0

    last_agent_run_result = await db.execute(
        select(AgentRun)
        .where(AgentRun.strategy_run_id == strategy_run.id)
        .order_by(AgentRun.started_at.desc())
        .limit(1)
    )
    last_agent_run = last_agent_run_result.scalar_one_or_none()

    return _serialize_strategy_run_summary(
        strategy_run,
        candidates_count=candidates_count,
        completed_steps=completed_steps,
        current_step=last_agent_run.step_name if last_agent_run else None,
    )


@router.post("/agent-runs", response_model=StrategyRunResponse)
async def create_agent_run(
    request: CreateStrategyRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new discovery run."""
    if (
        request.platform == SourcePlatform.ALIBABA_1688
        and settings.use_real_scrapers
        and not settings.tmapi_api_token
    ):
        raise HTTPException(
            status_code=503,
            detail="TMAPI API token is required for alibaba_1688 discovery. Configure TMAPI_API_TOKEN, or disable real scrapers.",
        )

    run_id = uuid4()
    strategy_run = StrategyRun(
        id=run_id,
        trigger_type=TriggerType.API,
        source_platform=request.platform,
        region=request.region,
        category=request.category,
        keywords=request.keywords,
        target_languages=request.target_languages,
        price_min=request.price_min,
        price_max=request.price_max,
        max_candidates=request.max_candidates,
        status=StrategyRunStatus.QUEUED,
    )
    db.add(strategy_run)
    await db.commit()
    await db.refresh(strategy_run)

    start_discovery_pipeline.delay(str(run_id))

    logger.info("agent_run_created", run_id=str(run_id))

    return StrategyRunResponse(
        run_id=strategy_run.id,
        status=strategy_run.status,
        created_at=strategy_run.created_at,
    )


@router.get("/agent-runs", response_model=ListStrategyRunsResponse)
async def list_agent_runs(
    status: StrategyRunStatus | None = Query(default=None, description="Filter by run status"),
    source_platform: SourcePlatform | None = Query(default=None, description="Filter by source platform"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List strategy runs for task monitoring."""
    query = select(StrategyRun)

    if status:
        query = query.where(StrategyRun.status == status)
    if source_platform:
        query = query.where(StrategyRun.source_platform == source_platform)

    query = query.order_by(StrategyRun.created_at.desc())

    total_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = total_result.scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    strategy_runs = list(result.scalars().all())

    run_ids = [strategy_run.id for strategy_run in strategy_runs]
    candidate_counts: dict[UUID, int] = {}
    completed_step_counts: dict[UUID, int] = {}
    latest_steps: dict[UUID, str | None] = {}

    if run_ids:
        candidate_counts_result = await db.execute(
            select(CandidateProduct.strategy_run_id, func.count(CandidateProduct.id))
            .where(CandidateProduct.strategy_run_id.in_(run_ids))
            .group_by(CandidateProduct.strategy_run_id)
        )
        candidate_counts = {run_id: count for run_id, count in candidate_counts_result.all()}

        completed_steps_result = await db.execute(
            select(AgentRun.strategy_run_id, func.count(AgentRun.id))
            .where(
                AgentRun.strategy_run_id.in_(run_ids),
                AgentRun.status == AgentRunStatus.COMPLETED,
            )
            .group_by(AgentRun.strategy_run_id)
        )
        completed_step_counts = {run_id: count for run_id, count in completed_steps_result.all()}

        latest_steps_result = await db.execute(
            select(AgentRun.strategy_run_id, AgentRun.step_name, AgentRun.started_at)
            .where(AgentRun.strategy_run_id.in_(run_ids))
            .order_by(AgentRun.strategy_run_id.asc(), AgentRun.started_at.desc())
        )
        for run_id, step_name, _started_at in latest_steps_result.all():
            latest_steps.setdefault(run_id, step_name)

    runs = [
        _serialize_strategy_run_summary(
            strategy_run,
            candidates_count=candidate_counts.get(strategy_run.id, 0),
            completed_steps=completed_step_counts.get(strategy_run.id, 0),
            current_step=latest_steps.get(strategy_run.id),
        )
        for strategy_run in strategy_runs
    ]
    return ListStrategyRunsResponse(total=total, runs=runs)


@router.get("/agent-runs/{run_id}", response_model=StrategyRunStatusResponse)
async def get_agent_run_status(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get agent run status."""
    strategy_run = await db.get(StrategyRun, run_id)
    if not strategy_run:
        raise HTTPException(status_code=404, detail="Run not found")

    summary = await _build_strategy_run_summary(strategy_run, db)

    return StrategyRunStatusResponse(
        run_id=strategy_run.id,
        status=strategy_run.status,
        current_step=summary.current_step,
        progress={
            "total_steps": summary.total_steps,
            "completed_steps": summary.completed_steps,
        },
        candidates_discovered=summary.candidates_discovered,
        created_at=strategy_run.created_at,
        started_at=strategy_run.started_at,
        completed_at=strategy_run.completed_at,
    )


@router.get("/agent-runs/{run_id}/steps", response_model=ListAgentRunStepsResponse)
async def get_agent_run_steps(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed pipeline step executions for a run."""
    strategy_run = await db.get(StrategyRun, run_id)
    if not strategy_run:
        raise HTTPException(status_code=404, detail="Run not found")

    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.strategy_run_id == run_id)
        .order_by(AgentRun.started_at.asc())
    )
    steps = list(result.scalars().all())

    return ListAgentRunStepsResponse(
        run_id=run_id,
        steps=[
            AgentRunStepResponse(
                id=step.id,
                step_name=step.step_name,
                agent_name=step.agent_name,
                status=step.status.value,
                attempt=step.attempt,
                error_message=step.error_message,
                started_at=step.started_at.isoformat() if step.started_at else "",
                completed_at=step.completed_at.isoformat() if step.completed_at else None,
                latency_ms=step.latency_ms,
            )
            for step in steps
        ],
    )


@router.get("/agent-runs/{run_id}/results")
async def get_agent_run_results(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get agent run results."""
    strategy_run = await db.get(StrategyRun, run_id)
    if not strategy_run:
        raise HTTPException(status_code=404, detail="Run not found")

    result = await db.execute(
        select(CandidateProduct)
        .where(CandidateProduct.strategy_run_id == run_id)
        .options(
            selectinload(CandidateProduct.pricing_assessment),
            selectinload(CandidateProduct.risk_assessment),
            selectinload(CandidateProduct.listing_drafts),
        )
    )
    candidates = result.scalars().all()

    candidates_data = []
    for candidate in candidates:
        pricing = candidate.pricing_assessment
        risk = candidate.risk_assessment

        candidate_data = {
            "candidate_id": str(candidate.id),
            "title": candidate.title,
            "platform_price": float(candidate.platform_price) if candidate.platform_price else None,
            "estimated_margin": float(pricing.estimated_margin) if pricing else None,
            "margin_percentage": float(pricing.margin_percentage) if pricing else None,
            "risk_decision": risk.decision.value if risk else None,
            "risk_score": risk.score if risk else None,
            "listing_drafts": [
                {
                    "language": draft.language,
                    "title": draft.title,
                    "bullets": draft.bullets or [],
                }
                for draft in candidate.listing_drafts
            ],
        }
        candidates_data.append(candidate_data)

    candidates_data.sort(
        key=lambda x: x.get("margin_percentage") or 0,
        reverse=True,
    )

    return {
        "run_id": str(run_id),
        "status": strategy_run.status.value,
        "candidates": candidates_data,
    }
