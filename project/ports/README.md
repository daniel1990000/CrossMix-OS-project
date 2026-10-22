# Optional port source patches

`celeste-fix.lock.json` records upstream revision and exact pre/post hashes for
the Celeste launcher/repack failure fix. The diff is tested only on disposable
copies of those inputs, with fake game/runtime/mount helpers. Upstream source
checkouts remain untouched.

This patch is not selected by the original-only host preview. It includes no
game data or engine, and grants no rights to the upstream port, Mono/FNA,
Celeste or other assets. Exact terms and device runtime behavior remain separate
review gates. See [the preparation/save contract](../docs/ports-preparation-and-saves.md).
