import { useEffect, useRef, useState } from "react";

const API_BASE = "http://localhost:8000";
const WS_URL = "ws://localhost:8000/ws/telemetry";
const HISTORY_WINDOW_SECONDS = 120;
const MAX_POINTS = 120; // ring-buffer cap for the live chart

function normalizeTick(tick) {
  return { ...tick, ts: tick.ts ?? tick.timestamp };
}

/**
 * Loads recent history once over REST (so the chart isn't empty on first
 * paint), then keeps appending live ticks pushed over the WebSocket.
 *
 * The history array is capped at MAX_POINTS -- old points are dropped as
 * new ones arrive, same idea as the deque ring buffer on the Python side.
 * This keeps the chart re-render cheap no matter how long the dashboard
 * has been open.
 */
export function useTelemetry() {
  const [latest, setLatest] = useState(null);
  const [history, setHistory] = useState([]);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef(null);

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE}/telemetry/history?seconds=${HISTORY_WINDOW_SECONDS}`)
      .then((res) => res.json())
      .then((rows) => {
        if (cancelled) return;
        const normalized = rows.map(normalizeTick);
        setHistory(normalized.slice(-MAX_POINTS));
        if (normalized.length) setLatest(normalized[normalized.length - 1]);
      })
      .catch((err) => console.error("Failed to load telemetry history", err));

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let ws;
    let stopped = false;

    function connect() {
      ws = new WebSocket(WS_URL);

      ws.onopen = () => setConnected(true);

      ws.onmessage = (event) => {
        const tick = normalizeTick(JSON.parse(event.data));
        setLatest(tick);
        setHistory((prev) => {
          const next = [...prev, tick];
          return next.length > MAX_POINTS ? next.slice(-MAX_POINTS) : next;
        });
      };

      ws.onclose = () => {
        setConnected(false);
        if (!stopped) {
          // simple fixed-delay reconnect -- fine for a dev dashboard;
          // a real deployment would want exponential backoff
          reconnectTimer.current = setTimeout(connect, 2000);
        }
      };

      ws.onerror = () => ws.close();
    }

    connect();

    return () => {
      stopped = true;
      clearTimeout(reconnectTimer.current);
      ws?.close();
    };
  }, []);

  return { latest, history, connected };
}
