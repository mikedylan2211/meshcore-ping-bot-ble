import asyncio
from types import SimpleNamespace

import pytest
from meshcore import EventType
from meshcore.events import Event

from pingbot import PingBot, format_path_info, is_ping, split_sender_and_body


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            {"path_len": 3, "path_hash_mode": 0, "path": "aabbcc"},
            "(3 hops, aa:bb:cc)",
        ),
        (
            {"path_len": 2, "path_hash_mode": 1, "path": "a1a2b1b2"},
            "(2 hops, a1a2:b1b2)",
        ),
        (
            {"path_len": 2, "path_hash_mode": 2, "path": "010203aabbcc"},
            "(2 hops, 010203:aabbcc)",
        ),
        ({"path_len": 0, "path_hash_mode": 0, "path": ""}, "(0 hops, zero-hop)"),
        ({"path_len": 0xFF, "path_hash_mode": -1}, "(direct)"),
        ({"path_len": 2, "path_hash_mode": 1}, "(2 hops, path unavailable)"),
        (
            {"path_len": 2, "path_hash_mode": 1, "path": "aabb"},
            "(2 hops, path unavailable)",
        ),
    ],
)
def test_format_path_info(message, expected):
    assert format_path_info(message) == expected


def test_path_hash_size_can_be_inferred_for_compatible_payloads():
    assert format_path_info({"path_len": 2, "path": bytes.fromhex("01020304")}) == (
        "(2 hops, 0102:0304)"
    )


def test_long_paths_are_abbreviated_without_losing_hop_count():
    assert format_path_info(
        {"path_len": 10, "path_hash_mode": 0, "path": bytes(range(10))},
        max_nodes=4,
    ) == "(10 hops, 00:01:...:08:09)"


def test_ping_detection_uses_message_body_not_sender_name():
    sender, body = split_sender_and_body("pingmaster: all quiet")
    assert sender == "pingmaster"
    assert not is_ping(body)
    assert is_ping("please PING now")
    assert not is_ping("spinglass")


class FakeCommands:
    def __init__(self):
        self.sent = []
        self.channel_result = Event(EventType.CHANNEL_INFO, {"channel_idx": 1})

    async def get_channel(self, channel_idx):
        self.loaded_channel = channel_idx
        return self.channel_result

    async def send_chan_msg(self, channel_idx, text):
        self.sent.append((channel_idx, text))
        return Event(EventType.OK, {})


class FakeMeshCore:
    def __init__(self):
        self.commands = FakeCommands()
        self.decrypt_channel_logs = False

    def set_decrypt_channel_logs(self, enabled):
        self.decrypt_channel_logs = enabled


def test_prepare_enables_correlated_channel_logs_and_loads_channel():
    async def scenario():
        meshcore = FakeMeshCore()
        bot = PingBot(meshcore, 1)
        await bot.prepare()
        assert meshcore.decrypt_channel_logs is True
        assert meshcore.commands.loaded_channel == 1

    asyncio.run(scenario())


def test_channel_ping_gets_one_pong_with_correlated_multibyte_path():
    async def scenario():
        meshcore = FakeMeshCore()
        bot = PingBot(meshcore, 1)
        event = SimpleNamespace(
            payload={
                "channel_idx": 1,
                "text": "alice: ping",
                "path_len": 2,
                "path_hash_mode": 1,
                "path": "a1a2b1b2",
                "RSSI": -101,
                "SNR": 7.5,
            }
        )

        await bot.handle_channel_message(event)

        assert meshcore.commands.sent == [
            (1, "@[alice] Pong 🏓 (2 hops, a1a2:b1b2)")
        ]

    asyncio.run(scenario())


def test_ping_on_another_channel_is_ignored_defensively():
    async def scenario():
        meshcore = FakeMeshCore()
        bot = PingBot(meshcore, 1)
        await bot.handle_channel_message(
            SimpleNamespace(payload={"channel_idx": 2, "text": "alice: ping"})
        )
        assert meshcore.commands.sent == []

    asyncio.run(scenario())
