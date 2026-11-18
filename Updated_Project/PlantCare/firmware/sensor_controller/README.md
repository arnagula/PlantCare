# Canonical XIAO ESP32-S3 controller

Build from the repository root using `platformio.ini`; the current canonical sketch is `sensor_controller.ino`. `Config.h` is generated from `profiles/live.json` and remains unqualified by default. Do not manually substitute simulation numbers.

I2C SDA GPIO5, SCL GPIO6; SHT31 0x44, VEML7700 0x10, STEMMA soil 0x36. Relay GPIO2 assumes active HIGH; verify actual OFF polarity before connecting the pump. The main task owns control/sensors. A dedicated network task owns TLS/MQTT. `esp_timer` turns the GPIO off independently of either task's network activity. The NVS transaction/configuration marker and the last-16-ID ring provide recovery/deduplication safeguards.

Copy `secrets.example.h` to `secrets.h` with the sensor-specific certificate/private key; never commit it. Sync time before MQTT; status LWT uses null time, while receipts are recorded by the backend. The event queue retries the same JSON until QoS-1 acknowledgement. Telemetry uses a one-slot no-backfill queue. `PUBLISHED` serial lines contain acknowledged packet identities for completeness evidence. Type `SHUTDOWN` followed by newline while idle to disarm locally and publish offline before disconnecting.

Build success is not physical acceptance. Complete `docs/BENCH_ACCEPTANCE.md`, including blocked networking, sensor failure, NVS/power interruption and actual cutoff timing.
