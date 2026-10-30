Smart Pro Check — baseline collector, not an OS installer

After a verified full-card backup, add this new folder under Apps/ on the
current stock/CrossMix card. Exit USB Storage, then open Apps > Smart Pro Check.
The app returns to the existing menu after collecting. Reconnect USB Storage
and copy the whole reports/session-* directory to the laptop.

Share baseline.txt only. Keep PRIVATE-internal-recovery private: it can contain
configuration. An INCOMPLETE.txt marker means the archive did not finish.

No game, firmware, emulator, launcher or setting is changed. The app writes only
its new report directory and retains selected internal files in a private tar.
The archive is not a full internal backup or a tested restoration procedure.

The app has been tested using host fixtures, not on the actual TrimUI device.
Its source and original check-mark icon are provided under the included MIT
license. The collector requires /bin/sh plus common BusyBox-style utilities;
it does not require Python or download/install any dependency.
