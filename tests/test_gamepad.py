from dataclasses import replace
from pathlib import Path
import time
import unittest
from unittest.mock import patch

import numpy as np
from opentdcr import load_config
from opentdcr.gamepad import DualSenseUSB, GamepadState, parse_usb_report, validate_gamepad
from opentdcr.teleop import TeleopSession
from opentdcr.transport import DryRunTransport


class GamepadTests(unittest.TestCase):
    def report(self):
        data = [0]*64
        data[0] = 1
        data[1:5] = [128]*4
        data[8] = 8  # no D-pad press
        return data

    def test_center_deadzone(self):
        data = self.report(); data[1:3] = [130, 127]
        state = parse_usb_report(data, 10)
        self.assertEqual((state.x, state.y), (0, 0))
        self.assertFalse(state.deadman)

    def test_buttons_and_axis_mapping(self):
        data = self.report(); data[1] = 255; data[2] = 0
        data[8] = 64; data[9] = 1
        state = parse_usb_report(data, 10)
        self.assertAlmostEqual(np.hypot(state.x, state.y), 1)
        self.assertTrue(state.deadman and state.exit and state.next_segment)
        self.assertGreater(state.x, 0)
        self.assertGreater(state.y, 0)

    def test_wireless_and_malformed_rejected(self):
        for data in ([], [1]*78, [49]*64, self.report()[:-1]):
            with self.assertRaises(ValueError): parse_usb_report(data, 10)

    def test_stale_and_released_deadman_rejected(self):
        state = parse_usb_report(self.report(), 10)
        with self.assertRaises(RuntimeError): validate_gamepad(state, 10.3)
        with self.assertRaises(RuntimeError): validate_gamepad(state, 10.1, require_deadman=True)
        self.assertIs(validate_gamepad(state, 10.1), state)
        with self.assertRaises(RuntimeError): validate_gamepad(replace(state, exit=True), 10.1)

    def test_no_import_or_device_io_on_construction(self):
        with patch("opentdcr.gamepad.importlib.import_module", side_effect=AssertionError("HID import")):
            controller = DualSenseUSB()
            controller.close()

    def test_guard_prevents_motion(self):
        cfg = load_config(Path(__file__).resolve().parents[1] / "configs/three_segment.example.json")
        transport = DryRunTransport(cfg).open()
        session = TeleopSession(cfg, transport)
        session.motion_guard = lambda: validate_gamepad(parse_usb_report(self.report(), time.monotonic()),
                                                       require_deadman=True)
        with self.assertRaises(RuntimeError): session.step((1, 0))
        np.testing.assert_array_equal(transport.position_mm, np.zeros(9))
        np.testing.assert_array_equal(session.coordinates_mm, np.zeros((3, 2)))

    def test_unbounded_input_rejected(self):
        cfg = load_config(Path(__file__).resolve().parents[1] / "configs/three_segment.example.json")
        session = TeleopSession(cfg, DryRunTransport(cfg).open())
        with self.assertRaises(ValueError): session.step((10, 10))


if __name__ == "__main__":
    unittest.main()
