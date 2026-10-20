"""Build an extract-and-install Windows bundle with models; private media is excluded."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile
import sys

EXCLUDED = {'.git', '.runtime', '.deployment', '.venv', '__pycache__',
            'node_modules', 'dist', '.pytest_cache', 'releases'}

def include(path, root):
    parts = path.relative_to(root).parts
    private_dirs = ('public/media/', 'airport-detective-backend/videos/', 'airport-detective-backend/data/', '图片/')
    relative = path.relative_to(root).as_posix()
    if any(('/' + value) in ('/' + relative) for value in private_dirs):
        return False
    if 'vendor' not in parts and path.suffix.lower() in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}:
        return False
    return (parts[:2] != ('airport-detective-backend', 'data')
            and not any(p in EXCLUDED or 'backup' in p.lower() for p in parts)
            and path.suffix.lower() not in {'.pyc', '.pyo', '.log', '.zip', '.7z'}
            and not path.name.startswith('.env'))

def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    root = args.source.resolve()
    sys.path.insert(0, str(root / 'deploy'))
    from check_env import check_resources
    check_resources()
    output = (args.output or root / 'releases').resolve()
    output.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in root.rglob('*') if p.is_file() and include(p, root) and p.name != 'SHA256SUMS.json')
    manifest = {p.relative_to(root).as_posix(): digest(p) for p in files}
    (root / 'SHA256SUMS.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    archive = output / 'airport-detective-code-models-v1.1.0.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as bundle:
        for path in files + [root / 'SHA256SUMS.json']:
            bundle.write(path, 'airport-detective/' + path.relative_to(root).as_posix())
    archive_hash = digest(archive)
    archive.with_suffix('.zip.sha256').write_text(f'{archive_hash}  {archive.name}\n', encoding='ascii')
    print(json.dumps({'archive': str(archive), 'bytes': archive.stat().st_size, 'sha256': archive_hash, 'files': len(manifest) + 1}), flush=True)

if __name__ == '__main__':
    main()
