"""
EV Vehicle State Simulator
---------------------------
Generates believable EV telemetry (speed, power draw, battery SOC, voltage,
motor temperature, fault flags) using a simple but physically-grounded model,
and publishes each tick over MQTT as JSON.

Run standalone to sanity-check the physics (prints to console):
    python simulate.py --no-mqtt

Run against a local Mosquitto broker:
    python simulate.py --mqtt-host localhost

Design notes:
- One tick = one second of simulated time (Hz is configurable).
- "Driver behavior" is a simple random-walk over acceleration, clamped to
  realistic speed bounds -- swap this out later for a real drive-cycle
  trace (e.g. EPA UDDS/US06) if you want more realistic driving patterns.
- Battery model uses Coulomb counting (current x time / capacity) plus a
  simple open-circuit-voltage curve so voltage sags under load like a real
  pack, instead of just being a flat number tied to SOC.
- Thermal model is a first-order lag: heats up under load (I^2 * R losses),
  cools toward ambient otherwise.
"""

import argparse
import json
import logging
import math
import random
import time
from dataclasses import asdict, dataclass, field

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ev_sim")


# ---------------------------------------------------------------------------
# Vehicle / physics constants (tune these to model a different vehicle)
# ---------------------------------------------------------------------------

MASS_KG = 1750.0                 # curb weight
GRAVITY = 9.81
ROLLING_RESISTANCE_COEFF = 0.011  # typical for EV tires
AIR_DENSITY = 1.225               # kg/m^3
DRAG_COEFF = 0.23                 # Cd
FRONTAL_AREA_M2 = 2.22
DRIVETRAIN_EFFICIENCY = 0.90      # motor + inverter + gearbox combined
REGEN_EFFICIENCY = 0.65           # fraction of braking energy recovered

BATTERY_CAPACITY_AH = 230.0       # pack capacity in amp-hours
NOMINAL_VOLTAGE = 350.0           # pack nominal voltage
INTERNAL_RESISTANCE_OHM = 0.05    # causes voltage sag under load

AMBIENT_TEMP_C = 25.0
HEAT_COEFF = 0.00025              # how fast motor heats under current^2
COOL_COEFF = 0.02                 # how fast motor cools toward ambient
MOTOR_TEMP_WARN_C = 90.0
MOTOR_TEMP_FAULT_C = 105.0
LOW_SOC_WARN_PCT = 15.0

MAX_SPEED_KPH = 160.0
MAX_ACCEL_MPS2 = 2.5
MAX_DECEL_MPS2 = -3.5


@dataclass
class VehicleState:
    timestamp: float
    soc_pct: float
    pack_voltage: float
    pack_current: float       # positive = discharging, negative = charging/regen
    motor_temp_c: float
    speed_kph: float
    odometer_km: float
    range_km: float
    power_kw: float
    consumption_kwh_per_100km: float
    power_mode: str            # "drive" | "eco" | "regen" | "idle"
    fault_flags: list = field(default_factory=list)


def open_circuit_voltage(soc_pct: float) -> float:
    """
    Rough OCV curve: flat through the mid-range, drops off at both ends,
    like a real lithium-ion pack. Returns volts.
    """
    soc = max(0.0, min(100.0, soc_pct))
    if soc > 80:
        # top of curve tapers off
        return NOMINAL_VOLTAGE * (1.05 - 0.05 * (100 - soc) / 20)
    elif soc < 15:
        # bottom of curve drops faster
        return NOMINAL_VOLTAGE * (0.85 * soc / 15)
    else:
        return NOMINAL_VOLTAGE * (0.95 + 0.10 * (soc - 15) / 65)


class DriverBehavior:
    """Simple random-walk driver: occasionally changes target acceleration."""

    def __init__(self):
        self.accel_mps2 = 0.0
        self._ticks_until_change = 0

    def step(self, speed_kph: float) -> float:
        if self._ticks_until_change <= 0:
            # pick a new behavior: accelerate, cruise, or brake
            choice = random.choices(
                ["accelerate", "cruise", "brake"], weights=[0.35, 0.4, 0.25]
            )[0]
            if choice == "accelerate":
                self.accel_mps2 = random.uniform(0.3, MAX_ACCEL_MPS2)
            elif choice == "brake":
                self.accel_mps2 = random.uniform(MAX_DECEL_MPS2, -0.3)
            else:
                self.accel_mps2 = random.uniform(-0.1, 0.1)
            self._ticks_until_change = random.randint(5, 20)
        self._ticks_until_change -= 1

        # don't accelerate past top speed, don't brake below 0
        if speed_kph >= MAX_SPEED_KPH and self.accel_mps2 > 0:
            self.accel_mps2 = 0.0
        if speed_kph <= 0 and self.accel_mps2 < 0:
            self.accel_mps2 = 0.0

        return self.accel_mps2


def compute_tractive_power_kw(speed_kph: float, accel_mps2: float) -> float:
    """
    Tractive power required at the wheels, converted to electrical power
    drawn from the pack (or returned to it, if negative = regen braking).
    """
    v_mps = speed_kph / 3.6

    f_roll = ROLLING_RESISTANCE_COEFF * MASS_KG * GRAVITY
    f_drag = 0.5 * AIR_DENSITY * DRAG_COEFF * FRONTAL_AREA_M2 * v_mps**2
    f_accel = MASS_KG * accel_mps2

    f_total = f_roll + f_drag + f_accel
    p_watts = f_total * v_mps

    if p_watts >= 0:
        p_watts = p_watts / DRIVETRAIN_EFFICIENCY  # losses when driving
    else:
        p_watts = p_watts * REGEN_EFFICIENCY        # recovery when braking

    return p_watts / 1000.0  # -> kW


def update_battery(state: VehicleState, power_kw: float, dt_s: float) -> None:
    current_a = (power_kw * 1000.0) / max(state.pack_voltage, 1.0)
    state.pack_current = current_a

    # Coulomb counting: amp-hours drawn this tick, as a % of full capacity
    delta_ah = current_a * (dt_s / 3600.0)
    delta_soc_pct = (delta_ah / BATTERY_CAPACITY_AH) * 100.0
    state.soc_pct = max(0.0, min(100.0, state.soc_pct - delta_soc_pct))

    ocv = open_circuit_voltage(state.soc_pct)
    state.pack_voltage = ocv - current_a * INTERNAL_RESISTANCE_OHM


def update_thermal(state: VehicleState, dt_s: float) -> None:
    heat = HEAT_COEFF * (state.pack_current**2)
    cool = COOL_COEFF * (state.motor_temp_c - AMBIENT_TEMP_C)
    state.motor_temp_c += (heat - cool) * dt_s


def update_consumption_and_range(state: VehicleState, power_kw: float) -> None:
    speed_kmh = max(state.speed_kph, 0.1)
    # instantaneous consumption -> rough exponential smoothing against last value
    instant_kwh_per_100km = (power_kw / speed_kmh) * 100.0 if power_kw > 0 else 0.0
    alpha = 0.1
    state.consumption_kwh_per_100km = (
        alpha * instant_kwh_per_100km + (1 - alpha) * state.consumption_kwh_per_100km
    )
    usable_kwh = (state.soc_pct / 100.0) * (BATTERY_CAPACITY_AH * NOMINAL_VOLTAGE / 1000.0)
    avg_consumption = max(state.consumption_kwh_per_100km, 5.0)  # floor to avoid div/0 blowups
    state.range_km = (usable_kwh / avg_consumption) * 100.0


def check_faults(state: VehicleState) -> None:
    flags = []
    if state.motor_temp_c >= MOTOR_TEMP_FAULT_C:
        flags.append("motor_overheat_critical")
    elif state.motor_temp_c >= MOTOR_TEMP_WARN_C:
        flags.append("motor_temp_warning")
    if state.soc_pct <= LOW_SOC_WARN_PCT:
        flags.append("low_battery")
    if state.pack_voltage < NOMINAL_VOLTAGE * 0.6:
        flags.append("voltage_sag_warning")
    # small chance of a transient sensor gremlin, for UI testing
    if random.random() < 0.002:
        flags.append("gearbox_sensor_glitch")
    state.fault_flags = flags


def make_initial_state() -> VehicleState:
    return VehicleState(
        timestamp=time.time(),
        soc_pct=80.0,
        pack_voltage=open_circuit_voltage(80.0),
        pack_current=0.0,
        motor_temp_c=AMBIENT_TEMP_C,
        speed_kph=0.0,
        odometer_km=0.0,
        range_km=0.0,
        power_kw=0.0,
        consumption_kwh_per_100km=16.0,
        power_mode="idle",
        fault_flags=[],
    )


def step_simulation(state: VehicleState, driver: DriverBehavior, dt_s: float) -> None:
    accel = driver.step(state.speed_kph)

    v_mps = state.speed_kph / 3.6 + accel * dt_s
    v_mps = max(0.0, v_mps)
    state.speed_kph = v_mps * 3.6
    state.odometer_km += (v_mps * dt_s) / 1000.0

    power_kw = compute_tractive_power_kw(state.speed_kph, accel)
    state.power_kw = power_kw

    if power_kw > 0.1:
        state.power_mode = "drive"
    elif power_kw < -0.1:
        state.power_mode = "regen"
    else:
        state.power_mode = "idle"

    update_battery(state, power_kw, dt_s)
    update_thermal(state, dt_s)
    update_consumption_and_range(state, power_kw)
    check_faults(state)

    state.timestamp = time.time()

    # simple "recharge" behavior once nearly empty, so a long-running demo
    # doesn't just sit dead at 0% forever
    if state.soc_pct <= 2.0:
        state.power_mode = "charge"
        state.soc_pct = min(100.0, state.soc_pct + 0.5)
        state.pack_voltage = open_circuit_voltage(state.soc_pct)


def build_mqtt_client(host: str, port: int):
    import paho.mqtt.client as mqtt

    client = mqtt.Client()
    client.connect(host, port)
    return client


def main():
    parser = argparse.ArgumentParser(description="EV telemetry simulator")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument("--topic", default="vehicle/telemetry")
    parser.add_argument("--hz", type=float, default=1.0, help="publish rate")
    parser.add_argument("--no-mqtt", action="store_true", help="print to console only")
    args = parser.parse_args()

    dt_s = 1.0 / args.hz
    state = make_initial_state()
    driver = DriverBehavior()

    client = None
    if not args.no_mqtt:
        try:
            client = build_mqtt_client(args.mqtt_host, args.mqtt_port)
            log.info("Connected to MQTT broker at %s:%s", args.mqtt_host, args.mqtt_port)
        except Exception as exc:
            log.warning("Could not connect to MQTT (%s) -- falling back to console output", exc)

    log.info("Starting simulation loop (Ctrl+C to stop)")
    try:
        while True:
            step_simulation(state, driver, dt_s)
            payload = json.dumps(asdict(state))

            if client:
                client.publish(args.topic, payload)
            else:
                log.info(payload)

            time.sleep(dt_s)
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
