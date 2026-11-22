"""A hardware-free example for researchers and automated agents.

Run from the repository root: python -m examples.programmatic_dry_run
"""
from opentdcr import load_config
from opentdcr.sensors import MockSensor
from opentdcr.teleop import TeleopSession
from opentdcr.transport import DryRunTransport


def main():
    config = load_config("configs/three_segment.example.json")
    transport = DryRunTransport(config).open()
    sensor = MockSensor()
    try:
        session = TeleopSession(config, transport, sensor)
        for command in ("1", "w", "2", "a", "home"):
            target = session.command(command)
            if target is not None:
                print(target)
    finally:
        transport.close()
        sensor.close()


if __name__ == "__main__":
    main()
