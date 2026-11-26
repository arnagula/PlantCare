# Bottom-watering setup

The saved bench sketch `Arduino/demo1/demo1.ino` used 735/750 and a 4-second pulse. This build uses the requested provisional 760/820 cutoffs and 1.5 seconds on active-HIGH D2/GPIO3. At 16 mL/s the expected dose is about 24 mL. Measure delivery with the installed tubing.

## Flash the sensor

Run from `Updated_Project/PlantCare`. Keep the sensor's existing `firmware/sensor_controller/secrets.h`. If it is missing, copy `secrets.example.h` alongside it and supply the sensor-specific credentials for MQTT. The example values allow an offline build.

```powershell
pio run -e xiao
pio device list
pio run -e xiao -t upload --upload-port COMx
pio device monitor --port COMx --baud 115200
```

Replace `COMx` with the XIAO port. If needed, hold BOOT, tap RESET, release BOOT and list the ports again. Disconnect pump power for the flash and first checks. Verify relay-off behavior on D2/GPIO3 during power-up, reset and bootloader entry. GPIO3 is a strapping pin, so verify the relay input stays inactive when the pin is high impedance. I2C remains on GPIO5/GPIO6.

1. Wet soil and transition readings should keep the relay off. An unplugged probe or raw value outside 500–1100 must keep it off and reset the dry count.
2. At consistent probe depth, confirm ten consecutive readings below 760 start the pulse. Measure relay high for approximately 1.5 seconds even with Wi-Fi disconnected. Confirm no second pulse through the 60-second soak or during the rest of the boot. Values above 820 only label the soil wet.
3. With pump power disconnected, send `S` during a pulse, unplug the probe during a separate pulse, and cut controller power during another pulse. Verify cutoff and persistent lockout for interrupted pulses. Inspect the equipment before clearing a lockout. On this sensor board only, `pio run -e xiao -t erase --upload-port COMx` clears all flash settings and requires reflashing.
4. Collect one measured dose in a graduated container, then observe actual tray watering for 5–10 minutes. Serial samples every second. MQTT publishes every 10 seconds for 10 minutes after a completed dose, then returns to normal cadence. Verify the probe in both wet and dry media before unattended operation, since a plausible but incorrect low reading can qualify.

## Build and review the cloud change

```powershell
python -m pytest -q tests
npm ci
npm test
g++ -std=c++17 -Wall -Wextra -Werror tests_cpp/bottom_watering.cpp -o bottom-watering-test.exe
./bottom-watering-test.exe
sam validate --lint --template-file template.yaml --region YOUR_REGION
sam build --template-file template.yaml
```

Use `template.yaml`. An AWS IoT rule invokes LiveIngress asynchronously on each live MQTT message. LiveIngress validates the message and writes through the existing DynamoDB state and history transaction. It publishes the existing display condition feed. LiveIngress is limited to one concurrent invocation to serialize state changes and retained MQTT publishes. Duplicate messages are deduplicated, and older telemetry cannot replace the latest sample.

Both SQS mappings and the heartbeat schedule are disabled. The live path does not enqueue messages. Simulation still queues messages and will need separately approved processing to advance its cloud state. LiveIngress retries function errors twice and expires queued invocations after one hour. Inspect LiveIngress failures and dropped async events in CloudWatch after rollout.

At the prior 266,000 empty receives per day, a 30-day month produced approximately 7.98 million empty receives. At one sample per minute, direct live ingestion handles about 1,440 telemetry messages/day per device, plus watering events and faster post-dose samples. The cloud dashboard polls every 30 seconds while visible, about 120 API requests per active viewer-hour. Include IoT, Lambda, API Gateway and DynamoDB usage in the rollout estimate. Review any buffered simulation messages before separately approved processing. [AWS SQS pricing](https://aws.amazon.com/sqs/pricing/)

After approval to prepare a change set, use `sam deploy --guided --no-execute-changeset` with the existing stack name, region, IoT endpoint and JWT settings. Review the change set for DynamoDB table retention and disabled mappings. Execute only after deployment approval. Queue activation requires separate approval.

Verify the mapping state read-only with `aws lambda list-event-source-mappings --function-name FUNCTION_NAME --region YOUR_REGION --query 'EventSourceMappings[].{State:State,Queue:EventSourceArn}'` for each worker. The IoT MQTT test client can verify messages on `plantcare/team3/pothos1/telemetry` and `plantcare/team3/pothos1/watering/event` with the workers paused.

After authorized deployment, verify that publishing live telemetry updates the cloud dashboard while both SQS mappings remain disabled. Verify one `started` and one terminal event per cycle in authenticated `GET /api/watering?mode=live`. A redelivery should leave one history row per event. Check the watering stage, raw soil and dose duration in Live mode, then toggle to Simulation and confirm that live activity clears. Check the existing `plantcare/team3/pothos1/condition` topic for the display's watering and soaking updates.
