"""Database tables and connection setup (SQLAlchemy 2, async).

One `games` table: summary columns to list, filter and rank games, plus the full game record
(every move, attempt and the analysis) as JSON. That's all the leaderboard and replays need,
without splitting moves into their own table.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


class GameRow(Base):
    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), index=True)
    white_model: Mapped[str] = mapped_column(String(200), index=True)
    black_model: Mapped[str] = mapped_column(String(200), index=True)
    result: Mapped[str] = mapped_column(String(8))
    termination: Mapped[str | None] = mapped_column(String(32))
    winner: Mapped[str | None] = mapped_column(String(5))
    moves: Mapped[int] = mapped_column(Integer)
    white_accuracy: Mapped[float | None] = mapped_column(Float)
    black_accuracy: Mapped[float | None] = mapped_column(Float)
    cost_usd: Mapped[float] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)  # why the game crashed, if it did
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The whole `GameRecord`. JSONB on PostgreSQL (queryable), plain JSON elsewhere.
    data: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))


def make_engine(url: str) -> AsyncEngine:
    if url.startswith("sqlite"):
        # In-memory SQLite (tests): one shared connection, or each would see an empty DB.
        return create_async_engine(
            url, poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
    return create_async_engine(url, pool_pre_ping=True)


def make_sessions(engine: AsyncEngine) -> async_sessionmaker:
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables(engine: AsyncEngine) -> None:
    """For tests. Real databases are set up with Alembic migrations (`alembic upgrade head`)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
