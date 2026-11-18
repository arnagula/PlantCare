#pragma once
#include <Arduino.h>

void startCloudTelemetry();
void queueTelemetry(float temperature, float humidity, float lux, uint16_t raw, bool rawValid);
