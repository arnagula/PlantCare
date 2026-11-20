"""Public, latest-sample telemetry for the single live demo plant."""
import json
import logging
import os
from pathlib import Path
import time

from plantcare.contracts import number, timestamp, utc
from plantcare.engine import Engine, RULES
from plantcare.storage import DynamoStore
from .http import response

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
}


def load_live_state():
    import boto3

    return DynamoStore(boto3.client('dynamodb'), os.environ['HISTORY_TABLE']).load('live')


def snapshot(state, now):
    state = state or {}
    profile = state.get('profile')
    if profile is None:
        profile = json.loads((ROOT / 'profiles/live.json').read_text(encoding='utf-8'))
    engine = Engine(profile, state.get('engine'))
    assessment = engine.assess(now)
    sample = engine.state['sample']
    status = assessment['data_status']
    if not sample or status == 'stale':
        return {'status': 'stale', 'condition': 'unknown', 'readings': None}

    values = engine.values(sample)
    raw = sample['soil']['raw'] if sample['soil']['raw_valid'] is True else None
    bounds = {
        'temperature_c': (values['temperature_c'], -40, 85),
        'humidity_pct': (values['humidity_pct'], 0, 100),
        'light_lux': (values['light_lux'], 0, 200000),
        'soil_pct': (values['soil'], 0, 100),
        'soil_raw': (raw, 0, 65535),
    }
    condition = assessment['state']
    sample_time = timestamp(sample['ts'])
    return {
        'status': status,
        'condition': condition if condition in RULES or condition == 'happy' else 'unknown',
        'sample_time': utc(sample_time),
        'fresh_for_s': max(0, engine.timeout() - max(0, now - sample_time)),
        'readings': {
            key: value if number(value, low, high) else None
            for key, (value, low, high) in bounds.items()
        },
    }


def handler(event, context):
    path = event.get('rawPath')
    method = event.get('requestContext', {}).get('http', {}).get('method')
    if method != 'GET' or (path not in ASSETS and path != '/api/demo/telemetry'):
        return response(404, {'error': 'not_found'})
    if path in ASSETS:
        name, content_type = ASSETS[path]
        return response(200, (ROOT / 'dashboard' / name).read_text(encoding='utf-8'), content_type)
    if event.get('rawQueryString') or event.get('queryStringParameters'):
        return response(400, {'error': 'unexpected_query'})
    try:
        return response(200, snapshot(load_live_state(), time.time()))
    except Exception:
        logging.getLogger(__name__).error('Demo telemetry unavailable')
        return response(503, {'error': 'telemetry_unavailable'})
