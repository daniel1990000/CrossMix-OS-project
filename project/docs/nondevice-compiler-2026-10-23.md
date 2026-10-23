# Restoring the retained private compiler

The R04 compiler image was restored from owner-only retained storage into the
managed Docker daemon after observing zero images and zero containers. This
closes the previously unrun empty-daemon restoration check without using the
Smart Pro. It does not repeat or qualify a native engine build.

All eight Drive parts were freshly retrieved. Each part, the reassembled
471,632,780-byte compressed archive and the 1,516,103,168-byte Docker save stream
match their existing independent R04 digests. The archive's image configuration
and all eight content-addressed blobs also match. Loading the archive returned
image `sha256:15ef8c75094bd51d1116ad4218846b6949821f545c053ddda89b8bfbba85f51b`.
The same daemon then contained that one image and no remaining containers. No
existing image, container or unrelated workload was removed.

The restored image compiled and linked original C and C++ smoke sources against
`/opt/sysroot` using its active AArch64 GCC/G++ 9.4.0 compiler. The C++ smoke uses
static libstdc++ and libgcc. Readelf confirms both outputs are AArch64 ELF files
with the expected target interpreter; neither target executable was run.
CMake 3.16.3 and GNU Make 4.2.1 are available. The container ran without network,
with a read-only root, dropped capabilities, no-new-privileges and UID/GID 1000.
Only temporary scratch/output paths were writable.

An initial optional probe assumed the old GCC7 executable was retained; that
path is absent. Only its Linaro sysroot is retained, while the actual build uses
GCC9. The initial version pipeline hid that optional command failure. The final
script removes the irrelevant probe and version pipelines and passes with
checked commands. Both logs are retained so the corrected result does not erase
the first observation.

[Verification and exact hashes](../evidence/nondevice-compiler-20261023/verification.json)
include the before/after daemon observations, archive checks, active compiler
output and the smoke source/script. Compiler archives, SDK material and generated
AArch64 executables remain in private scratch, outside Git and public host
packages. No licence grant, target compatibility, hardware qualification or
production gate follows from compiler restoration. Permanent storage
availability is not guaranteed.
