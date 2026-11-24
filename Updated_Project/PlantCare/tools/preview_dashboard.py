"""Local dashboard preview. Not packaged into Lambda.

Run from the project folder, then open http://localhost:8000:
  python -m tools.preview_dashboard                 fake readings (default)
  python -m tools.preview_dashboard --data empty    no readings stored yet (sensor/simulator never sent data)
  python -m tools.preview_dashboard --data down     backend error (e.g. DynamoDB unavailable)
  python -m tools.preview_dashboard --data aws --aws-url https://<api-id>.execute-api.<region>.amazonaws.com
                                                    real readings from the deployed public telemetry endpoint
The dashboard files are always served from this folder, so you see your local changes.
"""
import argparse
from contextlib import ExitStack
import json
import logging
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
import time
import urllib.error
import urllib.request

from aws import demo
from plantcare.profile import default
from plantcare.service import Service
from plantcare.storage import MemoryStore
from tools.scenarios import packet

# Deliberately different readings so it is obvious which mode is on screen.
FAKE_READINGS = {
    'live': dict(soil=20, temp=22, rh=48, lux=900),        # shows "Thirsty"
    'simulated': dict(soil=55, temp=24, rh=62, lux=2500),  # shows "Happy"
}


def drifting(base, now):
    """Fake readings that wander slowly so the dashboard graphs have something to show."""
    wave = math.sin(now / 40)
    return dict(soil=round(base['soil'] + 3 * wave), temp=round(base['temp'] + 2.5 * wave, 1),
                rh=round(base['rh'] + 4 * math.cos(now / 55)), lux=round(base['lux'] + 300 * math.sin(now / 70)))


def fake_state(mode):
    """Build a fresh stored state for one mode, as the backend worker would."""
    now = time.time()
    store = MemoryStore()
    service = Service(store, Mock(), default('simulated'))
    # The engine needs a short run of samples before it changes condition.
    for seq in range(1, 11):
        sample_time = now - 2 * (10 - seq)
        service.handle('telemetry', packet(sample_time, seq, **drifting(FAKE_READINGS[mode], sample_time)), sample_time)
    return store.load('simulated')


def unavailable(mode):
    raise RuntimeError('simulated backend failure')


def forward_to_aws(base_url, path_and_query):
    """Fetch the deployed public telemetry endpoint; returns (status, body bytes)."""
    request = urllib.request.Request(base_url.rstrip('/') + path_and_query, headers={'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError):
        return 502, b'{"error": "aws_unreachable"}'


class Handler(BaseHTTPRequestHandler):
    data = 'fake'
    aws_url = None

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query, keep_blank_values=True)
        event = {
            'rawPath': url.path,
            'rawQueryString': url.query,
            'queryStringParameters': {k: ','.join(v) for k, v in query.items()} or None,
            'requestContext': {'http': {'method': 'GET'}},
        }
        if self.data == 'aws' and url.path == '/api/demo/telemetry':
            status, body = forward_to_aws(self.aws_url, self.path)
            self.reply(status, {'content-type': 'application/json', 'cache-control': 'no-store'}, body)
            return
        # Otherwise run the real Lambda handler, swapping only DynamoDB.
        if self.data == 'fake':
            # The fake states need the simulator's soil calibration, so show the real profile's thresholds instead.
            mode = demo.requested_mode(event)
            real_profile = json.loads((demo.ROOT / 'profiles' / ((mode or 'live') + '.json')).read_text(encoding='utf-8'))
            patches = [patch.object(demo, 'load_state', side_effect=fake_state),
                       patch.object(demo, 'public_thresholds', return_value=demo.public_thresholds(real_profile))]
        elif self.data == 'empty':
            patches = [patch.object(demo, 'load_state', return_value=None)]
        else:  # 'down', or static files in 'aws' mode (which never read DynamoDB)
            patches = [patch.object(demo, 'load_state', side_effect=unavailable)]
        with ExitStack() as stack:
            for active in patches:
                stack.enter_context(active)
            result = demo.handler(event, None)
        self.reply(result['statusCode'], result['headers'], result['body'].encode('utf-8'))

    def reply(self, status, headers, body):
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header('content-length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--data', choices=['fake', 'empty', 'down', 'aws'], default='fake',
                        help='where telemetry comes from (default: fake)')
    parser.add_argument('--aws-url', help='deployed API base URL, required with --data aws')
    args = parser.parse_args()
    if args.data == 'aws' and not args.aws_url:
        parser.error('--data aws needs --aws-url https://<api-id>.execute-api.<region>.amazonaws.com')
    if args.data == 'down':
        logging.getLogger('aws.demo').setLevel(logging.CRITICAL)  # the failure is intended; keep the terminal quiet
    Handler.data = args.data
    Handler.aws_url = args.aws_url
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print('Dashboard preview (%s data) at http://localhost:%d  -  Ctrl+C to stop' % (args.data, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
