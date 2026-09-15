function socColor(pct) {
  if (pct > 50) return "var(--accent-teal)";
  if (pct > 20) return "var(--accent-amber)";
  return "var(--accent-coral)";
}

export default function RangeHero({ latest }) {
  const range = latest ? Math.round(latest.range_km) : "--";
  const soc = latest ? latest.soc_pct : 0;

  return (
    <div className="hero">
      <p className="hero-label">Estimated range</p>
      <div className="hero-value-row">
        <span className="hero-value">{range}</span>
        <span className="hero-unit">km</span>
      </div>
      <div className="soc-track">
        <div
          className="soc-fill"
          style={{ width: `${soc}%`, background: socColor(soc) }}
        />
      </div>
      <div className="soc-caption">
        <span>Battery</span>
        <span>{soc.toFixed(1)}%</span>
      </div>
    </div>
  );
}
