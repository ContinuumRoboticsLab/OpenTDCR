"""Optional wired DualSense input with fresh-report and deadman checks.

USB report fields are documented by the Linux hid-playstation driver:
https://github.com/torvalds/linux/blob/master/drivers/hid/hid-playstation.c
Only the standard Sony DualSense (054c:0ce6), 64-byte USB report 0x01 is accepted.
No Bluetooth, Edge, rumble, or LED output is implemented.
"""
from dataclasses import dataclass
import importlib
import math
import threading
import time


@dataclass(frozen=True)
class GamepadState:
    x: float
    y: float
    deadman: bool
    exit: bool
    next_segment: bool
    previous_segment: bool
    timestamp_s: float


def parse_usb_report(report, timestamp_s):
    if len(report) != 64 or report[0] != 1:
        raise ValueError("expected a 64-byte wired DualSense USB report")
    if any(type(v) is not int or not 0 <= v <= 255 for v in report):
        raise ValueError("malformed controller report")
    x, y = (report[1]-128)/128, (128-report[2])/128
    magnitude = math.hypot(x, y)
    if magnitude < 0.15:
        x = y = 0.0
    elif magnitude > 1:
        x, y = x/magnitude, y/magnitude
    dpad = report[8] & 15
    return GamepadState(x, y, bool(report[9] & 1), bool(report[8] & 64),
                        dpad == 0, dpad == 4, timestamp_s)


def validate_gamepad(state, now_s=None, *, require_deadman=False):
    now = time.monotonic() if now_s is None else now_s
    if state is None or not math.isfinite(state.timestamp_s) or not 0 <= now-state.timestamp_s <= 0.25:
        raise RuntimeError("controller report stale or disconnected; session stopped")
    if state.exit:
        raise RuntimeError("controller exit pressed; session stopped")
    if require_deadman and not state.deadman:
        raise RuntimeError("L1 released during movement; session stopped")
    return state


class DualSenseUSB:
    def __init__(self):
        self.device = None
        self.thread = None
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.state = None
        self.error = None

    def open(self):
        try:
            hid = importlib.import_module("hid")
        except ImportError as exc:
            raise RuntimeError('Install gamepad support: pip install -e ".[gamepad]"') from exc
        devices = [d for d in hid.enumerate(0x054c, 0x0ce6)
                   if d.get("usage_page", 1) == 1 and d.get("usage", 5) in (4, 5)]
        if len(devices) != 1:
            raise RuntimeError("connect exactly one standard DualSense over USB")
        self.device = hid.device()
        try:
            self.device.open_path(devices[0]["path"])
            self.thread = threading.Thread(target=self._receive, name="opentdcr-gamepad", daemon=True)
            self.thread.start()
            deadline = time.monotonic()+0.3
            while time.monotonic() < deadline:
                with self.lock:
                    ready = self.state is not None or self.error is not None
                if ready:
                    state = self.read()
                    if state.deadman:
                        raise RuntimeError("release L1 before starting the session")
                    return self
                time.sleep(0.01)
            raise RuntimeError("no wired DualSense reports received")
        except BaseException:
            self.close()
            raise

    def _receive(self):
        previous_sequence = None
        try:
            while not self.stop.is_set():
                report = self.device.read(64, timeout_ms=100)
                if not report:
                    continue
                state = parse_usb_report(report, time.monotonic())
                # An unchanged device sequence must not refresh cached input.
                if report[7] != previous_sequence:
                    with self.lock:
                        self.state = state
                    previous_sequence = report[7]
        except Exception as exc:
            with self.lock:
                self.error = str(exc)

    def read(self, *, require_deadman=False):
        with self.lock:
            state, error = self.state, self.error
        if error is not None:
            raise RuntimeError(f"controller read failed: {error}")
        return validate_gamepad(state, require_deadman=require_deadman)

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=0.3)
        if self.device is not None:
            self.device.close()
            self.device = None
