# Signal list and tag map

## 1. Physical I/O

| Address | Type | Description | State |
| --- | --- | --- | --- |
| `I0.0` | DI | Emergency stop contact (NC) | 1 = healthy |
| `I0.1` | DI | Overload relay auxiliary (NC) | 1 = healthy |
| `I0.2` | DI | VFD ready | 1 = ready |
| `I0.3` | DI | Motor thermistor / temperature OK | 1 = healthy |
| `I0.4` | DI | Local mode selector | 1 = local |
| `I0.5` | DI | Local start pushbutton (NO) | 1 = pressed |
| `I0.6` | DI | Local stop pushbutton (NC) | 1 = healthy |
| `IW64` | AI | Speed reference potentiometer, 4-20 mA | 0-50 Hz |
| `IW66` | AI | Motor current transmitter, 4-20 mA | 0-10 A |
| `Q0.0` | DO | VFD run command | 1 = run |
| `Q0.1` | DO | Fault reset pulse | 1 = reset |
| `Q0.2` | DO | Run lamp (green) | 1 = on |
| `Q0.3` | DO | Fault lamp (red) | 1 = on |
| `Q0.4` | DO | Horn | 1 = on |
| `QW80` | AQ | VFD speed reference, 4-20 mA | 0-50 Hz |

## 2. HMI tag database (DB20)

| Name | Type | Access | Description |
| --- | --- | --- | --- |
| `StartCmd` | Bool | R/W | Remote start command |
| `StopCmd` | Bool | R/W | Remote stop command |
| `ResetCmd` | Bool | R/W | Fault reset command |
| `RemoteMode` | Bool | R/W | 1 = HMI controls the motor |
| `SpeedSetpoint_Hz` | Real | R/W | Requested frequency, 0-50 Hz |
| `ActualFrequency_Hz` | Real | R | Ramped output frequency |
| `MotorCurrent_A` | Real | R | Measured current |
| `State` | Int | R | 0 stopped, 1 starting, 2 running, 3 stopping, 4 faulted |
| `FaultCode` | Int | R | 0 none, 1 overload, 2 VFD fault, 3 overcurrent, 4 cooling, 5 E-stop |
| `FaultLatched` | Bool | R | Fault memory active |
| `RunOutput` | Bool | R | VFD run command status |
| `VFDReady` | Bool | R | Drive ready input |
| `OverloadOK` | Bool | R | Overload relay health |
| `EStopOK` | Bool | R | E-stop health |
| `AccelRate_Hz_s` | Real | R/W | Acceleration ramp, Hz/s |
| `DecelRate_Hz_s` | Real | R/W | Deceleration ramp, Hz/s |
| `RatedCurrent_A` | Real | R/W | Motor rated current, A |
| `Runtime_s` | DInt | R | Accumulated running time |
| `StartCount` | Int | R | Number of start commands accepted |

## 3. Scaling

```text
Hz = ((RAW - 5530) / 22118) * 50.0
A  = ((RAW - 5530) / 22118) * 10.0
```

## 4. Nota (ES)

Las señales NC se leen como `1 = healthy`; así una pérdida de cable también se detecta como falla.
