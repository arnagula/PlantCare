# Data collection and Lambda integration

## Capture from the XIAO

Use firmware/Plant_Care_Companion_Sensors/Plant_Care_Companion_Sensors.ino if you need to reflash. If the working sensor sketch is already installed, keep it running. Close Arduino Serial Monitor before starting the logger. Replace COM5 with the actual XIAO port.

```powershell
py -m pip install pyserial
py tools/log_sensors.py COM5 baseline.csv
py tools/log_sensors.py COM5 dry.csv --phase dry --hours 0.1
py tools/log_sensors.py COM5 wet.csv --phase wet --hours 0.1
```

Keep the USB host awake for the baseline. Timestamps are host UTC receipt times. Blank CSV fields preserve invalid samples and their validity flags. Use unique file names for repeated runs. Ctrl+C closes the file cleanly. Each sample is flushed as received. Check that data rows are accumulating before leaving it running.

Use two cups of the same potting mix, one dry and one thoroughly wetted and drained. Collect at least 20 valid readings per cup across repeated probe insertions. Keep the pump off. Retain the raw readings and note insertion depth and soil conditions. Review spread and overlap before choosing calibration endpoints. The baseline is environment history and does not provide labeled plant-health outcomes.

## Exercise Lambda locally

```sh
python -m pip install -r requirements.txt
python -m ml.train_example
python -m unittest discover -s tests -v
```

The tests exercise the same handler analysis path used by Lambda. ENABLE_SYNTHETIC_MODEL enables the bundled demonstration model on simulated packets. The live path uses the existing rule baseline until a suitable model is available. The demonstration model learns synthetic threshold labels. It has no measured plant-health accuracy.

## AWS integration

Use the included SAM template once the team is ready for a billable deployment. Obtain the regional IoT Data-ATS hostname first. Run `sam validate --lint`, `sam build --use-container`, then `sam deploy --guided` and supply the IoTDataEndpoint parameter. Use a SAM build environment that supports the Python 3.12 runtime and its compiled dependencies. The template has one IoT rule and Lambda per mode. The Lambdas reject wrong-mode payloads, write telemetry to DynamoDB by device and sample identity, and publish condition reports to their respective topics. Repeat delivery writes the same sample key. Retained reports can still arrive out of order and durable condition state remains to be implemented.

Device Things, certificates, and AWS IoT device policies must be provisioned separately. Refer to the certificate and endpoint steps in AWS_SETUP.md. Its prototype deployment steps predate this template.

AWS reference: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/sam-property-function-iotrule.html

## Remaining work

- XIAO MQTT/TLS firmware and a live publish test.
- AWS SAM validation and integration against the team's AWS account.
- Persistent hysteresis, staleness and out-of-order report handling.
- Authenticated history API and dashboard.
- Command validation, watering state machine, relay and flow qualification.
- PlantFace networking and physical AMOLED validation by the teammate who has the board.
- Real dry/wet calibration, baseline history, and labeled evaluation data for live ML.
