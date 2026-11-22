"""Model benchmark: a round-robin tournament to choose the models the public site offers.

Every pair of candidates plays. For each model we measure what matters for a live demo:
does it finish its games (no forfeits, timeouts or API failures), how fast it answers,
how often it tries illegal moves, how well it plays (Stockfish accuracy) and what it costs.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from itertools import combinations
from statistics import fmean

from app.game.models import Color, GameRecord, Termination

log = logging.getLogger(__name__)

PlayGame = Callable[[str, str], Awaitable[GameRecord]]  # (white, black) -> finished game


def pairings(models: list[str], games_per_pair: int = 1) -> list[tuple[str, str]]:
    """(white, black) for every game. Colors alternate so each model gets White about half
    the time; with `games_per_pair=2` every pair plays once with each color."""
    games = []
    for n, (a, b) in enumerate(combinations(models, 2)):
        for k in range(games_per_pair):
            games.append((a, b) if (n + k) % 2 == 0 else (b, a))
    return games


async def run_games(
    games: list[tuple[str, str]],
    play: PlayGame,
    *,
    concurrency: int = 2,
    on_done: Callable[[GameRecord], None] | None = None,
) -> list[GameRecord]:
    """Play every game, `concurrency` at a time. A crash in one game doesn't stop the rest."""
    slots = asyncio.Semaphore(concurrency)

    async def one(white: str, black: str) -> GameRecord:
        async with slots:
            try:
                record = await play(white, black)
            except Exception as exc:
                log.exception("Benchmark game %s vs %s crashed", white, black)
                record = GameRecord(
                    white_model=white, black_model=black, error=f"{type(exc).__name__}: {exc}"
                )
        if on_done:
            on_done(record)
        return record

    return list(await asyncio.gather(*(one(white, black) for white, black in games)))


@dataclass
class ModelResult:
    model: str
    games: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    forfeits: int = 0  # lost by illegal or unreadable moves
    timeouts: int = 0  # lost on time
    api_errors: int = 0  # game aborted while it was this model's turn (rate limits, outages)
    replies: int = 0  # every answer, accepted or rejected
    rejected: int = 0
    latency_ms: int = 0
    cost_usd: float = 0.0
    accuracies: list[float] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Win = 1, draw = 0.5, as a share of the games that got a result."""
        decided = self.wins + self.draws + self.losses
        return (self.wins + 0.5 * self.draws) / decided if decided else 0.0

    @property
    def finish_rate(self) -> float:
        """Share of games the model got through without forfeiting, timing out or failing."""
        failed = self.forfeits + self.timeouts + self.api_errors
        return (self.games - failed) / self.games if self.games else 0.0

    @property
    def illegal_rate(self) -> float:
        return self.rejected / self.replies if self.replies else 0.0

    @property
    def sec_per_reply(self) -> float:
        return self.latency_ms / self.replies / 1000 if self.replies else 0.0

    @property
    def accuracy(self) -> float | None:
        return round(fmean(self.accuracies), 1) if self.accuracies else None

    @property
    def cost_per_game(self) -> float:
        return self.cost_usd / self.games if self.games else 0.0

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "games": self.games,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "forfeits": self.forfeits,
            "timeouts": self.timeouts,
            "api_errors": self.api_errors,
            "score": round(self.score, 3),
            "finish_rate": round(self.finish_rate, 3),
            "illegal_rate": round(self.illegal_rate, 3),
            "sec_per_reply": round(self.sec_per_reply, 2),
            "accuracy": self.accuracy,
            "cost_per_game": round(self.cost_per_game, 6),
        }


def _add_game(result: ModelResult, record: GameRecord, color: Color) -> None:
    result.games += 1
    attempts = [a for m in record.moves if m.color is color for a in m.attempts]
    if record.failed_color is color:
        attempts += record.failed_attempts
    result.replies += len(attempts)
    result.rejected += sum(1 for a in attempts if a.error)
    result.latency_ms += sum(a.latency_ms for a in attempts)
    result.cost_usd += sum(a.cost_usd or 0 for a in attempts)

    if record.analysis and (accuracy := record.analysis.player(color).accuracy) is not None:
        result.accuracies.append(accuracy)

    if record.result == "*":  # aborted: no chess result
        if record.failed_color is color:
            result.api_errors += 1
        return
    if record.winner is None:
        result.draws += 1
    elif record.winner is color:
        result.wins += 1
    else:
        result.losses += 1
        if record.termination is Termination.FORFEIT_ILLEGAL_MOVES:
            result.forfeits += 1
        elif record.termination is Termination.TIMEOUT:
            result.timeouts += 1


def summarize(records: list[GameRecord]) -> list[ModelResult]:
    """One result per model, the most reliable and strongest first."""
    results: dict[str, ModelResult] = {}
    for record in records:
        for color in Color:
            model = record.model_for(color)
            _add_game(results.setdefault(model, ModelResult(model)), record, color)
    return sorted(
        results.values(),
        key=lambda r: (r.finish_rate, r.score, r.accuracy or 0, -r.sec_per_reply),
        reverse=True,
    )


HEADERS = [
    "Model",
    "Games",
    "Finish",
    "Score",
    "W-D-L",
    "Accuracy",
    "Sec/reply",
    "Illegal",
    "$/game",
    "Failures",
]


def table_rows(results: list[ModelResult]) -> list[list[str]]:
    rows = []
    for r in results:
        failures = [
            f"{n} {label}"
            for n, label in (
                (r.forfeits, "forfeit"),
                (r.timeouts, "timeout"),
                (r.api_errors, "API error"),
            )
            if n
        ]
        rows.append(
            [
                r.model,
                str(r.games),
                f"{r.finish_rate:.0%}",
                f"{r.score:.0%}",
                f"{r.wins}-{r.draws}-{r.losses}",
                f"{r.accuracy:.1f}" if r.accuracy is not None else "-",
                f"{r.sec_per_reply:.1f}",
                f"{r.illegal_rate:.0%}",
                f"{r.cost_per_game:.4f}",
                ", ".join(failures) or "-",
            ]
        )
    return rows


def to_markdown(results: list[ModelResult], title: str, notes: list[str]) -> str:
    lines = [f"# {title}", "", *notes, ""]
    lines.append("| " + " | ".join(HEADERS) + " |")
    lines.append("|" + "---|" * len(HEADERS))
    lines += ["| " + " | ".join(row) + " |" for row in table_rows(results)]
    return "\n".join(lines) + "\n"
