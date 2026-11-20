"""Prompts sent to the models. Each turn is a fresh conversation with the full game state."""

import chess

SYSTEM_PROMPT = """You are a strong chess player in a game against another AI. You play {color}.
On each turn you receive the current position and must answer with exactly one legal move.

Reply with a single JSON object and nothing else:
{{"reasoning": "<one to three short sentences>", "move": "<your move in SAN>"}}

SAN examples: e4, Nf3, exd5, Bxf7+, O-O, O-O-O, e8=Q."""


def system_prompt(color: chess.Color) -> str:
    return SYSTEM_PROMPT.format(color="White" if color == chess.WHITE else "Black")


def move_history(board: chess.Board) -> str:
    """Moves so far in standard notation, e.g. '1. e4 e5 2. Nf3'."""
    if not board.move_stack:
        return ""
    return board.root().variation_san(board.move_stack)


def board_diagram(board: chess.Board) -> str:
    """Text board with coordinates. Uppercase = White, lowercase = Black."""
    rows = []
    for rank in range(7, -1, -1):
        pieces = []
        for file in range(8):
            piece = board.piece_at(chess.square(file, rank))
            pieces.append(piece.symbol() if piece else ".")
        rows.append(f"{rank + 1} " + " ".join(pieces))
    rows.append("  a b c d e f g h")
    return "\n".join(rows)


def turn_prompt(board: chess.Board, *, show_legal_moves: bool) -> str:
    side = "White" if board.turn == chess.WHITE else "Black"
    history = move_history(board)
    lines = [
        f"You are {side}. It is move {board.fullmove_number}, your turn.",
        f"Moves so far: {history}" if history else "No moves yet: you make the first move.",
        f"Position (FEN): {board.fen()}",
        "Board (uppercase = White, lowercase = Black):",
        board_diagram(board),
    ]
    if board.is_check():
        lines.append("You are in check.")
    if show_legal_moves:
        legal = ", ".join(sorted(board.san(m) for m in board.legal_moves))
        lines.append(f"Legal moves: {legal}")
    lines.append('Reply with JSON only: {"reasoning": "...", "move": "..."}')
    return "\n".join(lines)


def retry_prompt(error: str) -> str:
    return (
        f"Your move was rejected: {error}\n"
        'Try again. Reply with JSON only: {"reasoning": "...", "move": "..."}'
    )
