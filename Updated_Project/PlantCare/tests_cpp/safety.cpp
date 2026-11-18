#include "../firmware/shared/SafetyCore.h"
#include <cassert>
#include <iostream>
using namespace plantcare;
struct HW:Hardware{bool saved=false,running=false,fail=false;Marker marker;bool save(const Marker&m)override{if(fail)return false;marker=m;saved=true;return true;}bool start(uint32_t)override{assert(saved&&marker.active);running=true;return true;}void stop()override{running=false;}};
int main(){
 Config cfg{true,"simulated","cfg",3000,2000,12000,30};HW hw;SafetyCore s(hw,cfg,"boot",{},0);
 Command arm{"arm","arm","boot","cfg","simulated",100000,110000,0,false};
 assert(!hw.running&&!s.armed);assert(s.accept(arm,100000,0,true,true,20).status=="accepted");
 Command water{"water","water","boot","cfg","simulated",100001,110001,2000,false};
 assert(s.accept(water,100001,1,true,true,20).status=="started");assert(hw.marker.active&&hw.running);
 assert(s.accept(water,100001,1,true,true,20).status=="duplicate");
 assert(s.tick(2000,true).status.empty());assert(s.tick(2001,true).status=="completed");assert(!hw.running&&!hw.marker.active);assert(s.cooldown(2001)==12000);
 Command next=water;next.id="next";next.issued=102002;next.expires=112002;assert(s.accept(next,102002,2002,true,true,20).reason=="cooldown");
 HW reboot;SafetyCore restart(reboot,cfg,"new",Marker{true,true,"water",100001},0);assert(restart.fault&&!restart.armed&&!reboot.running);
 HW h2;SafetyCore a(h2,cfg,"boot",{},0);auto unarmed=water;unarmed.id="unarmed";assert(a.accept(unarmed,100001,0,true,true,20).reason=="not_armed");assert(a.accept(arm,100000,0,true,true,20).status=="accepted");assert(a.accept(unarmed,100001,1,true,true,20).status=="duplicate");assert(!h2.running);
 for(auto reason:{"wrong_boot","config_mismatch","expired","duration_invalid","moisture_invalid","soil_not_dry","clock_invalid"}){
  auto c=water;c.id=reason;bool valid=true,clock=true;double pct=20;int64_t now=100001;
  if(std::string(reason)=="wrong_boot")c.boot="old";
  if(std::string(reason)=="config_mismatch")c.config="bad";
  if(std::string(reason)=="expired")now=110001;
  if(std::string(reason)=="duration_invalid")c.duration=3001;
  if(std::string(reason)=="moisture_invalid")valid=false;
  if(std::string(reason)=="soil_not_dry")pct=30;
  if(std::string(reason)=="clock_invalid")clock=false;
  assert(a.accept(c,now,1,clock,valid,pct).reason==reason);assert(!h2.running);
 }
 assert(a.accept(water,100001,1,true,true,20).status=="started");assert(a.tick(2,false).status=="aborted");assert(a.fault&&!h2.running);
 Command reset{"reset","reset_fault","boot","cfg","simulated",100005,110005,0,false};assert(a.accept(reset,100005,5,true,true,20).reason=="malformed");reset.id="reset-inspected";reset.inspected=true;assert(a.accept(reset,100005,5,true,true,20).status=="accepted");assert(!a.armed&&!a.fault);assert(a.cooldown(5)>0);
 HW fail;fail.fail=true;SafetyCore broken(fail,cfg,"boot",{},0);assert(broken.accept(arm,100000,0,true,true,20).status=="accepted");assert(broken.accept(water,100001,1,true,true,20).reason=="fault_active");assert(!fail.running);
 std::cout<<"Safety core assertion suite passed\n";
}
