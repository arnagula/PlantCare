#pragma once
#include <Arduino.h>
// Implement these two hooks in the EXISTING PlantFace GUI. No replacement GUI is supplied.
void onPlantMessage(const String &json);
void renderPlantCareStatus(const String &mode,const String &connection,const String &state,const String &mood,const String &reason,bool pumpOn);
void beginPlantCareNetwork();
void pollPlantCareNetwork();
void endPlantCareNetwork();
