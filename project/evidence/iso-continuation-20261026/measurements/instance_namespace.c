// SPDX-License-Identifier: MIT
// Private host-test isolation only. No device/runtime payload uses this shim.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
static const char *mapped(const char *name) {
    if (strcmp(name,"/PPSSPP_ID")) return name;
    const char *value=getenv("TRIMUI_TEST_INSTANCE_SHM");
    if (!value || strncmp(value,"/trimui-audit-",14) || strlen(value)>120) {errno=EINVAL;return NULL;}
    for (const char *p=value+1;*p;++p) if (!((*p>='a'&&*p<='z')||(*p>='0'&&*p<='9')||*p=='-')) {errno=EINVAL;return NULL;}
    return value;
}
int shm_open(const char *name,int flags,mode_t mode) {
    static int (*original)(const char*,int,mode_t);
    if(!original)original=dlsym(RTLD_NEXT,"shm_open");
    const char *use=mapped(name);return use?original(use,flags,mode):-1;
}
int shm_unlink(const char *name) {
    static int (*original)(const char*);
    if(!original)original=dlsym(RTLD_NEXT,"shm_unlink");
    const char *use=mapped(name);return use?original(use):-1;
}
// Prevent the private debugger's optional discovery registration from blocking
// this offline host test. All other DNS lookups retain the native implementation.
#include <netdb.h>
int getaddrinfo(const char *node,const char *service,const struct addrinfo *hints,struct addrinfo **res) {
    static int (*original)(const char*,const char*,const struct addrinfo*,struct addrinfo**);
    if(!original)original=dlsym(RTLD_NEXT,"getaddrinfo");
    if(node&&!strcmp(node,"report.ppsspp.org"))return EAI_NONAME;
    return original(node,service,hints,res);
}
