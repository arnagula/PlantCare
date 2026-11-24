# Plant Care Companion — AWS implementation candidate

This revision implements the master v2.0 behavior using AWS IoT Core, FIFO SQS, Lambda, DynamoDB and an authenticated HTTP API. **AWS has not been deployed. Live calibration and watering remain unqualified. Physical acceptance and the original PlantFace GUI integration are outstanding.** This is a software candidate, not an accepted watering installation.

## Reproduce locally

Use Python 3.12, Node 18+, g++ with C++17, and a virtual environment:

```sh
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m tools.verify
python -m aws.local_invoke
python -m tools.run_demo
python -m tools.run_demo --no-rise
python -m tools.preview_dashboard   # dashboard with fake Live/Simulation data at http://localhost:8000
python -m tools.preview_dashboard --data empty   # or: down, or aws --aws-url <deployed API URL>
npm ci
npm test
cfn-lint template.yaml
```

The local commands use in-memory test storage only; production functions use DynamoDB. No SQLite path is included. Tests do not need AWS credentials. Historical tests and original code are preserved under `evidence/legacy` and the separate initial audit archive; obsolete immediate-classifier tests are not production acceptance tests.

```sh
g++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined tests_cpp/safety.cpp -o safety-test
ASAN_OPTIONS=detect_leaks=0 ./safety-test
g++ -std=c++17 -Wall -Wextra -Werror -fsanitize=address,undefined tests_cpp/display.cpp -o display-test
ASAN_OPTIONS=detect_leaks=0 ./display-test
```

## Firmware

Canonical controller: `firmware/sensor_controller/sensor_controller.ino`. Generate its configuration from **live** JSON only; do not insert simulation calibration values:

```sh
python -m tools.generate_firmware_config
# --demo selects demo timing, but still requires measured live calibration.
# Copy secrets.example.h to secrets.h and supply distinct real sensor credentials.
pio run
```

`platformio.ini` pins the board platform, Arduino framework and libraries. A template credential file is enough to compile, not to connect. Credentials are excluded from deliverable and Lambda packaging. GPIO2 is assumed active HIGH; establish actual relay OFF polarity on the bench. GPIO5/GPIO6 are I2C SDA/SCL.

The serial CSV logger remains available for the original human-readable acquisition sketch at `firmware/Plant_Care_Companion_Sensors`. The production controller instead emits `PUBLISHED` packet identities for completeness evidence. Do not mix those serial protocols.

## Documentation

- `docs/IMPLEMENTATION_REPORT.md`: initial findings, changes, executed tests, evidence and remaining gates.
- `docs/AWS_SETUP.md`: provisioning and integration sequence.
- `docs/AWS_DESIGN_AMENDMENT.md`: explicit AWS adaptations to the master.
- `docs/BENCH_ACCEPTANCE.md`: measurements and physical failure tests.
- `firmware/display/README.md`: required integration into the missing original PlantFace GUI.

## Simulation

Live and simulated messages use the same engine/coordinator. `tools.run_demo` proves a deterministic local transaction. For AWS replay, install the dev requirements, provision the distinct `team3-sim-sensor` certificate/policy, and run:

```sh
python -m tools.scenario_publisher --endpoint YOUR_ATS_ENDPOINT --ca AmazonRootCA1.pem --cert sim.crt --key sim.key --scenario dry_response --seconds 90
```

For operator testing, use the protected watering API with a JWT and explicitly specify the simulated mode. The public dashboard displays the latest live plant telemetry. `no_rise` must latch FAULT; reset requires physical-inspection confirmation and remains DISARMED. Other scenarios include all six issues, happy, invalid, four-second dip, twelve-second dip, hysteresis and multiple issues. For `day`/`night`, explicitly set simulation-only `demo_daylight` true/false in `profiles/simulated.json`, bump `profile_revision`, and use the privileged reload operation described in AWS setup. Do not globally force night for other scenarios.
