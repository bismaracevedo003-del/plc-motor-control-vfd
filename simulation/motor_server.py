import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from motor_simulator import MotorDrive

HMI_DIR = Path(__file__).resolve().parent.parent / 'hmi'
STATIC_FILES = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
}

drive = MotorDrive()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get('Content-Length', 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode('utf-8'))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/state':
            self._send_json(drive.snapshot())
            return
        static = STATIC_FILES.get(path)
        if not static:
            self._send_json({'error': 'Not found'}, 404)
            return
        filename, content_type = static
        body = (HMI_DIR / filename).read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
        except json.JSONDecodeError:
            self._send_json({'error': 'Invalid JSON'}, 400)
            return

        if path == '/api/command':
            name = payload.get('command')
            if name not in ('START', 'STOP', 'RESET'):
                self._send_json({'error': 'command must be START, STOP or RESET'}, 400)
                return
            drive.reset_cmd = name == 'RESET'
            drive.start_cmd = name == 'START'
            drive.stop_cmd = name == 'STOP'
            self._send_json(drive.snapshot())
            return

        if path == '/api/setpoint':
            try:
                value = float(payload['setpoint_hz'])
            except (KeyError, TypeError, ValueError):
                self._send_json({'error': 'setpoint_hz must be a number'}, 400)
                return
            drive.setpoint_hz = min(50.0, max(0.0, value))
            self._send_json(drive.snapshot())
            return

        if path == '/api/fault':
            name = payload.get('fault')
            if not drive.set_fault(str(name), bool(payload.get('active', True))):
                self._send_json({'error': 'Unknown fault'}, 400)
                return
            self._send_json(drive.snapshot())
            return

        self._send_json({'error': 'Not found'}, 404)


def simulation_loop(stop_event: threading.Event, interval: float = 0.2) -> None:
    while not stop_event.is_set():
        drive.tick(interval)
        stop_event.wait(interval)


def create_server(host: str = '127.0.0.1', port: int = 4000) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    server = create_server()
    stop_event = threading.Event()
    worker = threading.Thread(target=simulation_loop, args=(stop_event,), daemon=True)
    worker.start()
    print(f'Motor HMI listening on http://127.0.0.1:{server.server_port}')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        server.server_close()


if __name__ == '__main__':
    main()
