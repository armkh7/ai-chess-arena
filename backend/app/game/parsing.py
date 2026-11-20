"""Pull the move and reasoning out of a model's reply, however messy it is."""

import json
import re

from pydantic import BaseModel

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_MOVE_FIELD = re.compile(r"""["']?move["']?\s*[:=]\s*["']?([^"'\s,}]+)""", re.IGNORECASE)
_SAN = re.compile(r"^(?:O-O(?:-O)?|[KQRBN]?[a-h]?[1-8]?x?[a-h][1-8](?:=?[QRBN])?)[+#]?$")
_UCI = re.compile(r"^[a-h][1-8][a-h][1-8][qrbn]?$")
_MOVE_NUMBER_PREFIX = re.compile(r"^\d+\.(?:\.\.)?\s*")


class ParsedReply(BaseModel):
    move: str | None
    reasoning: str | None


def clean_move(text: str) -> str:
    """Normalize how models tend to write moves: '12... Nf3!?' -> 'Nf3', '0-0' -> 'O-O'."""
    move = text.strip().strip("`\"'.,;")
    move = _MOVE_NUMBER_PREFIX.sub("", move)
    move = move.rstrip("!?")
    move = move.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    return move.strip()


def looks_like_move(text: str) -> bool:
    return bool(_SAN.match(text) or _UCI.match(text))


def _json_objects(text: str) -> list[dict]:
    """Every JSON object that can be decoded from somewhere in `text`."""
    decoder = json.JSONDecoder()
    found = []
    for i, char in enumerate(text):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            found.append(obj)
    return found


def parse_reply(text: str) -> ParsedReply:
    text = _THINK_BLOCK.sub("", text or "").strip()
    if not text:
        return ParsedReply(move=None, reasoning=None)

    # 1. A JSON object with a "move" field (the format we ask for). Prefer the last one.
    for obj in reversed(_json_objects(text)):
        if obj.get("move"):
            reasoning = obj.get("reasoning")
            return ParsedReply(
                move=clean_move(str(obj["move"])),
                reasoning=str(reasoning).strip() if reasoning else None,
            )

    # 2. Something like `move: e4` in free text.
    if match := _MOVE_FIELD.search(text):
        return ParsedReply(move=clean_move(match.group(1)), reasoning=None)

    # 3. The whole reply is just a move.
    candidate = clean_move(text)
    if looks_like_move(candidate):
        return ParsedReply(move=candidate, reasoning=None)

    return ParsedReply(move=None, reasoning=None)
