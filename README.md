# AI Chess Arena

Pick any two LLMs from [OpenRouter](https://openrouter.ai) and watch them play chess against each other.
Every move is checked for legality, illegal moves get a few retries, and every reply, token and cent is recorded.

## How a turn works

1. The model gets the position (FEN, move history, a text board and, optionally, the list of legal moves).
2. It replies with JSON: `{"reasoning": "...", "move": "Nf3"}`.
3. The move is parsed (it also copes with code fences, `<think>` blocks, `0-0`, `12... Nf6`, `e2e4`) and checked with [python-chess](https://python-chess.readthedocs.io).
4. If the move is illegal or unreadable, the model is told why and tries again, up to 3 more times. After that it forfeits.

A game ends on checkmate, stalemate, a draw by the rules (threefold repetition, fifty moves, insufficient material), a forfeit, or the move limit.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and an [OpenRouter API key](https://openrouter.ai/keys).

```bash
cp .env.example .env          # then put your OPENROUTER_API_KEY in .env
cd backend
uv sync
```

List models (add `--free` for free ones, `-s gemma` to search):

```bash
uv run arena models --free
```

Play a game:

```bash
uv run arena play google/gemma-4-31b-it:free nvidia/nemotron-3.5-lightning:free --max-moves 30
```

Use `--no-legal-moves` for "hard mode", where models don't see the list of legal moves.
Each game is saved to `backend/games/<id>.json` (every attempt, token count and cost) and `<id>.pgn`, which opens in any chess app with each model's reasoning as move comments.

## Development

```bash
cd backend
uv run pytest          # tests (no network calls)
uv run ruff check .    # lint
uv run ruff format .   # format
```

Run the API and Postgres with Docker Compose:

```bash
docker compose up --build    # API health check at http://localhost:8000/health
```

## Project structure

```
backend/
  app/
    cli.py              # `arena` command
    config.py           # settings from .env
    main.py             # FastAPI app
    llm/openrouter.py   # OpenRouter client: chat, cost tracking, model list
    game/
      runner.py         # game loop: turns, retries, forfeits, endings
      prompt.py         # what the models are told
      parsing.py        # pulling the move out of messy replies
      moves.py          # legality checks with helpful error messages
      models.py         # game, move and attempt records
      pgn.py            # PGN export
  tests/
docker-compose.yml
```
