function Tile({ value, unit, label }) {
  return (
    <div className="stat-tile">
      <div className="stat-value">
        {value}
        {unit && <span style={{ fontSize: 14, color: "var(--text-muted)", marginLeft: 4 }}>{unit}</span>}
      </div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function StatTiles({ latest }) {
  const t = latest;
  return (
    <div className="stat-grid">
      <Tile value={t ? t.speed_kph.toFixed(0) : "--"} unit="km/h" label="Speed" />
      <Tile value={t ? t.pack_voltage.toFixed(0) : "--"} unit="V" label="Pack voltage" />
      <Tile value={t ? t.pack_current.toFixed(0) : "--"} unit="A" label="Pack current" />
      <Tile value={t ? t.motor_temp_c.toFixed(0) : "--"} unit="°C" label="Motor temp" />
    </div>
  );
}
