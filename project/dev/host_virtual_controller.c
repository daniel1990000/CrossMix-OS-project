// SPDX-License-Identifier: MIT
// Development-only SDL2 virtual input probe. Never included in device/runtime payloads.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>
#include <limits.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <string.h>

typedef struct { uint8_t data[16]; } GUID;
static void *stick;
static int device=-1, active;
static long long last_seq=-1, expiry, start_ticks;
static const char *command_path, *log_path;
static uint64_t ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec; }
static long long process_start_ticks(void) {
 FILE *f=fopen("/proc/self/stat","r");if(!f)return -1;
 char line[4096];if(!fgets(line,sizeof(line),f)){fclose(f);return -1;}fclose(f);
 char *end=strrchr(line,')');if(!end)return -1;
 char *save=NULL,*part=strtok_r(end+2," ",&save);
 for(int field=3;part;field++,part=strtok_r(NULL," ",&save))if(field==22)return atoll(part);
 return -1;
}
static FILE *private_file(const char *path,int writing) {
 int fd=open(path,(writing?(O_WRONLY|O_CREAT|O_APPEND):O_RDONLY)|O_NOFOLLOW|O_CLOEXEC,0600);
 if(fd<0)return NULL;
 struct stat st;if(fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_uid!=getuid()||(st.st_mode&077)){close(fd);return NULL;}
 return fdopen(fd,writing?"a":"r");
}
static void record(const char *event,long long seq,long long requested,long long expires,const int *axes,unsigned buttons,int result) {
 if(!log_path)return;
 FILE *f=private_file(log_path,1);if(!f)return;
 fprintf(f,"{\"event\":\"%s\",\"pid\":%d,\"sequence\":%lld,\"requested_monotonic_ns\":%lld,\"observed_monotonic_ns\":%llu,\"expires_monotonic_ns\":%lld,\"axes\":[%d,%d,%d,%d],\"buttons\":%u,\"result\":%d}\n",event,getpid(),seq,requested,(unsigned long long)ns(),expires,axes[0],axes[1],axes[2],axes[3],buttons,result);fclose(f);
}
static int apply(const int *axes,unsigned buttons) {
 int (*axis)(void*,int,int16_t)=dlsym(RTLD_NEXT,"SDL_JoystickSetVirtualAxis");
 int (*button)(void*,int,uint8_t)=dlsym(RTLD_NEXT,"SDL_JoystickSetVirtualButton");
 int result=0;for(int i=0;i<6;i++)result|=axis(stick,i,(int16_t)(i<4?axes[i]:0));
 for(int i=0;i<15;i++)result|=button(stick,i,(buttons>>i)&1);
 void(*update)(void)=dlsym(RTLD_NEXT,"SDL_JoystickUpdate");update();
 return result;
}
static void neutral(const char *event) {const int zero[4]={0};if(stick){int result=apply(zero,0);record(event,last_seq,0,0,zero,0,result);}active=0;}
static void initialize(void) {
 if(stick)return;
 command_path=getenv("TRIMUI_CONTROLLER_COMMAND");log_path=getenv("TRIMUI_CONTROLLER_LOG");
 if(!command_path||command_path[0]!='/'||!log_path||log_path[0]!='/')return;
 const char *expected=getenv("TRIMUI_CONTROLLER_EXECUTABLE");char actual[PATH_MAX];
 if(!expected||!realpath("/proc/self/exe",actual)||strcmp(expected,actual))return;
 start_ticks=process_start_ticks();if(start_ticks<0)return;
 unsigned (*initialized)(unsigned)=dlsym(RTLD_NEXT,"SDL_WasInit");
 if(!initialized||!initialized(0x2000))return;
 int (*attach)(int,int,int,int)=dlsym(RTLD_NEXT,"SDL_JoystickAttachVirtual");
 void *(*open)(int)=dlsym(RTLD_NEXT,"SDL_JoystickOpen");
 GUID (*guid)(int)=dlsym(RTLD_NEXT,"SDL_JoystickGetDeviceGUID");
 void (*guidstr)(GUID,char*,int)=dlsym(RTLD_NEXT,"SDL_JoystickGetGUIDString");
 int (*mapping)(const char*)=dlsym(RTLD_NEXT,"SDL_GameControllerAddMapping");
 if(!attach||!open||!guid||!guidstr||!mapping)return;
 device=attach(1,6,15,0);if(device<0)return;stick=open(device);if(!stick)return;
 char id[33],text[512];guidstr(guid(device),id,sizeof(id));
 snprintf(text,sizeof(text),"%s,TrimUI Private Audit Controller,a:b0,b:b1,x:b2,y:b3,back:b4,guide:b5,start:b6,leftstick:b7,rightstick:b8,leftshoulder:b9,rightshoulder:b10,dpup:b11,dpdown:b12,dpleft:b13,dpright:b14,leftx:a0,lefty:a1,rightx:a2,righty:a3,lefttrigger:a4,righttrigger:a5,platform:Linux,",id);
 int result=mapping(text);const int zero[4]={0};record("attached",-1,0,0,zero,0,result);
}
static void pump(void) {
 initialize();if(!stick)return;
 FILE *f=private_file(command_path,0);
 if(f){long long seq,pid,ticks,requested,expires;int a[4];unsigned b;
  int count=fscanf(f,"%lld %lld %lld %lld %lld %d %d %d %d %u",&seq,&pid,&ticks,&requested,&expires,&a[0],&a[1],&a[2],&a[3],&b);fclose(f);
  if(count==10&&seq>last_seq){
   int valid=pid==getpid()&&ticks==start_ticks&&b<32768&&requested>=0&&requested<=(long long)ns()&&expires>requested&&expires-requested<=60000000000LL;
   for(int i=0;i<4;i++)valid=valid&&a[i]>=-32767&&a[i]<=32767;
   last_seq=seq;
   if(!valid){neutral("invalid_neutral");}
   else if((long long)ns()>expires){neutral("late_neutral");record("expired_command",seq,requested,expires,a,b,-1);}
   else {int result=apply(a,b);expiry=expires;active=1;record("applied",seq,requested,expires,a,b,result);}
  }
 }
 if(active&&(long long)ns()>expiry)neutral("deadline_neutral");
}
int SDL_PollEvent(void *event) {static int(*next)(void*);if(!next)next=dlsym(RTLD_NEXT,"SDL_PollEvent");pump();return next(event);}
void SDL_Quit(void) {void(*next)(void)=dlsym(RTLD_NEXT,"SDL_Quit");if(stick){neutral("quit_neutral");void(*close)(void*)=dlsym(RTLD_NEXT,"SDL_JoystickClose");int(*detach)(int)=dlsym(RTLD_NEXT,"SDL_JoystickDetachVirtual");close(stick);stick=NULL;detach(device);device=-1;}next();}
