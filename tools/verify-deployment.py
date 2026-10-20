"""Verify every file in the shipped ZIP against its manifest and resource hashes."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

archive = Path(sys.argv[1])
prefix = 'airport-detective/'
with zipfile.ZipFile(archive) as bundle:
    names = bundle.namelist()
    manifest = json.loads(bundle.read(prefix + 'SHA256SUMS.json'))
    required = json.loads(bundle.read(prefix + 'deploy/resources.json'))
    assert prefix + 'airport-detective-backend/vendor/ultralytics/data/loaders.py' in names
    assert set(names) == {prefix + p for p in manifest} | {prefix + 'SHA256SUMS.json'}
    for name, expected in manifest.items():
        parts = Path(name).parts
        assert not set(parts) & {'.venv', '.runtime', '.deployment', '__pycache__'}
        assert not name.startswith('airport-detective-backend/data/')
        digest = hashlib.sha256()
        with bundle.open(prefix + name) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        actual = digest.hexdigest()
        assert actual == expected, name
        if name in required:
            assert actual == required[name], f'Resource is not the original binary: {name}'
    assert set(required) <= set(manifest)
print(f'ZIP verified: {len(manifest)} file hashes, {len(required)} original resources; no runtime data or virtual environments.')
