#include <cassert>
#include "../firmware/shared/BottomWatering.h"

using namespace plantcare;

struct Relay : Hardware {
 bool high = false, canSave = true, canStart = true;
 unsigned pulses = 0;
 Marker marker;
 bool save(const Marker &next) override {
  if (!canSave) return false;
  marker = next;
  return true;
 }
 bool start(uint32_t duration) override {
  assert(marker.active && duration == 1500);
  if (!canStart) return false;
  ++pulses;
  high = true;
  return true;
 }
 void stop() override { high = false; }
};

int main() {
 Relay relay;
 BottomWatering cycle(relay, "boot-water", false);
 for (uint64_t ms=1000; ms<=9000; ms+=1000)
  assert(cycle.sample(ms,true,759).status.empty());
 assert(cycle.sample(10000,true,760).status.empty());
 for (uint64_t ms=11000; ms<=19000; ms+=1000)
  assert(cycle.sample(ms,true,700).status.empty());
 assert(cycle.sample(22000,true,700).status.empty()); // Missed sampling resets the count.
 for (uint64_t ms=23000; ms<=30000; ms+=1000) cycle.sample(ms,true,700);
 assert(cycle.sample(31000,true,700).status=="started" && relay.high);
 assert(cycle.tick(32499,false,0).status.empty());
 assert(cycle.tick(32510,true,32500).duration==1500 && !relay.high);
 assert(cycle.state()=="soaking" && !relay.marker.active);
 cycle.tick(92500,false,0);
 assert(cycle.state()=="complete");
 for (uint64_t ms=93000; ms<=105000; ms+=1000) cycle.sample(ms,true,700);
 assert(relay.pulses==1);

 BottomWatering faulty(relay,"next-water",false);
 for (uint64_t ms=1000; ms<=10000; ms+=1000) faulty.sample(ms,true,700);
 assert(faulty.sample(11000,true,65535).status=="aborted");
 assert(!relay.high && relay.marker.active);
 BottomWatering locked(relay,"locked-water",relay.marker.active);
 for (uint64_t ms=1000; ms<=10000; ms+=1000) locked.sample(ms,true,700);
 assert(!relay.high && locked.state()=="fault");

 BottomWatering stopped(relay,"stop-water",false);
 for (uint64_t ms=1000; ms<=10000; ms+=1000) stopped.sample(ms,true,700);
 assert(stopped.stop(10400).reason=="local_stop");
 assert(!relay.high && stopped.state()=="stopped");
 Relay failed;
 failed.canSave=false;
 BottomWatering storageFailure(failed,"storage-water",false);
 for (uint64_t ms=1000; ms<=10000; ms+=1000) storageFailure.sample(ms,true,700);
 assert(failed.pulses==0 && storageFailure.state()=="fault");
}
