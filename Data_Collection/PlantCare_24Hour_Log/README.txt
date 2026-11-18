PLANT CARE COMPANION — 24-HOUR SOIL / ENVIRONMENT STUDY

Files:
  PlantCare_24Hour_Log.ino   — flash to XIAO ESP32-S3
  log_24h.py                 — run on Windows laptop; saves timestamped CSV files

1. Install Arduino libraries from Library Manager:
   Adafruit SHT31 Library; Adafruit VEML7700 Library; Adafruit seesaw Library.
2. Select Seeed XIAO ESP32S3 board, select your COM port, upload the .ino.
   Keep soil probe in place at consistent depth, with the plant in its normal location.
3. Close Arduino Serial Monitor and Serial Plotter (only one program can open COM port).
4. Install Python 3 and pyserial:   py -m pip install pyserial
5. Check Arduino IDE > Tools > Port to find COM port (for example COM5).
6. In Command Prompt, from this folder:
       py log_24h.py --port COM5
   Or choose another port with --port. This logs for 24 hours by default.
7. Keep the laptop awake, with its lid open and USB/power connected. Turn off Windows
   automatic sleep for the duration. Prevent unexpected Windows restarts.
8. Midway through (for example ~12 hours), if watering is genuinely appropriate:
   - Type: water-start    and press Enter immediately BEFORE adding water.
   - Water the plant manually and measure the volume; allow excess water to drain.
   - Type: water-end 150 and press Enter immediately AFTER watering (replace 150 with
     the actual milliliters). Do not leave the plant sitting in runoff.
   - The logger records both event times and your volume in a second CSV.
   - Sampling is every 60 seconds normally and every 10 seconds during watering
     and for the first 30 minutes after watering. Subsequent samples return to 60 s.
   - To record an observation, type: note moved plant near window.
9. CSV files are saved in ./logs/ with UTC and local timestamps. The soil measurement
   is RAW, not a calibrated moisture percentage. Do not interpret it as soil water %.
10. Never use this script to automatically control a pump. For this study, watering is
    manual and should not be forced purely to meet the 12-hour mark if soil is still wet.

Expected outputs:
  *_samples.csv — sensor values, validity flags and BEFORE / DURING / AFTER phase
  *_events.csv  — WATER_START, WATER_END and annotations with timestamps

Typical combined 24-hour count: about 1,600–1,800 readings, depending on how long
watering lasts, versus about 1,440 at an uninterrupted 60-second cadence.

Data collection caveats:
  * Soil raw values are sensor-dependent; use dry/wet calibration for mapping.
  * One 24-hour run captures watering response, not a complete dry-down cycle.
  * No scientific proof of good/bad plant health is available from this log alone.
  * If laptop disconnects or loses power, files survive to last flushed sample but
    the logger must be restarted; there will be a data gap.
