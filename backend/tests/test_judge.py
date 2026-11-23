"""The judge agent: its tools, its loop with a scripted chat model, and the API flow."""

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.analysis.analyzer import analyze_record
from app.config import Settings
from app.game.models import GameRecord, JudgeReport, JudgeResult, JudgeStep
from app.game.runner import GameRunner
from app.judge.agent import LangChainJudge
from app.judge.tools import GameView, make_tools, step_title
from app.main import create_app
from tests.conftest import ScriptedPlayer, reply
from tests.test_api import FOOLS_MATE, MODELS, LevelEngine, RateLimitedPlayer, level_engine, start

REPORT = {
    "headline": "Queen strikes on move 2",
    "summary": "White weakened the king and Black mated at once.",
    "key_moments": [
        {
            "ply": 3,
            "title": "The fatal pawn push",
            "what_happened": "2. g4 opened the diagonal to the king.",
            "reasoning_check": "White called it an attack; it was a blunder.",
            "reasoning_matched": False,
        }
    ],
    "white": {
        "strengths": "None.",
        "weaknesses": "Opened its own king.",
        "reasoning_quality": "Described threats that weren't there.",
        "grade": "F",
    },
    "black": {
        "strengths": "Saw the mate.",
        "weaknesses": "Nothing to test it.",
        "reasoning_quality": "Accurate.",
        "grade": "A",
    },
}


async def fools_mate() -> GameRecord:
    record = await GameRunner(
        ScriptedPlayer(
            "w/model", [reply("f3", "Make room."), reply("g4", "Attack on the kingside!")]
        ),
        ScriptedPlayer("b/model", [reply("e5"), reply("Qh4#", "Mate on the diagonal.")]),
    ).play()
    await analyze_record(record, LevelEngine(), 300)
    return record


def tool(tools, name):
    return next(t for t in tools if t.name == name)


async def test_tools_show_the_game_to_the_agent():
    record = await fools_mate()
    tools = make_tools(record)

    overview = tool(tools, "get_game_overview").invoke({"purpose": "who won"})
    assert "Result: 0-1, ended by checkmate" in overview
    assert "White (w/model)" in overview

    move = tool(tools, "get_move_details").invoke({"ply": 3, "purpose": "the blunder"})
    assert "ply 3: 2. g4 by White (w/model)" in move
    assert "The model's explanation: Attack on the kingside!" in move
    assert "Stockfish:" in move

    board = tool(tools, "show_board").invoke({"ply": 4, "purpose": "the mate"})
    assert "Board after 2... Qh4#. White to move, in check." in board
    assert "q" in board  # the black queen on the text board

    moves = tool(tools, "get_moves").invoke({"from_ply": 1, "to_ply": 99, "purpose": "all"})
    assert moves.count("\n") == 3  # four plies, capped at the end of the game
    assert "No move at ply 9" in tool(tools, "get_move_details").invoke({"ply": 9, "purpose": "x"})

    report = tool(tools, "submit_report").invoke(REPORT)
    assert JudgeReport.model_validate_json(report).white.grade == "F"


async def test_step_titles_use_chess_notation():
    view = GameView(await fools_mate())
    assert step_title(view, "get_move_details", {"ply": 4}) == "Move 2... Qh4#"
    assert step_title(view, "show_board", {"ply": 0}) == "Starting position"
    assert step_title(view, "get_moves", {"from_ply": 1, "to_ply": 3}) == "Moves 1. f3 to 2. g4"


class ScriptedChatModel(GenericFakeChatModel):
    """Replies with pre-written messages and accepts tools, like a real chat model."""

    def bind_tools(self, tools, **kwargs):
        return self


def call(name, args, id):
    return {"name": name, "args": args, "id": id, "type": "tool_call"}


async def test_agent_streams_its_steps_and_returns_the_report():
    record = await fools_mate()
    model = ScriptedChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    additional_kwargs={"reasoning_content": "Start with the overview."},
                    tool_calls=[call("get_game_overview", {"purpose": "See who won."}, "1")],
                    response_metadata={"cost": 0.001},
                    usage_metadata={"input_tokens": 500, "output_tokens": 50, "total_tokens": 550},
                ),
                AIMessage(
                    content="",
                    tool_calls=[call("get_move_details", {"ply": 3, "purpose": "Check g4."}, "2")],
                    response_metadata={"cost": 0.002},
                ),
                AIMessage(content="", tool_calls=[call("submit_report", REPORT, "3")]),
            ]
        )
    )
    seen = []
    result = await LangChainJudge(model, "fake/judge").judge(record, seen.append)

    assert result.error is None
    assert result.report.headline == "Queen strikes on move 2"
    assert [(s.kind, s.title) for s in result.steps] == [
        ("thinking", None),
        ("tool", "Game overview"),
        ("tool", "Move 2. g4"),
        ("tool", "Final report"),
    ]
    assert result.steps[1].text == "See who won."
    assert seen == result.steps  # every step was reported live
    assert result.cost_usd == pytest.approx(0.003)
    assert result.input_tokens == 500


async def test_agent_without_a_report_is_an_error_not_a_crash():
    record = await fools_mate()
    model = ScriptedChatModel(messages=iter([AIMessage(content="I think White lost.")]))
    result = await LangChainJudge(model, "fake/judge").judge(record)
    assert result.report is None
    assert result.error == "The judge finished without submitting a report."
    assert result.steps[0].text == "I think White lost."


INVALID_REPORT = {k: v for k, v in REPORT.items() if k != "black"}  # a required field missing


async def test_a_rejected_report_goes_back_to_the_judge_to_fix():
    # Regression: submit_report used to be return_direct, and LangChain ends the run after a
    # return_direct tool even when it fails, so one invalid report meant no report at all.
    record = await fools_mate()
    model = ScriptedChatModel(
        messages=iter(
            [
                AIMessage(content="", tool_calls=[call("submit_report", INVALID_REPORT, "1")]),
                AIMessage(content="", tool_calls=[call("submit_report", REPORT, "2")]),
            ]
        )
    )
    result = await LangChainJudge(model, "fake/judge").judge(record)
    assert result.error is None
    assert result.report.black.grade == "A"
    assert [s.tool for s in result.steps] == ["submit_report", "submit_report"]


async def test_a_report_never_fixed_says_why_it_was_rejected():
    record = await fools_mate()
    model = ScriptedChatModel(
        messages=iter(
            [
                AIMessage(content="", tool_calls=[call("submit_report", INVALID_REPORT, "1")]),
                AIMessage(content="I can't fix it."),
            ]
        )
    )
    result = await LangChainJudge(model, "fake/judge").judge(record)
    assert result.report is None
    assert result.error.startswith("The judge's report was rejected:")
    assert "black" in result.error  # the validation message names the missing field


class ScriptedJudge:
    async def judge(self, record, on_step=None):
        steps = [
            JudgeStep(kind="thinking", text="Looking at the mate."),
            JudgeStep(
                kind="tool",
                text="Check the last move.",
                tool="get_move_details",
                title="Move 2... Qh4#",
            ),
        ]
        for step in steps:
            on_step(step)
        return JudgeResult(
            model="fake/judge", steps=steps, report=JudgeReport.model_validate(REPORT)
        )


@pytest.fixture
async def api():
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite://",
        create_tables_on_startup=True,
        move_time_limit_seconds=0,
        public_models_file="",
    )

    async def models():
        return MODELS

    app = create_app(
        settings,
        make_player=lambda model, effort, cb: RateLimitedPlayer(model, list(FOOLS_MATE[model]), cb),
        make_evaluator=level_engine,
        model_source=models,
        make_judge=ScriptedJudge,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            client.service = app.state.service
            yield client


async def test_games_are_judged_after_the_analysis(api):
    game_id = await start(api)
    channel = api.service.live[game_id]
    await api.service.wait_all()

    events = [(e.type, e.data.get("status")) for e in channel.history]
    tail = [t for t, _ in events[-6:]]
    assert tail == ["analysis", "status", "judge_step", "judge_step", "judge", "end"]
    assert ("status", "judging") in events

    game = (await api.get(f"/games/{game_id}")).json()["game"]
    assert game["judge"]["report"]["black"]["grade"] == "A"
    assert game["judge"]["steps"][1]["title"] == "Move 2... Qh4#"

    replay = (await api.get(f"/games/{game_id}/stream")).text
    assert replay.count("event: judge_step") == 2
    assert "event: judge\n" in replay


async def test_judge_can_be_skipped(api):
    game_id = await start(api, judge=False)
    await api.service.wait_all()
    assert (await api.get(f"/games/{game_id}")).json()["game"]["judge"] is None
