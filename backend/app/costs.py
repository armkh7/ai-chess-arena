"""Costs are for the site owner, not visitors.

Every API response goes through `strip_costs`, and each finished game adds one line to a CSV
log (`COST_LOG_FILE`, default `logs/costs.csv`) that `uv run arena costs` summarizes.
"""

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.game.models import Color, GameRecord
from app.public_models import BACKEND_DIR

COLUMNS = [
    "finished_at",
    "game_id",
    "white_model",
    "black_model",
    "result",
    "termination",
    "moves",
    "white_cost_usd",
    "black_cost_usd",
    "judge_model",
    "judge_cost_usd",
    "total_cost_usd",
]


def strip_costs(data: Any) -> Any:
    """The same JSON without any `cost_usd` field, at any depth."""
    if isinstance(data, dict):
        return {k: strip_costs(v) for k, v in data.items() if k != "cost_usd"}
    if isinstance(data, list):
        return [strip_costs(v) for v in data]
    return data


def log_path(setting: str) -> Path | None:
    """The log file from the setting: relative paths are inside backend/; empty = no log."""
    if not setting:
        return None
    path = Path(setting)
    return path if path.is_absolute() else BACKEND_DIR / path


def cost_row(record: GameRecord) -> dict[str, str]:
    white = record.player_stats(Color.WHITE).cost_usd
    black = record.player_stats(Color.BLACK).cost_usd
    judge = record.judge.cost_usd if record.judge else 0.0
    finished = record.finished_at or datetime.now(UTC)
    return {
        "finished_at": finished.astimezone(UTC).isoformat(timespec="seconds"),
        "game_id": record.id,
        "white_model": record.white_model,
        "black_model": record.black_model,
        "result": record.result,
        "termination": record.termination.value if record.termination else "",
        "moves": str(len(record.moves)),
        "white_cost_usd": f"{white:.6f}",
        "black_cost_usd": f"{black:.6f}",
        "judge_model": record.judge.model if record.judge else "",
        "judge_cost_usd": f"{judge:.6f}",
        "total_cost_usd": f"{white + black + judge:.6f}",
    }


def append_cost(path: Path, record: GameRecord) -> None:
    """Add the game's line, creating the file (with a header row) if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            writer.writeheader()
        writer.writerow(cost_row(record))


@dataclass
class Spend:
    games: int = 0
    usd: float = 0.0

    def add(self, usd: float, games: int = 1) -> None:
        self.games += games
        self.usd += usd


@dataclass
class CostSummary:
    today: Spend = field(default_factory=Spend)
    this_month: Spend = field(default_factory=Spend)
    total: Spend = field(default_factory=Spend)
    judge: Spend = field(default_factory=Spend)
    # What each model cost as a player, in all the games it played.
    by_model: dict[str, Spend] = field(default_factory=lambda: defaultdict(Spend))


def summarize(path: Path, now: datetime | None = None) -> CostSummary:
    """Totals for today and this month (UTC), all time, the judge, and each model."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    summary = CostSummary()
    if not path.exists():
        return summary
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            when = datetime.fromisoformat(row["finished_at"]).astimezone(UTC)
            total = float(row["total_cost_usd"])
            summary.total.add(total)
            if (when.year, when.month) == (now.year, now.month):
                summary.this_month.add(total)
                if when.date() == now.date():
                    summary.today.add(total)
            summary.judge.add(float(row["judge_cost_usd"]), games=1 if row["judge_model"] else 0)
            summary.by_model[row["white_model"]].add(float(row["white_cost_usd"]))
            summary.by_model[row["black_model"]].add(float(row["black_cost_usd"]))
    return summary
