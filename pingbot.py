"""Shared MeshCore channel ping-bot logic."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from meshcore import EventType


UNKNOWN_PATH = "(? hops, path unavailable)"
_PING_RE = re.compile(r"\bping\b", re.IGNORECASE)


def _path_bytes(value: Any) -> bytes | None:
    if isinstance(value, (bytes, bytearray)):
        return bytes(value)
    if not isinstance(value, str):
        return None

    compact = value.replace(":", "").replace(" ", "")
    try:
        return bytes.fromhex(compact)
    except ValueError:
        return None


def _path_hash_size(message: dict[str, Any], path: bytes, path_len: int) -> int | None:
    size = message.get("path_hash_size")
    if isinstance(size, int) and 1 <= size <= 4:
        return size

    mode = message.get("path_hash_mode")
    if isinstance(mode, int) and 0 <= mode <= 3:
        return mode + 1

    if path_len > 0 and len(path) % path_len == 0:
        inferred = len(path) // path_len
        if 1 <= inferred <= 4:
            return inferred
    return None


def format_path_info(message: dict[str, Any], max_nodes: int = 8) -> str:
    """Format a decoded MeshCore message path.

    Firmware 1.14+ supports one-, two-, and three-byte hop hashes. Current
    meshcore_py versions expose the decoded hop count, hash mode, and the path
    correlated with the channel message.
    """

    path_len = message.get("path_len")
    if not isinstance(path_len, int):
        return UNKNOWN_PATH
    if path_len == 0xFF:
        return "(direct)"
    if path_len == 0:
        return "(0 hops, zero-hop)"
    if path_len < 0:
        return UNKNOWN_PATH

    path = _path_bytes(message.get("path"))
    if path is None:
        return f"({path_len} hops, path unavailable)"

    hash_size = _path_hash_size(message, path, path_len)
    if hash_size is None or len(path) != path_len * hash_size:
        return f"({path_len} hops, path unavailable)"

    nodes = [
        path[offset : offset + hash_size].hex()
        for offset in range(0, len(path), hash_size)
    ]
    if max_nodes >= 3 and len(nodes) > max_nodes:
        first_count = max_nodes // 2
        last_count = max_nodes - first_count
        nodes = nodes[:first_count] + ["..."] + nodes[-last_count:]

    return f"({path_len} hops, {':'.join(nodes)})"


def split_sender_and_body(text: str) -> tuple[str, str]:
    """Split the ``sender: message`` form emitted for channel messages."""

    sender, separator, body = text.partition(":")
    if not separator:
        return "unknown", text.strip()
    return sender.strip() or "unknown", body.strip()


def is_ping(body: str) -> bool:
    """Return whether the message body contains the word ``ping``."""

    return _PING_RE.search(body) is not None


def reception_details(message: dict[str, Any]) -> str:
    details = []
    if isinstance(message.get("RSSI"), (int, float)):
        details.append(f"RSSI={message['RSSI']} dBm")
    if isinstance(message.get("SNR"), (int, float)):
        details.append(f"SNR={message['SNR']} dB")
    return ", ".join(details)


class PingBot:
    """Respond to pings on one MeshCore channel."""

    def __init__(self, meshcore: Any, channel_idx: int, transport_label: str = ""):
        self.meshcore = meshcore
        self.channel_idx = channel_idx
        self.transport_label = transport_label

    async def prepare(self) -> None:
        # Decrypting RF channel logs lets meshcore_py correlate a message with
        # its exact path/RSSI/SNR instead of guessing from the most recent log.
        self.meshcore.set_decrypt_channel_logs(True)
        result = await self.meshcore.commands.get_channel(self.channel_idx)
        if result.type == EventType.ERROR:
            raise RuntimeError(
                f"Could not load channel {self.channel_idx}: {result.payload}"
            )

    async def handle_channel_message(self, event: Any) -> None:
        message = event.payload or {}
        if message.get("channel_idx") != self.channel_idx:
            return

        text = str(message.get("text", ""))
        sender, body = split_sender_and_body(text)
        path_info = format_path_info(message)
        radio_info = reception_details(message)
        label = f"[{self.transport_label}] " if self.transport_label else ""
        details = f" | {radio_info}" if radio_info else ""
        print(
            f"{label}Received on channel {self.channel_idx} from {sender}: "
            f"{body} | {path_info}{details}"
        )

        if not is_ping(body):
            return

        reply = f"@[{sender}] Pong 🏓 {path_info}"
        print(f"{label}Replying with: {reply}")
        result = await self.meshcore.commands.send_chan_msg(self.channel_idx, reply)
        if result.type == EventType.ERROR:
            print(f"{label}Error sending reply: {result.payload}")
        else:
            print(f"{label}Reply sent")

    async def run(self) -> None:
        await self.prepare()
        subscription = self.meshcore.subscribe(
            EventType.CHANNEL_MSG_RECV,
            self.handle_channel_message,
            attribute_filters={"channel_idx": self.channel_idx},
        )
        auto_fetch_started = False
        try:
            auto_fetch_started = True
            await self.meshcore.start_auto_message_fetching()
            print(f"Listening for 'ping' on channel {self.channel_idx}...")
            await asyncio.Event().wait()
        finally:
            self.meshcore.unsubscribe(subscription)
            if auto_fetch_started:
                await self.meshcore.stop_auto_message_fetching()
