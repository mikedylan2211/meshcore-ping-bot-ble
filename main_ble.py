"""Run the MeshCore ping bot over BLE."""

import asyncio

from meshcore import EventType, MeshCore

from pingbot import PingBot


BLE_ADDRESS = "MeshCore-1234"  # advertised name or MAC address
BLE_PIN = None  # for example, "123456"
CHANNEL_IDX = 1  # change to the index of your #ping channel


async def main() -> None:
    print(f"Connecting to BLE device: {BLE_ADDRESS}")
    meshcore = await MeshCore.create_ble(BLE_ADDRESS, pin=BLE_PIN)
    if meshcore is None:
        raise ConnectionError(f"Could not connect to {BLE_ADDRESS}")

    print("Connected over BLE")
    try:
        device_info = await meshcore.commands.send_device_query()
        if device_info.type != EventType.ERROR:
            firmware = device_info.payload.get("ver", "unknown")
            model = device_info.payload.get("model", "unknown device")
            print(f"Device: {model}; firmware: {firmware}")

        await PingBot(meshcore, CHANNEL_IDX, "BLE").run()
    finally:
        await meshcore.disconnect()
        print("Disconnected")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")
