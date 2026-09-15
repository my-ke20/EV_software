const SUBSYSTEMS = [
  {
    name: "Battery",
    fault: ["low_battery"],
    warn: ["voltage_sag_warning"],
  },
  {
    name: "Motor",
    fault: ["motor_overheat_critical"],
    warn: ["motor_temp_warning"],
  },
  {
    name: "Gearbox",
    fault: [],
    warn: ["gearbox_sensor_glitch"],
  },
];

function severityFor(flags, subsystem) {
  if (subsystem.fault.some((f) => flags.includes(f))) return "fault";
  if (subsystem.warn.some((f) => flags.includes(f))) return "warn";
  return "ok";
}

const SEVERITY_COLOR = {
  ok: "var(--accent-teal)",
  warn: "var(--accent-amber)",
  fault: "var(--accent-coral)",
};

const SEVERITY_LABEL = {
  ok: "Normal",
  warn: "Warning",
  fault: "Fault",
};

export default function SystemStatus({ latest }) {
  const flags = latest?.fault_flags ?? [];

  return (
    <div className="panel">
      <p className="panel-title">System status</p>
      <p className="panel-subtitle">
        {flags.length === 0 ? "All systems normal" : `${flags.length} active alert(s)`}
      </p>
      {SUBSYSTEMS.map((sub) => {
        const severity = severityFor(flags, sub);
        return (
          <div className="status-row" key={sub.name}>
            <span className="status-name">
              <span className="status-dot" style={{ background: SEVERITY_COLOR[severity] }} />
              {sub.name}
            </span>
            <span className="status-state">{SEVERITY_LABEL[severity]}</span>
          </div>
        );
      })}
    </div>
  );
}
