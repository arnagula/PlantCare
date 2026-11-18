# Parallel development handoffs

All features must match schema-1 messages and topic names in the master guide; this version moves trained classification and rules to AWS Lambda. No changes to contracts without team approval.

## Anish — sensor controller
1. Add board-specific AWS TLS MQTT publish/subscribe to the sensor starter. Save secrets outside repo. The sketch presently prints JSON over USB and is not AWS-ready.
2. Calibrate same potting mix using at least 20 dry and 20 wetted-and-drained readings with repeat insertions; store raw endpoints and calibration ID in NVS. Preserve raw values.
3. Bench-test relay power and OFF-at-reset, pump submerged and safely isolated; measure delivery at 1, 2, 3, 5 seconds x3.
4. Develop separate command/relay firmware module with hard maximum, local timer, fault lockout, duplicate/expired/old-boot rejection, NVS transaction marker and cooldown. Do not connect live commands until all tests pass.

## Pranav — AWS infrastructure
1. Create AWS IoT Thing/certificate/policy pair for each board; verify publish/sub with simulator in restricted prefixes.
2. Deploy Lambda integration; test Rule invocation; set environment and IAM least privilege for `iot:Publish` of conditions only.
3. Implement DynamoDB tables for history and current device/analysis state with unique sample identities, conditional updates and stale tracking. Ensure timestamp ordering and idempotency.
4. Add secure API Gateway/Lambda endpoints for dashboard and history; ensure browser receives no device credentials.
5. Introduce monitoring/logging and manual tests against sample packets. Track AWS usage costs.

## Cristian — condition analysis and ML
1. Produce documented dataset, label source/provenance and train/test split by independent experiment or time block. Do not claim true pothos-health accuracy from synthetic labels.
2. Train several models; compare against interpretable horticultural rules; use versioned trusted model artifact and documented evaluation.
3. Wire real inference into `aws/analysis.py` via `predict_issues`; only enable model when actual evaluation is complete.
4. Implement persistent timers, hysteresis, day/night decisions and issue prioritization using DynamoDB state rather than process memory.
5. Design watering coordinator with persistent state and only publish live commands after both soil/pump gates are qualified and physical local interlocks pass.

## Camilo — display and dashboard
1. Integrate Wi-Fi, NTP, AWS MQTT TLS + QoS1 and reconnect into existing PlantFace; subscribe to condition. Maintain original animation/touch/audio code.
2. Parse extended schema-1 condition, label LIVE/SIMULATED, implement stale/local connection indication and updated watering states.
3. Implement web dashboard against Pranav's authenticated APIs: live readings, invalid flags, current condition, history graphs, events and safeguards.
4. Test with `contracts/condition.json` in simulation before real AWS publishes.

## Acceptance
Code complete does not mean tested. Require unit tests, AWS invocation traces, flashed-device logs, pump safety evidence, and actual device end-to-end packet trace. Defer physical pump actuation until safe qualification.
