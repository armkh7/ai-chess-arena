import pytest

from app.game.parsing import clean_move, parse_reply


def test_plain_json():
    parsed = parse_reply('{"reasoning": "Control the center.", "move": "e4"}')
    assert parsed.move == "e4"
    assert parsed.reasoning == "Control the center."


def test_json_in_code_fence_with_extra_text():
    text = (
        'Sure! Here is my move:\n```json\n{"reasoning": "Develop.", "move": "Nf3"}\n```\nGood luck.'
    )
    assert parse_reply(text).move == "Nf3"


def test_think_block_is_ignored():
    text = '<think>Maybe {"move": "h4"}? No.</think>{"reasoning": "Solid.", "move": "d4"}'
    assert parse_reply(text).move == "d4"


def test_last_json_object_wins():
    text = '{"move": "e4"} wait, actually {"reasoning": "better", "move": "c4"}'
    assert parse_reply(text).move == "c4"


def test_free_text_move_field():
    assert parse_reply("I think the best is... move: Bb5").move == "Bb5"


def test_bare_move():
    assert parse_reply("exd5").move == "exd5"


def test_no_move():
    assert parse_reply("I resign, this is too hard.").move is None
    assert parse_reply("").move is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1. e4", "e4"),
        ("12... Nf6", "Nf6"),
        ("Nf3!?", "Nf3"),
        ("Qxf7#", "Qxf7#"),
        ("0-0", "O-O"),
        ("0-0-0", "O-O-O"),
        ("`e8=Q`", "e8=Q"),
    ],
)
def test_clean_move(raw, expected):
    assert clean_move(raw) == expected
