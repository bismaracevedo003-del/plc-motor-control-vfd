# TIA Portal V19 project generation

## Requirements

- TIA Portal V19 with a valid TIA Openness license.
- PowerShell 5.1+.
- S7-1200 CPU 1214C hardware catalog entry.

## Build

```powershell
cd plc\program
.\generate_tia_project.ps1
```

The script creates `tia_export/PLC_Motor_Control_VFD.ap19`, imports the sources in `src/`, generates the blocks and compiles. Use `-WithoutUI` for unattended builds.

`.ap19` files are ignored by Git. The `.scl` sources and `../documentation/ladder-blocks.md` are the versioned source of truth.

## Blocks

| Block | Purpose |
| --- | --- |
| `DB20` | HMI/API tag interface |
| `FB_AI_Scale` | 4-20 mA scaling |
| `FB_VFD_Ramp` | Acceleration/deceleration ramp |
| `FB_MotorFaults` | Priority fault latching and reset |
| `FB_MotorControl` | State machine and interlocks |
| `OB1` | I/O mapping and cyclic coordination |

## Not verified here

Written against the TIA V19 Openness PublicAPI but not executed in this environment. Verify the generated project in TIA before claiming hardware validation.

## Nota (ES)

Sin licencia Openness, importa los `.scl` desde TIA usando `External source files` y reconstruye las redes LAD con la documentación.
