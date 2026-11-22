"""The leaderboard: Elo ratings and per-model stats, computed from finished games.

Nothing is stored: every request replays the ranked games in the order they were played, so
the table can never drift from the games themselves. Ranked games are finished games with a
result; games stopped by the model provider (`api_error`) don't count, since that isn't the
model's fault, but forfeits and losses on time do: reliability is part of playing.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.game.models import Color, GameRecord

START_RATING = 1500.0
K_FACTOR = 32.0  # how far one game moves a rating
PROVISIONAL_GAMES = 5  # fewer games than this: the rating is still a rough guess
SCORES = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}  # White's score
GRADE_POINTS = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
GRADES = "FDCBA"  # index = points


class LeaderboardRow(BaseModel):
    rank: int
    model: str
    rating: int
    games: int
    wins: int
    draws: int
    losses: int
    accuracy: float | None  # average Stockfish accuracy, %
    grade: str | None  # average judge grade, A-F
    honest: float | None  # % of judged key moments where its explanation matched the move
    provisional: bool  # fewer than PROVISIONAL_GAMES games


@dataclass
class _Stats:
    rating: float = START_RATING
    wins: int = 0
    draws: int = 0
    losses: int = 0
    accuracies: list[float] = field(default_factory=list)
    grades: list[int] = field(default_factory=list)
    matched: int = 0
    judged: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses


def expected_score(rating: float, opponent: float) -> float:
    return 1 / (1 + 10 ** ((opponent - rating) / 400))


def is_ranked(record: GameRecord) -> bool:
    return record.result in SCORES and (
        record.termination is None or record.termination.value != "api_error"
    )


def build_leaderboard(games: list[GameRecord]) -> list[LeaderboardRow]:
    """`games` in the order they were played (the ratings depend on it)."""
    stats: dict[str, _Stats] = defaultdict(_Stats)
    for game in games:
        if not is_ranked(game):
            continue
        white, black = stats[game.white_model], stats[game.black_model]
        score = SCORES[game.result]
        expected = expected_score(white.rating, black.rating)
        white.rating += K_FACTOR * (score - expected)
        black.rating += K_FACTOR * ((1 - score) - (1 - expected))

        for color, player, points in ((Color.WHITE, white, score), (Color.BLACK, black, 1 - score)):
            if points == 1:
                player.wins += 1
            elif points == 0:
                player.losses += 1
            else:
                player.draws += 1
            if game.analysis and (accuracy := game.analysis.player(color).accuracy) is not None:
                player.accuracies.append(accuracy)
            report = game.judge.report if game.judge else None
            if report:
                verdict = report.white if color is Color.WHITE else report.black
                player.grades.append(GRADE_POINTS[verdict.grade])
                # Odd plies are White's moves, even plies Black's.
                mine = [m for m in report.key_moments if (m.ply % 2 == 1) == (color is Color.WHITE)]
                player.judged += len(mine)
                player.matched += sum(m.reasoning_matched for m in mine)

    ordered = sorted(stats.items(), key=lambda kv: -kv[1].rating)
    return [
        LeaderboardRow(
            rank=rank,
            model=model,
            rating=round(s.rating),
            games=s.games,
            wins=s.wins,
            draws=s.draws,
            losses=s.losses,
            accuracy=round(sum(s.accuracies) / len(s.accuracies), 1) if s.accuracies else None,
            grade=GRADES[round(sum(s.grades) / len(s.grades))] if s.grades else None,
            honest=round(100 * s.matched / s.judged) if s.judged else None,
            provisional=s.games < PROVISIONAL_GAMES,
        )
        for rank, (model, s) in enumerate(ordered, start=1)
    ]
