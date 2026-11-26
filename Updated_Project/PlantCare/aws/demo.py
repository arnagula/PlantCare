"""Public, read-only latest-sample telemetry for the live plant or the simulator."""
import json
import logging
import os
from pathlib import Path
import time

from plantcare.contracts import number, timestamp, utc
from plantcare.engine import Engine, RULES
from plantcare.storage import DynamoStore
from plantcare.service import local_watering
from .http import response

ROOT = Path(__file__).resolve().parents[1]
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
}
MODES = ('live', 'simulated')


def load_state(mode):
    import boto3

    return DynamoStore(boto3.client('dynamodb'), os.environ['HISTORY_TABLE']).load(mode)


def requested_mode(event):
    """Return the requested mode, or None for any query other than a single valid mode."""
    raw = event.get('rawQueryString') or ''
    params = event.get('queryStringParameters') or {}
    if not raw and not params:
        return 'live'
    if set(params) != {'mode'} or raw != 'mode=' + str(params['mode']):
        return None
    return params['mode'] if params['mode'] in MODES else None


def public_thresholds(profile):
    """Points where each warning starts, from the profile stored with that mode.

    A bound is None when the profile has no valid number for it, e.g. uncalibrated live soil.
    """
    t = profile.get('thresholds') or {}
    soil = profile.get('soil') or {}
    bounds = {
        'temperature_c': ((t.get('cold_enter_c'), t.get('hot_enter_c')), -40, 85),
        'humidity_pct': ((t.get('humidity_enter_pct'), None), 0, 100),
        'light_lux': ((t.get('light_enter_lux'), None), 0, 200000),
        'soil_pct': ((soil.get('dry_enter_pct'), soil.get('wet_enter_pct')), 0, 100),
    }
    return {
        key: {name: value if number(value, low, high) else None
              for name, value in zip(('low', 'high'), pair)}
        for key, (pair, low, high) in bounds.items()
    }


def snapshot(state, now, mode='live'):
    state = state or {}
    profile = state.get('profile')
    if profile is None:
        profile = json.loads((ROOT / 'profiles' / (mode + '.json')).read_text(encoding='utf-8'))
    engine = Engine(profile, state.get('engine'))
    assessment = engine.assess(now)
    sample = engine.state['sample']
    status = assessment['data_status']
    if not sample or status == 'stale':
        return {'mode': mode, 'status': 'stale', 'condition': 'unknown', 'readings': None,
                'thresholds': public_thresholds(profile)}

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
    result = {
        'mode': mode,
        'status': status,
        'condition': condition if condition in RULES or condition == 'happy' else 'unknown',
        'sample_time': utc(sample_time),
        'fresh_for_s': max(0, engine.timeout() - max(0, now - sample_time)),
        'readings': {
            key: value if number(value, low, high) else None
            for key, (value, low, high) in bounds.items()
        },
        'thresholds': public_thresholds(profile),
    }
    stage, latest = local_watering(state, sample)
    if stage or latest:
        result['watering'] = {'stage': stage}
        if latest:
            result['watering']['last_event'] = {
                key: latest[key] for key in ('status','ts','actual_duration_ms') if key in latest
            }
    return result


def handler(event, context):
    path = event.get('rawPath')
    method = event.get('requestContext', {}).get('http', {}).get('method')
    if method != 'GET' or (path not in ASSETS and path != '/api/demo/telemetry'):
        return response(404, {'error': 'not_found'})
    if path in ASSETS:
        name, content_type = ASSETS[path]
        return response(200, (ROOT / 'dashboard' / name).read_text(encoding='utf-8'), content_type)
    mode = requested_mode(event)
    if mode is None:
        return response(400, {'error': 'unexpected_query'})
    try:
        return response(200, snapshot(load_state(mode), time.time(), mode))
    except Exception:
        logging.getLogger(__name__).error('Demo telemetry unavailable')
        return response(503, {'error': 'telemetry_unavailable'})
