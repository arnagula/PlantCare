#include <Arduino.h>
#include <Wire.h>
#include "CloudTelemetry.h"
#include <Adafruit_SHT31.h>
#include <Adafruit_VEML7700.h>
#include <Adafruit_seesaw.h>

// PLANT CARE COMPANION — XIAO ESP32-S3
// Sensor-only sketch: no AWS, relay, or pump control.
// I2C: SDA = D4/GPIO5, SCL = D5/GPIO6.

constexpr uint8_t I2C_SDA = 5;
constexpr uint8_t I2C_SCL = 6;
constexpr uint8_t SHT_ADDR = 0x44;
constexpr uint8_t LIGHT_ADDR = 0x10;
constexpr uint8_t SOIL_ADDR = 0x36;
constexpr unsigned long SAMPLE_INTERVAL_MS = 2000;

Adafruit_SHT31 sht31 = Adafruit_SHT31();
Adafruit_VEML7700 veml7700;
Adafruit_seesaw soil;

bool shtReady = false;
bool lightReady = false;
bool soilReady = false;
unsigned long lastSample = 0;

bool responds(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void scanI2C() {
  Serial.println("Scanning I2C bus...");
  for (uint8_t addr = 1; addr < 127; ++addr) {
    if (responds(addr)) {
      Serial.printf("  Found device: 0x%02X\n", addr);
    }
  }
}

void initializeSensors() {
  if (!shtReady && responds(SHT_ADDR)) {
    shtReady = sht31.begin(SHT_ADDR);
    if (shtReady) Serial.println("SHT31-D connected");
  }
  if (!lightReady && responds(LIGHT_ADDR)) {
    lightReady = veml7700.begin(&Wire);
    if (lightReady) Serial.println("VEML7700 connected");
  }
  if (!soilReady && responds(SOIL_ADDR)) {
    soilReady = soil.begin(SOIL_ADDR);
    if (soilReady) Serial.println("STEMMA soil sensor connected");
  }
}

void readAndPrint() {
  // Recheck connectivity each sample; attempt to recover disconnected sensors.
  if (shtReady && !responds(SHT_ADDR)) shtReady = false;
  if (lightReady && !responds(LIGHT_ADDR)) lightReady = false;
  if (soilReady && !responds(SOIL_ADDR)) soilReady = false;
  initializeSensors();

  float temperature = NAN;
  float humidity = NAN;
  float lux = NAN;
  uint16_t soilRaw = 0;
  bool soilValid = false;

  if (shtReady) {
    temperature = sht31.readTemperature();
    humidity = sht31.readHumidity();
    if (!isfinite(temperature) || !isfinite(humidity)) shtReady = false;
  }
  if (lightReady) {
    lux = veml7700.readLux();
    if (!isfinite(lux) || lux < 0) lightReady = false;
  }
  if (soilReady) {
    soilRaw = soil.touchRead(0);
    soilValid = responds(SOIL_ADDR);
    if (!soilValid) soilReady = false;
  }

  queueTelemetry(temperature, humidity, lux, soilRaw, soilValid);
  Serial.println("------------------------------");
  Serial.printf("Uptime: %lu ms\n", millis());
  if (isfinite(temperature)) Serial.printf("Temperature: %.2f C\n", temperature);
  else Serial.println("Temperature: INVALID / OFFLINE");
  if (isfinite(humidity)) Serial.printf("Humidity: %.2f %%\n", humidity);
  else Serial.println("Humidity: INVALID / OFFLINE");
  if (lightReady) Serial.printf("Light: %.2f lux\n", lux);
  else Serial.println("Light: INVALID / OFFLINE");
  if (soilValid) Serial.printf("Soil Moisture (raw): %u\n", soilRaw);
  else Serial.println("Soil Moisture: INVALID / OFFLINE");
}

void setup() {
  Serial.begin(115200);
  delay(1200);
  Serial.println("\nPLANT CARE COMPANION");
  Serial.println("Seeed Studio XIAO ESP32-S3 — sensor test");
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000);
  startCloudTelemetry();
  scanI2C();
  initializeSensors();
  readAndPrint();
  lastSample = millis();
}

void loop() {
  unsigned long now = millis();
  if (now - lastSample >= SAMPLE_INTERVAL_MS) {
    lastSample = now;
    readAndPrint();
  }
}
