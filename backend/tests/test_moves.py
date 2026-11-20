import chess
import pytest

from app.game.moves import MoveRejected, resolve_move


def test_san_move():
    assert resolve_move(chess.Board(), "Nf3") == chess.Move.from_uci("g1f3")


def test_uci_move():
    assert resolve_move(chess.Board(), "e2e4") == chess.Move.from_uci("e2e4")


def test_illegal_move():
    with pytest.raises(MoveRejected, match="not a legal move"):
        resolve_move(chess.Board(), "Ke2")


def test_garbage():
    with pytest.raises(MoveRejected):
        resolve_move(chess.Board(), "hello")


def test_ambiguous_move():
    board = chess.Board("4k3/8/8/8/8/8/8/N1N1K3 w - - 0 1")  # knights on a1 and c1 both reach b3
    with pytest.raises(MoveRejected, match="ambiguous"):
        resolve_move(board, "Nb3")
    assert resolve_move(board, "Nab3") == chess.Move.from_uci("a1b3")


def test_check_hint():
    board = chess.Board()
    for san in ["e4", "f5", "Qh5+"]:
        board.push_san(san)
    with pytest.raises(MoveRejected, match="in check"):
        resolve_move(board, "a6")
