"""Lyra tests use synthetic frames/SDK calls only; no tracker or vendor module."""
import sys
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from opentdcr.adapters.lyra import (
    LyraConfig, LyraError, LyraFrame, LyraSensor, _NativeConnection,
    _ProcessBackend, create_lyra_sensor, load_lyra_config,
)


def config_data(**updates):
    data = {
        "host": "test.invalid", "port": 8765, "configuration_reviewed": True,
        "sensor_to_base": {"rotation": [[0, -1, 0], [1, 0, 0], [0, 0, 1]], "translation_mm": [10, 20, 30]},
        "tip": {"mode": "exactly_one"},
        "timeout_s": 0.2, "open_timeout_s": 5, "max_frame_age_s": 0.25, "frame_period_s": 0.02,
    }
    data.update(updates)
    return data


class FakeClock:
    def __init__(self, value=10.0):
        self.value = value

    def __call__(self):
        return self.value


class FakeBackend:
    def __init__(self, frames, *, clock=None, delay=0, error=None):
        self.frames = iter(frames)
        self.clock, self.delay, self.error = clock, delay, error
        self.opens = self.closes = self.reads = 0

    def open(self, config):
        self.opens += 1

    def read_frame(self):
        self.reads += 1
        if self.clock:
            self.clock.value += self.delay
        if self.error:
            raise self.error
        return next(self.frames)

    def close(self):
        self.closes += 1


def frame(markers=((1, 2, 3),), frame_number=1, timestamp_s=9.98, system_status=0):
    return LyraFrame(markers, frame_number, timestamp_s, system_status)


class FakeSDK:
    def __init__(self, *, failure=None, timeout=True):
        self.calls, self.failure = [], failure
        self.frame_number, self.count, self.status = 7, 1, 0
        self.marker = (1.0, 2.0, 3.0)
        if not timeout:
            self.ndiTimeoutSocket = None

    def ndiOpenNetwork(self, host, port):
        self.calls.append(("open", host, port))
        return "fake-device"

    def ndiTimeoutSocket(self, device, timeout):
        self.calls.append(("timeout", timeout))

    def ndiCommand(self, device, command):
        self.calls.append(("command", command))
        self.last_command = command
        return "OKAY"

    def ndiGetError(self, device):
        return 5 if self.last_command == self.failure else 0

    def ndiGetPHRQHandle(self, device):
        return 7

    def ndiGetTXFrame(self, device, handle):
        self.calls.append(("frame", handle))
        return self.frame_number

    def ndiGetTXNumberOfPassiveStrays(self, device):
        return self.count

    def ndiGetTXPassiveStray(self, device, index):
        return self.marker

    def ndiGetTXSystemStatus(self, device):
        return self.status

    def ndiCloseNetwork(self, device):
        self.calls.append(("close", device))


def hanging_worker(channel, config):
    """A fake child that opens normally but never completes read or close."""
    channel.send(("ok", None))
    channel.recv()
    time.sleep(30)


def opening_hangs_worker(channel, config):
    """A fake connect that never reaches its initialization acknowledgment."""
    time.sleep(30)


def disconnected_worker(channel, config):
    channel.send(("ok", None))
    channel.close()


class LyraConfigurationTests(unittest.TestCase):
    def test_example_is_deliberately_unreviewed(self):
        config = load_lyra_config(Path(__file__).parents[1] / "configs/lyra.example.json")
        backend = FakeBackend([])
        with self.assertRaisesRegex(ValueError, "configuration_reviewed"):
            LyraSensor(config, backend=backend).open()
        self.assertEqual(backend.opens, 0)

    def test_explicit_transform_required(self):
        data = config_data()
        del data["sensor_to_base"]
        with self.assertRaisesRegex(ValueError, "sensor_to_base"):
            LyraConfig.from_dict(data)

    def test_reject_nonrigid_and_reflected_transforms(self):
        for rotation in (
            [[1, 0, 0], [0, 2, 0], [0, 0, 1]],
            [[-1, 0, 0], [0, 1, 0], [0, 0, 1]],
            [[1, 0, 0], [0, float("nan"), 0], [0, 0, 1]],
            [[1, 0, 0]],
        ):
            with self.subTest(rotation=rotation), self.assertRaises(ValueError):
                LyraConfig.from_dict(config_data(sensor_to_base={"rotation": rotation, "translation_mm": [0, 0, 0]}))

    def test_reject_invalid_config_before_sdk_use(self):
        invalid = [
            {"host": ""}, {"port": True}, {"port": 0}, {"timeout_s": 0},
            {"timeout_s": float("inf")}, {"timeout_s": 61}, {"open_timeout_s": -1},
            {"frame_period_s": .25}, {"configuration_reviewed": "true"},
            {"tip": {"mode": "index", "index": 0}}, {"unknown": 3},
            {"tip": {"mode": "roi", "min_sensor_mm": [1, 0, 0], "max_sensor_mm": [0, 1, 1]}},
        ]
        for update in invalid:
            with self.subTest(update=update), self.assertRaises(ValueError):
                LyraConfig.from_dict(config_data(**update))

    def test_import_and_construction_are_inert(self):
        with patch("opentdcr.adapters.lyra.import_module", side_effect=AssertionError("SDK imported")):
            backend = FakeBackend([])
            sensor = LyraSensor(LyraConfig.from_dict(config_data()), backend=backend)
            self.assertEqual(backend.opens, 0)
            with self.assertRaisesRegex(LyraError, "not open"):
                sensor.read()
        self.assertNotIn("ndicapy", sys.modules)



class LyraMeasurementTests(unittest.TestCase):
    def make_sensor(self, frames, data=None, **kwargs):
        clock = kwargs.pop("clock", FakeClock())
        backend = FakeBackend(frames, clock=clock, **kwargs)
        sensor = LyraSensor(LyraConfig.from_dict(data or config_data()), backend=backend, clock=clock).open()
        self.addCleanup(sensor.close)
        return sensor, backend, clock

    def test_transforms_mm_and_preserves_acquisition_time(self):
        sensor, backend, _ = self.make_sensor([frame()])
        result = sensor.read()
        self.assertEqual(result.position_mm, (8.0, 21.0, 33.0))
        self.assertEqual(result.frame, "robot_base")
        self.assertEqual(result.timestamp_s, 9.98)
        self.assertTrue(result.valid)
        sensor.close()
        sensor.close()
        self.assertEqual(backend.closes, 1)

    def test_factory_opens_only_explicitly_requested_fake_backend(self):
        backend = FakeBackend([frame()])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "local.lyra.json"
            path.write_text(json.dumps(config_data()), encoding="utf-8")
            with patch("opentdcr.adapters.lyra.import_module", side_effect=AssertionError("SDK imported")):
                with create_lyra_sensor(path, backend=backend, clock=FakeClock()) as sensor:
                    self.assertEqual(sensor.read().position_mm, (8.0, 21.0, 33.0))
            self.assertEqual(backend.opens, 1)
            self.assertEqual(backend.closes, 1)

    def test_roi_ignores_order_and_requires_one_candidate(self):
        tip = {"mode": "roi", "min_sensor_mm": [0, 0, 0], "max_sensor_mm": [5, 5, 5]}
        sensor, _, clock = self.make_sensor([
            frame(((100, 100, 100), (1, 2, 3))),
            frame(((1, 2, 3), (-50, -50, -50)), frame_number=2, timestamp_s=10.01),
        ], config_data(tip=tip))
        self.assertEqual(sensor.read().position_mm, (8, 21, 33))
        clock.value = 10.02
        self.assertEqual(sensor.read().position_mm, (8, 21, 33))

    def test_missing_or_ambiguous_tip_fails_and_closes(self):
        cases = [(), ((1, 2, 3), (4, 5, 6))]
        for markers in cases:
            with self.subTest(markers=markers):
                sensor, backend, _ = self.make_sensor([frame(markers)])
                with self.assertRaisesRegex(LyraError, "exactly one"):
                    sensor.read()
                self.assertEqual(backend.closes, 1)
                with self.assertRaisesRegex(LyraError, "not open"):
                    sensor.read()

    def test_missing_or_ambiguous_roi_fails(self):
        tip = {"mode": "roi", "min_sensor_mm": [0, 0, 0], "max_sensor_mm": [5, 5, 5]}
        for markers in (((100, 100, 100),), ((1, 1, 1), (2, 2, 2))):
            with self.subTest(markers=markers):
                sensor, _, _ = self.make_sensor([frame(markers)], config_data(tip=tip))
                with self.assertRaisesRegex(LyraError, "exactly one"):
                    sensor.read()

    def test_invalid_frame_data_fails_closed(self):
        cases = [frame(timestamp_s=9), frame(timestamp_s=10.1), frame(timestamp_s=float("nan")),
                 frame(frame_number=0), frame(frame_number=True), frame(frame_number=-1),
                 frame(system_status=16), frame(((1, float("nan"), 3),)), frame(("MISSING",)),
                 frame(((1, 2),)), object()]
        for invalid in cases:
            with self.subTest(invalid=invalid):
                sensor, backend, _ = self.make_sensor([invalid])
                with self.assertRaises((LyraError, ValueError)):
                    sensor.read()
                self.assertEqual(backend.closes, 1)

    def test_backwards_and_stale_timestamps_fail(self):
        for second in [frame(frame_number=0xffffffff, timestamp_s=9.99), frame(frame_number=2, timestamp_s=9.98)]:
            with self.subTest(second=second):
                sensor, backend, _ = self.make_sensor([frame(), second])
                sensor.read()
                with self.assertRaises(LyraError):
                    sensor.read()
                self.assertEqual(backend.closes, 1)

    def test_fresh_duplicate_returns_original_sample_and_timestamp(self):
        sensor, _, clock = self.make_sensor([frame(), frame(timestamp_s=10.08)])
        first = sensor.read()
        clock.value = 10.1
        repeated = sensor.read()
        self.assertIs(repeated, first)
        self.assertEqual(repeated.timestamp_s, 9.98)

    def test_duplicate_with_changed_marker_payload_fails(self):
        sensor, backend, _ = self.make_sensor([frame(), frame(((2, 3, 4),), timestamp_s=9.99)])
        sensor.read()
        with self.assertRaisesRegex(LyraError, "changed marker"):
            sensor.read()
        self.assertEqual(backend.closes, 1)

    def test_duplicate_cannot_refresh_stale_acquisition_timestamp(self):
        sensor, backend, clock = self.make_sensor([frame(), frame(timestamp_s=10.29)])
        sensor.read()
        clock.value = 10.3
        with self.assertRaisesRegex(ValueError, "freshness"):
            sensor.read()
        self.assertEqual(backend.closes, 1)

    def test_counter_wrap_is_supported_without_accepting_missing_zero(self):
        sensor, _, clock = self.make_sensor([frame(frame_number=0xffffffff), frame(frame_number=1, timestamp_s=10.01)])
        sensor.read()
        clock.value = 10.02
        self.assertEqual(sensor.read().timestamp_s, 10.01)

    def test_slow_read_and_backend_disconnect_close_source(self):
        sensor, backend, _ = self.make_sensor([frame()], delay=.3)
        with self.assertRaisesRegex(LyraError, "timeout"):
            sensor.read()
        self.assertEqual(backend.closes, 1)
        sensor, backend, _ = self.make_sensor([], error=OSError("disconnected"))
        with self.assertRaisesRegex(OSError, "disconnected"):
            sensor.read()
        self.assertEqual(backend.closes, 1)

    def test_failed_open_releases_partial_backend(self):
        backend = FakeBackend([])
        backend.open = lambda config: (_ for _ in ()).throw(OSError("open failed"))
        sensor = LyraSensor(LyraConfig.from_dict(config_data()), backend=backend)
        with self.assertRaisesRegex(OSError, "open failed"):
            sensor.open()
        self.assertEqual(backend.closes, 1)
        sensor.close()
        self.assertEqual(backend.closes, 1)


class LyraNativeTests(unittest.TestCase):
    def test_native_tx_getters_allocated_handle_and_timeout(self):
        sdk = FakeSDK()
        native = _NativeConnection(LyraConfig.from_dict(config_data()), sdk=sdk, clock=FakeClock())
        self.assertEqual(sdk.calls, [])
        native.open()
        result = native.read_frame()
        native.close()
        native.close()
        self.assertEqual(result.markers_mm, ((1.0, 2.0, 3.0),))
        self.assertEqual(result.frame_number, 7)
        self.assertEqual(result.timestamp_s, 9.98)
        self.assertIn(("open", "test.invalid", 8765), sdk.calls)
        self.assertIn(("timeout", 200), sdk.calls)
        self.assertIn(("command", "PENA:07D"), sdk.calls)
        self.assertIn(("command", "TX:1001"), sdk.calls)
        self.assertIn(("frame", b"\x07"), sdk.calls)
        self.assertEqual(sdk.calls.count(("close", "fake-device")), 1)

    def test_sdk_without_timeout_setter_is_accepted_inside_worker(self):
        sdk = FakeSDK(timeout=False)
        native = _NativeConnection(LyraConfig.from_dict(config_data()), sdk=sdk)
        native.open()
        native.close()
        self.assertFalse(any(call[0] == "timeout" for call in sdk.calls))

    def test_native_command_error_closes_partially_open_connection(self):
        sdk = FakeSDK(failure="PENA:07D")
        native = _NativeConnection(LyraConfig.from_dict(config_data()), sdk=sdk)
        with self.assertRaisesRegex(LyraError, "PENA"):
            native.open()
        self.assertEqual(sdk.calls.count(("close", "fake-device")), 1)

    def test_native_missing_sdk_is_actionable(self):
        native = _NativeConnection(LyraConfig.from_dict(config_data()))
        with patch("opentdcr.adapters.lyra.import_module", side_effect=ImportError("missing")):
            with self.assertRaisesRegex(LyraError, "optional ndicapi"):
                native.open()

    def test_native_missing_marker_is_not_parsed_or_silently_selected(self):
        sdk = FakeSDK()
        sdk.marker = "MISSING"
        native = _NativeConnection(LyraConfig.from_dict(config_data()), sdk=sdk, clock=FakeClock())
        native.open()
        self.addCleanup(native.close)
        result = native.read_frame()
        sensor = LyraSensor(LyraConfig.from_dict(config_data()), backend=FakeBackend([result]), clock=FakeClock()).open()
        with self.assertRaises(ValueError):
            sensor.read()

    def test_worker_read_timeout_is_bounded_and_terminal(self):
        backend = _ProcessBackend(worker_target=hanging_worker)
        backend.open(LyraConfig.from_dict(config_data(timeout_s=.04)))
        self.addCleanup(backend.close)
        started = time.monotonic()
        with self.assertRaisesRegex(LyraError, "timed out"):
            backend.read_frame()
        self.assertLess(time.monotonic() - started, 1)
        self.assertIsNone(backend._process)
        with self.assertRaisesRegex(LyraError, "closed"):
            backend.read_frame()
        backend.close()

    def test_worker_open_timeout_releases_process(self):
        backend = _ProcessBackend(worker_target=opening_hangs_worker)
        started = time.monotonic()
        with self.assertRaisesRegex(LyraError, "timed out"):
            backend.open(LyraConfig.from_dict(config_data(open_timeout_s=.04)))
        self.assertLess(time.monotonic() - started, 1)
        self.assertIsNone(backend._process)
        backend.close()

    def test_worker_close_timeout_is_bounded_and_idempotent(self):
        backend = _ProcessBackend(worker_target=hanging_worker)
        backend.open(LyraConfig.from_dict(config_data(timeout_s=.04)))
        started = time.monotonic()
        backend.close()
        backend.close()
        self.assertLess(time.monotonic() - started, 1)
        self.assertIsNone(backend._process)

    def test_worker_disconnect_does_not_return_cached_frame(self):
        backend = _ProcessBackend(worker_target=disconnected_worker)
        backend.open(LyraConfig.from_dict(config_data()))
        self.addCleanup(backend.close)
        with self.assertRaises(LyraError):
            backend.read_frame()


if __name__ == "__main__":
    unittest.main()
