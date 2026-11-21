"""Plays one game between two players and enforces the rules.

Each turn: build the prompt -> ask the player -> parse the reply -> check the move is legal.
An illegal or unreadable reply is sent back with the reason, up to `max_illegal_retries`
extra tries; after that the player forfeits.
"""

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import chess

from app.game.models import Attempt, Color, GameRecord, MoveRecord, Termination
from app.game.moves import MoveRejected, resolve_move
from app.game.parsing import parse_reply
from app.game.pgn import build_pgn
from app.game.players import Player
from app.game.prompt import retry_prompt, system_prompt, turn_prompt
from app.llm.openrouter import LLMError, LLMResponse, LLMTimeout

MoveCallback = Callable[[MoveRecord], Awaitable[None] | None]
RejectCallback = Callable[[Color, Attempt], Awaitable[None] | None]

ANSWER_FORMAT = 'Answer with JSON like {"reasoning": "...", "move": "e4"}.'
NO_MOVE_FOUND = f"No move found in your reply. {ANSWER_FORMAT}"


def no_move_error(reply: LLMResponse) -> str:
    """Why a reply had no move. Also sent back to the model, so it says what to change."""
    if reply.finish_reason == "length":
        # Reasoning models spend hidden "thinking" tokens first; those count toward the limit.
        used = f" ({reply.completion_tokens:,} tokens)" if reply.completion_tokens else ""
        what = "Empty reply" if not reply.content.strip() else "Reply cut off before the move"
        return f"{what}: ran out of tokens while thinking{used}. Think less. {ANSWER_FORMAT}"
    if not reply.content.strip():
        return f"Empty reply. {ANSWER_FORMAT}"
    return NO_MOVE_FOUND


def _color(turn: chess.Color) -> Color:
    return Color.WHITE if turn == chess.WHITE else Color.BLACK


async def _notify(callback: Callable[..., Any] | None, *args: Any) -> None:
    if callback is None:
        return
    result = callback(*args)
    if inspect.isawaitable(result):
        await result


class _TurnAborted(Exception):
    def __init__(self, error: LLMError, attempts: list[Attempt]) -> None:
        super().__init__(str(error))
        self.error = error
        self.attempts = attempts


class GameRunner:
    def __init__(
        self,
        white: Player,
        black: Player,
        *,
        max_full_moves: int = 60,
        max_illegal_retries: int = 3,
        show_legal_moves: bool = True,
        move_time_limit: float | None = None,
        on_move: MoveCallback | None = None,
        on_rejected: RejectCallback | None = None,
    ) -> None:
        self.white = white
        self.black = black
        # Seconds a player gets per reply. A slow reply counts as a failed attempt, like an
        # illegal move; running out of tries this way loses on time.
        self.move_time_limit = move_time_limit or None
        self.max_full_moves = max_full_moves
        self.max_illegal_retries = max_illegal_retries
        self.show_legal_moves = show_legal_moves
        self.on_move = on_move
        self.on_rejected = on_rejected

    async def play(self, record: GameRecord | None = None) -> GameRecord:
        """Play the game. Pass a `record` to fill in one created earlier (the API does this so
        it knows the game id up front and can save progress after every move)."""
        board = chess.Board()
        record = record or GameRecord(white_model=self.white.name, black_model=self.black.name)
        record.white_model = self.white.name
        record.black_model = self.black.name
        record.show_legal_moves = self.show_legal_moves
        record.max_full_moves = self.max_full_moves
        record.move_time_limit = self.move_time_limit

        while True:
            # claim_draw=True ends the game on threefold repetition / fifty moves right away,
            # instead of letting two models shuffle pieces forever.
            outcome = board.outcome(claim_draw=True)
            if outcome is not None:
                record.result = outcome.result()
                record.termination = Termination(outcome.termination.name.lower())
                record.winner = None if outcome.winner is None else _color(outcome.winner)
                break

            if len(board.move_stack) >= 2 * self.max_full_moves:
                record.result = "1/2-1/2"
                record.termination = Termination.MOVE_LIMIT
                break

            color = _color(board.turn)
            player = self.white if color is Color.WHITE else self.black
            try:
                move, attempts = await self._play_turn(board, player, color)
            except _TurnAborted as exc:
                record.result = "*"
                record.termination = Termination.API_ERROR
                record.error = str(exc.error)
                record.failed_attempts = exc.attempts
                record.failed_color = color
                break

            if move is None:
                record.winner = color.opponent
                record.result = "1-0" if record.winner is Color.WHITE else "0-1"
                record.termination = (
                    Termination.TIMEOUT
                    if attempts[-1].timed_out
                    else Termination.FORFEIT_ILLEGAL_MOVES
                )
                record.failed_attempts = attempts
                record.failed_color = color
                break

            move_record = MoveRecord(
                ply=len(board.move_stack) + 1,
                move_number=board.fullmove_number,
                color=color,
                san=board.san(move),
                uci=move.uci(),
                fen_before=board.fen(),
                fen_after="",
                reasoning=attempts[-1].reasoning,
                attempts=attempts,
            )
            board.push(move)
            move_record.fen_after = board.fen()
            record.moves.append(move_record)
            await _notify(self.on_move, move_record)

        record.finished_at = datetime.now(UTC)
        record.pgn = build_pgn(record)
        return record

    async def _play_turn(
        self, board: chess.Board, player: Player, color: Color
    ) -> tuple[chess.Move | None, list[Attempt]]:
        messages = [
            {"role": "system", "content": system_prompt(board.turn)},
            {"role": "user", "content": turn_prompt(board, show_legal_moves=self.show_legal_moves)},
        ]
        attempts: list[Attempt] = []

        for _ in range(1 + self.max_illegal_retries):
            try:
                reply = await player.respond(messages, timeout=self.move_time_limit)
            except LLMTimeout:
                limit = self.move_time_limit or 0
                attempt = Attempt(
                    raw_reply="",
                    error=f"No reply within {limit:g}s: time limit exceeded. "
                    "Think less and answer faster.",
                    latency_ms=int(limit * 1000),
                    timed_out=True,
                )
                attempts.append(attempt)
                await _notify(self.on_rejected, color, attempt)
                # No reply arrived, so there's no assistant message to send back.
                messages.append({"role": "user", "content": retry_prompt(attempt.error)})
                continue
            except LLMError as exc:  # API problems abort the game; they're nobody's fault
                raise _TurnAborted(exc, attempts) from exc

            parsed = parse_reply(reply.content)
            attempt = Attempt(
                raw_reply=reply.content,
                move_text=parsed.move,
                reasoning=parsed.reasoning,
                latency_ms=reply.latency_ms,
                prompt_tokens=reply.prompt_tokens,
                completion_tokens=reply.completion_tokens,
                cost_usd=reply.cost_usd,
                finish_reason=reply.finish_reason,
            )
            move: chess.Move | None = None
            if parsed.move is None:
                attempt.error = no_move_error(reply)
            else:
                try:
                    move = resolve_move(board, parsed.move)
                except MoveRejected as exc:
                    attempt.error = str(exc)
            attempts.append(attempt)

            if move is not None:
                return move, attempts

            await _notify(self.on_rejected, color, attempt)
            messages += [
                {"role": "assistant", "content": reply.content or "(empty reply)"},
                {"role": "user", "content": retry_prompt(attempt.error or NO_MOVE_FOUND)},
            ]

        return None, attempts
