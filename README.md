# MeshCore BLE ping bot

A small BLE bot that listens on a MeshCore channel and replies to `ping` with
`Pong`, the received hop count, and the correlated route.

It uses `meshcore` 2.3.8 or newer and supports the multi-byte path hashes added
in MeshCore firmware 1.14, including current companion firmware 1.15.

## Configure

Edit these values near the top of `main_ble.py`:

```python
BLE_ADDRESS = "MeshCore-1234"  # advertised BLE name or MAC address
BLE_PIN = None                  # for example, "123456"
CHANNEL_IDX = 1                 # index of the #ping channel
```

The configured channel must already exist on the companion. The bot loads its
channel secret at startup so the Python client can correlate a decrypted
message with its exact RF receive log. If correlation data is unavailable, the
bot still reports the hop count supplied by the companion.

## Run with uv

```console
uv run python main_ble.py
```

Or install with pip:

```console
python -m pip install -r requirements.txt
python main_ble.py
```

Stop the bot with `Ctrl-C`.

## Test

The test command uses a temporary environment and does not create `.venv`:

```console
uv run --isolated --no-project --with meshcore==2.3.8 --with pytest python -m pytest -q
```
