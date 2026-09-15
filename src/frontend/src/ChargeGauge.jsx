const RADIUS = 80;
const ARC_LENGTH = Math.PI * RADIUS; // half-circle circumference

/**
 * Performance score is a derived display metric, not a raw sensor value.
 * It's a simple weighted composite:
 *   - each active fault knocks points off
 *   - motor temp above a comfortable baseline (60C) knocks points off
 *   - consumption above an efficient baseline (18 kWh/100km) knocks points off
 * The weights are a starting point -- tune them once you have a feel for
 * what "normal" looks like from the simulator.
 */
function computeScore(latest) {
  if (!latest) return null;
  const faultPenalty = (latest.fault_flags?.length ?? 0) * 15;
  const tempPenalty = Math.max(0, latest.motor_temp_c - 60) * 0.6;
  const consumptionPenalty = Math.max(0, latest.consumption_kwh_per_100km - 18) * 0.8;
  const score = 100 - faultPenalty - tempPenalty - consumptionPenalty;
  return Math.max(0, Math.min(100, Math.round(score)));
}

function scoreColor(score) {
  if (score >= 70) return "#33d6a6";
  if (score >= 40) return "#f5b942";
  return "#ff5c78";
}

export default function ChargeGauge({ latest }) {
  const score = computeScore(latest);
  const fraction = score === null ? 0 : score / 100;
  const dashOffset = ARC_LENGTH * (1 - fraction);

  return (
    <div className="panel">
      <p className="panel-title">Performance score</p>
      <p className="panel-subtitle">Battery health, thermal load, and efficiency combined</p>
      <div className="gauge-wrap">
        <svg viewBox="0 0 200 110" width="220" height="120">
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke="#262e37"
            strokeWidth="14"
            strokeLinecap="round"
          />
          <path
            d="M 20 100 A 80 80 0 0 1 180 100"
            fill="none"
            stroke={score === null ? "#262e37" : scoreColor(score)}
            strokeWidth="14"
            strokeLinecap="round"
            strokeDasharray={ARC_LENGTH}
            strokeDashoffset={dashOffset}
            style={{ transition: "stroke-dashoffset 0.5s ease" }}
          />
        </svg>
        <div className="gauge-score">{score === null ? "--" : score}</div>
        <div className="gauge-caption">out of 100</div>
      </div>
    </div>
  );
}
