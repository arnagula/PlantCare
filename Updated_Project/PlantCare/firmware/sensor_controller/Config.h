#pragma once
#include "../shared/SafetyCore.h"
namespace settings {
constexpr bool calibrated = false;
constexpr char profile[] = "normal";
constexpr char calibrationId[] = "";
constexpr double rawDry = 0;
constexpr double rawWet = 1;
constexpr double sampleMs = 60000;
constexpr double responseMs = 6000;
inline plantcare::Config config(){return {false,"live","cfg-unqualified",0,0,0,0};}
}
