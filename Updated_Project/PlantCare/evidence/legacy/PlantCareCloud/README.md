# XIAO to Lambda smoke test

Keep the current serial sketch on the XIAO until its data capture finishes, or use a second XIAO for this test. Flashing restarts the device and interrupts the capture.

1. In Arduino IDE select Seeed XIAO ESP32S3 and install ArduinoJson 7, MQTT by Joel Gaehwiler (256dpi), Adafruit SHT31, Adafruit VEML7700 and Adafruit seesaw. Open PlantCareCloud.ino.
2. Copy secrets.example.h to secrets.h. Enter Wi-Fi credentials, the IoT Data-ATS hostname, the Amazon root CA and the sensor device certificate and private key. Keep secrets.h local.
3. Provision the sensor IoT certificate policy with iot:Connect scoped to client/team3-sensor and iot:Publish scoped to topic/plantcare/team3/pothos1/telemetry and topic/plantcare/team3/pothos1/status/sensor. Use the account and region of the SAM stack.
4. Validate and build the SAM stack following docs/COLLECTION_AND_LAMBDA.md. An authorized AWS operator must deploy it before the live smoke test.
5. Subscribe in the IoT Core MQTT test client to the telemetry and condition topics under plantcare/team3/pothos1/. Flash the cloud sketch and look for a telemetry packet and a retained condition with a matching source boot_id and seq. Verify the same packet in the stack's DynamoDB SampleHistory table. Uncalibrated soil reports pct null and an unknown condition. A disconnected sensor reports an invalid reading.
6. Interrupt Wi-Fi and verify the serial samples continue, then verify telemetry resumes after reconnection. Expect gaps during the outage. The firmware keeps a single pending sample and discards it after 10 seconds. Run at the 2-second demo cadence only during integration testing.

No pump connection is needed. This build has telemetry and status publishing only. The local cloud-handler test uses mocked AWS clients. Arduino compilation, device certificates, RF reconnection and AWS services require the actual toolchain, board and account.
