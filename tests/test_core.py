import contextlib
from dataclasses import asdict, replace
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np
from opentdcr import TendonKinematics, load_config
from opentdcr.cli import main
from opentdcr.config import RobotConfig
from opentdcr.sensors import MockSensor, PositionMeasurement, validate_measurement
from opentdcr.teleop import TeleopSession
from opentdcr.transport import DryRunTransport, DynamixelTransport

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/three_segment.example.json"


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(CONFIG.read_text())

    def test_sample_is_not_hardware_reviewed(self):
        self.assertFalse(load_config(CONFIG).hardware_reviewed)

    def test_rejects_bad_motor_maps(self):
        for key, value in (("servo_ids", [1]*9), ("servo_direction", [0]*9),
                           ("spool_radius_mm", [0]*9), ("tendons_per_segment", [2, 3, 4])):
            with self.subTest(key=key), self.assertRaises(ValueError):
                RobotConfig.from_dict({**self.data, key: value})

    def test_rejects_nonfinite_and_bool(self):
        for value in (float("nan"), float("inf"), -1, 0, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                RobotConfig.from_dict({**self.data, "keyboard_step_mm": value})

    def test_rejects_unknown_fields_and_wrong_lengths(self):
        with self.assertRaises(ValueError):
            RobotConfig.from_dict({**self.data, "typo": 1})
        with self.assertRaises(ValueError):
            RobotConfig.from_dict({**self.data, "max_bend_rad": [1]})

    def test_direct_construction_copies_mutable_arrays(self):
        source = load_config(CONFIG)
        ids = list(source.servo_ids)
        config = replace(source, servo_ids=ids)
        ids[0] = 200
        self.assertEqual(config.servo_ids[0], 1)
        self.assertIsInstance(config.servo_ids, tuple)

    def test_hardware_requires_all_acknowledgements(self):
        cfg = load_config(CONFIG)
        with self.assertRaises(ValueError):
            DynamixelTransport(cfg, "unused", confirm_home=True)
        with self.assertRaises(ValueError):
            DynamixelTransport(replace(cfg, hardware_reviewed=True), "unused")
        with self.assertRaises(ValueError):
            DynamixelTransport(replace(cfg, hardware_reviewed=True), "", confirm_home=True)


class KinematicsTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(CONFIG)
        self.model = TendonKinematics(self.config)

    def test_neutral_is_zero(self):
        np.testing.assert_array_equal(self.model.to_tendons(np.zeros((3, 2))), np.zeros(9))

    def test_round_trip_with_mixed_radii_and_tendon_counts(self):
        cfg = replace(self.config, tendons_per_segment=(3, 4, 3), tendon_radius_mm=(2, 4, 3),
                      servo_ids=tuple(range(10)), spool_radius_mm=(10,)*10, servo_direction=(1,)*10)
        model = TendonKinematics(cfg)
        values = np.array([[0.2, -0.3], [-0.5, 0.1], [0.15, 0.6]])
        np.testing.assert_allclose(model.from_tendons(model.to_tendons(values)), values, atol=1e-12)

    def test_proximal_bend_affects_distal_tendons(self):
        values = np.zeros((3, 2)); values[0, 0] = 1
        tendons = self.model.to_tendons(values)
        self.assertTrue(np.any(tendons[6:] != 0))
        values[:] = 0; values[2, 0] = 1
        np.testing.assert_array_equal(self.model.to_tendons(values)[:6], np.zeros(6))

    def test_radius_scaling_has_physical_meaning(self):
        cfg = replace(self.config, tendon_radius_mm=(2, 4, 3), tendon_angle_offset_rad=(0, 0, 0))
        model = TendonKinematics(cfg)
        values = np.zeros((3, 2)); values[0, 0] = 0.5
        # A 0.25 rad base bend gives 0.5, 1.0, 0.75 mm along each group's first tendon.
        np.testing.assert_allclose(model.to_tendons(values)[::3], [0.5, 1.0, 0.75])

    def test_clamp_preserves_direction_and_limits_each_segment(self):
        values = np.array([[30, 40], [0.1, 0], [0, 0]])
        result = self.model.clamp(values)
        self.assertAlmostEqual(np.linalg.norm(result[0]), self.model.limit_mm[0])
        self.assertAlmostEqual(result[0, 0] / result[0, 1], 3/4)
        np.testing.assert_array_equal(result[1:], values[1:])

    def test_invalid_input_rejected(self):
        for values in ([1, 2], np.full((3, 2), np.nan)):
            with self.assertRaises(ValueError):
                self.model.to_tendons(values)


class MeasurementTests(unittest.TestCase):
    def test_valid_sample(self):
        sample = PositionMeasurement((1, 2, 3), 10)
        self.assertIs(validate_measurement(sample, now_s=10.1), sample)

    def test_stale_future_missing_and_invalid_rejected(self):
        samples = [PositionMeasurement((1, 2, 3), 9), PositionMeasurement((1, 2, 3), 11),
                   PositionMeasurement((1, 2, float("nan")), 10),
                   PositionMeasurement((1, 2, 3), 10, frame="camera"),
                   PositionMeasurement((1, 2, 3), 10, valid=False),
                   PositionMeasurement((1, 2), 10), None]
        for sample in samples:
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                validate_measurement(sample, now_s=10.1)

    def test_stale_sensor_prevents_write_and_state_change(self):
        cfg = load_config(CONFIG)
        transport = DryRunTransport(cfg).open()
        class StaleSensor:
            def read(self): return PositionMeasurement((0, 0, 0), time.monotonic()-1)
        session = TeleopSession(cfg, transport, StaleSensor())
        with self.assertRaises(ValueError):
            session.command("w")
        np.testing.assert_array_equal(transport.position_mm, np.zeros(9))
        np.testing.assert_array_equal(session.coordinates_mm, np.zeros((3, 2)))

    def test_travel_limit_rejects_without_writes(self):
        cfg = replace(load_config(CONFIG), max_tendon_travel_mm=0.1)
        transport = DryRunTransport(cfg).open()
        with self.assertRaises(ValueError):
            transport.move(np.ones(9))
        np.testing.assert_array_equal(transport.position_mm, np.zeros(9))


class CLITests(unittest.TestCase):
    def test_dry_run_commands_never_import_sdk(self):
        with patch("opentdcr.transport.importlib.import_module", side_effect=AssertionError("SDK import")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = main(["teleop", "--config", str(CONFIG), "--commands", "1 w 2 a home q"])
            self.assertEqual(result, 0)
            self.assertIn("DRY RUN", output.getvalue())

    def test_invalid_script_is_nonzero(self):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["teleop", "--config", str(CONFIG), "--commands", "bad"]), 2)

    def test_hardware_script_blocked_before_sdk_import(self):
        with patch("opentdcr.transport.importlib.import_module", side_effect=AssertionError("SDK import")):
            with contextlib.redirect_stderr(io.StringIO()):
                result = main(["teleop", "--config", str(CONFIG), "--hardware", "--commands", "w"])
            self.assertEqual(result, 2)

    def test_inspect_json(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["inspect", "--config", str(CONFIG)]), 0)
        self.assertFalse(json.loads(output.getvalue())["hardware_reviewed"])

    def test_installed_sensor_entry_points(self):
        console = Path(sys.executable).with_name("tdcr")
        if not console.is_file():
            self.skipTest("install the package to test its console launcher")
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        # A genuinely installed console launcher must find packaged adapters
        # even outside the checkout, without help from PYTHONPATH.
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([str(console), "sensor", "--samples", "1"],
                                    cwd=directory, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["position_mm"], [0, 0, 0])
        # Repository-local adapters intentionally use Python's module launcher:
        # unlike a console script, `python -m` makes the checkout importable.
        result = subprocess.run([sys.executable, "-m", "opentdcr", "sensor", "--sensor",
                                 "examples.sensor_adapter:create_sensor", "--samples", "1"],
                                cwd=ROOT, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["position_mm"], [0, 0, 100])

    def test_module_cli_in_subprocess(self):
        result = subprocess.run([sys.executable, "-m", "opentdcr", "teleop", "--config", str(CONFIG),
                                 "--commands", "w q"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
