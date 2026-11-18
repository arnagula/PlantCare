#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <MQTT.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <Adafruit_SHT31.h>
#include <Adafruit_VEML7700.h>
#include <Adafruit_seesaw.h>
#include <esp_timer.h>
#include <atomic>
#include "../shared/SafetyCore.h"
#include "../shared/Utc.h"
#include "Config.h"
#include "secrets.h"
using namespace plantcare;
constexpr int RELAY=2; // Active HIGH. Bench-confirm polarity before attaching the pump.
const char* prefix="plantcare/team3/pothos1/";
char bootId[32];uint32_t seq=0,eventSeq=0;
struct Message{char topic[100];char body[4097];uint64_t created;};
QueueHandle_t telemetryQueue,events,commands;Preferences preferences;esp_timer_handle_t cutoff;
std::atomic<bool> stopped{false},shutdownRequested{false};
portMUX_TYPE timerMux=portMUX_INITIALIZER_UNLOCKED;uint64_t stoppedAt=0;
uint64_t mono(){return esp_timer_get_time()/1000;}
int64_t wall(){struct timeval v;gettimeofday(&v,nullptr);return int64_t(v.tv_sec)*1000+v.tv_usec/1000;}
String stamp(int64_t ms){time_t seconds=ms/1000;tm utc;gmtime_r(&seconds,&utc);char out[25];strftime(out,20,"%Y-%m-%dT%H:%M:%S",&utc);snprintf(out+19,6,".%03uZ",unsigned(ms%1000));return String(out);}
void timerOff(void*){digitalWrite(RELAY,LOW);portENTER_CRITICAL(&timerMux);stoppedAt=mono();portEXIT_CRITICAL(&timerMux);stopped=true;}
struct Device:Hardware{
 bool save(const Marker&m)override{JsonDocument j;j["active"]=m.active;j["known"]=m.known;j["id"]=m.id;j["issued"]=m.issued;String out;serializeJson(j,out);return preferences.putString("transaction",out)==out.length();}
 bool start(uint32_t duration)override{stopped=false;digitalWrite(RELAY,HIGH);if(esp_timer_start_once(cutoff,uint64_t(duration)*1000)!=ESP_OK){digitalWrite(RELAY,LOW);return false;}return true;}
 void stop()override{digitalWrite(RELAY,LOW);if(cutoff)esp_timer_stop(cutoff);}
} hardware;
SafetyCore* safety=nullptr;String activeId;int64_t startedUtc=0;uint64_t fastUntil=0,lastSample=0;
Adafruit_SHT31 sht;Adafruit_VEML7700 light;Adafruit_seesaw soil;
bool shtReady=false,lightReady=false,soilReady=false,soilValid=false;double pct=NAN;uint16_t raw=0;float temp=NAN,rh=NAN,lux=NAN;
bool responds(uint8_t address){Wire.beginTransmission(address);return Wire.endTransmission()==0;}
void readSensors(){
 if(!responds(0x44))shtReady=false;if(!responds(0x10))lightReady=false;if(!responds(0x36))soilReady=false;
 if(!shtReady&&responds(0x44))shtReady=sht.begin(0x44);if(!lightReady&&responds(0x10))lightReady=light.begin(&Wire);if(!soilReady&&responds(0x36))soilReady=soil.begin(0x36);
 temp=shtReady?sht.readTemperature():NAN;rh=shtReady?sht.readHumidity():NAN;lux=lightReady?light.readLux():NAN;
 soilValid=soilReady;if(soilValid){raw=soil.touchRead(0);soilValid=responds(0x36);}
 pct=soilValid&&settings::calibrated?std::max(0.0,std::min(100.0,100.0*(raw-settings::rawDry)/(settings::rawWet-settings::rawDry))):NAN;
}
void metric(JsonObject o,float v,float lo,float hi){bool valid=isfinite(v)&&v>=lo&&v<=hi;o["valid"]=valid;if(valid)o["value"]=v;else o["value"]=nullptr;}
void enqueueEvent(const Event&e){
 if(e.status.empty()||e.status=="duplicate")return;
 JsonDocument j;j["schema"]=1;j["mode"]="live";j["device_id"]="sensor-01";j["boot_id"]=bootId;j["event_seq"]=++eventSeq;j["command_id"]=e.id;j["action"]=e.action;j["status"]=e.status;j["ts"]=stamp(wall());j["pump_on"]=safety->on;
 if(e.reason.empty())j["reason_code"]=nullptr;else j["reason_code"]=e.reason;
 if(e.status=="started"){startedUtc=wall();j["started_at"]=stamp(startedUtc);j["baseline_soil_pct"]=e.baseline;fastUntil=mono()+settings::responseMs+10000;}
 if(e.status=="completed"||e.status=="aborted"){j["started_at"]=stamp(startedUtc);j["ended_at"]=stamp(startedUtc+e.duration);j["actual_duration_ms"]=e.duration;j["baseline_soil_pct"]=e.baseline;fastUntil=mono()+settings::responseMs+10000;}
 Message m{};snprintf(m.topic,sizeof(m.topic),"%s%s/event",prefix,e.action=="water"?"watering":"control");serializeJson(j,m.body,sizeof(m.body));m.created=mono();
 if(xQueueSend(events,&m,0)!=pdTRUE){safety->fault=true;safety->armed=false;Serial.println("EVENT_QUEUE_FULL: local lockout");}
}
void sample(){
 readSensors();if(wall()<1704067200000LL)return;
 JsonDocument j;j["schema"]=1;j["mode"]="live";j["profile"]=settings::profile;j["device_id"]="sensor-01";j["boot_id"]=bootId;j["seq"]=++seq;j["ts"]=stamp(wall());j["uptime_ms"]=mono();j["sample_interval_s"]=(safety->on||mono()<fastUntil)?2:settings::sampleMs/1000;j["config_id"]=settings::config().id;
 metric(j["temperature_c"].to<JsonObject>(),temp,-40,85);metric(j["humidity_pct"].to<JsonObject>(),rh,0,100);metric(j["light_lux"].to<JsonObject>(),lux,0,200000);
 auto s=j["soil"].to<JsonObject>();if(soilValid)s["raw"]=raw;else s["raw"]=nullptr;s["raw_valid"]=soilValid;s["calibrated"]=settings::calibrated;s["valid"]=isfinite(pct);if(isfinite(pct))s["pct"]=pct;else s["pct"]=nullptr;if(settings::calibrated)s["calibration_id"]=settings::calibrationId;else s["calibration_id"]=nullptr;
 auto p=j["pump"].to<JsonObject>();p["on"]=safety->on;p["armed"]=safety->armed;if(safety->fault)p["fault"]="local_fault";else p["fault"]=nullptr;p["active_command_id"]=safety->on?activeId:String();if(!safety->on)p["active_command_id"]=nullptr;p["cooldown_remaining_s"]=safety->cooldown(mono())/1000.0;
 Message m{};snprintf(m.topic,sizeof(m.topic),"%stelemetry",prefix);serializeJson(j,m.body,sizeof(m.body));m.created=mono();xQueueOverwrite(telemetryQueue,&m);
}
bool id(JsonVariantConst v){return v.is<const char*>()&&strlen(v.as<const char*>())>0&&strlen(v.as<const char*>())<=64;}
void commandMessage(const Message&m){
 JsonDocument j;if(deserializeJson(j,m.body))return;
 Command c;c.id=j["command_id"]|"";c.action=j["action"]|"";c.mode=j["mode"]|"";c.boot=j["target_boot_id"]|"";c.config=j["config_id"]|"";c.issued=parseUtc(j["issued_at"]|"");c.expires=parseUtc(j["expires_at"]|"");c.duration=j["duration_ms"]|0;c.inspected=j["inspected"].is<bool>()&&j["inspected"].as<bool>();
 bool valid=j["schema"].is<int>()&&!j["schema"].is<bool>()&&j["schema"].as<int>()==1&&id(j["command_id"])&&id(j["target_boot_id"])&&id(j["config_id"])&&c.issued>=0&&c.expires>=0;
 if(c.action=="water")valid=valid&&j["duration_ms"].is<uint32_t>()&&(String(j["reason"]|"")=="manual"||String(j["reason"]|"")=="automatic");else valid=valid&&j["duration_ms"].isNull()&&(c.action=="arm"||c.action=="disarm"||c.action=="reset_fault");
 if(!valid||shutdownRequested){if(!c.id.empty())enqueueEvent(safety->reject(c,"malformed"));return;}
 readSensors();auto e=safety->accept(c,wall(),mono(),wall()>1704067200000LL,isfinite(pct),pct);if(e.status=="started")activeId=c.id.c_str();enqueueEvent(e);
}
void network(void*){
 WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);configTime(0,0,"pool.ntp.org","time.nist.gov");
 WiFiClientSecure tls;tls.setCACert(AWS_ROOT_CA);tls.setCertificate(AWS_DEVICE_CERT);tls.setPrivateKey(AWS_PRIVATE_KEY);tls.setHandshakeTimeout(8);MQTTClient mqtt(4608);mqtt.begin(AWS_ENDPOINT,8883,tls);mqtt.setOptions(30,true,2000);
 mqtt.onMessage(+[](String &topic,String &body){if(body.length()>4096)return;Message m{};topic.toCharArray(m.topic,sizeof(m.topic));body.toCharArray(m.body,sizeof(m.body));m.created=mono();if(xQueueSend(commands,&m,0)!=pdTRUE)Serial.println("COMMAND_QUEUE_FULL");});
 JsonDocument status;status["schema"]=1;status["mode"]="live";status["client"]="sensor";status["boot_id"]=bootId;status["status"]="offline";status["ts"]=nullptr;String will;serializeJson(status,will);String topic=String(prefix)+"status/sensor";mqtt.setWill(topic.c_str(),will.c_str(),true,1);
 const int backoff[]={1,2,4,8,16,30};unsigned retry=0;
 for(;;){
  if(WiFi.status()!=WL_CONNECTED||wall()<1704067200000LL){tls.stop();vTaskDelay(pdMS_TO_TICKS(500));continue;}
  if(!mqtt.connected()){tls.stop();if(!mqtt.connect("team3-sensor")){vTaskDelay(pdMS_TO_TICKS(backoff[retry]*1000));if(retry<5)retry++;continue;}retry=0;mqtt.subscribe((String(prefix)+"watering/command").c_str(),1);mqtt.subscribe((String(prefix)+"control/command").c_str(),1);status["status"]="online";status["ts"]=stamp(wall());String out;serializeJson(status,out);mqtt.publish(topic,out,true,1);}
  mqtt.loop();Message m{};
  if(xQueuePeek(events,&m,0)==pdTRUE){if(mqtt.publish(m.topic,m.body,false,1))xQueueReceive(events,&m,0);else tls.stop();}
  if(xQueueReceive(telemetryQueue,&m,0)==pdTRUE&&mono()-m.created<10000){if(mqtt.publish(m.topic,m.body,false,1))Serial.printf("PUBLISHED %s\n",m.body);else tls.stop();}
  if(shutdownRequested&&uxQueueMessagesWaiting(events)==0){status["status"]="offline";status["ts"]=stamp(wall());String out;serializeJson(status,out);if(mqtt.publish(topic,out,true,1)){mqtt.disconnect();vTaskDelete(nullptr);}}
  vTaskDelay(pdMS_TO_TICKS(20));
 }
}
void setup(){
 pinMode(RELAY,OUTPUT);digitalWrite(RELAY,LOW);Serial.begin(115200);bool nvsReady=preferences.begin("plantcare",false);
 JsonDocument configuration;configuration["config_id"]=settings::config().id;configuration["calibrated"]=settings::calibrated;configuration["calibration_id"]=settings::calibrationId;configuration["raw_dry"]=settings::rawDry;configuration["raw_wet"]=settings::rawWet;String savedConfig;serializeJson(configuration,savedConfig);bool configSaved=nvsReady&&preferences.putString("configuration",savedConfig)==savedConfig.length();
 snprintf(bootId,sizeof(bootId),"boot-%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
 esp_timer_create_args_t args{};args.callback=timerOff;args.name="pump-cutoff";if(esp_timer_create(&args,&cutoff)!=ESP_OK){Serial.println("Timer initialization failed");while(true)delay(1000);}
 JsonDocument saved;String markerText=preferences.getString("transaction","");bool corrupt=markerText.length()&&deserializeJson(saved,markerText);Marker marker{!configSaved||corrupt||bool(saved["active"]|false),bool(saved["known"]|false),saved["id"]|"",saved["issued"]|int64_t(0)};
 safety=new SafetyCore(hardware,settings::config(),bootId,marker,mono());telemetryQueue=xQueueCreate(1,sizeof(Message));events=xQueueCreate(32,sizeof(Message));commands=xQueueCreate(8,sizeof(Message));
 if(!telemetryQueue||!events||!commands){Serial.println("Queue allocation failed");while(true)delay(1000);}
 Wire.begin(5,6);Wire.setClock(100000);Wire.setTimeOut(50);xTaskCreate(network,"mqtt",16384,nullptr,1,nullptr);sample();lastSample=mono();
}
void loop(){
 uint64_t now=mono();if(Serial.available()&&Serial.readStringUntil('\n')=="SHUTDOWN"&&!safety->on){safety->armed=false;shutdownRequested=true;}
 if(safety->on){readSensors();bool didStop=stopped.exchange(false);portENTER_CRITICAL(&timerMux);uint64_t physical=stoppedAt;portEXIT_CRITICAL(&timerMux);enqueueEvent(safety->tick(now,isfinite(pct),didStop,physical));}
 Message m{};if(xQueueReceive(commands,&m,0)==pdTRUE)commandMessage(m);
 uint64_t interval=(safety->on||now<fastUntil)?2000:settings::sampleMs;if(now-lastSample>=interval){lastSample=now;sample();}delay(10);
}
