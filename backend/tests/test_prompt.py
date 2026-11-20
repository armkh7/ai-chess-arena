import chess

from app.game.prompt import board_diagram, move_history, system_prompt, turn_prompt


def test_system_prompt_names_the_color():
    assert "You play Black" in system_prompt(chess.BLACK)


def test_first_turn():
    text = turn_prompt(chess.Board(), show_legal_moves=True)
    assert "You are White" in text
    assert "No moves yet" in text
    assert chess.STARTING_FEN in text
    assert "Legal moves: " in text and "Nf3" in text


def test_legal_moves_hidden():
    assert "Legal moves" not in turn_prompt(chess.Board(), show_legal_moves=False)


def test_history_and_check():
    board = chess.Board()
    for san in ["e4", "f5", "Qh5+"]:
        board.push_san(san)
    assert move_history(board) == "1. e4 f5 2. Qh5+"
    text = turn_prompt(board, show_legal_moves=False)
    assert "You are Black" in text
    assert "You are in check." in text


def test_board_diagram_orientation():
    lines = board_diagram(chess.Board()).splitlines()
    assert lines[0] == "8 r n b q k b n r"
    assert lines[7] == "1 R N B Q K B N R"
    assert lines[8] == "  a b c d e f g h"
