"""Exercise the real release command without touching local research data."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile


PACKAGER = Path(__file__).resolve().parents[1] / "tools/package_release.py"


class ReleasePackagingTests(unittest.TestCase):
    def test_archive_keeps_source_and_excludes_local_calibration_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "candidate"
            (root / "tools").mkdir(parents=True)
            shutil.copy2(PACKAGER, root / "tools/package_release.py")
            intended = {
                "README.md": "Public release instructions",
                "src/opentdcr/__init__.py": "# public package",
                "configs/three_segment.example.json": '{"hardware_reviewed": false}',
                "hardware/bom.csv": "part,quantity\nspool,9\n",
                "website/dist/index.html": "<title>OpenTDCR</title>",
                "website/dist/assets/model.glb": "public viewer geometry",
            }
            private_or_generated = (
                "configs/robot.local.json",
                "configs/calibration/offsets.local.json",
                "measurements/tracker.csv",
                "measurements/session/positions.json",
                "docs/measurements/recording.csv",
                "run.log",
                "diagnostics/servo.log",
                "local.machine.json",
                "local.calibration/transforms.json",
                "configs/local.sensor/offsets.json",
                ".env",
                ".env.production",
                ".env.private/credentials.json",
                ".git/config",
                ".venv/settings.json",
                "src/opentdcr/__pycache__/config.pyc",
                "src/opentdcr/config.pyd",
                "src/opentdcr.egg-info/PKG-INFO",
                "node_modules/package/index.js",
                "dist/bundle.js",
                "tools/dist/output.js",
                "website/standalone/OpenTDCR.html",
                "website/dist/downloads/old-release.zip",
            )
            for name, content in intended.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            for name in private_or_generated:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("must not be published", encoding="utf-8")

            archive_path = root / "candidate.zip"
            result = subprocess.run(
                [sys.executable, str(root / "tools/package_release.py"),
                 "--output", str(archive_path)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(archive_path) as archive:
                expected = {"OpenTDCR/" + name for name in intended}
                expected.add("OpenTDCR/tools/package_release.py")
                self.assertEqual(set(archive.namelist()), expected)
                for name, content in intended.items():
                    self.assertEqual(archive.read("OpenTDCR/" + name).decode(), content)


if __name__ == "__main__":
    unittest.main()
