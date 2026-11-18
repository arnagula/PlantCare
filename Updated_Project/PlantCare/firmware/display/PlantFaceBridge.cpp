#include "PlantFaceBridge.h"
#include "../shared/DisplayState.h"
#include "../shared/Utc.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include <esp_timer.h>
#include <atomic>
#include "secrets.h"
#ifndef PLANTCARE_SIMULATED
#define PLANTCARE_SIMULATED 0
#endif
namespace {
const char* mode=PLANTCARE_SIMULATED?"simulated":"live";
const char* prefix=PLANTCARE_SIMULATED?"plantcare/team3/sim/pothos1/":"plantcare/team3/pothos1/";
const char* clientId=PLANTCARE_SIMULATED?"team3-sim-display":"team3-display";
struct Packet{char text[4097];};QueueHandle_t inbox;std::atomic<bool> connected{false},ending{false};plantcare::DisplayState watchdog;bool pump=false;String reason="Waiting for data";
int64_t wall(){timeval v;gettimeofday(&v,nullptr);return int64_t(v.tv_sec)*1000+v.tv_usec/1000;}
String timestamp(){int64_t ms=wall();time_t sec=ms/1000;tm t;gmtime_r(&sec,&t);char b[25];strftime(b,20,"%Y-%m-%dT%H:%M:%S",&t);snprintf(b+19,6,".%03uZ",unsigned(ms%1000));return b;}
void task(void*){
 WiFi.mode(WIFI_STA);WiFi.begin(WIFI_SSID,WIFI_PASSWORD);configTime(0,0,"pool.ntp.org","time.nist.gov");WiFiClientSecure tls;tls.setCACert(AWS_ROOT_CA);tls.setCertificate(AWS_DEVICE_CERT);tls.setPrivateKey(AWS_PRIVATE_KEY);MQTTClient mqtt(4608);mqtt.begin(AWS_ENDPOINT,8883,tls);mqtt.setOptions(30,true,2000);
 mqtt.onMessage(+[](String&topic,String&body){if(body.length()>4096)return;if(topic.endsWith("/condition")){Packet p{};body.toCharArray(p.text,sizeof(p.text));xQueueOverwrite(inbox,&p);}});
 JsonDocument s;s["schema"]=1;s["mode"]=mode;s["client"]="display";s["boot_id"]=String("display-")+String(esp_random(),HEX);s["status"]="offline";s["ts"]=nullptr;String out;serializeJson(s,out);String statusTopic=String(prefix)+"status/display";mqtt.setWill(statusTopic.c_str(),out.c_str(),true,1);
 const int backoff[]={1,2,4,8,16,30};unsigned retry=0;
 for(;;){
  if(WiFi.status()!=WL_CONNECTED||wall()<1704067200000LL){connected=false;tls.stop();vTaskDelay(pdMS_TO_TICKS(500));continue;}
  if(!mqtt.connected()){connected=false;tls.stop();if(!mqtt.connect(clientId)){vTaskDelay(pdMS_TO_TICKS(backoff[retry]*1000));if(retry<5)retry++;continue;}retry=0;mqtt.subscribe((String(prefix)+"condition").c_str(),1);mqtt.subscribe((String(prefix)+"status/backend").c_str(),1);s["status"]="online";s["ts"]=timestamp();out="";serializeJson(s,out);mqtt.publish(statusTopic,out,true,1);}
  connected=mqtt.connected();mqtt.loop();
  if(ending){s["status"]="offline";s["ts"]=timestamp();out="";serializeJson(s,out);if(mqtt.publish(statusTopic,out,true,1)){mqtt.disconnect();connected=false;vTaskDelete(nullptr);}}
  vTaskDelay(pdMS_TO_TICKS(20));
 }
}
}
void beginPlantCareNetwork(){inbox=xQueueCreate(1,sizeof(Packet));if(inbox)xTaskCreate(task,"display-network",16384,nullptr,1,nullptr);}
void endPlantCareNetwork(){ending=true;}
void pollPlantCareNetwork(){
 if(!inbox)return;Packet p{};
 if(xQueueReceive(inbox,&p,0)==pdTRUE){JsonDocument j;if(!deserializeJson(j,p.text)&&j["schema"].is<int>()&&j["schema"]==1&&String(j["mode"]|"")==mode){int64_t sample=plantcare::parseUtc(j["sample_ts"]|"");if(watchdog.accept(j["backend_boot_id"]|"",j["report_seq"]|uint64_t(0),j["mode"]|"",j["state"]|"",j["mood"]|"",sample,j["freshness_timeout_s"]|0.0,wall(),esp_timer_get_time()/1000,wall()>1704067200000LL)){pump=j["watering"]["pump_on"]|false;reason=j["reason"]|"";onPlantMessage(String(p.text));}}}
 bool stale=watchdog.stale(wall(),esp_timer_get_time()/1000,wall()>1704067200000LL);String connection=WiFi.status()!=WL_CONNECTED?"no_wifi":(!connected?"no_broker":"online");renderPlantCareStatus(mode,connection,stale?"unknown":watchdog.state.c_str(),stale?"regular":watchdog.mood.c_str(),stale?"No fresh sensor data":reason,pump&&!stale);
}
