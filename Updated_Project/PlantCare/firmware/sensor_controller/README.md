# Canonical XIAO ESP32-S3 controller

Build with the root PlatformIO configuration and the `xiao` environment. Copy the example secrets file to `secrets.h` and supply sensor-specific credentials for MQTT. I2C uses GPIO5/GPIO6. The relay is active HIGH on D2/GPIO3.

Live watering runs locally using the raw STEMMA readings, a relay cutoff timer and a persistent interrupted-dose marker. Send `S` or `s` at 115200 baud to stop for the boot. Uppercase `SHUTDOWN` also disconnects MQTT after queued events have been sent.

See [Bottom-watering setup](../../docs/BOTTOM_WATERING.md) for build, flash and verification.
