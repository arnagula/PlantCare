#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <string>
namespace plantcare {
struct Config { bool qualified=false;std::string mode="live",id="cfg-unqualified";uint32_t maximum=0,dose=0,cooldown=0;double dry=0; };
struct Command {std::string id,action,boot,config,mode;int64_t issued=0,expires=0;uint32_t duration=0;bool inspected=false;};
struct Marker {bool active=false,known=false;std::string id;int64_t issued=0;};
struct Event {std::string status,reason,id,action;uint32_t duration=0;double baseline=0;};
struct Hardware {virtual ~Hardware()=default;virtual bool save(const Marker&)=0;virtual bool start(uint32_t)=0;virtual void stop()=0;};
class SafetyCore {
 Hardware &hw; Config cfg;std::string boot;Marker marker;std::array<std::string,16> ids{};size_t next=0;uint64_t started=0,coolUntil=0;uint32_t duration=0;double baseline=0;Command current;
 bool seen(const std::string &id)const {return id==marker.id||std::find(ids.begin(),ids.end(),id)!=ids.end();}
 public:bool armed=false,on=false,fault=false;
 SafetyCore(Hardware &h,Config c,std::string b,Marker m,uint64_t now):hw(h),cfg(c),boot(b),marker(m){hw.stop();fault=m.active;if(m.known)coolUntil=now+cfg.cooldown;}
 uint64_t cooldown(uint64_t now)const{return now<coolUntil?coolUntil-now:0;}
 Event reject(const Command&c,const std::string&r){if(!c.id.empty()&&c.id.size()<=64)ids[next++%16]=c.id;return {"rejected",r,c.id,c.action,0,0};}
 Event accept(const Command &c,int64_t utc,uint64_t mono,bool clock,bool moisture,double pct){
  if(c.id.empty()||c.id.size()>64||c.boot.empty()||c.config.empty()||c.expires-c.issued!=10000||c.mode!=cfg.mode)return reject(c,"malformed");
  if(seen(c.id))return {"duplicate","",c.id,c.action,0,0};
  if(!clock||c.issued>utc+5000)return reject(c,"clock_invalid");
  if(c.boot!=boot)return reject(c,"wrong_boot");
  if(c.config!=cfg.id)return reject(c,"config_mismatch");
  if(utc>=c.expires||(marker.known&&c.issued<=marker.issued))return reject(c,"expired");
  if(on)return reject(c,"busy");
  if(c.action=="disarm"){armed=false;ids[next++%16]=c.id;return {"accepted","",c.id,c.action,0,0};}
  if(c.action=="reset_fault"){
   if(!c.inspected)return reject(c,"malformed");
   if(!moisture||!std::isfinite(pct))return reject(c,"moisture_invalid");
   Marker cleared=marker;cleared.active=false;if(!hw.save(cleared)){fault=true;return reject(c,"fault_active");}
   marker=cleared;fault=false;armed=false;ids[next++%16]=c.id;return {"accepted","",c.id,c.action,0,0};
  }
  if(fault)return reject(c,"fault_active");
  if(!cfg.qualified)return reject(c,"config_mismatch");
  if(cooldown(mono))return reject(c,"cooldown");
  if(!moisture||!std::isfinite(pct)||pct<0||pct>100)return reject(c,"moisture_invalid");
  if(c.action=="arm"){armed=true;ids[next++%16]=c.id;return {"accepted","",c.id,c.action,0,0};}
  if(c.action!="water")return reject(c,"malformed");
  if(!armed)return reject(c,"not_armed");
  if(pct>=cfg.dry)return reject(c,"soil_not_dry");
  if(c.duration==0||c.duration>cfg.maximum)return reject(c,"duration_invalid");
  Marker pending{true,true,c.id,c.issued};if(!hw.save(pending)){fault=true;return reject(c,"fault_active");}
  marker=pending;current=c;duration=c.duration;baseline=pct;started=mono;
  if(!hw.start(duration)){hw.stop();fault=true;return reject(c,"fault_active");}
  on=true;ids[next++%16]=c.id;return {"started","",c.id,c.action,0,pct};
 }
 Event tick(uint64_t mono,bool moisture,bool hardwareStopped=false,uint64_t physicalStop=0){
  if(!on)return {};
  if(!moisture||hardwareStopped||mono-started>=duration){
   hw.stop();on=false;uint64_t end=hardwareStopped?physicalStop:mono;coolUntil=end+cfg.cooldown;
   Marker done=marker;done.active=false;if(!hw.save(done)){fault=true;}else marker=done;
   if(!moisture)fault=true;
   return {moisture?"completed":"aborted",moisture?"":"moisture_invalid",current.id,"water",static_cast<uint32_t>(end-started),baseline};
  }
  return {};
 }
};
}
