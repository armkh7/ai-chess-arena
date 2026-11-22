"""Read and write games."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.game.models import Color, GameRecord
from app.storage.db import GameRow


class GameStatus(StrEnum):
    QUEUED = "queued"  # waiting for a free slot
    RUNNING = "running"
    ANALYZING = "analyzing"  # game over, Stockfish is reviewing it
    JUDGING = "judging"  # the judge agent is writing its report
    FINISHED = "finished"  # done, whatever the result (including forfeits and API errors)
    ERROR = "error"  # crashed: a bug, not a chess result
    INTERRUPTED = "interrupted"  # the server stopped while it was running

    @property
    def is_active(self) -> bool:
        return self in (
            GameStatus.QUEUED,
            GameStatus.RUNNING,
            GameStatus.ANALYZING,
            GameStatus.JUDGING,
        )


class GameSummary(BaseModel):
    """One line in a list of games."""

    id: str
    status: GameStatus
    white_model: str
    black_model: str
    result: str
    termination: str | None
    winner: str | None
    moves: int
    white_accuracy: float | None
    black_accuracy: float | None
    cost_usd: float
    created_at: datetime
    finished_at: datetime | None


class StoredGame(BaseModel):
    status: GameStatus
    error: str | None = None
    record: GameRecord


def _row(record: GameRecord, status: GameStatus, error: str | None) -> GameRow:
    analysis = record.analysis
    cost = sum(record.player_stats(color).cost_usd for color in Color)
    return GameRow(
        id=record.id,
        status=status.value,
        white_model=record.white_model,
        black_model=record.black_model,
        result=record.result,
        termination=record.termination.value if record.termination else None,
        winner=record.winner.value if record.winner else None,
        moves=len(record.moves),
        white_accuracy=analysis.white.accuracy if analysis else None,
        black_accuracy=analysis.black.accuracy if analysis else None,
        cost_usd=round(cost, 6),
        error=error,
        created_at=record.started_at,
        finished_at=record.finished_at,
        data=record.model_dump(mode="json"),
    )


class GameStore:
    def __init__(self, sessions: async_sessionmaker) -> None:
        self._sessions = sessions

    async def save(self, record: GameRecord, status: GameStatus, error: str | None = None) -> None:
        """Insert or update the game (called after every move while it runs)."""
        async with self._sessions() as session, session.begin():
            await session.merge(_row(record, status, error))

    async def get(self, game_id: str) -> StoredGame | None:
        async with self._sessions() as session:
            row = await session.get(GameRow, game_id)
        if row is None:
            return None
        return StoredGame(
            status=GameStatus(row.status),
            error=row.error,
            record=GameRecord.model_validate(row.data),
        )

    async def list_games(
        self, *, limit: int = 20, offset: int = 0
    ) -> tuple[list[GameSummary], int]:
        """Newest first, plus the total count."""
        async with self._sessions() as session:
            total = await session.scalar(select(func.count()).select_from(GameRow))
            rows = await session.scalars(
                select(GameRow).order_by(GameRow.created_at.desc()).limit(limit).offset(offset)
            )
            summaries = [GameSummary.model_validate(row, from_attributes=True) for row in rows]
        return summaries, total or 0

    async def finished_games(self) -> list[GameRecord]:
        """Every finished game with a result, oldest first (for the leaderboard)."""
        async with self._sessions() as session:
            rows = await session.scalars(
                select(GameRow.data)
                .where(GameRow.status == GameStatus.FINISHED.value, GameRow.result != "*")
                .order_by(GameRow.created_at)
            )
            return [GameRecord.model_validate(data) for data in rows]

    async def count_since(self, since: datetime) -> int:
        """Games started at or after `since` (for the daily cap)."""
        async with self._sessions() as session:
            count = await session.scalar(
                select(func.count()).select_from(GameRow).where(GameRow.created_at >= since)
            )
        return count or 0

    async def mark_interrupted(self) -> int:
        """At startup: games left running by a previous server process can't resume."""
        active = [s.value for s in GameStatus if s.is_active]
        async with self._sessions() as session, session.begin():
            result = await session.execute(
                update(GameRow)
                .where(GameRow.status.in_(active))
                .values(status=GameStatus.INTERRUPTED.value)
            )
        return result.rowcount or 0
