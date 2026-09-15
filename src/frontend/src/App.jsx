import { useTelemetry } from "./useTelemetry";
import ChargeGauge from "./ChargeGauge";
import PowerChart from "./PowerChart";
import RangeHero from "./RangeHero";
import StatTiles from "./StatTiles";
import SystemStatus from "./SystemStatus";
import "./App.css";

function App() {
  const { latest, history, connected } = useTelemetry();
  const mode = latest?.power_mode ?? "idle";
  const hasAlerts = latest?.fault_flags?.length > 0;

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">EV</div>
          <div><p className="eyebrow">Vehicle intelligence</p><h1>Pulse / 01</h1></div>
        </div>
        <div className="connection-state"><span className={`connection-dot ${connected ? "live" : ""}`} />{connected ? "Live telemetry" : "Reconnecting"}<span className="connection-divider" /><span className="mono">{mode.toUpperCase()}</span></div>
      </header>

      <section className="dashboard-heading">
        <div><p className="section-kicker">Cabin / remote view</p><h2>Good afternoon, driver.</h2></div>
        <div className={`alert-chip ${hasAlerts ? "alert" : ""}`}><span>{hasAlerts ? "!" : "✓"}</span>{hasAlerts ? `${latest.fault_flags.length} active alert` : "Systems nominal"}</div>
      </section>

      <section className="hero-grid">
        <div className="panel range-panel"><RangeHero latest={latest} /></div>
        <div className="panel energy-panel">
          <div className="panel-heading"><div><p className="panel-title">Energy reserve</p><p className="panel-subtitle">Current battery state</p></div><span className="live-tag">{latest ? "SYNCED" : "WAITING"}</span></div>
          <div className="energy-reading"><span>{latest ? latest.soc_pct.toFixed(1) : "--"}</span><small>% SOC</small></div>
          <div className="energy-meta"><span>Pack voltage</span><strong>{latest ? `${latest.pack_voltage.toFixed(0)} V` : "--"}</strong></div>
          <div className="energy-meta"><span>Estimated range</span><strong>{latest ? `${latest.range_km.toFixed(0)} km` : "--"}</strong></div>
        </div>
      </section>

      <StatTiles latest={latest} />
      <section className="content-grid"><PowerChart history={history} /><div className="side-stack"><ChargeGauge latest={latest} /><SystemStatus latest={latest} /></div></section>
      <footer><span>EV TELEMETRY NETWORK</span><span className="mono">{latest ? new Date(latest.ts * 1000).toLocaleTimeString() : "Awaiting signal"}</span></footer>
    </main>
  );
}

export default App;
