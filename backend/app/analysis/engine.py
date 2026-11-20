"""Run Stockfish through python-chess's UCI support.

Stockfish is a separate program (`brew install stockfish`, `apt install stockfish`).
python-chess starts it as a subprocess and talks to it over UCI, the standard text protocol
chess engines use.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

import chess
import chess.engine

from app.analysis.metrics import MATE
from app.config import Settings


class EngineNotFound(Exception):
    """Stockfish is not installed or not on PATH."""


@dataclass(frozen=True)
class Evaluation:
    score: int  # centipawns from White's point of view, mates as ±(MATE - moves)
    best_move: chess.Move | None


class Evaluator(Protocol):
    """Anything that can evaluate a position. Stockfish in production, a fake in tests."""

    name: str
    depth: int

    async def evaluate(self, board: chess.Board) -> Evaluation: ...


def find_stockfish(path: str = "stockfish") -> str | None:
    if found := shutil.which(path):
        return found
    return path if Path(path).is_file() else None


class Stockfish:
    """Async context manager: `async with Stockfish() as engine: await engine.evaluate(b)`."""

    def __init__(
        self,
        path: str = "stockfish",
        *,
        depth: int = 14,
        time_seconds: float = 0.0,
        threads: int = 1,
        hash_mb: int = 64,
    ) -> None:
        self.path = path
        self.depth = depth
        # Search stops at `depth` or after `time_seconds`, whichever comes first. Sharp
        # positions can take seconds at depth 14+, so the time cap keeps analysis predictable.
        self.time_seconds = time_seconds
        self.threads = threads
        self.hash_mb = hash_mb
        self.name = "Stockfish"
        self._engine: chess.engine.UciProtocol | None = None

    @classmethod
    def from_settings(cls, settings: Settings, depth: int | None = None) -> "Stockfish":
        return cls(
            settings.stockfish_path,
            depth=depth or settings.analysis_depth,
            time_seconds=settings.analysis_time_seconds,
            threads=settings.analysis_threads,
            hash_mb=settings.analysis_hash_mb,
        )

    async def __aenter__(self) -> Self:
        resolved = find_stockfish(self.path)
        if resolved is None:
            raise EngineNotFound(
                f"Stockfish not found ({self.path!r}). Install it, e.g. `brew install stockfish`, "
                "or set STOCKFISH_PATH."
            )
        _, self._engine = await chess.engine.popen_uci(resolved)
        await self._engine.configure({"Threads": self.threads, "Hash": self.hash_mb})
        self.name = self._engine.id.get("name", "Stockfish")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._engine is not None:
            await self._engine.quit()
            self._engine = None

    async def evaluate(self, board: chess.Board) -> Evaluation:
        if self._engine is None:
            raise RuntimeError("Use `async with Stockfish(...)` before evaluating.")
        limit = chess.engine.Limit(depth=self.depth, time=self.time_seconds or None)
        info = await self._engine.analyse(board, limit)
        score = info["score"].white().score(mate_score=MATE)
        pv = info.get("pv") or []
        return Evaluation(score=score, best_move=pv[0] if pv else None)
