"""Deployment preflight; no application data is created."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'airport-detective-backend'

def check_resources():
    expected = json.loads((ROOT / 'deploy' / 'resources.json').read_text(encoding='utf-8'))
    for name, digest in expected.items():
        path = ROOT / name
        if not path.is_file():
            raise RuntimeError(f'Missing resource: {name}. Extract the deployment ZIP or run git lfs pull.')
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest() if sys.version_info >= (3, 11) else hash_file(stream)
        if actual != digest:
            raise RuntimeError(f'Invalid resource: {name}. It may be a Git LFS pointer; run git lfs pull.')
    if not (ROOT / 'airport-detective-frontend' / 'live-client.js').is_file():
        raise RuntimeError('Frontend assets are missing.')
    if not (BACKEND / 'vendor' / 'ultralytics' / '__init__.py').is_file():
        raise RuntimeError('Vendored YOLOv10 code is missing.')
    if not (BACKEND / 'vendor' / 'ultralytics' / 'data' / 'loaders.py').is_file():
        raise RuntimeError('Vendored ultralytics/data source code is missing; only backend/data may be excluded.')
    return len(expected)

def hash_file(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b''):
        digest.update(block)
    return digest.hexdigest()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['gpu', 'cpu'], default='gpu')
    parser.add_argument('--infer', action='store_true')
    args = parser.parse_args()
    if sys.version_info[:2] not in {(3, 10), (3, 11)} or struct.calcsize('P') != 8:
        raise RuntimeError('64-bit Python 3.10 or 3.11 is required.')
    print(f'Resources verified: {check_resources()}', flush=True)
    sys.path.insert(0, str(BACKEND))
    from engine import Detector, torch, hardware
    import flask, waitress, imageio_ffmpeg
    if args.mode == 'gpu' and not torch.cuda.is_available():
        raise RuntimeError('GPU mode requires CUDA. Check driver/PyTorch or rebuild using install.cmd -Mode cpu.')
    print(json.dumps(hardware(), ensure_ascii=False), flush=True)
    if args.infer:
        import numpy as np
        detector = Detector()
        device = detector.load('yolov10n.pt', 'cpu' if args.mode == 'cpu' else 'auto')
        detector.predict(np.zeros((640, 640, 3), dtype=np.uint8),
                         {'confidence': .25, 'imgsz': 640, 'scope': 'luggage'}, device)
        print(f'Model inference passed (device: {device}).', flush=True)

if __name__ == '__main__':
    main()
