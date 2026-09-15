"""
API layer: sits between the database (historical reads) and MQTT (live
updates), and exposes both to the frontend over HTTP/WebSocket.

Two read paths, deliberately different mechanisms:

1. REST (/telemetry/latest, /telemetry/history) -- backed by SQLite via
   db.py. Good for: initial page load, chart history, anything where the
   client just needs a snapshot on demand.

2. WebSocket (/ws/telemetry) -- backed by a live MQTT subscription running
   in a background thread. Good for: the live-updating cards/gauges on the
   dashboard. Polling the REST endpoint every second would work too, but
   a push model avoids constant HTTP overhead and gives lower latency --
   the UI updates the instant a new tick is published, not on its next poll.

Note: this process does NOT write to the database -- that's ingest.py's
job. api.py only *reads* history from SQLite and *relays* live MQTT
messages to WebSocket clients. Keeping ingestion and serving separate
means you can restart/scale the API without ever risking a dropped
telemetry write.
"""

import asyncio
import json
import logging
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulator"))
import db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("api")

MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "vehicle/telemetry"

app = FastAPI(title="EV Telemetry API")

# Allow the React dev server (Vite default: 5173, CRA default: 3000) to
# call this API from the browser. Tighten this to your actual frontend
# origin before deploying anywhere real.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------

class ConnectionManager:
    """Tracks connected WebSocket clients and broadcasts to all of them."""

    def __init__(self):
        self.active: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        log.info("WebSocket client connected (%d total)", len(self.active))

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
        log.info("WebSocket client disconnected (%d total)", len(self.active))

    def broadcast_threadsafe(self, message: str):
        """
        Called from the MQTT thread (not the asyncio event loop), so we
        schedule the actual async send onto the loop instead of calling
        it directly -- asyncio objects aren't safe to touch from another
        thread without this handoff.
        """
        if self.loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(message), self.loop)

    async def _broadcast(self, message: str):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# MQTT bridge -- runs in a background thread, feeds the ConnectionManager
# ---------------------------------------------------------------------------

def on_mqtt_message(client, userdata, msg):
    manager.broadcast_threadsafe(msg.payload.decode("utf-8"))


def start_mqtt_bridge():
    client = mqtt.Client()
    client.on_message = on_mqtt_message

    def _run():
        while True:
            try:
                client.connect(MQTT_HOST, MQTT_PORT)
                client.subscribe(MQTT_TOPIC)
                log.info("MQTT bridge connected, subscribed to '%s'", MQTT_TOPIC)
                client.loop_forever()
            except Exception as exc:
                log.warning("MQTT bridge lost connection (%s), retrying in 3s", exc)
                time.sleep(3)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


@app.on_event("startup")
async def on_startup():
    manager.loop = asyncio.get_event_loop()
    db.init_db()
    start_mqtt_bridge()
    log.info("API ready")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get("/telemetry/latest")
def telemetry_latest():
    return db.get_latest() or {}


@app.get("/telemetry/history")
def telemetry_history(seconds: int = 1800):
    """Return telemetry from the last `seconds` seconds (default: 30 min)."""
    since_ts = time.time() - seconds
    return db.get_history(since_ts)


# ---------------------------------------------------------------------------
# WebSocket endpoint -- live push
# ---------------------------------------------------------------------------

@app.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # We don't expect messages from the client, but awaiting
            # receive_text() is what lets us detect disconnects promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
