"""Base agent classes."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AgentContext:
    """Context passed to agents."""

    strategy_run_id: UUID
    db: AsyncSession
    input_data: dict[str, Any]


@dataclass
class AgentResult:
    """Result returned by agents."""

    success: bool
    output_data: dict[str, Any]
    error_message: Optional[str] = None


class BaseAgent(ABC):
    """Base class for all agents."""

    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(f"agent.{name}")

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent logic."""
        pass

    async def _handle_error(self, error: Exception, context: AgentContext) -> AgentResult:
        """Handle agent execution errors."""
        self.logger.error(
            "agent_execution_failed",
            agent=self.name,
            strategy_run_id=str(context.strategy_run_id),
            error=str(error),
        )
        return AgentResult(
            success=False,
            output_data={},
            error_message=str(error),
        )
