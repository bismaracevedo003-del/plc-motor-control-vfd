# Real-mode integration (motor/VFD)

## 1. Default behaviour

`MODE` is unset by default, which means `simulation`. The existing simulator,
REST server, HMI and tests are unchanged. `simulation/real_adapter.py` is only
imported by the new CLI factory and is never used by `motor_server.py`.

## 2. Enabling real mode

Real mode is activated **only** by environment variables. The optional CLI
flag `--source real` selects the real adapter but still requires `MODE=real`.

```powershell
$env:MODE = 'real'
$env:REAL_STRICT = 'true'
$env:S7_HOST = '192.0.2.10'      # documentation IP: replace with the PLC IP
$env:S7_RACK = '0'
$env:S7_SLOT = '1'
python simulation/motor_simulator.py --duration 10 --source real
```

`S7_PORT` defaults to 102. `S7_HOST`, `S7_RACK` and `S7_SLOT` are mandatory in
real mode; placeholder values (`<...>`) count as missing. If the `snap7`
package is absent, or the PLC cannot be reached, the adapter raises
`RealModeDependencyError` / `RealModeConfigurationError` / `RealModeError`.
There is **no** silent fallback to simulation.

Optional packages are declared in `requirements-real.txt`. They are not
installed or required for the simulation tests.

## 3. Address map

`S7_ADDRESS_MAP` is an optional JSON object that overrides individual DB20
tag addresses. Address format is `AREA:byte[.bit]`, where AREA is `DBnn`,
`I`, `Q` or `M`. Booleans require a `.bit` suffix; `int`/`dint`/`real` tags
do not. Defaults mirror `docs/signal-list.md` (non-optimised DB20):

| Tag | Default | Tag | Default |
| --- | --- | --- | --- |
| `StartCmd` | `DB20:0.0` | `State` | `DB20:16` |
| `StopCmd` | `DB20:0.1` | `FaultCode` | `DB20:18` |
| `ResetCmd` | `DB20:0.2` | `FaultLatched` | `DB20:20.0` |
| `RemoteMode` | `DB20:0.3` | `RunOutput` | `DB20:20.1` |
| `SpeedSetpoint_Hz` | `DB20:4` | `VFDReady` | `DB20:20.2` |
| `ActualFrequency_Hz` | `DB20:8` | `OverloadOK` | `DB20:20.3` |
| `MotorCurrent_A` | `DB20:12` | `EStopOK` | `DB20:20.4` |
| `AccelRate_Hz_s` | `DB20:22` | `RatedCurrent_A` | `DB20:30` |
| `DecelRate_Hz_s` | `DB20:26` | `Runtime_s` | `DB20:34` |
| `StartCount` | `DB20:38` | | |

Example partial override:

```powershell
$env:S7_ADDRESS_MAP = '{"StartCmd":"DB30:2.0","ActualFrequency_Hz":"DB30:10"}'
```

Unknown tags, malformed JSON or invalid addresses fail with a clear error.

## 4. Read-only by default and safety

`ALLOW_WRITES=false` (default): `snapshot()`/`tick()` only read DB20 and
return the same tag contract as the simulator (`source` becomes `real-s7`).
`write_tag()`, `command()`, `release()` and `set_setpoint_hz()` raise
`WriteNotAllowedError` until `ALLOW_WRITES=true` is set explicitly.
`set_fault()` always raises: fault injection is simulation-only.

Even with writes enabled, software must never bypass the physical E-stop,
overload relay, thermistor or VFD-ready interlocks. Those remain field
contacts wired to the safety circuit, not writable tags.

## 5. Programmatic use

```python
from real_adapter import create_drive_source

drive = create_drive_source()          # MotorDrive unless MODE=real
try:
    print(drive.tick())
finally:
    close = getattr(drive, 'close', None)
    if close:
        close()
```

## 6. Verification

```powershell
python -m unittest discover -s simulation/tests -v
```
