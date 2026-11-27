#!/usr/bin/env python3
"""Create a deterministic, history-free source archive from this release tree."""
import argparse
import hashlib
from pathlib import Path
import zipfile

EXCLUDED_DIRS = {'.git', '.venv', 'venv', '__pycache__', 'node_modules', '.openai',
                 '.sites-local', '.sites-checkout', '.sites-runtime', '.pytest_cache',
                 'build', 'artifacts', 'standalone', 'downloads', 'measurements',
                 '.agents', '.codex'}
EXCLUDED_FILES = {'.DS_Store', '.env'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob('*')):
            relative = path.relative_to(root)
            if any(part in EXCLUDED_DIRS or part.endswith('.egg-info') for part in relative.parts):
                continue
            # Match local-data patterns in .gitignore, including descendants of
            # ignored directories. Keep the explicitly tracked website output.
            if relative.parts[:2] == ('docs', 'announcements'):
                continue
            if 'dist' in relative.parts and relative.parts[:2] != ('website', 'dist'):
                continue
            if relative.parts[0] == 'configs' and path.name.endswith('.local.json'):
                continue
            if path == output or path.name in EXCLUDED_FILES or path.suffix in {'.pyc', '.pyo', '.pyd', '.log', '.zip', '.tar', '.gz'}:
                continue
            if any(part.startswith(('.env.', 'local.')) for part in relative.parts):
                continue
            if path.is_symlink():
                raise ValueError(f'Symlinks must be reviewed before release: {relative}')
            if not path.is_file():
                continue
            info = zipfile.ZipInfo('OpenTDCR/' + relative.as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
            count += 1
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(f'{output}\n{count} files; {output.stat().st_size} bytes\nSHA256 {digest}')


if __name__ == '__main__':
    main()
