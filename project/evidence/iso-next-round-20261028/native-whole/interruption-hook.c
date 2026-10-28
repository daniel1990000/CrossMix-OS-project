#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>
static int active=0;
static const char *command_path,*marker_path,*session_path;
__attribute__((constructor)) static void init_hook(void) {
 const char *expected=getenv("TRIMUI_INTERRUPT_EXECUTABLE");
 char actual[4096];ssize_t n=readlink("/proc/self/exe",actual,sizeof(actual)-1);
 if(n>0)actual[n]=0;
 command_path=getenv("TRIMUI_INTERRUPT_COMMAND");marker_path=getenv("TRIMUI_INTERRUPT_MARKER");session_path=getenv("TRIMUI_INTERRUPT_SESSION");
 active=expected&&n>0&&!strcmp(expected,actual)&&command_path&&marker_path&&session_path;
}
static void fd_name(int fd,char *path,size_t size) {char input[64];snprintf(input,sizeof(input),"/proc/self/fd/%d",fd);ssize_t n=readlink(input,path,size-1);if(n<0)n=0;path[n]=0;}
static int armed(const char *point) {
 if(!active)return 0;
 int fd=syscall(SYS_openat,AT_FDCWD,command_path,O_RDONLY|O_CLOEXEC,0);if(fd<0)return 0;
 char command[128];ssize_t n=syscall(SYS_read,fd,command,sizeof(command)-1);syscall(SYS_close,fd);
 if(n<=0)return 0;command[n]=0;while(n>0&&(command[n-1]=='\n'||command[n-1]=='\r'))command[--n]=0;
 return !strcmp(command,point);
}
static void stop_at(const char *point) {
 if(!armed(point))return;
 int fd=syscall(SYS_openat,AT_FDCWD,marker_path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
 if(fd<0)return;
 struct timespec ts;clock_gettime(CLOCK_MONOTONIC,&ts);
 char line[256];int n=snprintf(line,sizeof(line),"{\"point\":\"%s\",\"pid\":%ld,\"monotonic_ns\":%lld}\n",point,(long)getpid(),(long long)ts.tv_sec*1000000000LL+ts.tv_nsec);
 syscall(SYS_write,fd,line,n);syscall(SYS_fsync,fd);syscall(SYS_close,fd);
 syscall(SYS_tgkill,getpid(),syscall(SYS_gettid),SIGSTOP);
 _exit(125); /* Never continue an intercepted syscall after a resumed stop. */
}
static int snapshot_fd(int fd) {char path[4096];fd_name(fd,path,sizeof(path));return strstr(path,"/.trimui-state-snapshots/")!=NULL;}
static int session_fd(int fd) {char path[4096];fd_name(fd,path,sizeof(path));return session_path&&!strcmp(path,session_path);}
ssize_t write(int fd,const void *data,size_t size) {
 static ssize_t(*real_write)(int,const void*,size_t)=NULL;if(!real_write)real_write=dlsym(RTLD_NEXT,"write");
 if(active&&snapshot_fd(fd)&&armed("snapshot-partial-write")) {ssize_t n=real_write(fd,data,size>9?9:size);if(n>0)stop_at("snapshot-partial-write");return n;}
 if(active&&armed("result-partial-write")) {char path[4096],expected[4096];fd_name(fd,path,sizeof(path));snprintf(expected,sizeof(expected),"%s/result.tmp",session_path);if(!strcmp(path,expected)){ssize_t n=real_write(fd,data,size>9?9:size);if(n>0)stop_at("result-partial-write");return n;}}
 return real_write(fd,data,size);
}
int fsync(int fd) {
 static int(*real_fsync)(int)=NULL;if(!real_fsync)real_fsync=dlsym(RTLD_NEXT,"fsync");
 int snapshot=active&&snapshot_fd(fd);if(snapshot)stop_at("snapshot-before-fsync");
 int result=real_fsync(fd);if(snapshot&&result==0)stop_at("snapshot-after-fsync");return result;
}
int rename(const char *old,const char *name) {
 static int(*real_rename)(const char*,const char*)=NULL;if(!real_rename)real_rename=dlsym(RTLD_NEXT,"rename");
 if(active&&strlen(old)>9&&!strcmp(old+strlen(old)-9,".ppst.tmp"))stop_at("state-before-rename");
 return real_rename(old,name);
}
int renameat(int oldfd,const char *old,int newfd,const char *name) {
 static int(*real_renameat)(int,const char*,int,const char*)=NULL;if(!real_renameat)real_renameat=dlsym(RTLD_NEXT,"renameat");
 int scope=active&&session_fd(newfd);
 if(scope&&!strcmp(name,"result"))stop_at("result-before-rename");
 if(scope&&!strcmp(name,"save-completed"))stop_at("completion-before-rename");
 int result=real_renameat(oldfd,old,newfd,name);
 if(scope&&result==0&&!strcmp(name,"save-completed"))stop_at("completion-after-rename");return result;
}
