import json
from pathlib import Path
from aws.handler import lambda_handler
packet=json.loads((Path(__file__).resolve().parents[1]/'contracts'/'telemetry.json').read_text())
print(json.dumps(lambda_handler(packet,None),indent=2))
