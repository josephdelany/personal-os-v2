#!/usr/bin/env python3
"""Package reviewed device source and instructions, never credentials or signed Shortcuts."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ('PersonalOSQueue.js', 'PersonalOSCapture.js', 'PersonalOSSetup.js', 'README.md')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sources = {name: (ROOT / 'device/scriptable' / name).read_bytes() for name in FILES}
    manifest = {'format': 1, 'installed': False, 'signed_shortcuts_included': False,
                'sha256': {name: hashlib.sha256(content).hexdigest() for name, content in sources.items()}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in sources.items():
            bundle.writestr(name, content)
        bundle.writestr('manifest.json', json.dumps(manifest, indent=2) + '\n')
    with zipfile.ZipFile(args.out) as bundle:
        assert bundle.testzip() is None
        for name, digest in manifest['sha256'].items():
            assert hashlib.sha256(bundle.read(name)).hexdigest() == digest
    print(f'Created verified source bundle: {args.out}')


if __name__ == '__main__':
    main()
