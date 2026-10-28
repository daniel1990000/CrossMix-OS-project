#!/bin/sh
set -eu
NATIVE_ROOT=/workspace/trimui-audit/native
HOST_PREFIX=/workspace/trimui-audit/host-libs/usr
export PATH="/workspace/trimui-audit/certification/venv/bin:$PATH"
export PKG_CONFIG_PATH="$HOST_PREFIX/lib/x86_64-linux-gnu/pkgconfig:$HOST_PREFIX/share/pkgconfig"
export PKG_CONFIG_SYSROOT_DIR=/workspace/trimui-audit/host-libs
export LD_LIBRARY_PATH="$HOST_PREFIX/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cmake -S "$NATIVE_ROOT/patched-source" -B "$NATIVE_ROOT/patched-build" -G Ninja \
 -DCMAKE_C_FLAGS=-I/workspace/trimui-audit/host-libs/usr/include/x86_64-linux-gnu \
 -DCMAKE_CXX_FLAGS=-I/workspace/trimui-audit/host-libs/usr/include/x86_64-linux-gnu \
 -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
 -DCMAKE_PREFIX_PATH="$HOST_PREFIX" -DCMAKE_INCLUDE_PATH="$HOST_PREFIX/include" \
 -DCMAKE_LIBRARY_PATH="$HOST_PREFIX/lib/x86_64-linux-gnu" \
 -DOPENGL_INCLUDE_DIR="$HOST_PREFIX/include" \
 -DOPENGL_opengl_LIBRARY=/lib/x86_64-linux-gnu/libOpenGL.so.0 \
 -DOPENGL_glx_LIBRARY=/lib/x86_64-linux-gnu/libGLX.so.0 \
 -DOPENGL_gl_LIBRARY=/lib/x86_64-linux-gnu/libGL.so.1 \
 -DFontconfig_LIBRARY=/lib/x86_64-linux-gnu/libfontconfig.so.1 \
 -DUSING_X11_VULKAN=OFF -DUSE_WAYLAND_WSI=OFF \
 -DUSE_SYSTEM_LIBPNG=OFF -DUSE_DISCORD=OFF -DUSE_MINIUPNPC=OFF \
 -DUNITTEST=OFF -DHEADLESS=OFF -DATLAS_TOOL=OFF -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
