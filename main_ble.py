import asyncio
import logging
from typing import Any
from meshcore import MeshCore, EventType

BLE_ADDRESS = "MeshCore-T114_t"  # MUST match advertised name or MAC
BLE_PIN = None                     # or "123456" if your device needs it
CHANNEL_IDX = 1

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("ble_pingbot")

latest_pathinfo_str = "(? hops, ?)"


def parse_rx_log_data(payload: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        hex_str = payload.get("payload") if isinstance(payload, dict) else payload
        if not hex_str:
            return result
        if isinstance(hex_str, bytes):
            hex_str = hex_str.hex()
        hex_str = hex_str.strip().lower()
        if len(hex_str) < 4:
            return result

        path_len = int(hex_str[2:4], 16)
        path_hex = hex_str[4:4 + path_len * 2]
        result["path_len"] = path_len
        result["path_nodes"] = [path_hex[i:i+2] for i in range(0, len(path_hex), 2)]
    except Exception:
        pass
    return result


def format_pathinfo(parsed: dict[str, Any]) -> str:
    if "path_len" not in parsed:
        return "(? hops, ?)"
    if parsed["path_len"] == 0:
        return "(0 hops, direct)"
    return f"({parsed['path_len']} hops nach Meisterschwanden, {':'.join(parsed['path_nodes'])})"


async def main():
    global latest_pathinfo_str

    print(f"Connecting to BLE device: {BLE_ADDRESS}")

    if BLE_PIN:
        mc = await MeshCore.create_ble(BLE_ADDRESS, pin=str(BLE_PIN))
    else:
        mc = await MeshCore.create_ble(BLE_ADDRESS)

    print("Connected over BLE")

    # 🚨 REQUIRED for BLE
    await mc.start_auto_message_fetching()

    async def handle_rx_log_data(event):
        global latest_pathinfo_str
        parsed = parse_rx_log_data(event.payload or {})
        if parsed:
            latest_pathinfo_str = format_pathinfo(parsed)

    async def handle_channel_message(event):
        msg = event.payload or {}
        chan = msg.get("channel_idx")
        text = msg.get("text", "")
        sender = text.split(":", 1)[0].strip()

        print(f"[BLE] ch={chan} {text}")

        if chan == CHANNEL_IDX and "ping" in text.lower():
            reply = f"@[{sender}] Pong 🏓 {latest_pathinfo_str}"
            await mc.commands.send_chan_msg(chan, reply)

    sub_chan = mc.subscribe(EventType.CHANNEL_MSG_RECV, handle_channel_message)
    sub_rx = mc.subscribe(EventType.RX_LOG_DATA, handle_rx_log_data)

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        mc.unsubscribe(sub_chan)
        mc.unsubscribe(sub_rx)
        await mc.stop_auto_message_fetching()
        await mc.disconnect()
        print("Disconnected")


asyncio.run(main())
