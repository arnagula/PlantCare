#include <Arduino.h>
#include <Wire.h>
#include <ArduinoJson.h>
#include <Adafruit_SHT31.h>
#include <Adafruit_VEML7700.h>
#include <Adafruit_seesaw.h>

// Sensor-only prototype. No relay/pump code by design.
constexpr uint8_t SDA_PIN=5, SCL_PIN=6;
constexpr uint32_t SAMPLE_MS=60000;
Adafruit_SHT31 sht;
Adafruit_VEML7700 light;
Adafruit_seesaw soil;
bool shtOk=false,lightOk=false,soilOk=false;
uint32_t seq=0,lastMs=0;

bool ack(uint8_t a){Wire.beginTransmission(a);return Wire.endTransmission()==0;}
void detect(){
  shtOk=ack(0x44)&&sht.begin(0x44);
  lightOk=ack(0x10)&&light.begin(&Wire);
  soilOk=ack(0x36)&&soil.begin(0x36);
}
void addReading(JsonObject entry,float v,bool valid){
  entry["valid"]=valid;
  if(valid)entry["value"]=v;else entry["value"]=nullptr;
}
void sample(){
  // No fabricated UTC timestamp: firmware must obtain NTP before AWS transmission.
  if(!shtOk||!lightOk||!soilOk)detect();
  bool st=shtOk&&ack(0x44),sl=lightOk&&ack(0x10),ss=soilOk&&ack(0x36);
  float t=st?sht.readTemperature():NAN;
  float h=st?sht.readHumidity():NAN;
  float lux=sl?light.readLux():NAN;
  uint16_t raw=ss?soil.touchRead(0):0;
  bool tv=isfinite(t)&&t>=-40&&t<=85;
  bool hv=isfinite(h)&&h>=0&&h<=100;
  bool lv=isfinite(lux)&&lux>=0;
  JsonDocument doc;
  doc["seq"]=++seq;doc["uptime_ms"]=millis();
  addReading(doc["temperature_c"].to<JsonObject>(),t,tv);
  addReading(doc["humidity_pct"].to<JsonObject>(),h,hv);
  addReading(doc["light_lux"].to<JsonObject>(),lux,lv);
  JsonObject sm=doc["soil"].to<JsonObject>();
  sm["raw_valid"]=ss;if(ss)sm["raw"]=raw;else sm["raw"]=nullptr;
  sm["pct"]=nullptr;sm["valid"]=false;sm["calibrated"]=false;
  if(!st)shtOk=false;if(!sl)lightOk=false;if(!ss)soilOk=false;
  serializeJson(doc,Serial);Serial.println();
}
void setup(){Serial.begin(115200);Wire.begin(SDA_PIN,SCL_PIN);Wire.setClock(100000);delay(1200);detect();sample();lastMs=millis();}
void loop(){uint32_t now=millis();if(now-lastMs>=SAMPLE_MS){lastMs=now;sample();}}
