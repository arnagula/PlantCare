#pragma once
#include "SafetyCore.h"

namespace plantcare {
class BottomWatering {
 public:
  static constexpr uint16_t dry = 760, wet = 820, rawMin = 500, rawMax = 1100;
  static constexpr uint32_t sampleMs = 1000, pulseMs = 1500, soakMs = 60000;
  static constexpr unsigned requiredDry = 10;

  BottomWatering(Hardware &hardware, std::string id, bool locked)
      : hw(hardware), cycleId(std::move(id)), stage(locked ? "fault" : "monitoring") {
    hw.stop();
  }

  static bool valid(uint16_t raw) { return raw >= rawMin && raw <= rawMax; }
  bool on() const { return stage == "running"; }
  const std::string& state() const { return stage; }
  const std::string& id() const { return cycleId; }

  Event sample(uint64_t now, bool readOk, uint16_t raw) {
    if (on()) {
      if (!readOk || !valid(raw)) return finish(now, "moisture_invalid");
      return {};
    }
    if (stage != "monitoring") return {};
    if (!readOk || !valid(raw) || raw >= dry || (previous && now - previous > 1500))
      dryCount = 0;
    previous = now;
    if (!readOk || !valid(raw) || raw >= dry || ++dryCount < requiredDry) return {};
    if (!hw.save({true, true, cycleId, 0}) || !hw.start(pulseMs)) {
      hw.stop();
      stage = "fault";
      return {"aborted", "start_failed", cycleId, "water"};
    }
    started = now;
    stage = "running";
    return {"started", "", cycleId, "water"};
  }

  Event tick(uint64_t now, bool cutoff, uint64_t cutoffAt) {
    if (on() && (cutoff || now - started >= pulseMs))
      return finish(cutoff ? cutoffAt : now, "");
    if (stage == "soaking" && now >= soakUntil) stage = "complete";
    return {};
  }

  Event stop(uint64_t now) {
    if (on()) return finish(now, "local_stop");
    hw.stop();
    if (stage != "fault") stage = "stopped";
    return {};
  }

 private:
  Hardware &hw;
  std::string cycleId, stage;
  unsigned dryCount = 0;
  uint64_t previous = 0, started = 0, soakUntil = 0;

  Event finish(uint64_t now, const std::string &reason) {
    hw.stop();
    // Leave the NVS marker active after faults, including interrupted power.
    bool cleared = reason.empty() && hw.save({false, true, cycleId, 0});
    stage = cleared ? "soaking" : "fault";
    if (reason == "local_stop") stage = "stopped";
    soakUntil = now + soakMs;
    return {cleared ? "completed" : "aborted",
            !cleared && reason.empty() ? "storage_failed" : reason,
            cycleId, "water", static_cast<uint32_t>(now >= started ? now - started : 0)};
  }
};
}
