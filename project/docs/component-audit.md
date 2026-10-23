# Native component record audit

The original host tool [component_audit.py](../tools/component_audit.py) advances
R06 by checking whether the existing component, selection and private-custody
records agree. It does not decide distribution rights, retrieve remote files or
modify any selection/profile. R06 remains open.

Run from the repository root with the project's Python environment:

```sh
PYTHONPATH=project python project/tools/component_audit.py
PYTHONPATH=project python project/tools/component_audit.py \
  --ppsspp-source-root /path/to/pinned-ppsspp \
  --ra-recipe-root /path/to/pinned-spruce-ra
```

The tool reads a fixed six-file set: the existing 16-scope ledger, current
descriptor, R04 replacement build/retention receipts and the two engine source
locks. Input bytes receive separate hashes. It refuses duplicate component or
candidate IDs, unsupported component scope, mutable source revisions, malformed
digest fields, inconsistent selection, changed binary/source/recipe identity,
and missing/misordered/short custody records. The five known project patch
files are hashed independently and joined to component/source-lock/R04 patch
records; fabricated matching record digests cannot replace the file check. It separately classifies build
tools, incorporated code, static libraries, target dynamic dependencies and
assets; compiler executables and compiled runtime code are different scopes.

Default review targets are the two R04 replacements. To inspect a historical
candidate, use `--candidate ppsspp-complete-state-candidate` or
`--candidate retroarch-igm-candidate`. Historical digests cannot inherit the
replacement artifacts' custody. Replacement reports pair the recorded binary,
source and build archive identities and the prior receipts' retrieval claims.
That comparison is **not a new retrieval** and cannot authenticate an operator's
earlier statement. Retention part bytes must still be fetched and checked when
fresh retrieval is required.

Optional source roots are read through no-follow directory descriptors with
bounded regular files and before/after identity checks. The tool performs no
Git command, compiler invocation, import of target code, network request or
native execution. A full-file Git blob hash is compared to the exact recorded
blob; whole-file SHA-256 is checked separately. An excerpt SHA-256 is never
compared to a complete file. Matching individual files does not establish that
the entire checkout is at the pinned revision. Missing sparse files and absent
reference roots remain explicit observations, not successful source checks.

Exit 0 means the fixed records are consistent. `--require-native-ready` exits 3
because the current component/source-use review remains unresolved; malformed or
inconsistent records exit 2. Every report keeps distribution, source-use,
hardware and runtime qualification false. A successful host check cannot
substitute for R05 notification, R06 grants or physical qualification.

## Additional pinned notice inspection, 23 October 2026

[The retained review](../evidence/continuation-20261023/component-review.json)
records complete returned-source hashes and Git blob identities at PPSSPP
`d357e6a32934800d3d80b49f910a603e1b069751`. Source functionality and licence
observations are distinguished from actual binary link membership:

| Component | Exact source observation | Remaining boundary |
|---|---|---|
| gason | `ext/gason/LICENSE` is MIT, copyright Ivan Vashchaev. The root CMake file builds the gason static target from its source/header and links it to native. | Retain its copyright/permission notice with the applicable distributed source/substantial portions; actual replacement link/source membership and complete notice packaging still require review. |
| CityHash | `ext/cityhash/COPYING` grants MIT-style permission, copyright Google. The root CMake file builds CityHash and lists it in the Core link set. | Preserve the copyright/permission notice; establish actual candidate membership and packaged notices. |
| minimp3 | Both `ext/minimp3/minimp3.h` and `minimp3_ex.h` contain the author's public-domain dedication/CC0 reference and no-warranty statement. `minimp3.cpp` defines the implementation macro and includes both headers; its CMake file defines a static target. The root Core link set lists that target. | This resolves the terms observed in those exact headers, not all audio dependencies or every jurisdictional question. Preserve the source notices and verify actual compiled/link membership before making a binary distribution decision. |

The prior broad component ledger described these libraries as review backlog.
These small observations identify the actual notice sources more precisely;
they do not replace that historical ledger or claim a complete SBOM. No
third-party implementation is copied into the new original tool or payload.
The fetched complete texts were used privately for inspection and hashing.
Exact recipe/IGM/SDK grants and other linked components' source/notices remain
open. No author was contacted and no native executable ran.

The focused host suite covers 22 cases, including tampered identities, selection
disagreement, forged clearance, historical/replacement separation, missing
source archives, invalid part order/length, excerpt/full-file scope, symlink/
traversal/FIFO refusal, bounded reads, changed inputs and distinct CLI exits.
