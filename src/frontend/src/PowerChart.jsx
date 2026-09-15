import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

function formatTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { minute: "2-digit", second: "2-digit" });
}

export default function PowerChart({ history }) {
  const data = history.map((row) => ({
    ts: row.ts,
    timeLabel: formatTime(row.ts),
    power: Number(row.power_kw.toFixed(2)),
  }));

  const latestConsumption =
    history.length > 0 ? history[history.length - 1].consumption_kwh_per_100km : null;

  return (
    <div className="panel">
      <p className="panel-title">Power draw</p>
      <p className="panel-subtitle">
        {latestConsumption !== null
          ? `${latestConsumption.toFixed(1)} kWh / 100km (rolling average)`
          : "Waiting for data\u2026"}
      </p>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
          <defs>
            <linearGradient id="powerFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#33d6a6" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#33d6a6" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#262e37" vertical={false} />
          <XAxis
            dataKey="timeLabel"
            tick={{ fill: "#7e8a97", fontSize: 11 }}
            axisLine={{ stroke: "#262e37" }}
            tickLine={false}
            minTickGap={40}
          />
          <YAxis
            tick={{ fill: "#7e8a97", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: "#1c232b",
              border: "1px solid #262e37",
              fontSize: 12,
              color: "#edf1f4",
            }}
            formatter={(value) => [`${value} kW`, "Power"]}
            labelFormatter={() => ""}
          />
          <Area
            type="monotone"
            dataKey="power"
            stroke="#33d6a6"
            strokeWidth={2}
            fill="url(#powerFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
