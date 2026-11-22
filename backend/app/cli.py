"""Command line: `uv run arena models` and `uv run arena play WHITE BLACK`."""

import asyncio
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import chess
import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from app.analysis.analyzer import analyze_record
from app.analysis.engine import EngineNotFound, Stockfish
from app.analysis.metrics import format_eval
from app.config import Settings, get_settings
from app.game.models import (
    Attempt,
    Color,
    GameRecord,
    JudgeStep,
    MoveLabel,
    MoveRecord,
    Termination,
)
from app.game.players import LLMPlayer
from app.game.prompt import board_diagram
from app.game.runner import GameRunner
from app.judge.agent import LangChainJudge
from app.llm.openrouter import LLMError, OpenRouterClient, fetch_models


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


app = typer.Typer(help="AI Chess Arena: let two LLMs play chess.", no_args_is_help=True)
# emoji=False: otherwise rich turns text like "gemma:free: Error" into the 🆓 emoji.
console = Console(emoji=False)


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
    if attempt.timed_out:
        seconds = attempt.latency_ms / 1000
        console.print(f"        [yellow]⏱ {color.value} ran out of time ({seconds:g}s)[/]")
        return
    tried = escape(attempt.move_text or "no move")
    console.print(
        f"        [yellow]✗ {color.value} tried {tried}: {escape(attempt.error or '')}[/]",
        highlight=False,
    )


def _print_rate_limit(model: str, seconds: float, retry: int) -> None:
    console.print(
        f"        [yellow]⏳ {escape(model)} is rate limited, waiting {seconds:.0f}s "
        f"(retry {retry})[/]",
        highlight=False,
    )


def _print_summary(record: GameRecord) -> None:
    fen = record.moves[-1].fen_after if record.moves else chess.STARTING_FEN
    console.print()
    console.print(board_diagram(chess.Board(fen)), highlight=False)
    console.print()
    termination = record.termination.value if record.termination else "?"
    console.rule(f"[bold]Result: {record.result}[/]  ({termination.replace('_', ' ')})")
    if record.analysis and record.termination in (Termination.MOVE_LIMIT, Termination.ADJUDICATION):
        verdict = f"so {record.winner.value} wins" if record.winner else "too close to call: a draw"
        console.print(
            f"Move limit reached. Stockfish rates the final position "
            f"{format_eval(record.analysis.final_eval)}, {verdict}."
        )
    if record.error:
        console.print(record.error, style="red", markup=False, highlight=False)

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


LABEL_STYLES = {
    MoveLabel.INACCURACY: ("?!", "yellow"),
    MoveLabel.MISTAKE: ("?", "dark_orange"),
    MoveLabel.BLUNDER: ("??", "red"),
}


def _print_analysis(record: GameRecord) -> None:
    analysis = record.analysis
    if analysis is None:
        return
    table = Table(title=f"{analysis.engine} analysis (depth {analysis.depth})")
    table.add_column("")
    table.add_column("Model")
    table.add_column("Accuracy", justify="right")
    table.add_column("Avg loss", justify="right")
    for label in MoveLabel:
        table.add_column(label.value.capitalize(), justify="right")
    for color in Color:
        player = analysis.player(color)
        accuracy = f"{player.accuracy:.1f}%" if player.accuracy is not None else "-"
        table.add_row(
            color.value,
            record.model_for(color),
            accuracy,
            f"{player.acpl} cp",
            *(str(player.counts.get(label, 0)) for label in MoveLabel),
        )
    console.print(table)

    moments = [
        (move, verdict)
        for move, verdict in zip(record.moves, analysis.moves, strict=True)
        if verdict.label in LABEL_STYLES
    ]
    if moments:
        console.print("[bold]Key moments[/]")
    for move, verdict in moments:
        mark, style = LABEL_STYLES[verdict.label]
        number = f"{move.move_number}." if move.color is Color.WHITE else f"{move.move_number}..."
        console.print(
            f"  {number:>5} [{style}]{move.san}{mark}[/] {verdict.label.value:<10} "
            f"{format_eval(verdict.eval_before)} → {format_eval(verdict.eval_after)}  "
            f"[dim]best: {verdict.best_san or '?'}[/]",
            highlight=False,
        )


def _analyze(record: GameRecord, settings: Settings, depth: int | None = None) -> None:
    """Run Stockfish on the game. Skipped with a warning if Stockfish isn't installed."""

    async def run() -> None:
        async with Stockfish.from_settings(settings, depth) as engine:
            await analyze_record(record, engine, settings.adjudicate_min_cp)

    try:
        with console.status(f"Analyzing {len(record.moves)} moves with Stockfish..."):
            asyncio.run(run())
    except EngineNotFound as exc:
        console.print(f"Skipping analysis: {exc}", style="yellow", markup=False)


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
    analysis: bool = typer.Option(
        True, "--analysis/--no-analysis", help="Analyze the game with Stockfish afterwards."
    ),
    effort: Effort | None = typer.Option(
        None,
        "--effort",
        help="How long reasoning models think (default: REASONING_EFFORT, else the model's own).",
    ),
    move_time: float | None = typer.Option(
        None, "--move-time", help="Seconds per reply, 0 = no limit (default from settings)."
    ),
) -> None:
    """Play one game between two OpenRouter models."""
    settings = get_settings()
    try:
        client = OpenRouterClient.from_settings(settings)
    except LLMError as exc:
        console.print(str(exc), style="red", markup=False)
        raise typer.Exit(1) from exc
    client.on_rate_limit = _print_rate_limit
    if effort:
        client.reasoning_effort = effort.value

    runner = GameRunner(
        LLMPlayer(client, white),
        LLMPlayer(client, black),
        max_full_moves=max_moves or settings.max_full_moves,
        max_illegal_retries=settings.max_illegal_retries,
        show_legal_moves=legal_moves,
        move_time_limit=settings.move_time_limit_seconds if move_time is None else move_time,
        on_move=_print_move,
        on_rejected=_print_rejected,
    )
    mode = "legal moves shown" if legal_moves else "no legal-move list"
    if client.reasoning_effort:
        mode += f"  ·  {client.reasoning_effort} effort"
    if runner.move_time_limit:
        mode += f"  ·  {runner.move_time_limit:g}s per move"
    console.rule(f"[bold]{white}[/] (White) vs [bold cyan]{black}[/] (Black)  ·  {mode}")
    record = asyncio.run(runner.play())
    record.reasoning_effort = client.reasoning_effort

    if not record.moves:
        _print_summary(record)
        console.print("[dim]Not saved: no moves were played.[/]")
        return
    if analysis:
        _analyze(record, settings)
    _print_summary(record)
    _print_analysis(record)
    json_path, pgn_path = save_game(record, out)
    console.print(f"Saved: {json_path}  and  {pgn_path}")


@app.command()
def analyze(
    game: Path = typer.Argument(..., help="A saved game, e.g. games/<id>.json", exists=True),
    depth: int | None = typer.Option(None, "--depth", help="Search depth (default from settings)."),
) -> None:
    """Analyze a saved game with Stockfish and update its JSON and PGN files."""
    settings = get_settings()
    record = GameRecord.model_validate_json(game.read_text(encoding="utf-8"))
    console.rule(f"[bold]{record.white_model}[/] (White) vs [bold cyan]{record.black_model}[/]")
    _analyze(record, settings, depth)
    _print_summary(record)
    _print_analysis(record)
    if record.analysis:
        json_path, pgn_path = save_game(record, game.parent)
        console.print(f"Updated: {json_path}  and  {pgn_path}")


@app.command()
def judge(
    game: Path = typer.Argument(
        ..., help="A saved, analyzed game, e.g. games/<id>.json", exists=True
    ),
    model: str | None = typer.Option(None, "--model", help="Judge model (default: JUDGE_MODEL)."),
) -> None:
    """Let the judge agent review a saved game; shows each step, then saves the report."""
    settings = get_settings()
    record = GameRecord.model_validate_json(game.read_text(encoding="utf-8"))
    if not record.analysis:
        console.print(f"Analyze it first: uv run arena analyze {game}", style="yellow")
        raise typer.Exit(1)
    if model:
        settings = settings.model_copy(update={"judge_model": model})
    judge_agent = LangChainJudge.from_settings(settings)
    console.rule(f"[bold]Judge agent[/] ({escape(settings.judge_model)})")

    def on_step(step: JudgeStep) -> None:
        if step.kind == "thinking":
            console.print(f"[dim italic]{escape(step.text)}[/]", highlight=False)
        else:
            console.print(
                f"[cyan]→ {escape(step.title or '')}[/]  {escape(step.text)}", highlight=False
            )

    result = asyncio.run(judge_agent.judge(record, on_step))
    record.judge = result
    console.print(
        f"[dim]{len(result.steps)} steps, {result.seconds:.0f} s, "
        f"{result.input_tokens:,} + {result.output_tokens:,} tokens, ${result.cost_usd:.4f}[/]"
    )
    if result.error or not result.report:
        console.print(f"Judge failed: {result.error}", style="red", markup=False)
        raise typer.Exit(1)
    report = result.report
    console.rule(f"[bold]{escape(report.headline)}[/]")
    console.print(report.summary, markup=False)
    for moment in report.key_moments:
        mark = "[green]✓[/]" if moment.reasoning_matched else "[red]✗[/]"
        console.print(f"\n[bold]{escape(moment.title)}[/] (ply {moment.ply})")
        console.print(f"  {escape(moment.what_happened)}", highlight=False)
        console.print(f"  {mark} {escape(moment.reasoning_check)}", highlight=False)
    for color, verdict in (("White", report.white), ("Black", report.black)):
        console.print(f"\n[bold]{color}: {verdict.grade}[/]  {escape(verdict.reasoning_quality)}")
    json_path, _ = save_game(record, game.parent)
    console.print(f"\nUpdated: {json_path}")


def _read_models(models: list[str] | None, models_file: Path | None) -> list[str]:
    names = list(models or [])
    if models_file:
        for line in models_file.read_text(encoding="utf-8").splitlines():
            if name := line.split("#", 1)[0].strip():
                names.append(name)
    return list(dict.fromkeys(names))  # drop duplicates, keep order


# Rough tokens per reply for the cost estimate: the prompt (board, history, legal moves)
# and the answer including some hidden thinking at low effort.
EST_PROMPT_TOKENS = 1_200
EST_COMPLETION_TOKENS = 800


@app.command()
def benchmark(
    models: list[str] | None = typer.Argument(None, help="Model ids to compare."),
    models_file: Path | None = typer.Option(
        None, "--models-file", exists=True, help="File with one model id per line (# comments)."
    ),
    games_per_pair: int = typer.Option(
        1, "--games-per-pair", min=1, help="Games each pair plays (2 = once with each color)."
    ),
    max_moves: int = typer.Option(20, "--max-moves", min=1, help="Moves per side per game."),
    concurrency: int = typer.Option(2, "--concurrency", min=1, help="Games played at once."),
    effort: Effort = typer.Option(Effort.LOW, "--effort", help="Reasoning effort for all models."),
    move_time: float | None = typer.Option(
        None, "--move-time", help="Seconds per reply (default from settings)."
    ),
    out: Path = typer.Option(Path("benchmarks"), "--out", help="Folder for the results."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Start without asking."),
) -> None:
    """Round-robin tournament: rank models by reliability, speed, strength and cost."""
    from app.analysis.engine import find_stockfish
    from app.benchmark import HEADERS, pairings, run_games, summarize, table_rows, to_markdown

    settings = get_settings()
    names = _read_models(models, models_file)
    if len(names) < 2:
        console.print("Give at least two models.", style="red")
        raise typer.Exit(1)

    catalog = {m.id: m for m in asyncio.run(fetch_models(settings.openrouter_base_url))}
    if unknown := [n for n in names if n not in catalog]:
        console.print(f"Unknown model(s): {', '.join(unknown)}", style="red", markup=False)
        raise typer.Exit(1)

    games = pairings(names, games_per_pair)
    per_model = len(games) * 2 // len(names)  # games each model plays
    cost = sum(
        per_model
        * max_moves
        * (
            EST_PROMPT_TOKENS * catalog[n].prompt_price
            + EST_COMPLETION_TOKENS * catalog[n].completion_price
        )
        for n in names
    )
    limit = settings.move_time_limit_seconds if move_time is None else move_time
    console.rule("[bold]Benchmark plan[/]")
    console.print(
        f"{len(names)} models, {len(games)} games ({per_model} per model), up to {max_moves} "
        f"moves per side, {concurrency} at a time, {effort.value} effort, {limit:g}s per reply.",
        highlight=False,
    )
    console.print(
        f"At most ~{len(games) * 2 * max_moves:,} OpenRouter requests, "
        f"rough cost ${cost:.2f} (free models cost $0).",
        highlight=False,
    )
    if find_stockfish(settings.stockfish_path) is None:
        console.print("Stockfish not found: accuracy will be missing.", style="yellow")
    if not yes and not typer.confirm("Start?"):
        raise typer.Exit()

    try:
        client = OpenRouterClient.from_settings(settings)
    except LLMError as exc:
        console.print(str(exc), style="red", markup=False)
        raise typer.Exit(1) from exc
    folder = out / datetime.now().strftime("%Y%m%d-%H%M")
    done = 0

    async def play(white: str, black: str) -> GameRecord:
        runner = GameRunner(
            LLMPlayer(client, white, reasoning_effort=effort.value),
            LLMPlayer(client, black, reasoning_effort=effort.value),
            max_full_moves=max_moves,
            max_illegal_retries=settings.max_illegal_retries,
            move_time_limit=limit,
        )
        record = await runner.play()
        record.reasoning_effort = effort.value
        if record.moves:
            try:
                async with Stockfish.from_settings(settings) as engine:
                    await analyze_record(record, engine, settings.adjudicate_min_cp)
            except EngineNotFound:
                pass
        save_game(record, folder / "games")
        return record

    def on_done(record: GameRecord) -> None:
        nonlocal done
        done += 1
        ending = record.termination.value.replace("_", " ") if record.termination else "crash"
        seconds = (
            (record.finished_at - record.started_at).total_seconds() if record.finished_at else 0
        )
        console.print(
            f"[{done}/{len(games)}] {record.white_model} vs {record.black_model}: "
            f"{record.result} ({ending}, {len(record.moves)} plies, {seconds / 60:.1f} min)",
            highlight=False,
            markup=False,
        )

    async def run_all() -> list[GameRecord]:
        try:
            return await run_games(games, play, concurrency=concurrency, on_done=on_done)
        finally:
            await client.aclose()

    results = summarize(asyncio.run(run_all()))

    table = Table(title="Benchmark results")
    for header in HEADERS:
        table.add_column(header, justify="left" if header in ("Model", "Failures") else "right")
    for row in table_rows(results):
        table.add_row(*row)
    console.print(table)

    notes = [
        f"- Date: {datetime.now():%Y-%m-%d %H:%M}",
        f"- {len(games)} games, up to {max_moves} moves per side, {effort.value} effort, "
        f"{limit:g}s per reply",
        "- Finish = games without forfeit, timeout or API error. Score = win 1, draw 0.5.",
    ]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "results.md").write_text(
        to_markdown(results, "Model benchmark", notes), encoding="utf-8"
    )
    (folder / "results.json").write_text(
        json.dumps([r.as_dict() for r in results], indent=2), encoding="utf-8"
    )
    console.print(f"Saved: {folder}/results.md, results.json and games/", highlight=False)


if __name__ == "__main__":
    app()
