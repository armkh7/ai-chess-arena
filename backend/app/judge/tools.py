"""The judge agent's tools: read-only views of one finished, analyzed game.

Every tool takes a `purpose`: one sentence on what the agent wants to learn and why. It costs
the model a few tokens and makes each step of the agent readable on the website.
"""

import chess
from langchain_core.tools import BaseTool, tool

from app.analysis.metrics import format_eval
from app.game.models import Color, GameRecord, JudgeReport, MoveAnalysis, MoveRecord

SUBMIT_REPORT = "submit_report"
MAX_SCAN_PLIES = 30
REASONING_PREVIEW = 140  # characters of each model explanation in `get_moves`


def notation(move: MoveRecord) -> str:
    """'7. Nf3' for White, '7... Nf6' for Black."""
    return f"{move.move_number}{'.' if move.color is Color.WHITE else '...'} {move.san}"


class GameView:
    """Lookups over one game that the tools and the step titles share."""

    def __init__(self, record: GameRecord) -> None:
        self.record = record
        self.moves = record.moves
        self.analysis: dict[int, MoveAnalysis] = (
            {m.ply: m for m in record.analysis.moves} if record.analysis else {}
        )

    def move(self, ply: int) -> MoveRecord | None:
        return self.moves[ply - 1] if 1 <= ply <= len(self.moves) else None

    def label(self, ply: int) -> str:
        move = self.move(ply)
        return notation(move) if move else f"ply {ply}"

    def side(self, color: Color) -> str:
        return f"{color.value.capitalize()} ({self.record.model_for(color)})"


def make_tools(record: GameRecord) -> list[BaseTool]:
    view = GameView(record)

    def no_move(ply: int) -> str:
        return f"No move at ply {ply}. This game has plies 1 to {len(view.moves)}."

    @tool(parse_docstring=True)
    def get_game_overview(purpose: str) -> str:
        """Who played, the result and how it ended, and each side's accuracy, blunders,
        illegal moves and timeouts. Start here.

        Args:
            purpose: One short sentence: what you want to learn and why.
        """
        rec = record
        ending = rec.termination.value if rec.termination else "unknown"
        lines = [
            f"White: {rec.white_model}",
            f"Black: {rec.black_model}",
            f"Result: {rec.result}, ended by {ending}",
            f"Length: {len(rec.moves)} plies ({(len(rec.moves) + 1) // 2} moves)",
        ]
        if rec.error:
            lines.append(f"Error: {rec.error}")
        if rec.analysis:
            lines.append(
                f"Final Stockfish evaluation: {format_eval(rec.analysis.final_eval)} "
                "(positive = White is better)"
            )
        for color in Color:
            stats = rec.player_stats(color)
            timeouts = sum(
                1 for m in rec.moves if m.color is color for a in m.attempts if a.timed_out
            )
            line = (
                f"{view.side(color)}: {stats.moves} moves, {stats.illegal_attempts} rejected "
                f"replies ({timeouts} too slow), {stats.avg_latency_ms / 1000:.1f} s per reply"
            )
            if rec.analysis:
                player = rec.analysis.player(color)
                counts = ", ".join(f"{n} {label.value}" for label, n in player.counts.items() if n)
                accuracy = f"{player.accuracy:.1f}%" if player.accuracy is not None else "n/a"
                line += f"; accuracy {accuracy}, average centipawn loss {player.acpl}; {counts}"
            lines.append(line)
        if rec.failed_attempts and rec.failed_color:
            errors = "; ".join(a.error or "?" for a in rec.failed_attempts)
            lines.append(f"{rec.failed_color.value.capitalize()}'s last failed replies: {errors}")
        opening = " ".join(notation(m) for m in rec.moves[:8])
        lines.append(f"Opening: {opening}")
        return "\n".join(lines)

    @tool(parse_docstring=True)
    def get_key_moments(purpose: str, count: int = 5) -> str:
        """The moves that changed the game most: the biggest drops in the mover's winning
        chance according to Stockfish.

        Args:
            purpose: One short sentence: what you want to learn and why.
            count: How many moments to list (1-8).
        """
        if not view.analysis:
            return "No Stockfish analysis for this game."
        count = max(1, min(count, 8))
        worst = sorted(view.analysis.values(), key=lambda a: a.win_after - a.win_before)[:count]
        lines = []
        for a in sorted(worst, key=lambda a: a.ply):
            move = view.move(a.ply)
            best = f", Stockfish preferred {a.best_san}" if a.best_san and a.label != "best" else ""
            lines.append(
                f"ply {a.ply}: {view.label(a.ply)} by {view.side(a.color)}: {a.label.value}; "
                f"winning chance {a.win_before:.0f}% -> {a.win_after:.0f}%, eval "
                f"{format_eval(a.eval_before)} -> {format_eval(a.eval_after)}{best}"
                + (
                    f"; {len(move.attempts) - 1} rejected tries first"
                    if move and len(move.attempts) > 1
                    else ""
                )
            )
        return "\n".join(lines)

    @tool(parse_docstring=True)
    def get_move_details(ply: int, purpose: str) -> str:
        """Everything about one move: the model's own explanation, its rejected tries, and
        Stockfish's verdict.

        Args:
            ply: Half-move index, 1 = White's first move.
            purpose: One short sentence: what you want to learn and why.
        """
        move = view.move(ply)
        if move is None:
            return no_move(ply)
        lines = [
            f"ply {ply}: {notation(move)} by {view.side(move.color)}",
            f"Position before the move (FEN): {move.fen_before}",
            f"The model's explanation: {move.reasoning or '(none)'}",
        ]
        rejected = move.attempts[:-1]
        if rejected:
            tries = "; ".join(f"{a.move_text or 'no move'} ({a.error})" for a in rejected)
            lines.append(f"Rejected tries before this move: {tries}")
        a = view.analysis.get(ply)
        if a:
            lines.append(
                f"Stockfish: {a.label.value}, accuracy {a.accuracy:.0f}%. Eval "
                f"{format_eval(a.eval_before)} -> {format_eval(a.eval_after)} (White's view); "
                f"the mover's winning chance {a.win_before:.0f}% -> {a.win_after:.0f}%. "
                f"Best move: {a.best_san or 'n/a'}."
            )
        return "\n".join(lines)

    @tool(parse_docstring=True)
    def show_board(ply: int, purpose: str) -> str:
        """The board after a move, as text (White pieces uppercase, Black lowercase,
        rank 8 at the top). ply 0 = the starting position.

        Args:
            ply: Half-move index; the board is shown after this move.
            purpose: One short sentence: what you want to see and why.
        """
        if ply == 0:
            board, last = chess.Board(), "start of the game"
        else:
            move = view.move(ply)
            if move is None:
                return no_move(ply)
            board, last = chess.Board(move.fen_after), f"after {notation(move)}"
        turn = "White" if board.turn == chess.WHITE else "Black"
        check = ", in check" if board.is_check() else ""
        return f"Board {last}. {turn} to move{check}.\n{board}\nFEN: {board.fen()}"

    @tool(parse_docstring=True)
    def get_moves(from_ply: int, to_ply: int, purpose: str) -> str:
        """A stretch of the game, one line per move with Stockfish's label and the start of
        the model's explanation. At most 30 plies per call.

        Args:
            from_ply: First half-move to list (1 = White's first move).
            to_ply: Last half-move to list.
            purpose: One short sentence: what you want to learn and why.
        """
        start = max(1, from_ply)
        end = min(len(view.moves), to_ply, start + MAX_SCAN_PLIES - 1)
        if start > end:
            return no_move(from_ply)
        lines = []
        for ply in range(start, end + 1):
            move = view.moves[ply - 1]
            a = view.analysis.get(ply)
            label = f" [{a.label.value}]" if a else ""
            reason = (move.reasoning or "")[:REASONING_PREVIEW]
            lines.append(f"ply {ply}: {notation(move)}{label}: {reason}")
        return "\n".join(lines)

    # Not `return_direct`: LangChain ends the run after a return_direct tool even when it
    # failed, so a report rejected by validation ended the judge with no report. Now the model
    # sees the error and can fix it; the agent loop stops once a report is accepted.
    @tool(SUBMIT_REPORT, args_schema=JudgeReport)
    def submit_report(**report) -> str:
        """Submit the final post-game report as your last step. If it's rejected, fix what the
        error says and submit it again."""
        return JudgeReport.model_validate(report).model_dump_json()

    return [
        get_game_overview,
        get_key_moments,
        get_move_details,
        show_board,
        get_moves,
        submit_report,
    ]


def step_title(view: GameView, tool_name: str, args: dict) -> str:
    """A short label for a tool call on the website, e.g. 'Move 7... Qe4+'."""
    ply = args.get("ply")
    match tool_name:
        case "get_game_overview":
            return "Game overview"
        case "get_key_moments":
            return "Turning points"
        case "get_move_details" if isinstance(ply, int):
            return f"Move {view.label(ply)}"
        case "show_board" if isinstance(ply, int):
            return "Starting position" if ply == 0 else f"Board after {view.label(ply)}"
        case "get_moves":
            first, last = view.label(args.get("from_ply", 1)), view.label(args.get("to_ply", 1))
            return f"Moves {first} to {last}"
        case "submit_report":
            return "Final report"
    return tool_name
