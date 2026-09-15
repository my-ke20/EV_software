"""
Ingest service: subscribes to the vehicle telemetry MQTT topic and writes
each message into SQLite as it arrives.

This is intentionally a separate process from the simulator and from the
API -- in a real deployment you'd have one physical vehicle publishing,
one ingest process persisting, and one (or many) API/UI processes reading.
Keeping them separate now means swapping the simulator for a real ESP32
publisher later requires zero changes here.

Run:
    python ingest.py --mqtt-host localhost --topic vehicle/telemetry
"""

import argparse
import json
import logging

import paho.mqtt.client as mqtt

import EV_software.simulator.db as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ingest")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to broker, subscribing to '%s'", userdata["topic"])
        client.subscribe(userdata["topic"])
    else:
        log.error("Failed to connect to broker (rc=%s)", rc)


def on_message(client, userdata, msg):
    try:
        state = json.loads(msg.payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        # A real vehicle feed will occasionally send a garbled frame --
        # log and skip rather than crashing the whole ingest process.
        log.warning("Dropped malformed message: %s", exc)
        return

    try:
        db.insert_telemetry(state)
        userdata["count"] += 1
        if userdata["count"] % 20 == 0:
            log.info("Ingested %d messages so far", userdata["count"])
    except KeyError as exc:
        log.warning("Dropped message missing expected field: %s", exc)


def main():
    parser = argparse.ArgumentParser(description="Telemetry ingest service")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--topic", default="vehicle/telemetry")
    args = parser.parse_args()

    db.init_db()
    log.info("Database ready at %s", db.DB_PATH)

    userdata = {"topic": args.topic, "count": 0}
    client = mqtt.Client(userdata=userdata)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(args.mqtt_host, args.mqtt_port)
    log.info("Listening for telemetry... (Ctrl+C to stop)")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        log.info("Stopped. Total ingested: %d", userdata["count"])


if __name__ == "__main__":
    main()
