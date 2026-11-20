"""Turn the text a model wrote into a legal move, or explain why it isn't one."""

import chess


class MoveRejected(ValueError):
    """The move text is not a legal move in the current position."""


def resolve_move(board: chess.Board, text: str) -> chess.Move:
    """Accept standard notation (Nf3) first, then from-to squares (g1f3)."""
    try:
        return board.parse_san(text)
    except chess.AmbiguousMoveError as exc:
        raise MoveRejected(
            f"'{text}' is ambiguous: more than one piece can make it. "
            "Add the starting file or rank, e.g. Nbd2 or R1e2."
        ) from exc
    except (chess.IllegalMoveError, chess.InvalidMoveError):
        pass

    try:
        move = chess.Move.from_uci(text.lower())
    except chess.InvalidMoveError:
        move = None
    if move is not None and move in board.legal_moves:
        return move

    reason = f"'{text}' is not a legal move in this position."
    if board.is_check():
        reason += " Your king is in check, so you must get out of check."
    raise MoveRejected(reason)
