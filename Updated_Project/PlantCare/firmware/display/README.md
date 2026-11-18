# PlantFace integration boundary

The supplied project does not contain Camilo's original Waveshare ESP32-S3 AMOLED 1.8 V2 GUI. This bridge adds network reception and dual source/arrival-age watchdogs without replacing that GUI.

Copy `PlantFaceBridge.cpp/.h` and `../shared/DisplayState.h` and `Utc.h` into the existing project, preserving relative includes. Provide display-specific `secrets.h` with the same symbol names as the sensor example but a distinct certificate and the `team3-display` policy. Set `PLANTCARE_SIMULATED=1` only for the separate simulated display identity/certificate.

Call `beginPlantCareNetwork()` once after GUI initialization and `pollPlantCareNetwork()` from the GUI task. Implement `onPlantMessage` by extending the existing parser to all six issue codes, details, mode banner, and watering indicator; keep touch/audio/animations intact. Implement `renderPlantCareStatus` in that same GUI task. Call `endPlantCareNetwork()` before a graceful exit.

**Not accepted yet:** the original GUI integration, actual board compile, screen layout, touch/audio/animation preservation, real TLS and reconnect tests. The bridge alone cannot establish those outcomes.
