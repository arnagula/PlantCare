#include "CloudTelemetry.h"
#include <ArduinoJson.h>
#include <MQTT.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_system.h>
#include <sys/time.h>
#include "secrets.h"

namespace {
constexpr char TELEMETRY[] = "plantcare/team3/pothos1/telemetry";
constexpr char STATUS[] = "plantcare/team3/pothos1/status/sensor";
constexpr uint32_t CONNECT_BACKOFF[] = {1000, 2000, 4000, 8000, 16000, 30000};

struct Sample {
  char payload[1024];
  uint32_t capturedAt;
};

QueueHandle_t outbox = nullptr;
char bootId[24];
uint32_t sequence = 0;

bool utcTimestamp(char (&output)[25]) {
  timeval now{};
  gettimeofday(&now, nullptr);
  if (now.tv_sec < 1704067200) return false;
  tm utc{};
  gmtime_r(&now.tv_sec, &utc);
  if (!strftime(output, sizeof(output), "%Y-%m-%dT%H:%M:%S", &utc)) return false;
  snprintf(output + 19, sizeof(output) - 19, ".%03uZ", unsigned(now.tv_usec / 1000));
  return true;
}

void metric(JsonObject entry, float value, float low, float high) {
  const bool valid = isfinite(value) && value >= low && value <= high;
  entry["valid"] = valid;
  if (valid) entry["value"] = value;
  else entry["value"] = nullptr;
}

void cloudTask(void *) {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");

  WiFiClientSecure tls;
  tls.setCACert(AWS_ROOT_CA);
  tls.setCertificate(AWS_DEVICE_CERT);
  tls.setPrivateKey(AWS_PRIVATE_KEY);
  tls.setHandshakeTimeout(8);
  MQTTClient mqtt(4096);
  mqtt.begin(AWS_ENDPOINT, 8883, tls);
  mqtt.setOptions(30, true, 2000);
  JsonDocument status;
  status["schema"] = 1;
  status["mode"] = "live";
  status["client"] = "sensor";
  status["boot_id"] = bootId;
  status["status"] = "offline";
  status["ts"] = nullptr;
  String offline;
  serializeJson(status, offline);
  mqtt.setWill(STATUS, offline.c_str(), true, 1);

  size_t retry = 0;
  for (;;) {
    char timestamp[25];
    if (WiFi.status() != WL_CONNECTED || !utcTimestamp(timestamp)) {
      if (mqtt.connected()) tls.stop();
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }
    if (!mqtt.connected()) {
      tls.stop();
      if (!mqtt.connect("team3-sensor")) {
        vTaskDelay(pdMS_TO_TICKS(CONNECT_BACKOFF[retry]));
        if (retry + 1 < sizeof(CONNECT_BACKOFF) / sizeof(CONNECT_BACKOFF[0])) ++retry;
        continue;
      }
      retry = 0;
      status["status"] = "online";
      status["ts"] = timestamp;
      String payload;
      serializeJson(status, payload);
      if (!mqtt.publish(STATUS, payload, true, 1)) {
        tls.stop();
        vTaskDelay(pdMS_TO_TICKS(1000));
        continue;
      }
    }
    mqtt.loop();
    Sample sample{};
    if (xQueueReceive(outbox, &sample, pdMS_TO_TICKS(100)) == pdTRUE &&
        millis() - sample.capturedAt < 10000 &&
        !mqtt.publish(TELEMETRY, sample.payload, false, 1)) {
      tls.stop();
      vTaskDelay(pdMS_TO_TICKS(1000));
    }
  }
}
}

void startCloudTelemetry() {
  snprintf(bootId, sizeof(bootId), "boot-%08lx%08lx",
           static_cast<unsigned long>(esp_random()), static_cast<unsigned long>(esp_random()));
  outbox = xQueueCreate(1, sizeof(Sample));
  if (outbox == nullptr) {
    Serial.println("Cloud queue allocation failed");
    return;
  }
  if (xTaskCreate(cloudTask, "cloud", 12288, nullptr, 1, nullptr) != pdPASS) {
    vQueueDelete(outbox);
    outbox = nullptr;
    Serial.println("Cloud task creation failed");
  }
}

void queueTelemetry(float temperature, float humidity, float lux, uint16_t raw, bool rawValid) {
  char timestamp[25];
  if (outbox == nullptr || !utcTimestamp(timestamp)) return;

  JsonDocument packet;
  packet["schema"] = 1;
  packet["mode"] = "live";
  packet["profile"] = "demo";
  packet["device_id"] = "sensor-01";
  packet["boot_id"] = bootId;
  packet["seq"] = ++sequence;
  packet["ts"] = timestamp;
  const uint32_t capturedAt = millis();
  packet["uptime_ms"] = capturedAt;
  packet["sample_interval_s"] = 2;
  packet["config_id"] = "cfg-unqualified";
  metric(packet["temperature_c"].to<JsonObject>(), temperature, -40, 85);
  metric(packet["humidity_pct"].to<JsonObject>(), humidity, 0, 100);
  metric(packet["light_lux"].to<JsonObject>(), lux, 0, 200000);

  JsonObject soil = packet["soil"].to<JsonObject>();
  if (rawValid) soil["raw"] = raw;
  else soil["raw"] = nullptr;
  soil["raw_valid"] = rawValid;
  soil["pct"] = nullptr;
  soil["valid"] = false;
  soil["calibrated"] = false;
  soil["calibration_id"] = nullptr;

  JsonObject pump = packet["pump"].to<JsonObject>();
  pump["on"] = false;
  pump["armed"] = false;
  pump["fault"] = nullptr;
  pump["active_command_id"] = nullptr;
  pump["cooldown_remaining_s"] = 0;

  Sample sample{};
  if (measureJson(packet) < sizeof(sample.payload)) {
    sample.capturedAt = capturedAt;
    serializeJson(packet, sample.payload);
    xQueueOverwrite(outbox, &sample);
  }
}
