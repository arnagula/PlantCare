# AWS deployment checklist — not yet deployed

1. In one AWS region create Things and distinct X.509 certificates for sensor and display; create narrowly scoped IoT policies for live topics only. Store credentials outside git. Install Amazon Root CA.
2. Obtain the **Data-ATS MQTT endpoint** from IoT Core. Set per-device Wi-Fi and certificates and verify mutual TLS; synchronize NTP before connecting.
3. Create a Lambda function with Python 3.12+ runtime; deploy `aws/` plus `profiles/` at matching relative paths. For real ML, package trusted `scikit-learn` and model dependencies for Lambda's architecture and version. Do not deploy the synthetic example model as a validated plant classifier.
4. Create IoT Rule with SQL `SELECT * FROM 'plantcare/team3/pothos1/telemetry'` invoking Lambda; attach `lambda:InvokeFunction` permission scoped to the **rule ARN** and AWS account. Separate simulation rule to simulation topic.
5. Add Lambda environment `DRY_RUN=false` and `IOT_DATA_ENDPOINT=<your iot data endpoint>` after dry-run tests. Lambda role needs `iot:Publish` ONLY on the condition topic(s). Do not give it permission for live watering commands until the state machine and security gates are implemented and verified.
6. Add DynamoDB tables for sample history, conditions and state with conditional writes for deduplication, ordering and persistent timers. **Not yet implemented in starter**. Lambda invocations are concurrent and stateless; do not use in-memory persistence as if it were durable.
7. Add authenticated HTTPS API for dashboard/history; avoid exposing AWS secrets to browser. Implement bounded history queries and watering controls after pump qualification.
8. Enable logs, cost alarms and safe device disconnect handling. Retain **condition** only, never retain watering commands.

**Important:** AWS IoT Core is message transport, not automatic history storage. This starter's handler publishes conditions but does not provide durable history, model inference, hysteresis or cloud-side watering authorization. Track each item as incomplete.

Docs: https://docs.aws.amazon.com/iot/latest/developerguide/lambda-rule-action.html ; https://docs.aws.amazon.com/boto3/latest/reference/services/iot-data/client/publish.html
