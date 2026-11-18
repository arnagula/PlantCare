/*
  Plant Care Companion — 24-hour sensor study
  Board: Seeed Studio XIAO ESP32-S3
  I2C: SDA = GPIO5 (D4), SCL = GPIO6 (D5)
  Libraries: Adafruit SHT31, Adafruit VEML7700, Adafruit seesaw

  Power the board over USB and keep a PC connected to log the serial output.
  NO PUMP CONTROL: Water the plant manually.

  PC serial commands (case-insensitive):
    WSTART  -> mark beginning of manual watering (10-second sample cadence)
    WEND    -> mark end of manual watering (10-second cadence for 30 minutes)
    MARK    -> mark an observation

  Data is CSV on serial as:
    DATA,uptime_ms,seq,phase,temperature_c,humidity_pct,light_lux,soil_raw,
         temperature_valid,humidity_valid,light_valid,soil_valid
  Missing measurements are empty cells, not zeros.
  Additional lines start with # or EVENT, and are not data samples.
*/

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_SHT31.h>
#include <Adafruit_VEML7700.h>
#include <Adafruit_seesaw.h>
#include <math.h>

constexpr uint8_t SDA_PIN = 5;
constexpr uint8_t SCL_PIN = 6;
constexpr uint8_t SHT_ADDR = 0x44;
constexpr uint8_t VEML_ADDR = 0x10;
constexpr uint8_t SOIL_ADDR = 0x36;
constexpr uint32_t NORMAL_INTERVAL_MS = 60000UL;
constexpr uint32_t WATER_INTERVAL_MS = 10000UL;
constexpr uint32_t POST_WATER_WINDOW_MS = 30UL * 60UL * 1000UL;

Adafruit_SHT31 sht;
Adafruit_VEML7700 light;
Adafruit_seesaw soil;
bool shtReady = false, lightReady = false, soilReady = false;
uint32_t lastSampleMs = 0;
uint32_t postWaterStartMs = 0;
uint32_t seq = 0;
uint32_t lastProbeMs = 0;
uint32_t lastWaterEndMs = 0;
bool duringWater = false;
bool postWater = false;
String commandBuffer;

enum Phase { BEFORE, DURING, AFTER };

bool responds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void initMissingSensors() {
  if (!shtReady && responds(SHT_ADDR)) shtReady = sht.begin(SHT_ADDR);
  if (!lightReady && responds(VEML_ADDR)) lightReady = light.begin(&Wire);
  if (!soilReady && responds(SOIL_ADDR)) soilReady = soil.begin(SOIL_ADDR);
}

void checkAndReconnect() {
  if (shtReady && !responds(SHT_ADDR)) shtReady = false;
  if (lightReady && !responds(VEML_ADDR)) lightReady = false;
  if (soilReady && !responds(SOIL_ADDR)) soilReady = false;
  initMissingSensors();
}

const char* phaseName() {
  return duringWater ? "DURING" : (postWater ? "AFTER" : "BEFORE");
}

void printFloatField(float number, bool valid, uint8_t precision) {
  if (valid) Serial.print(number, precision);
}

void sample() {
  checkAndReconnect();
  float temp = NAN, humidity = NAN, lux = NAN;
  uint16_t raw = 0;
  bool tValid = false, hValid = false, lValid = false, sValid = false;

  if (shtReady) {
    temp = sht.readTemperature();
    humidity = sht.readHumidity();
    tValid = isfinite(temp) && temp > -40.0f && temp < 125.0f;
    hValid = isfinite(humidity) && humidity >= 0.0f && humidity <= 100.0f;
    if (!tValid || !hValid) shtReady = false;
  }
  if (lightReady) {
    lux = light.readLux();
    lValid = isfinite(lux) && lux >= 0.0f;
    if (!lValid) lightReady = false;
  }
  if (soilReady) {
    raw = soil.touchRead(0);
    sValid = (raw != 65535U) && responds(SOIL_ADDR);
    if (!sValid) soilReady = false;
  }

  Serial.print("DATA,");
  Serial.print(millis()); Serial.print(',');
  Serial.print(++seq); Serial.print(',');
  Serial.print(phaseName()); Serial.print(',');
  printFloatField(temp, tValid, 2); Serial.print(',');
  printFloatField(humidity, hValid, 2); Serial.print(',');
  printFloatField(lux, lValid, 2); Serial.print(',');
  if (sValid) Serial.print(raw);
  Serial.print(','); Serial.print(tValid ? 1 : 0);
  Serial.print(','); Serial.print(hValid ? 1 : 0);
  Serial.print(','); Serial.print(lValid ? 1 : 0);
  Serial.print(','); Serial.println(sValid ? 1 : 0);
}

void handleCommand(String cmd) {
  cmd.trim(); cmd.toUpperCase();
  if (cmd == "WSTART") {
    if (duringWater) { Serial.println("# Watering already marked as started"); return; }
    duringWater = true;
    postWater = false;
    Serial.print("EVENT,WATER_START,"); Serial.println(millis());
    sample();
    lastSampleMs = millis();
  } else if (cmd == "WEND") {
    if (!duringWater) { Serial.println("# WSTART required before WEND"); return; }
    duringWater = false;
    postWater = true;
    lastWaterEndMs = millis();
    postWaterStartMs = lastWaterEndMs;
    Serial.print("EVENT,WATER_END,"); Serial.println(lastWaterEndMs);
    sample();
    lastSampleMs = millis();
  } else if (cmd == "MARK") {
    Serial.print("EVENT,MARK,"); Serial.println(millis());
    sample();
    lastSampleMs = millis();
  } else if (cmd.length() > 0) {
    Serial.println("# Unknown command (use WSTART, WEND or MARK)");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  initMissingSensors();
  Serial.println("# PLANT CARE COMPANION 24-HOUR STUDY");
  Serial.println("# Start the PC CSV logger; time stamps are applied on the PC.");
  Serial.println("# Normal sampling: 60s; during watering and first 30min after: 10s.");
  sample();
  lastSampleMs = millis();
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (commandBuffer.length() > 0) {
        handleCommand(commandBuffer);
        commandBuffer = "";
      }
    } else if (commandBuffer.length() < 32) {
      commandBuffer += c;
    }
  }

  uint32_t now = millis();
  if (postWater && (uint32_t)(now - postWaterStartMs) >= POST_WATER_WINDOW_MS) {
    postWater = false;
    Serial.print("EVENT,POST_WATER_WINDOW_END,"); Serial.println(now);
  }
  uint32_t interval = (duringWater || postWater) ? WATER_INTERVAL_MS : NORMAL_INTERVAL_MS;
  if ((uint32_t)(now - lastSampleMs) >= interval) {
    lastSampleMs = now;
    sample();
  }
  delay(10);
}
