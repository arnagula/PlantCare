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
#include "../shared/BottomWatering.h"
#include "Config.h"
#include "secrets.h"
using namespace plantcare;
constexpr int RELAY=3; // XIAO D2, active HIGH.
const char* prefix="plantcare/team3/pothos1/";
char bootId[32];uint32_t seq=0,eventSeq=0;
uint64_t relayStarted=0;
struct Message{char topic[100];char body[4097];uint64_t created;};
QueueHandle_t telemetryQueue,events;Preferences preferences;esp_timer_handle_t cutoff;
std::atomic<bool> stopped{false},shutdownRequested{false};
portMUX_TYPE timerMux=portMUX_INITIALIZER_UNLOCKED;uint64_t stoppedAt=0;
uint64_t mono(){return esp_timer_get_time()/1000;}
int64_t wall(){struct timeval v;gettimeofday(&v,nullptr);return int64_t(v.tv_sec)*1000+v.tv_usec/1000;}
String stamp(int64_t ms){time_t seconds=ms/1000;tm utc;gmtime_r(&seconds,&utc);char out[25];strftime(out,20,"%Y-%m-%dT%H:%M:%S",&utc);snprintf(out+19,6,".%03uZ",unsigned(ms%1000));return String(out);}
void timerOff(void*){digitalWrite(RELAY,LOW);portENTER_CRITICAL(&timerMux);stoppedAt=mono();portEXIT_CRITICAL(&timerMux);stopped=true;}
struct Device:Hardware{
 bool save(const Marker&m)override{JsonDocument j;j["active"]=m.active;j["known"]=m.known;j["id"]=m.id;j["issued"]=m.issued;String out;serializeJson(j,out);return preferences.putString("transaction",out)==out.length();}
 bool start(uint32_t duration)override{stopped=false;digitalWrite(RELAY,HIGH);relayStarted=mono();if(esp_timer_start_once(cutoff,uint64_t(duration)*1000)!=ESP_OK){digitalWrite(RELAY,LOW);return false;}return true;}
 void stop()override{digitalWrite(RELAY,LOW);if(cutoff)esp_timer_stop(cutoff);}
} hardware;
BottomWatering* watering=nullptr;
uint64_t lastSoil=0,lastSample=0,observeUntil=0;
constexpr uint32_t observationMs=600000;
bool publishSoon=true;
Adafruit_SHT31 sht;Adafruit_VEML7700 light;Adafruit_seesaw soil;
bool shtReady=false,lightReady=false,soilReady=false,soilValid=false;double pct=NAN;uint16_t raw=0;float temp=NAN,rh=NAN,lux=NAN;
bool responds(uint8_t address){Wire.beginTransmission(address);return Wire.endTransmission()==0;}
void readEnvironment(){
 if(!responds(0x44))shtReady=false;if(!responds(0x10))lightReady=false;
 if(!shtReady&&responds(0x44))shtReady=sht.begin(0x44);if(!lightReady&&responds(0x10))lightReady=light.begin(&Wire);
 temp=shtReady?sht.readTemperature():NAN;rh=shtReady?sht.readHumidity():NAN;lux=lightReady?light.readLux():NAN;
}
void readSoil(){
 if(!soilReady)soilReady=responds(0x36)&&soil.begin(0x36);
 raw=soilReady?soil.touchRead(0):0;
 soilValid=soilReady&&BottomWatering::valid(raw)&&responds(0x36);
 if(!soilValid)soilReady=false;
 pct=soilValid&&settings::calibrated?std::max(0.0,std::min(100.0,100.0*(raw-settings::rawDry)/(settings::rawWet-settings::rawDry))):NAN;
}
void metric(JsonObject o,float v,float lo,float hi){bool valid=isfinite(v)&&v>=lo&&v<=hi;o["valid"]=valid;if(valid)o["value"]=v;else o["value"]=nullptr;}
void enqueueEvent(const Event&e){
 if(e.status.empty())return;
 publishSoon=true;
 if(e.status=="completed")observeUntil=mono()+observationMs;
 uint64_t transition=mono();
 if(e.status=="started")transition=relayStarted;
 if(e.status=="completed"){
  portENTER_CRITICAL(&timerMux);
  if(stoppedAt>=relayStarted)transition=stoppedAt;
  portEXIT_CRITICAL(&timerMux);
 }
 uint32_t duration=e.reason=="start_failed"||transition<relayStarted?0:transition-relayStarted;
 Serial.printf("WATERING %s %s duration_ms=%u\n",e.status.c_str(),e.reason.c_str(),unsigned(e.status=="started"?0:duration));
 JsonDocument j;
 j["schema"]=1;j["mode"]="live";j["device_id"]="sensor-01";j["boot_id"]=bootId;
 j["event_seq"]=++eventSeq;j["command_id"]=e.id;j["action"]="water";j["source"]="device";
 j["status"]=e.status;j["pump_on"]=watering->on();
 if(e.reason.empty())j["reason_code"]=nullptr;else j["reason_code"]=e.reason;
 if(e.status!="started")j["actual_duration_ms"]=duration;
 if(soilValid)j["soil_raw"]=raw;else j["soil_raw"]=nullptr;
 static Message m{};
 snprintf(m.topic,sizeof(m.topic),"%swatering/event",prefix);
 serializeJson(j,m.body,sizeof(m.body));m.created=transition;
 if(xQueueSend(events,&m,0)!=pdTRUE){
  watering->stop(mono());
  Serial.println("EVENT_QUEUE_FULL: local lockout");
 }
}
void sample(){
 readEnvironment();
 JsonDocument environment;
 metric(environment["temperature_c"].to<JsonObject>(),temp,-40,85);
 metric(environment["humidity_pct"].to<JsonObject>(),rh,0,100);
 metric(environment["light_lux"].to<JsonObject>(),lux,0,200000);
 Serial.print("ENV ");
 serializeJson(environment,Serial);
 Serial.println();
 if(wall()<1704067200000LL)return;
 JsonDocument j;j["schema"]=1;j["mode"]="live";j["profile"]=settings::profile;j["device_id"]="sensor-01";j["boot_id"]=bootId;j["seq"]=++seq;j["ts"]=stamp(wall());j["uptime_ms"]=mono();j["sample_interval_s"]=mono()<observeUntil?10:settings::sampleMs/1000;j["config_id"]=settings::config().id;
 metric(j["temperature_c"].to<JsonObject>(),temp,-40,85);metric(j["humidity_pct"].to<JsonObject>(),rh,0,100);metric(j["light_lux"].to<JsonObject>(),lux,0,200000);
 auto s=j["soil"].to<JsonObject>();if(soilValid)s["raw"]=raw;else s["raw"]=nullptr;s["raw_valid"]=soilValid;s["calibrated"]=settings::calibrated;s["valid"]=isfinite(pct);if(isfinite(pct))s["pct"]=pct;else s["pct"]=nullptr;if(settings::calibrated)s["calibration_id"]=settings::calibrationId;else s["calibration_id"]=nullptr;
 auto p=j["pump"].to<JsonObject>();
 p["on"]=watering->on();p["armed"]=watering->state()=="monitoring";
 p["local_stage"]=watering->state();
 if(watering->state()=="fault")p["fault"]="local_fault";else p["fault"]=nullptr;
 if(watering->on())p["active_command_id"]=watering->id();else p["active_command_id"]=nullptr;
 p["cooldown_remaining_s"]=0;
 static Message m{};snprintf(m.topic,sizeof(m.topic),"%stelemetry",prefix);serializeJson(j,m.body,sizeof(m.body));m.created=mono();xQueueOverwrite(telemetryQueue,&m);
}
void network(void*){
 WiFi.mode(WIFI_STA);WiFi.setAutoReconnect(true);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);configTime(0,0,"pool.ntp.org","time.nist.gov");
 WiFiClientSecure tls;tls.setCACert(AWS_ROOT_CA);tls.setCertificate(AWS_DEVICE_CERT);tls.setPrivateKey(AWS_PRIVATE_KEY);tls.setHandshakeTimeout(8);MQTTClient mqtt(4608);mqtt.begin(AWS_ENDPOINT,8883,tls);mqtt.setOptions(30,true,2000);
 JsonDocument status;status["schema"]=1;status["mode"]="live";status["client"]="sensor";status["boot_id"]=bootId;status["status"]="offline";status["ts"]=nullptr;String will;serializeJson(status,will);String topic=String(prefix)+"status/sensor";mqtt.setWill(topic.c_str(),will.c_str(),true,1);
 const int backoff[]={1,2,4,8,16,30};unsigned retry=0;
 int64_t bootUtc=0;
 for(;;){
  if(WiFi.status()!=WL_CONNECTED||wall()<1704067200000LL){tls.stop();vTaskDelay(pdMS_TO_TICKS(500));continue;}
  if(!bootUtc)bootUtc=wall()-static_cast<int64_t>(mono());
  if(!mqtt.connected()){tls.stop();if(!mqtt.connect("team3-sensor")){vTaskDelay(pdMS_TO_TICKS(backoff[retry]*1000));if(retry<5)retry++;continue;}retry=0;status["status"]="online";status["ts"]=stamp(wall());String out;serializeJson(status,out);mqtt.publish(topic,out,true,1);}
  mqtt.loop();Message m{};
  if(xQueuePeek(events,&m,0)==pdTRUE){
   JsonDocument event;deserializeJson(event,m.body);
   event["ts"]=stamp(bootUtc+static_cast<int64_t>(m.created));
   String out;serializeJson(event,out);
   if(mqtt.publish(m.topic,out,false,1))xQueueReceive(events,&m,0);else tls.stop();
  }
  if(xQueueReceive(telemetryQueue,&m,0)==pdTRUE&&mono()-m.created<10000){if(mqtt.publish(m.topic,m.body,false,1))Serial.printf("PUBLISHED %s\n",m.body);else tls.stop();}
  if(shutdownRequested&&uxQueueMessagesWaiting(events)==0){status["status"]="offline";status["ts"]=stamp(wall());String out;serializeJson(status,out);if(mqtt.publish(topic,out,true,1)){mqtt.disconnect();vTaskDelete(nullptr);}}
  vTaskDelay(pdMS_TO_TICKS(20));
 }
}
void setup(){
 digitalWrite(RELAY,LOW);pinMode(RELAY,OUTPUT);digitalWrite(RELAY,LOW);Serial.begin(115200);delay(1500);Serial.println("PLANTCARE: SETUP STARTED");bool nvsReady=preferences.begin("plantcare",false);
 JsonDocument configuration;configuration["config_id"]=settings::config().id;configuration["calibrated"]=settings::calibrated;configuration["calibration_id"]=settings::calibrationId;configuration["raw_dry"]=settings::rawDry;configuration["raw_wet"]=settings::rawWet;String savedConfig;serializeJson(configuration,savedConfig);bool configSaved=nvsReady&&preferences.putString("configuration",savedConfig)==savedConfig.length();
 snprintf(bootId,sizeof(bootId),"boot-%08lx%08lx",(unsigned long)esp_random(),(unsigned long)esp_random());
 esp_timer_create_args_t args{};args.callback=timerOff;args.name="pump-cutoff";if(esp_timer_create(&args,&cutoff)!=ESP_OK){Serial.println("Timer initialization failed");while(true)delay(1000);}
 JsonDocument saved;
 String markerText=preferences.getString("transaction","");
 bool corrupt=markerText.length()&&(deserializeJson(saved,markerText)||!saved["active"].is<bool>());
 watering=new BottomWatering(hardware,std::string(bootId)+"-water",
                              !configSaved||corrupt||bool(saved["active"]|false));
 telemetryQueue=xQueueCreate(1,sizeof(Message));events=xQueueCreate(4,sizeof(Message));
 if(!telemetryQueue||!events){Serial.println("Queue allocation failed");while(true)delay(1000);}
 Wire.begin(5,6);Wire.setClock(100000);Wire.setTimeOut(50);
 if(xTaskCreate(network,"mqtt",16384,nullptr,1,nullptr)!=pdPASS)Serial.println("MQTT task unavailable");
 Serial.println("Local watering ready. Send S to stop.");
}
void loop(){
 static constexpr char shutdown[]="SHUTDOWN";
 static size_t shutdownIndex=0;
 while(Serial.available()){
  int key=Serial.read();
  if(key=='S'||key=='s'){
   enqueueEvent(watering->stop(mono()));
   publishSoon=true;
  }
  if(key==shutdown[shutdownIndex]){
   if(++shutdownIndex==sizeof(shutdown)-1){
    shutdownRequested=true;
    shutdownIndex=0;
   }
  }else shutdownIndex=key=='S'?1:0;
 }
 bool didStop=stopped.exchange(false);
 uint64_t physical=0;
 if(didStop){portENTER_CRITICAL(&timerMux);physical=stoppedAt;portEXIT_CRITICAL(&timerMux);}
 auto prior=watering->state();
 enqueueEvent(watering->tick(mono(),didStop,physical));
 if(prior!=watering->state())publishSoon=true;
 if(mono()-lastSoil>=BottomWatering::sampleMs){
  lastSoil=mono();
  readSoil();
  enqueueEvent(watering->sample(mono(),soilValid,raw));
  Serial.printf("SOIL raw=%u %s watering=%s\n",unsigned(raw),
                !soilValid?"invalid":raw<BottomWatering::dry?"dry":raw>BottomWatering::wet?"wet":"transition",
                watering->state().c_str());
 }
 uint64_t interval=mono()<observeUntil?10000:settings::sampleMs;
 if(!watering->on()&&(publishSoon||mono()-lastSample>=interval)){
  publishSoon=false;lastSample=mono();sample();
 }
 delay(10);
}
