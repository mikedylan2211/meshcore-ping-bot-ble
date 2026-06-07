import asyncio
import logging
from typing import Any
from meshcore import MeshCore, EventType

BLE_ADDRESS = "MeshCore-1234"  # MUST match advertised name or MAC
BLE_PIN = None                  # or "123456" if your device needs it
CHANNEL_IDX = 1

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger("ble_pingbot")

latest_pathinfo_str = "(? hops, ?)"


def parse_rx_log_data(payload: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        if isinstance(payload, dict):
            hex_str = payload.get("payload") or payload.get("raw_hex")
        else:
            hex_str = payload
        if not hex_str:
            return result
        if isinstance(hex_str, bytes):
            hex_str = hex_str.hex()
        hex_str = str(hex_str).lower().replace(" ", "").replace("\n", "").replace("\r", "")
        if len(hex_str) < 4:
            return result

        result["header"] = hex_str[0:2]
        path_len = int(hex_str[2:4], 16)
        path_start = 4
        path_end = path_start + path_len * 2
        if len(hex_str) < path_end:
            return {}

        path_hex = hex_str[path_start:path_end]
        result["path_len"] = path_len
        result["path"] = path_hex
        result["path_nodes"] = [path_hex[i:i + 2] for i in range(0, len(path_hex), 2)]
        if len(hex_str) >= path_end + 2:
            result["channel_hash"] = hex_str[path_end:path_end + 2]
    except Exception as ex:
        _LOGGER.debug("Error parsing RX_LOG_DATA: %s", ex)
    return result


def format_pathinfo(parsed: dict[str, Any]) -> str:
    path_len = parsed.get("path_len")
    path_nodes = parsed.get("path_nodes") or []
    if path_len is None:
        return "(? hops, ?)"
    if path_len == 0:
        return "(0 hops, direct)"
    return f"({path_len} hops nach London, {':'.join(path_nodes) if path_nodes else '?'})"


async def main() -> int:
    global latest_pathinfo_str

    print(f"Connecting to BLE device: {BLE_ADDRESS}")

    try:
        if BLE_PIN:
            mc = await MeshCore.create_ble(BLE_ADDRESS, pin=str(BLE_PIN))
        else:
            mc = await MeshCore.create_ble(BLE_ADDRESS)
    except Exception as ex:
        print(f"Failed to connect over BLE: {ex}")
        return 1

    if mc is None:
        print("Failed to connect over BLE: no response from MeshCore device")
        return 1

    print("Connected over BLE")

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
            result = await mc.commands.send_chan_msg(chan, reply)
            if result.type == EventType.ERROR:
                print(f"Error sending reply: {result.payload}")
            else:
                print(f"Reply sent: {reply}")

    sub_chan = mc.subscribe(
        EventType.CHANNEL_MSG_RECV,
        handle_channel_message,
        attribute_filters={"channel_idx": CHANNEL_IDX},
    )
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
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
