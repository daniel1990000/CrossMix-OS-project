# Scoped upstream review

The O03 host tool compares two local Git checkouts and produces an engineering
review queue. It does not fetch source, change a lock, apply a patch, build a
candidate or promote a runtime. A maintenance owner and the first device pilot
are still required to complete O03.

```sh
PYTHONPATH=project python3 project/tools/upstream_drift.py \
  --source SPRUCE_SOURCE_ROOT \
  --baseline-root /workspace/spruce-baseline \
  --candidate-root /path/to/separately-reviewed-spruce-checkout \
  --output /tmp/spruce-drift.json
```

The baseline must match its existing exact pin and required file hashes. Both
checkouts must have clean materialized bytes, including files hidden from Git
diff by index flags. Sparse-excluded paths are compared through Git tree
metadata, so an omitted file is not reported as a deletion. The report includes
added and removed files, executable-bit changes, symlinks and submodule identities.
It never imports proposed Python or executes proposed launch/build scripts.
The tool rechecks both inputs before returning. The output must be new and
outside both checkouts; publication flushes file and directory metadata.
If a write, sync or identity check fails, no successful receipt is returned.
Preserve any uncertain output for review and choose a new filename for a retry;
the tool never deletes a pathname that could now refer to someone else's file.

| Source scope | Required review after changes |
|---|---|
| spruce/PyUI, runtime scripts, updater, TrimUI launcher and licences | Exact patch preimages; host integration; ownership, input, power, USB and recovery cases affected; notification scope |
| PPSSPP Core/Common/SDL/UI/themes and submodules | Native patch acceptance; ABI/dependency audit and corresponding source; controls, saves and per-game settings; separately qualified device scenes |
| spruce RetroArch recipe, IGM sources and patches | Recipe and licence scope; native IGM acceptance and SDK audit; independent controls/save/return testing |
| Celeste port preparation | Repack/mount/full-storage fault cases; runtime/data requirements; retry and save preservation |
| PortMaster Harbourmaster and helpers | Installed-generation/self-update inventory; capability/readiness and save contracts; affected title qualification |

Changes outside the configured scopes are counted and require a scope review.
They are not evidence that integration remains safe. A new transitive dependency
can require broader inspection even when a known file is unchanged. Path labels
only prioritize review; the report cannot infer behavior or grant permissions.

For each proposed update, keep the report, exact old/new revisions, failure
reproduction and accepted test scope. Record whether each defect affects core,
an optional engine, an optional title or an unsupported configuration. Preserve
old source/build inputs and the corresponding restore route. Review and qualify
each change independently before updating a lock. No schedule or background
maintenance service is created by this tooling.
