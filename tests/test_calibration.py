"""Calibration orchestration with synthetic observations and in-memory motors."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from opentdcr.calibration import CalibrationConfig, calibrate, load_calibration_config
from opentdcr.config import RobotConfig
from opentdcr.sensors import PositionMeasurement


def robot(tendons=(3,), travel=8.0):
    n = sum(tendons)
    segments = len(tendons)
    return RobotConfig(
        name="synthetic calibration fixture", tendons_per_segment=tendons,
        tendon_radius_mm=(3.0,) * segments,
        tendon_angle_offset_rad=(0.0,) * segments,
        max_bend_rad=(0.5,) * segments,
        servo_ids=tuple(range(1, n+1)), spool_radius_mm=(10.0,) * n,
        servo_direction=(1,) * n, max_tendon_travel_mm=travel,
    )


def settings(configuration, **changes):
    data = {
        "loosen_amount_mm": 1.0,
        "movement_threshold_mm": 0.3,
        "movement_countback_mm": 0.1,
        "pull_step_mm": 0.2,
        "max_pull_mm": 0.6,
        "search_start_mm": -0.5,
        "settle_s": 0.0,
        "tendon_timeout_s": 5.0,
    }
    return CalibrationConfig.from_dict({**data, **changes}, configuration)


class FakeClock:
    def __init__(self): self.now = 100.0
    def __call__(self): return self.now
    def sleep(self, seconds): self.now += seconds


class FakeTransport:
    def __init__(self, configuration, clock):
        self.config = configuration
        self.clock = clock
        self.current = np.zeros(configuration.n_tendons)
        self.commands = []
        self.events = []
        self.closed = False
        self.captured = 0
        self.move_duration = 0.0
        self.fail_on_move = None
        self.readback_lag = 0.0
        self.capture_failure = None

    def move(self, target, check=None):
        if check:
            check()
        target = np.asarray(target, dtype=float)
        self.commands.append(target.copy())
        self.events.append("move")
        if self.fail_on_move == len(self.commands):
            raise OSError("synthetic motor communication failure")
        self.current = target.copy()
        # Simulate imperfect tracking only while a single tendon is pulled.
        active = np.flatnonzero(target > 0)
        if len(active) == 1:
            self.current[active[0]] -= self.readback_lag
        self.clock.sleep(self.move_duration)
        if check:
            check()

    def read_positions_mm(self):
        self.events.append("read")
        return self.current.copy()

    def capture_reference(self):
        if self.capture_failure is not None:
            raise self.capture_failure
        self.events.append("capture")
        self.captured += 1
        reference = {"offsets_mm": self.current.tolist(), "zero_ticks": None}
        self.current[:] = 0
        return reference

    def close(self):
        self.events.append("close")
        self.closed = True


class FakeSensor:
    def __init__(self, transport, clock, gain=1.0):
        self.transport, self.clock, self.gain = transport, clock, gain
        self.origin = np.array([10.0, 20.0, 30.0])
        self.corrupt = None

    def read(self):
        position = self.origin.copy()
        position[0] += max(0.0, float(np.max(self.transport.current))) * self.gain
        sample = PositionMeasurement(tuple(position.tolist()), self.clock())
        if self.corrupt is not None:
            sample = self.corrupt(sample)
        return sample

    def close(self):
        pass


class CalibrationConfigTests(unittest.TestCase):
    def test_scalar_broadcast_arrays_and_file_loader(self):
        cfg = robot((3, 4))
        config = settings(cfg, movement_countback_mm=[0, .1, .2, .3, .4, .5, .6])
        self.assertEqual(config.loosen_amount_mm, (1.0,) * 7)
        self.assertEqual(config.movement_countback_mm[-1], 0.6)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibration.json"
            path.write_text(json.dumps(config.to_dict()))
            self.assertEqual(load_calibration_config(path, cfg), config)

    def test_example_configuration_matches_robot_example(self):
        from opentdcr.config import load_config
        root = Path(__file__).resolve().parents[1]
        cfg = load_config(root / "configs/three_segment.example.json")
        config = load_calibration_config(root / "configs/calibration.example.json", cfg)
        self.assertEqual(len(config.loosen_amount_mm), cfg.n_tendons)

    def test_invalid_configuration_rejected(self):
        for changes in (
            {"loosen_amount_mm": [1, 1]}, {"movement_threshold_mm": 0},
            {"movement_countback_mm": -0.1}, {"pull_step_mm": 0},
            {"pull_step_mm": 2}, {"max_pull_mm": float("nan")},
            {"max_pull_mm": 9}, {"loosen_amount_mm": 9},
            {"search_start_mm": -2}, {"search_start_mm": 1},
            {"settle_s": -1}, {"tendon_timeout_s": 0},
            {"movement_threshold_mm": True}, {"settle_s": "1"},
            {"movement_countback_mm": float("inf")}, {"unknown": 1},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                settings(robot(), **changes)

    def test_required_vectors_cannot_be_omitted(self):
        data = settings(robot()).to_dict()
        del data["movement_threshold_mm"]
        with self.assertRaises(ValueError):
            CalibrationConfig.from_dict(data, robot())

    def test_direct_configuration_copies_vectors(self):
        values = [1.0] * 3
        config = CalibrationConfig(values, [.3]*3, [.1]*3)
        values[0] = 100
        self.assertEqual(config.loosen_amount_mm[0], 1)


class CalibrationFixture:
    def fixture(self, configuration=None, **changes):
        configuration = robot() if configuration is None else configuration
        clock = FakeClock()
        transport = FakeTransport(configuration, clock)
        sensor = FakeSensor(transport, clock)
        config = settings(configuration, **changes)
        return transport, sensor, config, clock

    def run_calibration(self, transport, sensor, config, clock, **callbacks):
        return calibrate(transport, sensor, config, clock=clock, sleep=clock.sleep, **callbacks)


class CalibrationSequenceTests(CalibrationFixture, unittest.TestCase):
    def test_exact_sequence_and_baseline_after_operator_perturbation(self):
        transport, sensor, config, clock = self.fixture()
        events = []
        def perturb():
            self.assertEqual(len(transport.commands), 1)
            np.testing.assert_array_equal(transport.current, [-1, -1, -1])
            sensor.origin += [1, 2, 3]
        result = self.run_calibration(transport, sensor, config, clock,
                                      on_loosened=perturb, on_progress=events.append)
        expected = [np.full(3, -1.0)]
        for index in range(3):
            for pull in (-.5, .2, .4):
                target = np.full(3, -1.0); target[index] = pull
                expected.append(target)
            expected.append(np.full(3, -1.0))
        expected.append(np.full(3, .3))
        np.testing.assert_allclose(transport.commands, expected, atol=1e-12)
        self.assertEqual(result.baseline_position_mm, (11, 22, 33))
        self.assertEqual(events[0]["stage"], "loosened")
        self.assertEqual(events[1]["stage"], "baseline")
        self.assertEqual(events[-1]["stage"], "capture_reference")
        self.assertEqual(transport.events[-1], "capture")
        self.assertEqual(transport.captured, 1)
        self.assertFalse(transport.closed)
        np.testing.assert_array_equal(transport.current, np.zeros(3))

    def test_arbitrary_segment_and_tendon_counts(self):
        for counts in ((4,), (3, 4)):
            with self.subTest(counts=counts):
                transport, sensor, config, clock = self.fixture(robot(counts))
                result = self.run_calibration(transport, sensor, config, clock)
                self.assertEqual(len(result.threshold_positions_mm), sum(counts))
                self.assertEqual(result.servo_ids, transport.config.servo_ids)

    def test_countback_uses_measured_motor_position(self):
        transport, sensor, config, clock = self.fixture()
        transport.readback_lag = .03
        result = self.run_calibration(transport, sensor, config, clock)
        np.testing.assert_allclose(result.threshold_positions_mm, [.37]*3)
        np.testing.assert_allclose(result.calibrated_positions_mm, [.27]*3)
        np.testing.assert_allclose(result.threshold_displacements_mm, [.37]*3)

    def test_adjustments_use_current_readback_and_capture_final_reference(self):
        transport, sensor, config, clock = self.fixture()
        adjustments = iter([.1, -.02, None])
        seen = []
        def adjust(current):
            seen.append(current)
            return next(adjustments)
        result = self.run_calibration(transport, sensor, config, clock, adjustment=adjust)
        np.testing.assert_allclose(seen, [[.3]*3, [.4]*3, [.38]*3])
        np.testing.assert_allclose(result.final_positions_mm, [.38]*3)
        np.testing.assert_allclose(result.reference["offsets_mm"], [.38]*3)
        self.assertEqual(result.manual_adjustments_mm, (.1, -.02))
        decoded = json.loads(json.dumps(result.to_dict(), allow_nan=False))
        self.assertEqual(decoded["status"], "complete")
        self.assertIsNone(decoded["reference"]["zero_ticks"])

    def test_settling_checks_sensor_and_uses_injected_clock(self):
        transport, sensor, config, clock = self.fixture(settle_s=.1)
        result = self.run_calibration(transport, sensor, config, clock)
        self.assertGreaterEqual(result.elapsed_s, 1.3)

    def test_baseline_waits_for_acquisition_after_operator_callback(self):
        transport, sensor, config, clock = self.fixture()
        cached = None
        next_acquisition = None
        def perturb():
            nonlocal cached, next_acquisition
            cached = sensor.read()
            sensor.origin += [1, 2, 3]
            clock.sleep(.02)
            next_acquisition = clock() + .03
        def delayed_camera(sample):
            if cached is not None and clock() < next_acquisition:
                return cached
            return sample
        sensor.corrupt = delayed_camera
        result = self.run_calibration(transport, sensor, config, clock, on_loosened=perturb)
        self.assertEqual(result.baseline_position_mm, (11, 22, 33))
        self.assertGreaterEqual(result.elapsed_s, .05)

    def test_threshold_waits_for_post_motion_camera_sample(self):
        transport, sensor, config, clock = self.fixture()
        transport.move_duration = .02
        last_command_count = 0
        cached = None
        next_acquisition = None
        def delayed_camera(sample):
            nonlocal last_command_count, cached, next_acquisition
            if transport.current.max() > 0:
                if len(transport.commands) != last_command_count:
                    last_command_count = len(transport.commands)
                    # An older high-displacement observation must not terminate
                    # this newly completed pull before its own sample arrives.
                    cached = replace(sample, position_mm=(20, 20, 30),
                                     timestamp_s=clock()-.005)
                    next_acquisition = clock()+.03
                if clock() < next_acquisition:
                    return cached
            return sample
        sensor.corrupt = delayed_camera
        result = self.run_calibration(transport, sensor, config, clock)
        np.testing.assert_allclose(result.threshold_positions_mm, [.4]*3)
        np.testing.assert_allclose(result.threshold_displacements_mm, [.4]*3)


class CalibrationFailureTests(CalibrationFixture, unittest.TestCase):
    # These tests exercise failures through the same fake transport contract.
    def assert_failed_without_reference(self, transport):
        self.assertTrue(transport.closed)
        self.assertEqual(transport.captured, 0)

    def test_no_threshold_fails_instead_of_applying_partial_result(self):
        transport, sensor, config, clock = self.fixture()
        sensor.gain = 0
        with self.assertRaisesRegex(RuntimeError, "did not reach"):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)
        self.assertLessEqual(max(target.max() for target in transport.commands), config.max_pull_mm)
        self.assertEqual(transport.commands[-1][0], config.max_pull_mm)

    def test_partial_search_success_is_not_applied_or_rebased(self):
        transport, sensor, config, clock = self.fixture(movement_threshold_mm=[.3, 10, .3])
        with self.assertRaisesRegex(RuntimeError, "tendon 2"):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)
        # A partially collected zero vector must never be sent as final tensions.
        self.assertTrue(all(np.count_nonzero(target > 0) <= 1 for target in transport.commands))

    def test_timeout_checked_inside_motor_move_callback(self):
        transport, sensor, config, clock = self.fixture(tendon_timeout_s=.1)
        transport.move_duration = .2
        with self.assertRaises(TimeoutError):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)

    def test_invalid_or_stale_sensor_stops_before_motor_commands(self):
        corruptions = (
            lambda sample: None,
            lambda sample: replace(sample, valid=False),
            lambda sample: replace(sample, frame="camera"),
            lambda sample: replace(sample, timestamp_s=sample.timestamp_s-1),
            lambda sample: replace(sample, position_mm=(float("nan"), 0, 0)),
        )
        for corrupt in corruptions:
            with self.subTest(corrupt=corrupt):
                transport, sensor, config, clock = self.fixture()
                sensor.corrupt = corrupt
                with self.assertRaises(ValueError):
                    self.run_calibration(transport, sensor, config, clock)
                self.assert_failed_without_reference(transport)
                self.assertEqual(transport.commands, [])

    def test_tracking_loss_mid_search_stops_without_capture(self):
        transport, sensor, config, clock = self.fixture()
        sensor.corrupt = lambda sample: replace(sample, valid=False) if transport.current.max() > 0 else sample
        with self.assertRaises(ValueError):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)
        self.assertEqual(len(transport.commands), 3)

    def test_pre_motion_cached_point_cannot_cause_false_threshold(self):
        transport, sensor, config, clock = self.fixture()
        transport.move_duration = .02
        cached = None
        events = []
        def frozen_camera(sample):
            nonlocal cached
            if cached is None and transport.current.max() > 0:
                cached = replace(sample, position_mm=(20, 20, 30),
                                 timestamp_s=clock()-.005)
            return cached if cached is not None else sample
        sensor.corrupt = frozen_camera
        with self.assertRaises((ValueError, TimeoutError)):
            self.run_calibration(transport, sensor, config, clock, on_progress=events.append)
        self.assert_failed_without_reference(transport)
        self.assertFalse(any(event["stage"] == "threshold" for event in events))
        self.assertEqual(len(transport.commands), 3)
        # Decision polling sleeps and stops within the freshness window.
        self.assertGreater(clock(), 100.06)
        self.assertLessEqual(clock(), 100.06 + transport.config.sensor_max_age_s + 1e-9)

    def test_decision_sample_wait_respects_tendon_deadline(self):
        transport, sensor, config, clock = self.fixture(tendon_timeout_s=.1)
        transport.move_duration = .02
        cached = None
        def frozen_camera(sample):
            nonlocal cached
            if cached is None and transport.current.max() > 0:
                cached = replace(sample, timestamp_s=clock()-.005)
            return cached if cached is not None else sample
        sensor.corrupt = frozen_camera
        with self.assertRaisesRegex(TimeoutError, "tendon search timed out"):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)
        self.assertLessEqual(clock(), 100.13)

    def test_late_returning_fresh_sample_does_not_override_decision_timeout(self):
        transport, sensor, config, clock = self.fixture()
        def slow_camera(sample):
            clock.sleep(.3)
            return replace(sample, timestamp_s=clock())
        sensor.corrupt = slow_camera
        with self.assertRaisesRegex(TimeoutError, "decision-sample wait timed out"):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)
        self.assertEqual(len(transport.commands), 1)

    def test_motor_error_and_keyboard_interrupt_close_transport(self):
        transport, sensor, config, clock = self.fixture()
        transport.fail_on_move = 4
        with self.assertRaises(OSError):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)
        transport, sensor, config, clock = self.fixture()
        def interrupted():
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.run_calibration(transport, sensor, config, clock, on_loosened=interrupted)
        self.assert_failed_without_reference(transport)

    def test_out_of_range_countback_and_adjustments_are_not_sent(self):
        for change, callback in (
            ({"movement_countback_mm": 2.0}, None),
            ({}, lambda current: 2.0),
            ({}, lambda current: float("nan")),
        ):
            with self.subTest(change=change, callback=callback):
                transport, sensor, config, clock = self.fixture(robot(travel=1), **change)
                with self.assertRaises(ValueError):
                    self.run_calibration(transport, sensor, config, clock, adjustment=callback)
                self.assert_failed_without_reference(transport)
                self.assertTrue(all(np.abs(target).max() <= 1 for target in transport.commands))

    def test_configuration_for_wrong_motor_count_closes_before_motion(self):
        transport, sensor, _, clock = self.fixture()
        config = settings(robot((4,)))
        with self.assertRaises(ValueError):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)
        self.assertEqual(transport.commands, [])

    def test_capture_and_progress_errors_close_transport(self):
        transport, sensor, config, clock = self.fixture()
        transport.capture_failure = OSError("cannot read reference encoders")
        with self.assertRaises(OSError):
            self.run_calibration(transport, sensor, config, clock)
        self.assert_failed_without_reference(transport)
        transport, sensor, config, clock = self.fixture()
        def broken_progress(event):
            if event["stage"] == "capture_reference":
                raise RuntimeError("progress callback failed")
        with self.assertRaises(RuntimeError):
            self.run_calibration(transport, sensor, config, clock, on_progress=broken_progress)
        self.assert_failed_without_reference(transport)


if __name__ == "__main__":
    unittest.main()
