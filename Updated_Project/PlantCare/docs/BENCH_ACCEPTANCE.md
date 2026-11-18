# Physical acceptance — not yet executed

Record date, firmware build hash, profile revision, device/boot IDs, apparatus, measured results, expected result and pass/fail for each test. Do not mark a step accepted merely because its source code exists.

## Soil and environmental sensors (Anish)

- Confirm GPIO5/GPIO6 and I2C addresses 0x44, 0x10 and 0x36 on the assembled XIAO ESP32-S3. Record relay OFF behavior before networking at GPIO2, including power-on and reset.
- Collect at least 20 dry and 20 wet/drained raw soil samples in the actual potting mix, with repeated insertion. Retain CSV including disconnected/invalid rows. Calculate endpoints and measured noise, reject overlapping/noisy calibration, select ordered dry/clear/wet thresholds and unique calibration ID.
- Verify clipped conversion, raw and percentage validity, unplug/replug of every sensor, normal 60-second cadence and demo/active 2-second cadence. Store the actual evidence before marking `evidence_approved` true.

## Pump qualification (Anish + Cristian)

- Test 1, 2, 3 and 5 second doses, three trials each, at the real supply voltage and reservoir/head height. Measure volume and variation. Choose measured dose/hard maximum; do not copy simulation values.
- Response wait is at least 6 seconds; cooldown is at least response wait; minimum moisture rise must exceed measured sensor noise. Record the response of the actual plant/pot. Confirm matching firmware/profile config IDs.
- With controlled water collection, measure independent GPIO cutoff during blocked Wi-Fi/TLS/MQTT and main-loop delays. Test invalid moisture during dose, reset/power loss before/after relay ON and OFF, NVS failure handling, reservoir/tubing faults, old/duplicate/expired commands, duration over maximum, cooldown and dry-now refusal.
- Reboot must leave relay OFF and system disarmed or faulted for an unfinished transaction. Inspected reset must not arm. Replaying a rejected command ID must never later start a pump.

## Display, dashboard and end-to-end demonstration (Camilo + Pranav)

- Use the original PlantFace GUI, preserving animations, touch and audio. Verify all six issues, details, mode banner, unknown before clock sync, source-age and arrival-age watchdogs, watering states and connection-loss indicators.
- Test in a real browser at laptop and phone widths: units, invalid values, UTC times, chart gaps, watering markers/logs, confirmations, disabled reasons, retry with the same ID, and JWT expiry.
- Trace one real telemetry identity through device publication, IoT, Lambda, DynamoDB, retained condition, display and dashboard. Measure completeness over a bounded connected run using acknowledged published IDs, not generated sequence counts. Record actual latency.
- Replay happy, each issue, 4-second versus 12-second dips, hysteresis, sustained recovery, night entry/exit, simultaneous issues, successful dose/response, no-rise fault and inspected reset.
- Apply the professor's original numbered 30-step checklist without changing its ownership/weights. That complete original numbered wording was not present in the master PDF supplied for this code audit; this document does not invent missing steps.
