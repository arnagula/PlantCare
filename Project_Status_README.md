# Plant Care Companion

ECE/CSC 571 · Team 3 · Golden pothos

Plant Care Companion monitors soil moisture, temperature, humidity, and light. The XIAO ESP32-S3 publishes readings over MQTT/TLS to AWS IoT Core. The cloud evaluates plant conditions, stores readings in DynamoDB, and publishes a condition report for the PlantFace AMOLED. The updated team code also provides a web dashboard and supports relay-controlled watering once the live soil and pump settings are qualified.

## What we’ve done

| Area | Implemented or verified | Remaining |
| --- | --- | --- |
| Sensors and logging | Read all three sensors on the XIAO and observed values in Serial Monitor. Added a CSV logger for the acquisition sketch with UTC timestamps and validity flags. | Complete and save the 24-hour log and dry/wet calibration runs. |
| AWS prototype | Built and deployed the SAM stack `plantcare-team3` in `us-east-1`. Verified IoT Core → Lambda → DynamoDB and a matching MQTT condition reply for simulated sample 47. | Connect the real XIAO and verify its telemetry end to end. |
| Prototype classifier | Verified uncalibrated (47–48), thirsty (49), happy (50), and multiple issues (51–52) in AWS simulation. Sample 52 used a fresh UTC timestamp. | The prototype’s separate freshness patch passed 10 local tests. AWS deployment of that patch was not confirmed. |
| Updated AWS backend | Team code adds separate live and simulation FIFO queues, persistent alert state, duplicate and out-of-order handling, stale-data detection, and retryable publication. | Deploy and verify this revision in AWS, including IAM permissions and retained reports. |
| Dashboard and AMOLED | Team code adds an authenticated API and dashboard for current conditions, history, and watering controls. The PlantFace bridge compiled in a harness. | Test the dashboard against AWS and integrate the bridge into the original PlantFace GUI. |
| Watering | Team code adds command validation, arming, cooldown, fault handling, and a device-side cutoff. Local simulation covered both successful watering and a no-rise fault. | Measure pump flow and relay behavior. Verify shutoff, fault behavior, and moisture response on the physical setup before arming live watering. |

## Hardware

| Component | Role |
| --- | --- |
| Seeed Studio XIAO ESP32-S3 | Sensor acquisition, Wi-Fi/MQTT, and local pump safeguards |
| Adafruit STEMMA capacitive soil sensor | Raw soil moisture over I²C |
| Sensirion SHT31-D | Temperature and relative humidity over I²C |
| VEML7700 | Illuminance in lux over I²C |
| Waveshare ESP32-S3 AMOLED | PlantFace display |
| Relay, 3–6 V submersible pump, tubing, and separate motor supply | Controlled water delivery |

The sensor bus uses SDA D4/GPIO5 and SCL D5/GPIO6 at 100 kHz. The updated controller assigns the relay to D1/GPIO2 and assumes active-high operation. Confirm the actual relay’s OFF level during bench testing.

## Classification and watering

The live implementation uses calibrated thresholds with persistence and hysteresis. An issue must persist before activation and clear past a separate recovery threshold. The engine can report several issues at once. It covers thirsty, too wet, low light, too cold, too hot, and low humidity. The watering coordinator also checks freshness, arming, cooldown, and device status. The XIAO independently validates a command before energizing the relay.

We prototyped a scikit-learn decision tree in the original AWS simulation path. It learned from synthetic examples labeled by thresholds. The cloud tests demonstrated the prediction path. Real plant accuracy remains unmeasured. The updated team implementation archives the tree and runs threshold rules in both modes. Use the tree as an optional comparison if the course requires an ML demonstration.

## Collect and use the calibration data

1. Use the acquisition sketch at `firmware/Plant_Care_Companion_Sensors/Plant_Care_Companion_Sensors.ino`. Close Arduino Serial Monitor before running the logger.
2. Prepare two cups of the same potting mix. Keep one dry. Wet the other thoroughly and let excess water drain. Use the same probe depth and collect at least 20 valid readings per endpoint across repeated insertions.
3. Move the probe to the pothos and leave it in one spot for the 24-hour log. Record the time of any watering. Keep the laptop awake and the logger running.
4. Use the median dry and wet readings as 0% and 100% on the relative moisture scale. Plot the calibrated log and check that moisture rises after watering if a watering event was captured. Choose the watering threshold separately from the 0% endpoint.

Run from the updated project folder in PowerShell. Replace `COM5` with the board’s port. Each 0.1-hour capture runs for about six minutes.

```powershell
py -m pip install pyserial
py tools/log_sensors.py COM5 dry.csv --phase dry --hours 0.1
py tools/log_sensors.py COM5 wet.csv --phase wet --hours 0.1
py tools/log_sensors.py COM5 baseline.csv
```

The production controller uses a different serial output format. Use the acquisition sketch for these CSV commands.

## AWS and local verification

Live telemetry uses `plantcare/team3/pothos1/telemetry` and live reports use `plantcare/team3/pothos1/condition`. Simulation uses `plantcare/team3/sim/pothos1/` with the same suffixes. Match a condition report’s `source.boot_id` and `source.seq` to the input when verifying a publish. The prototype’s successful uncalibrated test returned `unknown` and still stored the reading. The thirsty and low-light tests used simulated readings, and the pump stayed disarmed.

Run these commands from the updated code folder with Python 3.12 and the listed development dependencies.

```powershell
py -3.12 -m pip install -r requirements-dev.txt
py -3.12 -m tools.verify
py -3.12 -m tools.run_demo
py -3.12 -m tools.run_demo --no-rise
```

The team’s report records 204 Python passes, 10 dashboard DOM passes, successful template lint, and successful PlatformIO builds for the sensor controller and the display bridge harness. These results are local software evidence. Physical operation, real-browser rendering, and the updated AWS stack still need verification.

For deployment, use `docs/AWS_SETUP.md` in the updated ZIP. Configure the JWT issuer and audience, device certificates, and topic-scoped policies. Review the generated policies for `iot:RetainPublish` on retained messages, a permission missing from the reviewed template that caused a publish failure in the prototype. Test on a separate stack with isolated MQTT topics before replacing the verified prototype. Keep Wi-Fi credentials and private keys outside the shared project files.

## Live demonstration

Show the pothos’s current condition and readings. If it is already watered, use a separate dry test pot with the same mix and explain the switch. Place the probe and outlet in that pot, show the dry reading, and demonstrate one measured dose, pump shutoff, and the moisture response. Save a second dry pot or fresh mix for repeat runs. Use the simulated watering path until the physical relay and pump pass bench acceptance.

## Project files

- [PlantCare_Updated_Code.zip](https://chatgpt.com/library?file_id=libfile_ad94b179df648191b9b0873a7f190aef&account_id=personal) — updated team implementation, setup, simulations, and bench checklist
- [PlantCare_Implementation_and_Test_Report.pdf](https://chatgpt.com/library?file_id=libfile_6f40a802e66081918529202f1c6acc08&account_id=personal) — implementation details and test evidence
- [PlantCare_Team3_Freshness.zip](https://chatgpt.com/library?file_id=libfile_e923e0e517c48191a321f7aed7e14271&account_id=personal) — AWS prototype with the locally tested freshness patch
