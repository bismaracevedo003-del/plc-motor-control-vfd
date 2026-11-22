"""Simulated induction motor and variable frequency drive.

Tag names match DB20 in docs/signal-list.md.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

STOPPED = 0
STARTING = 1
RUNNING = 2
STOPPING = 3
FAULTED = 4

FAULT_PRIORITY = [5, 1, 4, 2, 3]

FAULT_NAMES = {
    1: "overload",
    2: "vfd_fault",
    3: "overcurrent",
    4: "cooling",
    5: "e_stop",
}


def scale_4_20ma(raw_ma: float, eu_min: float, eu_max: float) -> float:
    normalized = min(1.0, max(0.0, (raw_ma - 4.0) / 16.0))
    return eu_min + normalized * (eu_max - eu_min)


def value_to_ma(value: float, eu_min: float, eu_max: float) -> float:
    return 4.0 + (value - eu_min) / (eu_max - eu_min) * 16.0


def move_toward(current: float, target: float, step: float) -> float:
    if current < target:
        return min(current + step, target)
    if current > target:
        return max(current - step, target)
    return current


class MotorDrive:
    def __init__(self, rated_current_a: float = 6.0, accel_hz_s: float = 5.0, decel_hz_s: float = 7.0):
        self.rated_current_a = rated_current_a
        self.accel_hz_s = accel_hz_s
        self.decel_hz_s = decel_hz_s
        self.setpoint_hz = 30.0
        self.remote_mode = True
        self.start_cmd = False
        self.stop_cmd = False
        self.reset_cmd = False
        self.e_stop_ok = True
        self.overload_ok = True
        self.vfd_ready = True
        self.temp_ok = True
        self.local_start = False
        self.local_stop = True
        self.load_factor = 1.0
        self.frequency_hz = 0.0
        self.current_a = 0.0
        self.state = STOPPED
        self.run_output = False
        self.latched_faults: set[int] = set()
        self.fault_code = 0
        self.reset_prev = False
        self.start_prev = False
        self.start_count = 0
        self.runtime_s = 0.0
        self.elapsed_s = 0.0
        self.start_elapsed_s = 0.0
        self.overcurrent_timer_s = 0.0

    def command(self, name: str, value: Any = True) -> bool:
        names = {
            "START": lambda: setattr(self, "start_cmd", True),
            "STOP": lambda: setattr(self, "stop_cmd", True),
            "RESET": lambda: setattr(self, "reset_cmd", True),
        }
        if name not in names:
            return False
        names[name]()
        return True

    def release(self, name: str) -> bool:
        names = {
            "START": lambda: setattr(self, "start_cmd", False),
            "STOP": lambda: setattr(self, "stop_cmd", False),
            "RESET": lambda: setattr(self, "reset_cmd", False),
        }
        if name not in names:
            return False
        names[name]()
        return True

    def set_fault(self, name: str, active: bool = True) -> bool:
        mapping = {
            "overload": "overload_ok",
            "vfd_fault": "vfd_ready",
            "cooling": "temp_ok",
            "e_stop": "e_stop_ok",
        }
        if name not in mapping:
            return False
        setattr(self, mapping[name], not active)
        return True

    def tick(self, dt: float = 1.0) -> dict[str, Any]:
        dt = max(0.0, float(dt))
        self._update_current(dt)
        detected = self._detect_faults(dt)
        self._update_faults(detected)
        self._update_state(detected)
        self._update_ramp(dt)
        self.elapsed_s += dt
        if self.run_output:
            self.runtime_s += dt
        if self.state == STARTING:
            self.start_elapsed_s += dt
        self.start_prev = self.start_req
        self.reset_prev = self.reset_cmd
        return self.snapshot()

    @property
    def start_req(self) -> bool:
        return (self.remote_mode and self.start_cmd) or ((not self.remote_mode) and self.local_start)

    @property
    def stop_req(self) -> bool:
        return (self.remote_mode and self.stop_cmd) or ((not self.remote_mode) and not self.local_stop)

    @property
    def interlocks_ok(self) -> bool:
        return self.e_stop_ok and self.overload_ok and self.vfd_ready and self.temp_ok

    def _update_current(self, dt: float) -> None:
        if self.frequency_hz <= 0.0 or self.state in (STOPPED, FAULTED):
            self.current_a = 0.0
            return
        speed_ratio = self.frequency_hz / 50.0
        base = self.rated_current_a * (0.35 + 0.65 * speed_ratio**2) * self.load_factor
        inrush = 0.0
        if self.state == STARTING and self.start_elapsed_s < 2.0:
            inrush = self.rated_current_a * 1.2 * (1.0 - self.start_elapsed_s / 2.0)
        self.current_a = round(base + inrush, 3)

    def _detect_faults(self, dt: float) -> dict[int, bool]:
        overcurrent = self.current_a > self.rated_current_a * 1.5
        self.overcurrent_timer_s = self.overcurrent_timer_s + dt if overcurrent else 0.0
        return {
            5: not self.e_stop_ok,
            1: not self.overload_ok,
            4: not self.temp_ok,
            2: (not self.vfd_ready) and (self.run_output or self.start_req),
            3: self.overcurrent_timer_s >= 2.0,
        }

    def _update_faults(self, detected: dict[int, bool]) -> None:
        for code, active in detected.items():
            if active:
                self.latched_faults.add(code)
        reset_edge = self.reset_cmd and not self.reset_prev
        if reset_edge:
            for code in list(self.latched_faults):
                if not detected[code]:
                    self.latched_faults.remove(code)
        self.fault_code = next((code for code in FAULT_PRIORITY if code in self.latched_faults), 0)

    def _update_state(self, detected: dict[int, bool]) -> None:
        start_edge = self.start_req and not self.start_prev
        if self.fault_code:
            self.state = FAULTED
            self.run_output = False
            return
        if self.state == FAULTED:
            self.state = STOPPED
            self.run_output = False
            return
        if self.stop_req and self.state in (STARTING, RUNNING):
            self.state = STOPPING
            return
        if (
            start_edge
            and self.state == STOPPED
            and self.interlocks_ok
            and self.setpoint_hz > 0.0
            and not detected[3]
        ):
            self.state = STARTING
            self.run_output = True
            self.start_count += 1
            self.start_elapsed_s = 0.0

    def _update_ramp(self, dt: float) -> None:
        if self.state == FAULTED:
            self.frequency_hz = 0.0
            return
        if self.state in (STARTING, RUNNING):
            target = self.setpoint_hz
            step = self.accel_hz_s * dt
        elif self.state == STOPPING:
            target = 0.0
            step = self.decel_hz_s * dt
        else:
            self.frequency_hz = 0.0
            return
        self.frequency_hz = round(move_toward(self.frequency_hz, target, step), 3)
        if self.state == STARTING and abs(self.frequency_hz - target) <= 0.5:
            self.state = RUNNING
        if self.state == STOPPING and self.frequency_hz <= 0.5:
            self.frequency_hz = 0.0
            self.state = STOPPED
            self.run_output = False

    def snapshot(self) -> dict[str, Any]:
        return {
            "StartCmd": self.start_cmd,
            "StopCmd": self.stop_cmd,
            "ResetCmd": self.reset_cmd,
            "RemoteMode": self.remote_mode,
            "SpeedSetpoint_Hz": round(self.setpoint_hz, 2),
            "ActualFrequency_Hz": round(self.frequency_hz, 3),
            "MotorCurrent_A": self.current_a,
            "State": self.state,
            "FaultCode": self.fault_code,
            "FaultLatched": bool(self.latched_faults),
            "RunOutput": self.run_output,
            "VFDReady": self.vfd_ready,
            "OverloadOK": self.overload_ok,
            "EStopOK": self.e_stop_ok,
            "AccelRate_Hz_s": self.accel_hz_s,
            "DecelRate_Hz_s": self.decel_hz_s,
            "RatedCurrent_A": self.rated_current_a,
            "Runtime_s": round(self.runtime_s, 1),
            "StartCount": self.start_count,
            "FaultName": FAULT_NAMES.get(self.fault_code, "none"),
            "source": "simulator",
            "elapsed_s": round(self.elapsed_s, 1),
        }


def run_demo(duration_s: int, setpoint_hz: float, interval: int) -> None:
    drive = MotorDrive()
    drive.setpoint_hz = setpoint_hz
    drive.command("START")
    for second in range(1, duration_s + 1):
        snapshot = drive.tick(1.0)
        if second == 2:
            drive.release("START")
        if second == 20:
            drive.command("STOP")
        if second == 22:
            drive.release("STOP")
        if second % interval == 0 or second == 1:
            print(json.dumps(snapshot, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate motor control with VFD")
    parser.add_argument("--duration", type=int, default=40)
    parser.add_argument("--setpoint", type=float, default=35.0)
    parser.add_argument("--interval", type=int, default=2)
    args = parser.parse_args()
    run_demo(args.duration, args.setpoint, args.interval)


if __name__ == "__main__":
    main()
