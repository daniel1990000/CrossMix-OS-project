#!/bin/sh
set -eu
command -v aarch64-linux-gnu-gcc
command -v aarch64-linux-gnu-g++
aarch64-linux-gnu-gcc --version
aarch64-linux-gnu-g++ --version
aarch64-linux-gnu-gcc -dumpmachine
aarch64-linux-gnu-gcc --sysroot=/opt/sysroot -O2 /input/smoke.c -o /output/smoke-c
aarch64-linux-gnu-g++ --sysroot=/opt/sysroot -O2 -static-libstdc++ -static-libgcc /input/smoke.cpp -o /output/smoke-cpp
aarch64-linux-gnu-readelf -h /output/smoke-c
aarch64-linux-gnu-readelf -h /output/smoke-cpp
aarch64-linux-gnu-readelf -l /output/smoke-c | grep interpreter
aarch64-linux-gnu-readelf -d /output/smoke-cpp | grep NEEDED
cmake --version
make --version
sha256sum /output/smoke-c /output/smoke-cpp
