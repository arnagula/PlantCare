// Compile-only adapter harness. NOT the Waveshare PlantFace firmware; do not flash it as a GUI.
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <MQTT.h>
#include "../display/PlantFaceBridge.cpp"
void onPlantMessage(const String&){}
void renderPlantCareStatus(const String&,const String&,const String&,const String&,const String&,bool){}
void setup(){}
void loop(){delay(1000);}
