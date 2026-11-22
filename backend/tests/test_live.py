import asyncio

from app.live import PING, SYNCED, GameChannel


async def collect(channel: GameChannel, **kwargs) -> list[str]:
    return [event.type async for event in channel.subscribe(**kwargs)]


async def test_late_viewer_gets_history_then_live_events():
    channel = GameChannel()
    channel.publish("game", {})
    channel.publish("move", {"ply": 1})

    viewer = asyncio.create_task(collect(channel))
    await asyncio.sleep(0)  # the viewer subscribes and reads the history
    channel.publish("move", {"ply": 2})
    channel.publish("end", {})
    channel.close()

    # "synced" marks where the history ends and live events begin
    assert await viewer == ["game", "move", "synced", "move", "end"]


async def test_viewer_after_the_end_gets_everything_and_stops():
    channel = GameChannel()
    channel.publish("game", {})
    channel.publish("end", {})
    channel.close()
    assert await collect(channel) == ["game", "end", "synced"]


async def test_idle_stream_sends_pings():
    channel = GameChannel()
    events = channel.subscribe(ping_after=0.01)
    assert await anext(events) is SYNCED  # no history yet
    assert await anext(events) is PING
    await events.aclose()
