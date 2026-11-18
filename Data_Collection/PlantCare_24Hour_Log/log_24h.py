"""Record XIAO serial samples for 24 hours; mark watering from keyboard.

Usage: pip install pyserial
       python log_24h.py --port COM5

Commands while running:
  water-start       Mark start of watering; immediately sample
  water-end 150     Mark watering finished (150 mL); immediately sample
  note moved plant  Record an observation
  status            Show how many samples have been saved
  stop              Stop early and close output files

Keep the laptop awake and the board powered via USB.
"""
import argparse
import csv
import datetime as dt
import os
from pathlib import Path
import queue
import threading
import time
import uuid

import serial

DATA_FIELDS = [
    'timestamp_utc', 'timestamp_local', 'device_uptime_ms', 'seq', 'phase',
    'temperature_c', 'humidity_pct', 'light_lux', 'soil_raw',
    'temperature_valid', 'humidity_valid', 'light_valid', 'soil_valid',
]
EVENT_FIELDS = ['timestamp_utc', 'timestamp_local', 'event', 'device_uptime_ms', 'detail']

def stamp():
    now = dt.datetime.now(dt.timezone.utc)
    return now.isoformat(timespec='milliseconds'), now.astimezone().isoformat(timespec='milliseconds')

def commands(q):
    while True:
        try:
            q.put(input('Action [water-start | water-end <mL> | note <text> | status | stop]: ').strip())
        except EOFError:
            return

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', required=True, help='Serial port such as COM5')
    p.add_argument('--hours', type=float, default=24.0, help='Recording duration in hours')
    p.add_argument('--output', default='logs', help='Directory for CSV files')
    args = p.parse_args()
    if args.hours <= 0:
        p.error('--hours must be positive')

    folder = Path(args.output)
    folder.mkdir(parents=True, exist_ok=True)
    session = dt.datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
    samples_path = folder / f'{session}_samples.csv'
    events_path = folder / f'{session}_events.csv'
    command_queue = queue.Queue()
    n = 0
    start = time.monotonic()
    end = start + args.hours * 3600
    print('Opening', args.port)
    with serial.Serial(args.port, 115200, timeout=0.5, write_timeout=2) as board, \
         samples_path.open('w', newline='', encoding='utf-8') as samples_file, \
         events_path.open('w', newline='', encoding='utf-8') as events_file:
        # Opening the port may reset the board; wait for its startup banner.
        sample_writer = csv.DictWriter(samples_file, fieldnames=DATA_FIELDS)
        event_writer = csv.DictWriter(events_file, fieldnames=EVENT_FIELDS)
        sample_writer.writeheader(); event_writer.writeheader()
        samples_file.flush(); events_file.flush()
        threading.Thread(target=commands, args=(command_queue,), daemon=True).start()
        print('Logging to:', samples_path)
        print('Event log:', events_path)
        print('Duration:', args.hours, 'hours. Keep laptop awake. Water manually, not via software.')
        print('Use water-start immediately before watering and water-end <mL> afterward.')
        while time.monotonic() < end:
            while not command_queue.empty():
                cmd = command_queue.get()
                t_utc, t_local = stamp()
                if cmd == 'water-start':
                    board.write(b'WSTART\n')
                    event_writer.writerow(dict(timestamp_utc=t_utc, timestamp_local=t_local,
                                              event='USER_WATER_START', device_uptime_ms='', detail=''))
                    events_file.flush()
                elif cmd.startswith('water-end'):
                    parts = cmd.split(maxsplit=1)
                    detail = parts[1].strip() if len(parts) > 1 else 'volume not recorded'
                    board.write(b'WEND\n')
                    event_writer.writerow(dict(timestamp_utc=t_utc, timestamp_local=t_local,
                                              event='USER_WATER_END', device_uptime_ms='', detail=f'volume_ml={detail}'))
                    events_file.flush()
                elif cmd.startswith('note '):
                    event_writer.writerow(dict(timestamp_utc=t_utc, timestamp_local=t_local,
                                              event='USER_NOTE', device_uptime_ms='', detail=cmd[5:]))
                    events_file.flush()
                    board.write(b'MARK\n')
                elif cmd == 'status':
                    print(f'{n} samples saved; elapsed {(time.monotonic()-start)/3600:.2f}h')
                elif cmd == 'stop':
                    print('Stopped by user; files closed cleanly.')
                    return
                elif cmd:
                    print('Unknown action:', cmd)
            try:
                line = board.readline().decode('utf-8', errors='replace').strip()
            except serial.SerialException as exc:
                print('SERIAL CONNECTION LOST. Logging stopped; check USB connection:', exc)
                raise
            if not line:
                continue
            t_utc, t_local = stamp()
            parts = line.split(',')
            if parts[0] == 'DATA' and len(parts) == 12:
                values = parts[1:]
                row = dict(zip(DATA_FIELDS[2:], values))
                row.update(timestamp_utc=t_utc, timestamp_local=t_local)
                sample_writer.writerow(row)
                samples_file.flush()
                n += 1
                print(f'[{t_local[11:19]}] #{n} {values[2]} soil={values[6] or "INVALID"} '
                      f'temp={values[3] or "INVALID"}C lux={values[5] or "INVALID"}')
            elif parts[0] == 'EVENT' and len(parts) >= 3:
                event_writer.writerow(dict(timestamp_utc=t_utc, timestamp_local=t_local,
                                           event=parts[1], device_uptime_ms=parts[2], detail=''))
                events_file.flush()
                print('DEVICE EVENT:', parts[1])
            elif line.startswith('#'):
                print('DEVICE:', line[1:].strip())
            else:
                print('Unrecognized serial message:', line)
        print(f'24-hour duration completed: {n} samples recorded.')
    print('Saved:', samples_path, events_path)

if __name__ == '__main__':
    main()
