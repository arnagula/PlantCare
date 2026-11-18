"""Capture complete readings from the working XIAO serial sketch."""
import argparse
import csv
from datetime import datetime, timezone
import math
from pathlib import Path
import re
import time

FIELDS = {
    'Temperature': ('temperature_c', ' C', -40, 85),
    'Humidity': ('humidity_pct', ' %', 0, 100),
    'Light': ('light_lux', ' lux', 0, 200000),
    'Soil Moisture (raw)': ('soil_raw', '', 0, 65535),
}
COLUMNS = ['ts_utc', 'phase', 'uptime_ms'] + [
    column for field, *_ in FIELDS.values() for column in (field, field + '_valid')
]


def samples(lines, phase):
    row = None
    for line in lines:
        match = re.fullmatch(r'Uptime: (\d+) ms', line)
        if match:
            row = {'ts_utc': datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                   'phase': phase, 'uptime_ms': int(match[1])}
            continue
        label, _, reading = line.partition(': ')
        if label == 'Soil Moisture': label = 'Soil Moisture (raw)'
        if row is None or label not in FIELDS:
            continue
        key, unit, low, high = FIELDS[label]
        value = None
        if not unit or reading.endswith(unit):
            try:
                candidate = float(reading.removesuffix(unit))
                if math.isfinite(candidate) and low <= candidate <= high and (key != 'soil_raw' or candidate.is_integer()):
                    value = int(candidate) if key == 'soil_raw' else candidate
            except ValueError:
                pass
        row[key] = value
        row[key + '_valid'] = value is not None
        if len(row) == len(COLUMNS):
            yield row
            row = None


def serial_lines(port, deadline):
    while time.monotonic() < deadline:
        raw = port.readline()
        if raw.endswith(b'\n'):
            yield raw.decode('utf-8', errors='replace').strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port')
    parser.add_argument('output', type=Path)
    parser.add_argument('--phase', choices=('baseline', 'dry', 'wet'), default='baseline')
    parser.add_argument('--hours', type=float, default=24)
    args = parser.parse_args()
    if not math.isfinite(args.hours) or args.hours <= 0:
        parser.error('--hours must be positive and finite')
    import serial
    count = 0
    with serial.Serial(args.port, 115200, timeout=1) as port, args.output.open(
        'x', newline='', encoding='utf-8'
    ) as output:
        writer = csv.DictWriter(output, fieldnames=COLUMNS)
        writer.writeheader()
        try:
            for row in samples(serial_lines(port, time.monotonic() + args.hours * 3600), args.phase):
                writer.writerow(row)
                output.flush()
                count += 1
        except KeyboardInterrupt:
            pass
    print(f'Saved {count} samples to {args.output}')
    if not count:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
