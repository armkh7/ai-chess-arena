"""Command line: `uv run arena models` and `uv run arena play WHITE BLACK`."""

import asyncio
from pathlib import Path

import chess
import typer
from rich.console import Console
from rich.table import Table

from app.config import get_settings
from app.game.models import Attempt, Color, GameRecord, MoveRecord
from app.game.players import LLMPlayer
from app.game.prompt import board_diagram
from app.game.runner import GameRunner
from app.llm.openrouter import LLMError, OpenRouterClient, fetch_models

app = typer.Typer(help="AI Chess Arena: let two LLMs play chess.", no_args_is_help=True)
console = Console()


@app.command()
def models(
    free: bool = typer.Option(False, "--free", help="Only show free models."),
    search: str | None = typer.Option(None, "--search", "-s", help="Filter by text in the id."),
) -> None:
    """List models available on OpenRouter, with prices."""
    found = asyncio.run(fetch_models(get_settings().openrouter_base_url))
    if free:
        found = [m for m in found if m.is_free]
    if search:
        found = [m for m in found if search.lower() in m.id.lower()]

    table = Table(title=f"OpenRouter models ({len(found)})")
    table.add_column("Model id")
    table.add_column("$ / 1M in", justify="right")
    table.add_column("$ / 1M out", justify="right")
    table.add_column("Context", justify="right")
    for m in found:
        table.add_row(
            m.id,
            "free" if m.is_free else f"{m.prompt_price * 1e6:.2f}",
            "free" if m.is_free else f"{m.completion_price * 1e6:.2f}",
            f"{m.context_length:,}" if m.context_length else "?",
        )
    console.print(table)


def _print_move(move: MoveRecord) -> None:
    number = f"{move.move_number}." if move.color is Color.WHITE else f"{move.move_number}..."
    style = "bold white" if move.color is Color.WHITE else "bold cyan"
    seconds = move.attempts[-1].latency_ms / 1000
    retries = f" [yellow]({move.illegal_attempts} rejected)[/]" if move.illegal_attempts else ""
    console.print(f"[{style}]{number:>5} {move.san:<7}[/] [dim]{seconds:5.1f}s[/]{retries}")
    if move.reasoning:
        reasoning = move.reasoning if len(move.reasoning) <= 160 else move.reasoning[:157] + "..."
        console.print(f"        [dim italic]{reasoning}[/]", highlight=False)


def _print_rejected(color: Color, attempt: Attempt) -> None:
    tried = attempt.move_text or "no move"
    console.print(
        f"        [yellow]✗ {color.value} tried {tried}: {attempt.error}[/]", highlight=False
    )


def _print_summary(record: GameRecord) -> None:
    fen = record.moves[-1].fen_after if record.moves else chess.STARTING_FEN
    console.print()
    console.print(board_diagram(chess.Board(fen)), highlight=False)
    console.print()
    termination = record.termination.value if record.termination else "?"
    console.rule(f"[bold]Result: {record.result}[/]  ({termination.replace('_', ' ')})")
    if record.error:
        console.print(f"[red]{record.error}[/]")

    table = Table()
    table.add_column("")
    table.add_column("Model")
    table.add_column("Moves", justify="right")
    table.add_column("Rejected", justify="right")
    table.add_column("Tokens in/out", justify="right")
    table.add_column("Cost $", justify="right")
    table.add_column("Avg time", justify="right")
    for color in Color:
        s = record.player_stats(color)
        table.add_row(
            color.value,
            s.model,
            str(s.moves),
            str(s.illegal_attempts),
            f"{s.prompt_tokens:,} / {s.completion_tokens:,}",
            f"{s.cost_usd:.4f}",
            f"{s.avg_latency_ms / 1000:.1f}s",
        )
    console.print(table)


def save_game(record: GameRecord, folder: Path) -> tuple[Path, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / f"{record.id}.json"
    pgn_path = folder / f"{record.id}.pgn"
    json_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    pgn_path.write_text(record.pgn + "\n", encoding="utf-8")
    return json_path, pgn_path


@app.command()
def play(
    white: str = typer.Argument(..., help="Model id for White, e.g. openai/gpt-4o-mini"),
    black: str = typer.Argument(..., help="Model id for Black"),
    max_moves: int | None = typer.Option(
        None, "--max-moves", help="Moves per side before the game stops (default from settings)."
    ),
    legal_moves: bool = typer.Option(
        True, "--legal-moves/--no-legal-moves", help="Give models the list of legal moves."
    ),
    out: Path = typer.Option(Path("games"), "--out", help="Folder to save the game in."),
) -> None:
    """Play one game between two OpenRouter models."""
    settings = get_settings()
    try:
        client = OpenRouterClient.from_settings(settings)
    except LLMError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc

    runner = GameRunner(
        LLMPlayer(client, white),
        LLMPlayer(client, black),
        max_full_moves=max_moves or settings.max_full_moves,
        max_illegal_retries=settings.max_illegal_retries,
        show_legal_moves=legal_moves,
        on_move=_print_move,
        on_rejected=_print_rejected,
    )
    mode = "legal moves shown" if legal_moves else "no legal-move list"
    console.rule(f"[bold]{white}[/] (White) vs [bold cyan]{black}[/] (Black)  ·  {mode}")
    record = asyncio.run(runner.play())

    _print_summary(record)
    json_path, pgn_path = save_game(record, out)
    console.print(f"Saved: {json_path}  and  {pgn_path}")


if __name__ == "__main__":
    app()
