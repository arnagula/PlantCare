#pragma once
#include <cstdint>
#include <string>
#include <cmath>
namespace plantcare {
struct DisplayState {
 std::string boot,mode="live",state="unknown",mood="regular";uint64_t sequence=0,arrival=0;int64_t sample=0;double timeout=10;
 bool accept(const std::string&newBoot,uint64_t seq,const std::string&m,const std::string&s,const std::string&face,int64_t sampled,double limit,int64_t utc,uint64_t monotonic,bool clock){
  if(!clock||newBoot.empty()||newBoot.size()>64||seq==0||(m!="live"&&m!="simulated")||!std::isfinite(limit)||limit<=0||sampled<=0||sampled>utc+5000||utc-sampled>limit*1000)return false;
  if(face!="happy"&&face!="regular"&&face!="sad")return false;
  if(s!="unknown"&&s!="happy"&&s!="watering"&&s!="watering_fault"&&s!="checking_moisture"&&s!="thirsty"&&s!="too_wet"&&s!="too_hot"&&s!="too_cold"&&s!="low_light"&&s!="low_humidity")return false;
  if((newBoot==boot&&seq<=sequence)||sampled<sample)return false;
  boot=newBoot;sequence=seq;mode=m;state=s;mood=face;sample=sampled;timeout=limit;arrival=monotonic;return true;
 }
 bool stale(int64_t utc,uint64_t monotonic,bool clock)const{return !clock||sample==0||utc<sample-5000||utc-sample>timeout*1000||monotonic-arrival>timeout*1000;}
};
}
