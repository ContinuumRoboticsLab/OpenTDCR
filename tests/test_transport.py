"""Fake SDK tests verify transaction order and failure behavior, never motor I/O."""
from dataclasses import replace
from pathlib import Path
import unittest
import warnings
from unittest.mock import patch
import numpy as np
from opentdcr import load_config
from opentdcr.transport import DynamixelTransport

CONFIG = Path(__file__).resolve().parents[1] / "configs/three_segment.example.json"


class FakePort:
    def __init__(self): self.closed = False
    def openPort(self): return True
    def setBaudRate(self, baudrate): return True
    def closePort(self): self.closed = True


class FakeSDK:
    COMM_SUCCESS = 0
    def __init__(self):
        self.port = FakePort()
        self.events = []
        self.registers = {}
        self.models = {}
        self.write_failure = None
        self.sync_failure = False
        self.read_failure = None
    def PortHandler(self, name): return self.port
    def PacketHandler(self, version): return self
    def ping(self, port, servo_id):
        self.events.append(("ping", servo_id))
        return self.models.get(servo_id, 1060), 0, 0
    def read1ByteTxRx(self, port, servo_id, addr):
        if self.read_failure == (servo_id, addr): return 0, -1, 0
        default = {11: 4, 10: 0, 12: 255, 64: 0, 68: 2, 98: 0, 70: 0}.get(addr, 0)
        return self.registers.get((servo_id, addr), default), 0, 0
    def read4ByteTxRx(self, port, servo_id, addr):
        if self.read_failure == (servo_id, addr): return 0, -1, 0
        return self.registers.get((servo_id, addr), 2048), 0, 0
    def write1ByteTxRx(self, port, servo_id, addr, value):
        self.events.append(("write", servo_id, addr, value))
        if self.write_failure == (servo_id, addr, value): return -1, 0
        self.registers[(servo_id, addr)] = value
        return 0, 0
    def write4ByteTxRx(self, port, servo_id, addr, value):
        return self.write1ByteTxRx(port, servo_id, addr, value)
    def GroupSyncWrite(self, port, packet, addr, size):
        owner = self
        class Writer:
            def __init__(self): self.targets = []
            def addParam(self, servo_id, data):
                self.targets.append((servo_id, int.from_bytes(bytes(data), "little")))
                return True
            def txPacket(self):
                owner.events.append(("sync", tuple(self.targets)))
                if owner.sync_failure: return -1
                for servo_id, value in self.targets:
                    owner.registers[(servo_id, 116)] = value
                    owner.registers[(servo_id, 132)] = value
                return 0
            def clearParam(self): pass
        return Writer()


class HardwareTransportTests(unittest.TestCase):
    def setUp(self):
        self.config = replace(load_config(CONFIG), hardware_reviewed=True)
        self.sdk = FakeSDK()
        self.driver = DynamixelTransport(self.config, "fake", confirm_home=True, sdk=self.sdk)

    def test_construction_performs_no_io(self):
        self.assertEqual(self.sdk.events, [])

    def test_neutral_goals_precede_torque_and_cleanup_disables_all(self):
        self.driver.open()
        events = self.sdk.events
        enables = [i for i, event in enumerate(events) if event[0] == "write" and event[2:] == (64, 1)]
        goals = [i for i, event in enumerate(events) if event[0] == "write" and event[2] == 116]
        self.assertLess(max(goals), min(enables))
        self.driver.close()
        for servo_id in self.config.servo_ids:
            self.assertEqual(self.sdk.registers[(servo_id, 64)], 0)
        self.assertTrue(self.sdk.port.closed)
        self.driver.close()  # idempotent

    def test_wrong_model_never_enables_torque(self):
        self.sdk.models[5] = 1234
        with self.assertRaises(ValueError): self.driver.open()
        self.assertFalse(any(e[0] == "write" and e[2:] == (64, 1) for e in self.sdk.events))
        self.assertTrue(self.sdk.port.closed)

    def test_active_secondary_id_rejected(self):
        self.sdk.registers[(1, 12)] = 5
        with self.assertRaises(ValueError): self.driver.open()
        self.assertFalse(any(e[0] == "write" and e[2:] == (64, 1) for e in self.sdk.events))

    def test_near_target_still_polls_until_profile_complete(self):
        self.driver.open()
        self.sdk.registers[(1, 122)] = 1
        self.sdk.registers[(1, 123)] = 2
        calls = 0
        def gate():
            nonlocal calls
            calls += 1
            if calls == 3:
                raise ValueError("tracking stale while profile still moving")
        with self.assertRaises(ValueError):
            self.driver.move(np.full(9, 0.01), check=gate)
        self.assertEqual(calls, 3)
        self.assertTrue(self.sdk.port.closed)

    def test_time_based_profile_rejected(self):
        self.sdk.registers[(2, 10)] = 4
        with self.assertRaises(ValueError): self.driver.open()
        self.assertFalse(any(e[0] == "write" and e[2:] == (64, 1) for e in self.sdk.events))

    def test_never_programs_zero_unlimited_velocity(self):
        cfg = replace(self.config, max_tendon_speed_mm_s=0.001)
        driver = DynamixelTransport(cfg, "fake", confirm_home=True, sdk=self.sdk)
        with self.assertRaises(ValueError): driver.open()
        self.assertFalse(any(e[0] == "write" and e[2:] == (112, 0) for e in self.sdk.events))

    def test_initialization_failure_disables_even_partially_enabled_motors(self):
        self.sdk.write_failure = (4, 64, 1)
        with self.assertRaises(OSError): self.driver.open()
        for servo_id in self.config.servo_ids:
            self.assertIn(("write", servo_id, 64, 0), self.sdk.events)

    def test_signed_ticks_and_direction(self):
        cfg = replace(self.config, servo_direction=(-1,)*9)
        driver = DynamixelTransport(cfg, "fake", confirm_home=True, sdk=self.sdk)
        for servo_id in cfg.servo_ids: self.sdk.registers[(servo_id, 132)] = (-1000) & 0xffffffff
        driver.open()
        driver.move(np.ones(9))
        np.testing.assert_array_equal(driver.zero_ticks, np.full(9, -1000))
        expected = -1000 - round(1 / 10 / driver.TICK_RAD)
        self.assertEqual(self.sdk.registers[(1, 132)], expected & 0xffffffff)
        driver.close()

    def test_write_failure_and_sensor_failure_disable_torque(self):
        for failure in ("write", "sensor"):
            with self.subTest(failure=failure):
                self.setUp()
                self.driver.open()
                if failure == "write": self.sdk.sync_failure = True
                def check():
                    if failure == "sensor": raise ValueError("tracking lost")
                with self.assertRaises((OSError, ValueError)):
                    self.driver.move(np.ones(9), check=check)
                self.assertFalse(self.driver.is_open)
                self.assertTrue(self.sdk.port.closed)
                for servo_id in self.config.servo_ids:
                    self.assertEqual(self.sdk.registers[(servo_id, 64)], 0)

    def test_position_read_failure_disables_torque(self):
        self.driver.open()
        self.sdk.read_failure = (1, 132)
        with self.assertRaises(OSError): self.driver.move(np.ones(9))
        self.assertFalse(self.driver.is_open)
        self.assertTrue(self.sdk.port.closed)

    def test_capture_reference_uses_actual_signed_encoders_without_motion(self):
        cfg = replace(self.config, servo_direction=(-1,)*9)
        driver = DynamixelTransport(cfg, "fake", confirm_home=True, sdk=self.sdk).open()
        driver.move(np.ones(9))
        # Readback differs slightly from the last commanded position.
        self.sdk.registers[(1, 132)] += 1
        actual_before = driver.read_positions_mm()
        events_before = list(self.sdk.events)
        reference = driver.capture_reference()
        np.testing.assert_allclose(reference["offsets_mm"], actual_before)
        self.assertEqual(reference["zero_ticks"][0], self.sdk.registers[(1, 132)])
        self.assertEqual(self.sdk.events, events_before)  # rebase issues no movement
        np.testing.assert_array_equal(driver.read_positions_mm(), np.zeros(9))
        driver.move(np.full(9, 0.2))
        expected = reference["zero_ticks"][0] - round(0.2 / 10 / driver.TICK_RAD)
        self.assertEqual(self.sdk.registers[(1, 132)], expected)
        driver.close()

    def test_reference_capture_failure_disables_torque(self):
        for failure in ("moving", "read"):
            with self.subTest(failure=failure):
                self.setUp()
                self.driver.open()
                initial_zero = self.driver.zero_ticks.copy()
                if failure == "moving":
                    self.sdk.registers[(1, 122)] = 1
                else:
                    self.sdk.read_failure = (1, 132)
                with self.assertRaises((RuntimeError, OSError)):
                    self.driver.capture_reference()
                np.testing.assert_array_equal(self.driver.zero_ticks, initial_zero)
                self.assertFalse(self.driver.is_open)
                for servo_id in self.config.servo_ids:
                    self.assertEqual(self.sdk.registers[(servo_id, 64)], 0)

    def test_shutdown_attempts_all_motors_even_when_warnings_are_errors(self):
        self.driver.open()
        self.sdk.write_failure = (1, 64, 0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            with self.assertRaises(RuntimeWarning):
                self.driver.close()
        for servo_id in self.config.servo_ids:
            self.assertIn(("write", servo_id, 64, 0), self.sdk.events)
        for servo_id in self.config.servo_ids[1:]:
            self.assertEqual(self.sdk.registers[(servo_id, 64)], 0)
        self.assertTrue(self.sdk.port.closed)
        self.assertIsNone(self.driver.port)
        self.assertFalse(self.driver.is_open)
        self.driver.close()


if __name__ == "__main__":
    unittest.main()
