#pragma once
#include <cstdint>
#include <string>
namespace plantcare {
inline int64_t parseUtc(const std::string&s){
 if(s.size()!=24||s[4]!='-'||s[7]!='-'||s[10]!='T'||s[13]!=':'||s[16]!=':'||s[19]!='.'||s[23]!='Z')return -1;
 for(size_t i=0;i<24;i++){if(i==4||i==7||i==10||i==13||i==16||i==19||i==23)continue;if(s[i]<'0'||s[i]>'9')return -1;}
 auto n=[&](int start,int len){int x=0;for(int i=0;i<len;i++)x=10*x+s[start+i]-'0';return x;};
 int y=n(0,4),m=n(5,2),d=n(8,2),hh=n(11,2),mm=n(14,2),ss=n(17,2),ms=n(20,3);
 int days[]={31,28,31,30,31,30,31,31,30,31,30,31};if(y%4==0&&(y%100!=0||y%400==0))days[1]=29;
 if(y<1970||m<1||m>12||d<1||d>days[m-1]||hh>23||mm>59||ss>59)return -1;
 y-=m<=2;const int era=y/400;const unsigned yoe=static_cast<unsigned>(y-era*400);const unsigned doy=(153*(m+(m>2?-3:9))+2)/5+d-1;const unsigned doe=yoe*365+yoe/4-yoe/100+doy;
 const int64_t z=era*146097+static_cast<int>(doe)-719468;return ((z*24+hh)*60*60+mm*60+ss)*1000+ms;
}
}
