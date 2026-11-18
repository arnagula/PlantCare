# Integration gates & interface handoffs

**Sensor → Cloud**: inspect valid `contracts/telemetry.json`, verify 60 s cadence with UTC time, boot ID + increasing sequence; keep `soil.pct=null` until calibrated; inspect a disconnected-sensor sample with `{value:null,valid:false}`.

**Cloud → Display**: Camilo uses existing `onPlantMessage()` parser; subscribe to retained `plantcare/team3/pothos1/condition`; verify `ts,mood,state,issues,reason`; extend stale/unknown and statuses. Show distinct LIVE/SIMULATED state.

**Simulations**: use `plantcare/team3/sim/pothos1/` and separate certificates; no live watering in demo simulation. Generate realistic sequences for each condition, timer/hysteresis boundaries, stale sensor and invalid fields.

**Watering**: do not arm until calibration and pump-volume evidence; relay OFF during every reboot; no commands retained; hard cutoff on device independent of MQTT. Maintain persistent transaction identity and lockout after interrupted run. Cloud state transitions need durable conditional writes.

**Data collection**: 24 h CSV with real timestamps and raw readings; pump disabled. Use dry/wet cups same potting mix for calibration. Never claim real biological condition accuracy from synthetic threshold labels.

## Evidence to collect
- I2C scan (0x10 0x36 0x44), wiring photos and sensor fault/recovery logs
- Dry/wet raw readings (20+ each), repeated insertion, noise, calibration reference
- Relay boot-off, 1/2/3/5 s water delivery x3, measured current supply behavior
- AWS pub/sub traces, Lambda logs, retained condition, timeouts and reconnect
- AMOLED updates, dashboard history (no fabricated data), duplicate and stale-event tests
