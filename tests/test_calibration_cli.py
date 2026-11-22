"""Calibration CLI integration using synthetic measurements and motor transports."""
import contextlib
from dataclasses import asdict, replace
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import numpy as np

from opentdcr.cli import main
from opentdcr.config import load_config
from opentdcr.sensors import MockSensor, PositionMeasurement
from opentdcr.transport import DryRunTransport

ROOT = Path(__file__).resolve().parents[1]
ROBOT = ROOT / 'configs/three_segment.example.json'


class CalibrationCLITests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.calibration = self.root / 'calibration.json'
        self.calibration.write_text(json.dumps({
            'loosen_amount_mm': 0.2, 'movement_threshold_mm': 0.1,
            'movement_countback_mm': 0.02, 'pull_step_mm': 0.2,
            'max_pull_mm': 1, 'search_start_mm': -0.1,
            'settle_s': 0, 'tendon_timeout_s': 1,
        }))
        self.args = ['calibrate', '--config', str(ROBOT),
                     '--calibration-config', str(self.calibration)]

    def run_cli(self, args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main(args)

    def test_synthetic_calibration_report_and_teleop_share_reference(self):
        report = self.root / 'run.local.json'
        drivers = []
        class ObservedDryRun(DryRunTransport):
            def __init__(self, config):
                super().__init__(config)
                self.open_count = 0
                self.after_reference = []
                self.captured = False
                drivers.append(self)
            def open(self):
                self.open_count += 1
                return super().open()
            def capture_reference(self):
                result = super().capture_reference()
                self.captured = True
                return result
            def move(self, target, check=None):
                if self.captured:
                    self.after_reference.append(np.asarray(target).copy())
                return super().move(target, check=check)
        with patch('opentdcr.cli.DryRunTransport', ObservedDryRun), \
             patch('opentdcr.transport.importlib.import_module', side_effect=AssertionError('SDK loaded')):
            result = self.run_cli(self.args + ['--output', str(report), '--teleop', '--commands', 'w home q'])
        self.assertEqual(result, 0)
        saved = json.loads(report.read_text())
        self.assertTrue(saved['dry_run'])
        self.assertEqual(saved['result']['status'], 'complete')
        self.assertEqual(len(saved['result']['threshold_positions_mm']), 9)
        np.testing.assert_allclose(saved['result']['reference']['offsets_mm'], [0.18]*9)
        self.assertIsNone(saved['result']['reference']['zero_ticks'])
        self.assertEqual(drivers[0].open_count, 1)
        self.assertTrue(drivers[0].captured)
        self.assertFalse(drivers[0].is_open)
        self.assertGreater(np.linalg.norm(drivers[0].after_reference[0]), 0)
        np.testing.assert_array_equal(drivers[0].after_reference[-1], np.zeros(9))

    def test_existing_report_is_not_overwritten_or_devices_opened(self):
        report = self.root / 'run.local.json'
        report.write_text('keep existing calibration')
        with patch('opentdcr.cli._make_sensor', side_effect=AssertionError('device opened')):
            self.assertEqual(self.run_cli(self.args + ['--output', str(report)]), 2)
        self.assertEqual(report.read_text(), 'keep existing calibration')

    def test_invalid_parameters_are_rejected_before_loading_sensor(self):
        data = json.loads(self.calibration.read_text())
        data['movement_threshold_mm'] = -1
        self.calibration.write_text(json.dumps(data))
        with patch('opentdcr.cli._make_sensor', side_effect=AssertionError('device opened')):
            self.assertEqual(self.run_cli(self.args), 2)

    def test_physical_calibration_requires_real_sensor_before_motor_start(self):
        reviewed = self.root / 'robot.local.json'
        reviewed.write_text(json.dumps(asdict(replace(load_config(ROBOT), hardware_reviewed=True))))
        args = self.args.copy()
        args[2] = str(reviewed)
        args += ['--hardware', '--port', 'fake', '--confirm-home']
        with patch('sys.stdin.isatty', return_value=True), \
             patch('opentdcr.cli.DynamixelTransport.open', side_effect=AssertionError('motors opened')):
            self.assertEqual(self.run_cli(args), 2)
            self.assertEqual(self.run_cli(args + ['--sensor', 'opentdcr.sensors:MockSensor']), 2)

    def test_bad_or_lost_measurement_emits_no_success_report_and_closes(self):
        class LostSensor:
            closed = False
            def read(self):
                return PositionMeasurement((0, 0, 0), 0, valid=False)
            def close(self):
                self.closed = True
        sensor = LostSensor()
        report = self.root / 'failed.local.json'
        with patch('opentdcr.cli._make_sensor', return_value=sensor):
            self.assertEqual(self.run_cli(self.args + ['--output', str(report)]), 2)
        self.assertFalse(report.exists())
        self.assertTrue(sensor.closed)

    def test_sensor_config_requires_explicit_lyra_selection(self):
        with patch('opentdcr.transport.importlib.import_module', side_effect=AssertionError('SDK loaded')):
            self.assertEqual(self.run_cli(self.args + ['--sensor-config', 'missing.json']), 2)
            self.assertEqual(self.run_cli(['sensor', '--sensor', 'lyra']), 2)

    def test_external_sensor_label_and_lyra_configuration_provenance(self):
        from opentdcr.adapters.lyra import LyraConfig
        reviewed = LyraConfig(
            host='test-tracker.invalid', port=8765, configuration_reviewed=True,
            rotation=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
            translation_mm=(1, 2, 3), tip_mode='exactly_one')
        drivers = []
        def create_transport(config):
            transport = DryRunTransport(config)
            drivers.append(transport)
            return transport
        class ExternalTestSensor:
            config = reviewed
            closed = False
            def read(self):
                displacement = max(0.0, float(max(drivers[0].position_mm)))
                return PositionMeasurement((displacement, 0, 0), time.monotonic())
            def close(self):
                self.closed = True
        sensor = ExternalTestSensor()
        report = self.root / 'lyra.local.json'
        with patch('opentdcr.cli.DryRunTransport', side_effect=create_transport), \
             patch('opentdcr.cli._make_sensor', return_value=sensor), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            result = main(self.args + ['--sensor', 'lyra', '--sensor-config', 'local-test.json',
                                      '--output', str(report)])
        self.assertEqual(result, 0)
        self.assertIn('external sensor measurements', output.getvalue())
        self.assertNotIn('synthetic calibration', output.getvalue())
        saved = json.loads(report.read_text())
        self.assertEqual(saved['sensor_configuration']['translation_mm'], [1, 2, 3])
        self.assertEqual(saved['sensor_configuration']['frame_period_s'], reviewed.frame_period_s)
        self.assertTrue(sensor.closed)


if __name__ == '__main__':
    unittest.main()
