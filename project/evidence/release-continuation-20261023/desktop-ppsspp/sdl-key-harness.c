// SPDX-License-Identifier: MIT
// Test-only native SDL key injection; not part of the emulator or device runtime.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
static double clock_s(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec+t.tv_nsec/1e9; }
int SDL_PollEvent(void *event) {
 static int (*next)(void *); static double start; static int step;
 static const double due[]={5,5.1,10,10.1,13,13.1,18};
 static const int codes[]={59,59,61,61,60,60,0};
 if(!next) next=dlsym(RTLD_NEXT,"SDL_PollEvent");
 if(!start) start=clock_s();
 if(step<7 && clock_s()-start>=due[step]) {
   unsigned char *e=event; memset(e,0,56);
   uint32_t kind=step==6?0x100:step%2?0x301:0x300;
   memcpy(e,&kind,4); e[12]=step%2?0:1;
   int32_t scan=codes[step],sym=(1<<30)|scan;
   memcpy(e+16,&scan,4); memcpy(e+20,&sym,4);
   fprintf(stderr,"DESKTOP_HARNESS event step=%d type=%x scancode=%d at=%.3f\n",step,kind,scan,clock_s()-start);
   ++step; return 1;
 }
 return next(event);
}
