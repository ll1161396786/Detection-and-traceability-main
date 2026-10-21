"""Single-process Waitress deployment for the shared four-camera scheduler."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import sys
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.1.0'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT / 'deploy' / 'config.json')
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding='utf-8-sig'))
    import psutil
    state_file = ROOT / '.deployment' / 'server.json'
    if state_file.exists():
        previous = json.loads(state_file.read_text(encoding='utf-8'))
        try:
            process = psutil.Process(previous['pid'])
            old_time = datetime.fromisoformat(previous['created_utc']).timestamp()
            if abs(process.create_time() - old_time) < 3:
                raise RuntimeError('This deployment is already running. Stop it before starting another instance.')
        except psutil.NoSuchProcess:
            pass
    host, port, threads = config['host'], int(config['port']), int(config['threads'])
    if host not in {'127.0.0.1', '0.0.0.0'} or not 1024 <= port <= 65535 or not 4 <= threads <= 64:
        raise ValueError('Invalid host/port/threads in deployment configuration.')
    from check_env import check_resources
    check_resources()
    # Prevent Windows from sharing an occupied port with an older application.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == 'nt':
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        probe.bind((host, port))
    sys.path.insert(0, str(ROOT / 'airport-detective-backend'))
    import app as backend
    from waitress import create_server
    instance = uuid.uuid4().hex
    original_health = backend.app.view_functions['health']
    def health():
        with backend.lock:
            active_offline = sum(j['status'] not in backend.TERMINAL and not j.get('live_camera') for j in backend.jobs.values())
        payload = original_health().get_json()
        return {**payload, 'status': 'ok', 'version': VERSION, 'instance': instance,
                'active_offline_jobs': active_offline}
    backend.app.view_functions['health'] = health
    server = create_server(backend.app, host=host, port=port, threads=threads,
                           max_request_body_size=2 * 1024**3, expose_tracebacks=False)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    # Process creation time is used with PID and executable path by stop.ps1.
    created = datetime.fromtimestamp(psutil.Process().create_time(), timezone.utc).isoformat()
    state_file.write_text(json.dumps({'pid': os.getpid(), 'port': port, 'instance': instance,
                                     'executable': psutil.Process().exe(), 'created_utc': created}), encoding='utf-8')
    url = f'http://127.0.0.1:{port}/'
    print(f'Airport Detective {VERSION}: {url}\nPress Ctrl+C to stop this server.', flush=True)
    if config.get('open_browser', True):
        webbrowser.open(url)
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    finally:
        backend.monitor.stop()
        worker = backend.monitor.worker
        if worker:
            worker.join(timeout=60)
        server.close()
        if state_file.exists() and json.loads(state_file.read_text(encoding='utf-8')).get('instance') == instance:
            state_file.unlink()

if __name__ == '__main__':
    main()
