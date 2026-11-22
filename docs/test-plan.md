# Test plan and results

## 1. Scope

Tests cover scaling, ramp behavior, start permissives, fault latching/reset, current model, telemetry contract and REST endpoints. No physical motor or VFD was connected.

## 2. Test cases

| ID | Case | Expected | Status |
| --- | --- | --- | --- |
| T-01 | 4-20 mA to Hz scaling | 4 mA → 0 Hz, 20 mA → 50 Hz | Pass |
| T-02 | Ramp up at 5 Hz/s | 10 Hz after 2 s from 0 | Pass |
| T-03 | Ramp down at 7 Hz/s | 0 Hz after 2 s from 10 Hz | Pass |
| T-04 | Start with E-stop tripped | Remains stopped, fault code 5 | Pass |
| T-05 | Start with overload tripped | Remains stopped, fault code 1 | Pass |
| T-06 | Start with VFD not ready | Remains stopped, fault code 2 | Pass |
| T-07 | Start with zero setpoint | Start rejected | Pass |
| T-08 | Normal start | State STARTING then RUNNING | Pass |
| T-09 | Overload during run | Fault latched, run output off | Pass |
| T-10 | Reset with fault still active | Fault remains | Pass |
| T-11 | Reset after fault clears | Fault clears, start allowed | Pass |
| T-12 | Overcurrent trip after 2 s | Fault code 3 | Pass |
| T-13 | Current increases with frequency | Monotonic below rated load | Pass |
| T-14 | StartCount only increments on accepted starts | Verified | Pass |
| T-15 | REST state and commands | DB20 contract honored | Pass |

## 3. Commands

```powershell
python -m unittest discover -s simulation/tests -v
```

## 4. Pending verification (hardware)

- TIA Openness project generation and download to CPU 1214C.
- VFD run/enable wiring and analog reference loop check.
- Motor current measurement with a real clamp meter.
- E-stop category verification by a qualified electrician.

## 5. Nota (ES)

Todos los casos automatizados pasan en simulador. Los pendientes requieren hardware y no se presentan como resultados obtenidos.
