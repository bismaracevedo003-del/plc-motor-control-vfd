import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor_server import create_server, drive
from motor_simulator import FAULTED, RUNNING, STARTING, STOPPED, MotorDrive, move_toward, scale_4_20ma, value_to_ma

TAGS = (
    'StartCmd', 'StopCmd', 'ResetCmd', 'RemoteMode', 'SpeedSetpoint_Hz',
    'ActualFrequency_Hz', 'MotorCurrent_A', 'State', 'FaultCode', 'FaultLatched',
    'RunOutput', 'VFDReady', 'OverloadOK', 'EStopOK', 'AccelRate_Hz_s',
    'DecelRate_Hz_s', 'RatedCurrent_A', 'Runtime_s', 'StartCount',
)


def running_drive(setpoint=30.0):
    motor = MotorDrive()
    motor.setpoint_hz = setpoint
    motor.command('START')
    for _ in range(8):
        motor.tick(1.0)
    motor.release('START')
    return motor


class ScalingTests(unittest.TestCase):
    def test_4ma_maps_to_zero(self):
        self.assertAlmostEqual(scale_4_20ma(4.0, 0.0, 50.0), 0.0)

    def test_20ma_maps_to_full_scale(self):
        self.assertAlmostEqual(scale_4_20ma(20.0, 0.0, 50.0), 50.0)
        self.assertAlmostEqual(scale_4_20ma(20.0, 0.0, 10.0), 10.0)

    def test_value_to_ma_roundtrip(self):
        self.assertAlmostEqual(scale_4_20ma(value_to_ma(35.0, 0.0, 50.0), 0.0, 50.0), 35.0)

    def test_move_toward_never_overshoots(self):
        self.assertEqual(move_toward(48.0, 50.0, 5.0), 50.0)
        self.assertEqual(move_toward(2.0, 0.0, 7.0), 0.0)


class RampTests(unittest.TestCase):
    def test_accel_ramp(self):
        motor = MotorDrive()
        motor.setpoint_hz = 30.0
        motor.command('START')
        motor.tick(1.0)
        motor.release('START')
        motor.tick(1.0)
        self.assertEqual(motor.frequency_hz, 10.0)
        self.assertEqual(motor.state, STARTING)

    def test_decel_ramp_to_stop(self):
        motor = running_drive()
        self.assertEqual(motor.state, RUNNING)
        motor.command('STOP')
        for _ in range(5):
            motor.tick(1.0)
        self.assertEqual(motor.state, STOPPED)
        self.assertEqual(motor.frequency_hz, 0.0)

    def test_reaches_running_state(self):
        motor = running_drive(setpoint=20.0)
        self.assertEqual(motor.state, RUNNING)
        self.assertEqual(motor.frequency_hz, 20.0)


class InterlockTests(unittest.TestCase):
    def test_estop_rejects_start(self):
        motor = MotorDrive()
        motor.e_stop_ok = False
        motor.command('START')
        snapshot = motor.tick()
        self.assertEqual(snapshot['State'], FAULTED)
        self.assertEqual(snapshot['FaultCode'], 5)
        self.assertEqual(snapshot['StartCount'], 0)

    def test_overload_rejects_start(self):
        motor = MotorDrive()
        motor.overload_ok = False
        motor.command('START')
        snapshot = motor.tick()
        self.assertEqual(snapshot['FaultCode'], 1)
        self.assertFalse(snapshot['RunOutput'])

    def test_vfd_not_ready_rejects_start(self):
        motor = MotorDrive()
        motor.vfd_ready = False
        motor.command('START')
        snapshot = motor.tick()
        self.assertEqual(snapshot['FaultCode'], 2)

    def test_zero_setpoint_rejects_start(self):
        motor = MotorDrive()
        motor.setpoint_hz = 0.0
        motor.command('START')
        snapshot = motor.tick()
        self.assertEqual(snapshot['State'], STOPPED)
        self.assertEqual(snapshot['StartCount'], 0)

    def test_local_mode_start(self):
        motor = MotorDrive()
        motor.remote_mode = False
        motor.local_start = True
        motor.tick()
        self.assertEqual(motor.state, STARTING)
        self.assertEqual(motor.start_count, 1)


class FaultTests(unittest.TestCase):
    def test_overload_during_run_latches_fault(self):
        motor = running_drive()
        motor.overload_ok = False
        snapshot = motor.tick()
        self.assertEqual(snapshot['FaultCode'], 1)
        self.assertTrue(snapshot['FaultLatched'])
        self.assertFalse(snapshot['RunOutput'])

    def test_reset_with_active_fault_keeps_latch(self):
        motor = running_drive()
        motor.overload_ok = False
        motor.tick()
        motor.command('RESET')
        snapshot = motor.tick()
        self.assertEqual(snapshot['FaultCode'], 1)

    def test_reset_after_fault_clears_allows_start(self):
        motor = running_drive()
        motor.overload_ok = False
        motor.tick()
        motor.overload_ok = True
        motor.command('RESET')
        motor.tick()
        motor.release('RESET')
        motor.command('START')
        snapshot = motor.tick()
        self.assertEqual(snapshot['FaultCode'], 0)
        self.assertEqual(snapshot['State'], STARTING)

    def test_overcurrent_trip_after_two_seconds(self):
        motor = running_drive()
        motor.load_factor = 3.0
        for _ in range(3):
            snapshot = motor.tick(1.0)
        self.assertEqual(snapshot['FaultCode'], 3)


class ModelContractTests(unittest.TestCase):
    def test_current_increases_with_frequency(self):
        low = MotorDrive()
        low.frequency_hz = 10.0
        low.state = RUNNING
        low._update_current(1.0)
        high = MotorDrive()
        high.frequency_hz = 40.0
        high.state = RUNNING
        high._update_current(1.0)
        self.assertGreater(high.current_a, low.current_a)

    def test_snapshot_exposes_db20_tags(self):
        snapshot = MotorDrive().tick()
        for tag in TAGS:
            self.assertIn(tag, snapshot)

    def test_start_count_only_for_accepted_starts(self):
        motor = MotorDrive()
        motor.e_stop_ok = False
        motor.command('START')
        motor.tick()
        motor.release('START')
        motor.e_stop_ok = True
        motor.command('RESET')
        motor.tick()
        motor.release('RESET')
        motor.command('START')
        motor.tick()
        self.assertEqual(motor.start_count, 1)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(port=0)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        drive.__init__()

    def request(self, path, payload=None):
        if payload is None:
            with urllib.request.urlopen(f'http://127.0.0.1:{self.port}{path}') as response:
                return response.status, json.load(response)
        data = json.dumps(payload).encode('utf-8')
        request = urllib.request.Request(
            f'http://127.0.0.1:{self.port}{path}',
            data=data,
            headers={'content-type': 'application/json'},
        )
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)

    def test_get_state(self):
        status, body = self.request('/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(body['State'], STOPPED)

    def test_command_endpoint(self):
        _, body = self.request('/api/command', {'command': 'START'})
        self.assertTrue(body['StartCmd'])

    def test_setpoint_endpoint(self):
        _, body = self.request('/api/setpoint', {'setpoint_hz': 42})
        self.assertEqual(body['SpeedSetpoint_Hz'], 42.0)

    def test_fault_endpoint(self):
        _, body = self.request('/api/fault', {'fault': 'overload', 'active': True})
        self.assertFalse(body['OverloadOK'])

    def test_invalid_command_returns_400(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request('/api/command', {'command': 'JUMP'})
        self.assertEqual(context.exception.code, 400)
        context.exception.close()

    def test_static_hmi_is_served(self):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/') as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b'VFD Motor Station', response.read())


if __name__ == '__main__':
    unittest.main()
