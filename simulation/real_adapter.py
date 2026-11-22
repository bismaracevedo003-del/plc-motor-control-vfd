"""Optional real-mode (Siemens S7) source for the motor/VFD station.

The Python simulator remains the default source. Real mode is enabled only
through environment variables. Missing configuration or a missing optional
dependency raises a clear error; it never falls back to simulation silently.

Address format: ``AREA:byte[.bit]`` where AREA is ``DBnn``, ``I``, ``Q`` or
``M`` (for example ``DB20:0.0`` or ``I0:0``).
"""

from __future__ import annotations

import json
import os
import re
import struct
from dataclasses import dataclass
from typing import Any

TAG_TYPES = {
    'StartCmd': 'bool',
    'StopCmd': 'bool',
    'ResetCmd': 'bool',
    'RemoteMode': 'bool',
    'SpeedSetpoint_Hz': 'real',
    'ActualFrequency_Hz': 'real',
    'MotorCurrent_A': 'real',
    'State': 'int',
    'FaultCode': 'int',
    'FaultLatched': 'bool',
    'RunOutput': 'bool',
    'VFDReady': 'bool',
    'OverloadOK': 'bool',
    'EStopOK': 'bool',
    'AccelRate_Hz_s': 'real',
    'DecelRate_Hz_s': 'real',
    'RatedCurrent_A': 'real',
    'Runtime_s': 'dint',
    'StartCount': 'int',
}

DEFAULT_S7_ADDRESS_MAP = {
    'StartCmd': 'DB20:0.0',
    'StopCmd': 'DB20:0.1',
    'ResetCmd': 'DB20:0.2',
    'RemoteMode': 'DB20:0.3',
    'SpeedSetpoint_Hz': 'DB20:4',
    'ActualFrequency_Hz': 'DB20:8',
    'MotorCurrent_A': 'DB20:12',
    'State': 'DB20:16',
    'FaultCode': 'DB20:18',
    'FaultLatched': 'DB20:20.0',
    'RunOutput': 'DB20:20.1',
    'VFDReady': 'DB20:20.2',
    'OverloadOK': 'DB20:20.3',
    'EStopOK': 'DB20:20.4',
    'AccelRate_Hz_s': 'DB20:22',
    'DecelRate_Hz_s': 'DB20:26',
    'RatedCurrent_A': 'DB20:30',
    'Runtime_s': 'DB20:34',
    'StartCount': 'DB20:38',
}

WRITABLE_TAGS = (
    'StartCmd', 'StopCmd', 'ResetCmd', 'RemoteMode',
    'SpeedSetpoint_Hz', 'AccelRate_Hz_s', 'DecelRate_Hz_s', 'RatedCurrent_A',
)

_ADDRESS_RE = re.compile(r'^(?P<area>DB\d+|I|Q|M):(?P<byte>\d+)(?:\.(?P<bit>[0-7]))?$')
_TRUE_VALUES = ('1', 'true', 'yes', 'on')
_FALSE_VALUES = ('0', 'false', 'no', 'off')


class RealModeError(RuntimeError):
    """Base error for the optional real-mode adapter."""


class RealModeConfigurationError(RealModeError):
    """Raised when MODE=real is requested with incomplete or invalid config."""


class RealModeDependencyError(RealModeError):
    """Raised when MODE=real is requested but its optional package is absent."""


class WriteNotAllowedError(RealModeError):
    """Raised when a write is attempted without ALLOW_WRITES=true."""


@dataclass(frozen=True)
class RealConfig:
    mode: str
    strict: bool
    allow_writes: bool
    log_level: str
    host: str
    port: int
    rack: int
    slot: int
    address_map: dict[str, str]


def _filled(value: Any) -> bool:
    text = '' if value is None else str(value).strip()
    return bool(text) and not text.startswith('<')


def _env_bool(env: Any, name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return default
    text = str(raw).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise RealModeConfigurationError(f'{name} must be true or false, got {raw!r}')


def _env_int(env: Any, name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError) as exc:
        raise RealModeConfigurationError(f'{name} must be an integer, got {raw!r}') from exc
    if not minimum <= value <= maximum:
        raise RealModeConfigurationError(f'{name} must be between {minimum} and {maximum}, got {value}')
    return value


def _parse_address(address: str) -> tuple[str, int, int, int | None]:
    text = '' if address is None else str(address).strip().upper()
    match = _ADDRESS_RE.fullmatch(text)
    if not match:
        raise RealModeConfigurationError(
            f'Invalid S7 address {address!r}; expected AREA:byte[.bit] '
            f'(AREA = DBnn, I, Q or M)'
        )
    area = match.group('area')
    db_number = int(area[2:]) if area.startswith('DB') else 0
    area_kind = 'DB' if area.startswith('DB') else area
    bit = match.group('bit')
    return area_kind, db_number, int(match.group('byte')), int(bit) if bit is not None else None


def _load_address_map(env: Any) -> dict[str, str]:
    result = dict(DEFAULT_S7_ADDRESS_MAP)
    raw = env.get('S7_ADDRESS_MAP')
    if raw is None or not str(raw).strip():
        return result
    try:
        overrides = json.loads(str(raw))
    except json.JSONDecodeError as exc:
        raise RealModeConfigurationError(f'S7_ADDRESS_MAP must be valid JSON: {exc}') from exc
    if not isinstance(overrides, dict):
        raise RealModeConfigurationError('S7_ADDRESS_MAP must be a JSON object of tag -> address')
    unknown = sorted(set(overrides) - set(result))
    if unknown:
        raise RealModeConfigurationError(f'S7_ADDRESS_MAP contains unknown tags: {", ".join(unknown)}')
    for tag, address in overrides.items():
        _, _, _, bit = _parse_address(str(address))
        if TAG_TYPES[tag] != 'bool' and bit is not None:
            raise RealModeConfigurationError(f'S7_ADDRESS_MAP tag {tag} is not bool; remove the bit suffix')
        if TAG_TYPES[tag] == 'bool' and bit is None:
            raise RealModeConfigurationError(f'S7_ADDRESS_MAP tag {tag} is bool; add a .bit suffix')
        result[tag] = str(address).strip().upper()
    return result


def load_real_config(env: Any = None) -> RealConfig:
    """Validate MODE=real settings. Never supplies simulation defaults for missing values."""
    env = os.environ if env is None else env
    mode = str(env.get('MODE', 'simulation')).strip().lower() or 'simulation'
    if mode not in ('simulation', 'real'):
        raise RealModeConfigurationError(f'MODE must be "simulation" or "real", got {mode!r}')

    strict = _env_bool(env, 'REAL_STRICT', True)
    allow_writes = _env_bool(env, 'ALLOW_WRITES', False)
    log_level = str(env.get('LOG_LEVEL', 'INFO')).strip().upper() or 'INFO'

    if mode == 'simulation':
        return RealConfig(mode, strict, allow_writes, log_level, '', 102, 0, 1, dict(DEFAULT_S7_ADDRESS_MAP))

    if not strict:
        raise RealModeConfigurationError(
            'REAL_STRICT=false is not allowed with MODE=real; silent fallback to simulation is forbidden'
        )
    missing = [name for name in ('S7_HOST', 'S7_RACK', 'S7_SLOT') if not _filled(env.get(name))]
    if missing:
        raise RealModeConfigurationError(
            'MODE=real requires explicit configuration; missing or placeholder values: ' + ', '.join(missing)
        )
    return RealConfig(
        mode=mode,
        strict=strict,
        allow_writes=allow_writes,
        log_level=log_level,
        host=str(env['S7_HOST']).strip(),
        port=_env_int(env, 'S7_PORT', 102, 1, 65535),
        rack=_env_int(env, 'S7_RACK', 0, 0, 7),
        slot=_env_int(env, 'S7_SLOT', 1, 0, 7),
        address_map=_load_address_map(env),
    )


class S7MotorAdapter:
    """Read-only-by-default S7 source with the same snapshot contract as MotorDrive."""

    def __init__(self, env: Any = None):
        self.config = load_real_config(env)
        if self.config.mode != 'real':
            raise RealModeConfigurationError('S7MotorAdapter requires MODE=real')
        self.address_map = self.config.address_map
        self._client = None
        self._area_codes: dict[str, Any] = {}

    def connect(self) -> 'S7MotorAdapter':
        try:
            import snap7
        except ImportError as exc:
            raise RealModeDependencyError(
                'MODE=real requires python-snap7; install requirements-real.txt on the target host. '
                'No simulation fallback is available.'
            ) from exc
        areas = snap7.types.Areas
        self._area_codes = {'DB': areas.DB, 'I': areas.PE, 'Q': areas.PA, 'M': areas.MK}
        client = snap7.client.Client()
        try:
            client.connect(self.config.host, self.config.rack, self.config.slot, self.config.port)
        except Exception as exc:
            raise RealModeError(
                f'Cannot connect to S7 PLC at {self.config.host} '
                f'rack={self.config.rack} slot={self.config.slot} port={self.config.port}: {exc}'
            ) from exc
        self._client = client
        return self

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.disconnect()
            finally:
                self._client = None

    def _read_tag(self, tag: str) -> Any:
        if self._client is None:
            raise RealModeError('S7 client is not connected; call connect() first')
        if tag not in self.address_map:
            raise RealModeConfigurationError(f'No address configured for tag {tag!r}')
        area_kind, db_number, byte, bit = _parse_address(self.address_map[tag])
        size = 1 if TAG_TYPES[tag] == 'bool' or bit is not None else {'int': 2, 'dint': 4, 'real': 4}[TAG_TYPES[tag]]
        try:
            data = self._client.read_area(self._area_codes[area_kind], db_number, byte, size)
        except Exception as exc:
            raise RealModeError(f'S7 read failed for {tag} at {self.address_map[tag]}: {exc}') from exc
        if TAG_TYPES[tag] == 'bool':
            if bit is None:
                raise RealModeConfigurationError(f'Bool tag {tag} needs a .bit suffix')
            return bool(data[0] & (1 << bit))
        if TAG_TYPES[tag] == 'int':
            return struct.unpack('>h', data)[0]
        if TAG_TYPES[tag] == 'dint':
            return struct.unpack('>i', data)[0]
        return round(struct.unpack('>f', data)[0], 3)

    def snapshot(self) -> dict[str, Any]:
        from motor_simulator import FAULT_NAMES

        values = {tag: self._read_tag(tag) for tag in TAG_TYPES}
        values['FaultName'] = FAULT_NAMES.get(values['FaultCode'], 'none')
        values['source'] = 'real-s7'
        values['elapsed_s'] = 0.0
        return values

    def tick(self, dt: float = 1.0) -> dict[str, Any]:
        del dt
        return self.snapshot()

    def _require_writes(self) -> None:
        if not self.config.allow_writes:
            raise WriteNotAllowedError(
                'Writes are disabled; set ALLOW_WRITES=true explicitly to command the PLC. '
                'Physical E-stop, overload and VFD-ready interlocks cannot be bypassed in software.'
            )

    def write_tag(self, tag: str, value: Any) -> None:
        self._require_writes()
        if tag not in WRITABLE_TAGS:
            raise RealModeError(f'Tag {tag!r} is read-only in the real adapter')
        if self._client is None:
            raise RealModeError('S7 client is not connected; call connect() first')
        area_kind, db_number, byte, bit = _parse_address(self.address_map[tag])
        if TAG_TYPES[tag] == 'bool':
            payload = bytes([1 if bool(value) else 0])
        elif TAG_TYPES[tag] == 'int':
            payload = struct.pack('>h', int(value))
        elif TAG_TYPES[tag] == 'dint':
            payload = struct.pack('>i', int(value))
        else:
            payload = struct.pack('>f', float(value))
        try:
            self._client.write_area(self._area_codes[area_kind], db_number, byte, payload)
        except Exception as exc:
            raise RealModeError(f'S7 write failed for {tag} at {self.address_map[tag]}: {exc}') from exc

    def command(self, name: str, value: Any = True) -> bool:
        mapping = {'START': 'StartCmd', 'STOP': 'StopCmd', 'RESET': 'ResetCmd'}
        if name not in mapping:
            return False
        self.write_tag(mapping[name], value)
        return True

    def release(self, name: str) -> bool:
        return self.command(name, False)

    def set_setpoint_hz(self, value: float) -> None:
        hz = min(50.0, max(0.0, float(value)))
        self.write_tag('SpeedSetpoint_Hz', hz)

    def set_fault(self, name: str, active: bool = True) -> bool:
        del name, active
        raise RealModeError('Fault injection is simulation-only; never inject faults into a real drive')


def create_drive_source(env: Any = None, source: str | None = None):
    """Factory: MotorDrive by default, connected S7MotorAdapter for real mode.

    Real mode is activated by the MODE=real environment variable. The
    ``source`` argument only selects the adapter once that variable is set.
    """
    env = os.environ if env is None else env
    mode_env = str(env.get('MODE', 'simulation')).strip().lower() or 'simulation'
    requested = source if source is not None else mode_env
    mode = str(requested).strip().lower()
    if mode not in ('simulation', 'real'):
        raise RealModeConfigurationError(f'source must be "simulation" or "real", got {requested!r}')
    if mode == 'simulation':
        from motor_simulator import MotorDrive

        return MotorDrive()
    if mode_env != 'real':
        raise RealModeConfigurationError(
            'MODE=real must be set in the environment before the real source can be selected'
        )
    return S7MotorAdapter(env=env).connect()
