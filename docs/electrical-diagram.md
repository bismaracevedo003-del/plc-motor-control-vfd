# Power and control diagrams

The editable SVGs are in `screenshots/power-circuit.svg` and `screenshots/control-circuit.svg`.

## 1. Power circuit

```text
L1 L2 L3 → Q1 breaker → F1 fuses → KM1 contactor → VFD → M 3~
                                      ↓
                                   PE / ground
```

| Device | Function |
| --- | --- |
| `Q1` | Main circuit breaker, motor-group protection |
| `F1` | Backup fuses for the VFD |
| `KM1` | Line contactor commanded by `Q0.0` |
| `VFD` | Variable frequency drive, 0-50 Hz |
| `M` | 3-phase induction motor, 4 kW, 400 V, 50 Hz |
| `F2` | Thermal overload relay (auxiliary to `I0.1`) |

## 2. Control circuit

```text
+24 V → F3 → S1 E-stop (NC) → F2 overload (NC) → PLC DI
PLC Q0.0 → K1 relay → KM1 coil
PLC Q0.1 → fault reset pushbutton equivalent
```

| Device | Function |
| --- | --- |
| `S1` | Emergency stop, NC, `I0.0` |
| `S2` | Local start, NO, `I0.5` |
| `S3` | Local stop, NC, `I0.6` |
| `S4` | Local/remote selector, `I0.4` |
| `K1` | Interposing relay for contactor coil |
| `H1/H2` | Run and fault indication |
| `H3` | Horn |

## 3. Safety notes

- The E-stop must interrupt the contactor coil circuit independently of software.
- VFD enable and contactor feedback must be verified before applying run.
- This is a training design; verify safety categories and wiring with a qualified electrician.

## 4. Nota (ES)

Los diagramas muestran la intención de diseño; no sustituyen un esquema eléctrico aprobado para instalación real.
