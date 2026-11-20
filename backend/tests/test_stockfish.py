"""Runs the real engine. Skipped when Stockfish isn't installed."""

import pytest

from app.analysis.analyzer import analyze_record
from app.analysis.engine import EngineNotFound, Stockfish, find_stockfish
from app.game.models import MoveLabel
from app.game.runner import GameRunner
from tests.conftest import ScriptedPlayer, reply

needs_stockfish = pytest.mark.skipif(find_stockfish() is None, reason="Stockfish not installed")


@needs_stockfish
async def test_stockfish_finds_the_blunder():
    white = ScriptedPlayer("w", [reply("f3"), reply("g4")])
    black = ScriptedPlayer("b", [reply("e5"), reply("Qh4#")])
    record = await GameRunner(white, black).play()

    async with Stockfish(depth=10) as engine:
        await analyze_record(record, engine, adjudicate_min_cp=300)

    labels = [m.label for m in record.analysis.moves]
    assert labels[2] is MoveLabel.BLUNDER  # 2. g4??
    assert labels[3] is MoveLabel.BEST  # 2... Qh4#
    assert record.analysis.engine.startswith("Stockfish")
    assert record.analysis.black.accuracy > record.analysis.white.accuracy


async def test_missing_engine_is_reported():
    with pytest.raises(EngineNotFound, match="not found"):
        async with Stockfish("definitely-not-a-chess-engine"):
            pass
