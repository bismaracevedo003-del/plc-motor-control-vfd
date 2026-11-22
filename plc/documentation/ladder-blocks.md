# Ladder block documentation

SCL sources in `../program/src/` are imported by the Openness script. Use the networks below as the reference when recreating the blocks in LAD in TIA Portal V19.

## FB_VFD_Ramp

| Network | Contacts / operations | Result |
| --- | --- | --- |
| N1 | `Enable` NO → `target := Setpoint` else `target := 0` | Active target |
| N2 | `Actual < target` → `ADD(Actual, AccelRate * 0.1)` | Ramp up |
| N3 | `Actual > target` → `SUB(Actual, DecelRate * 0.1)` | Ramp down |
| N4 | `LIMIT(0, Actual, 50)` | Bounded frequency |
| N5 | `ABS(Actual - target) <= 0.5` → `Done` | At target |

## FB_MotorFaults

| Network | Contacts / operations | Result |
| --- | --- | --- |
| N1 | `EStopOK` NC → `newCode := 5` | E-stop fault |
| N2 | `OverloadOK` NC → `newCode := 1` | Overload fault (higher priority overrides) |
| N3 | `TempOK` NC → `newCode := 4` | Cooling fault |
| N4 | `VFDReady` NC + `RunRequest` → `newCode := 2` | Drive fault |
| N5 | `OvercurrentTimed` → `newCode := 3` | Overcurrent |
| N6 | `newCode <> 0` → `MOV(newCode, latchedCode)` | Latch |
| N7 | `ResetEdge` + `newCode = 0` → `MOV(0, latchedCode)` | Reset only when healthy |

## FB_MotorControl

| Network | Contacts / operations | Result |
| --- | --- | --- |
| N1 | `FaultCode <> 0` → `State := 4`, `RunOutput := FALSE` | Fault state |
| N2 | `Stop request` → `State := 3`, `RampEnable := TRUE` | Stop ramp |
| N3 | `Start edge` + permissives + `State = 0` → `State := 1`, `RunOutput := TRUE` | Start |
| N4 | `State = 1` + `Done` → `State := 2` | Running |
| N5 | `State = 3` + `Actual <= 0.5` → `State := 0` | Stopped |
| N6 | `RunOutput` → `INC Runtime` | Runtime counter |

## OB1

| Network | Description |
| --- | --- |
| N1 | Scale speed reference and current feedback |
| N2 | Call `FB_MotorFaults` with timer-based overcurrent detection |
| N3 | Call `FB_MotorControl` with local/remote command selection |
| N4 | Call `FB_VFD_Ramp` with `RampEnable` from the state machine |
| N5 | Map run, lamps, horn and DB20 telemetry |

## Nota (ES)

El estado `FAULTED` tiene prioridad absoluta: ningún Start puede salir de él sin un Reset válido con la falla ya desaparecida.
