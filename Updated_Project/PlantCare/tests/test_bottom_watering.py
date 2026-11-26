import base64
import json
from unittest.mock import Mock, patch

from aws import api, demo, handler
from plantcare.contracts import timestamp, utc
from plantcare.profile import default
from plantcare.service import Service
from plantcare.storage import MemoryStore
from tools.scenarios import packet

NOW = timestamp('2026-11-12T15:00:00.000Z')
PREFIX = 'plantcare/team3/pothos1/'


def live_packet():
    sample = packet(NOW, 1)
    sample.update(mode='live', device_id='sensor-01', boot_id='test-boot')
    sample['soil'] = dict(raw=730, raw_valid=True, calibrated=False, valid=False,
                          pct=None, calibration_id=None)
    sample['pump'].update(local_stage='monitoring', armed=True)
    return sample


def dose(status, seq, **overrides):
    payload = dict(schema=1, mode='live', source='device', device_id='sensor-01',
                   boot_id='test-boot', command_id='test-boot-water', action='water',
                   event_seq=seq, status=status, ts=utc(NOW+seq),
                   pump_on=status=='started', soil_raw=730, reason_code=None)
    if status != 'started':
        payload['actual_duration_ms'] = 1500
    return {**payload, **overrides}


def test_ingress_worker_history_and_dashboard():
    store = MemoryStore()
    publish = Mock()
    app = Service(store, publish, default('live'))
    with patch.dict('os.environ', {'EXPECTED_MODE':'live'}), patch.object(
        handler, 'service', return_value=app
    ), patch.object(handler.time, 'time', return_value=NOW+3):
        def ingest(tail, payload):
            event = dict(source_topic=PREFIX+tail,
                         raw_payload=base64.b64encode(json.dumps(payload).encode()).decode())
            def enqueue(mode, kind, payload):
                body = json.dumps(dict(kind=kind, payload=payload, received_at=NOW+3))
                return handler.worker({'Records':[{'body':body}]}, None)
            with patch.object(handler, 'enqueue', side_effect=enqueue):
                return handler.ingress(event, None)

        assert ingest('telemetry',live_packet())['status']=='accepted'
        start, stop = dose('started',1), dose('completed',2)
        assert ingest('watering/event',start)['status']=='accepted'
        assert app.get_state(NOW+3)['watering']['pump_on'] is True
        assert ingest('watering/event',stop)['status']=='accepted'
        assert ingest('watering/event',stop)['status']=='duplicate'

    rows = store.history('live','LOG#',utc(NOW),utc(NOW+3))
    assert [row['status'] for row in rows]==['started','completed']
    snapshot = demo.snapshot(store.load('live'),NOW+3)
    assert snapshot['watering']==dict(stage='soaking',last_event=dict(
        status='completed',ts=stop['ts'],actual_duration_ms=1500))
    assert 'test-boot' not in json.dumps(snapshot)
    assert not demo.snapshot(store.load('simulated'),NOW+3).get('watering')
    assert all(not call.args[0].endswith('/command') for call in publish.call_args_list)


def test_bad_events_and_cloud_commands_are_rejected():
    app = Service(MemoryStore(), Mock(), default('live'))
    for changes in ({'soil_raw':65535}, {'boot_id':'other'}, {'pump_on':False},
                    {'soil_raw':True}, {'soil_raw':760}, {'mode':'simulated'}):
        assert app.handle('event',dose('started',1,**changes),NOW+3)['status']=='rejected'
    assert app.handle('request',dict(action='water',request_id='req'),NOW)['reason']=='local_control_only'
    request = dict(rawPath='/api/watering', body='{"request_id":"req"}',
                   requestContext={'http':{'method':'POST'},
                                   'authorizer':{'jwt':{'claims':{'sub':'test'}}}})
    with patch.object(api,'service',return_value=app), patch.object(api,'enqueue') as enqueue:
        assert api.handler(request,None)['statusCode']==409
        enqueue.assert_not_called()


def test_template_keeps_pollers_disabled():
    with open('template.yaml',encoding='utf-8') as template:
        resources = json.load(template)['Resources']
    for worker in ('LiveWorker','SimWorker'):
        assert resources[worker]['Properties']['Events']['Queue']['Properties']['Enabled'] is False
    assert resources['Heartbeat']['Properties']['Events']['Pulse']['Properties']['Enabled'] is False
