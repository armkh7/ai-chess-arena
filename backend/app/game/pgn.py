"""Export a finished game as PGN, the standard chess game format."""

import chess
import chess.pgn

from app.game.models import GameRecord


def build_pgn(board: chess.Board, record: GameRecord) -> str:
    game = chess.pgn.Game.from_board(board)
    game.headers["Event"] = "AI Chess Arena"
    game.headers["Site"] = "?"  # set to the live URL after deploy
    game.headers["Date"] = record.started_at.strftime("%Y.%m.%d")
    game.headers["White"] = record.white_model
    game.headers["Black"] = record.black_model
    game.headers["Result"] = record.result
    if record.termination:
        game.headers["Termination"] = record.termination.value

    # Each model's reasoning becomes a comment on its move.
    for node, move in zip(game.mainline(), record.moves, strict=True):
        if move.reasoning:
            node.comment = move.reasoning

    exporter = chess.pgn.StringExporter(headers=True, variations=False, comments=True)
    return game.accept(exporter)
