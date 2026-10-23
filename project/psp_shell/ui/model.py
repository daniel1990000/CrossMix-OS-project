"""Pure navigation: immutable frames in, typed backend requests out.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Iterable, Mapping
import uuid

from .keyboard import KEYBOARD_KEYS, keyboard_text, move_keyboard_focus


CATEGORIES = ("Games", "Continue Playing", "Tools", "Settings")


def _text(value: Any, limit: int = 512) -> str:
    """Metadata is display text, never markup or executable input."""
    if not isinstance(value, str):
        return ""
    return "".join(c if c >= " " or c == "\n" else "�" for c in value)[:limit]


def _checkpoint_utc(value: str) -> str:
    """Format the backend's original signed observation; never invent an age."""
    if not isinstance(value, str):
        return ""
    try:
        recorded = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if recorded.utcoffset() != timedelta(0):
            return ""
        return recorded.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError, OverflowError):
        return ""


def _warning_message(value: str) -> str:
    return {
        "MISSING_DISC_FILE": "A referenced disc file is missing or empty.",
        "MISSING_DISC": "A referenced disc file is missing.",
        "MISSING_TRACK_FILE": "A disc's referenced track file is missing or empty.",
        "MALFORMED_CUE_FILE": "A disc track description is malformed.",
        "CUE_HAS_NO_TRACK_FILES": "A disc description contains no track files.",
        "CUE_UNREADABLE": "A disc track description could not be read.",
        "EMPTY_PLAYLIST": "The playlist contains no disc entries.",
        "PLAYLIST_UNREADABLE": "The playlist could not be read.",
        "UNSUPPORTED_DISC_REFERENCE": "A playlist entry uses an unsupported disc format.",
        "DISC_PATH_OUTSIDE_CARD": "A disc reference points outside this card.",
        "INVALID_DISC_PATH": "A disc reference contains an invalid path.",
        "INVALID_DISC_REFERENCE_TEXT": "A disc reference contains invalid text.",
        "DISC_REFERENCE_TOO_LARGE_OR_SPECIAL": "A disc reference cannot be safely inspected.",
        "DISC_REFERENCE_LIMIT": "This disc set exceeds the inspection limit; review the complete playlist.",
        "DISC_SET_REQUIRES_REVIEW": "Review the disc set before launching.",
        "SAVED_PRESET_UNAVAILABLE": "The saved emulator choice is unavailable; review existing Game options.",
        "ROM_UNAVAILABLE": "The game file is unavailable.",
        "EMPTY_ROM": "The game file is empty.",
        "FILENAME_COLLISION": "Some game names share the same existing per-game settings.",
        "REQUIRED_FILES_MISSING": "Required system files are missing.",
        "ARTWORK_OUTSIDE_SNAPSHOT": "The artwork is outside the inspected collection.",
        "EXISTING_SPRUCE_ROUTE_REQUIRED": "Open this entry through the existing spruce interface.",
    }.get(value, "This entry needs review in the existing game or emulator options.")


@dataclass(frozen=True)
class Preferences:
    confirm: str = "south"
    motion: bool = True
    sound: bool = True
    text_scale: float = 1.0
    high_contrast: bool = False
    interface: str = "classic"

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any] | None) -> "Preferences":
        values = values or {}
        scale = values.get("text_scale", 1.0)
        if not isinstance(scale, (float, int)) or isinstance(scale, bool):
            scale = 1.0
        return cls(
            confirm=values.get("confirm") if values.get("confirm") in ("south", "east") else "south",
            motion=values.get("motion", True) is True,
            sound=values.get("sound", True) is True,
            text_scale=max(0.75, min(1.75, float(scale))),
            high_contrast=values.get("high_contrast", False) is True,
            interface=values.get("interface") if values.get("interface") in ("classic", "project") else "classic",
        )


@dataclass(frozen=True)
class UIItem:
    id: str
    title: str
    subtitle: str = ""
    kind: str = "game"
    system_id: str = ""
    artwork: str = ""
    available: bool = True
    resume_available: bool = False
    reason: str = ""
    favorite: bool = False
    state_recorded_at: str = ""
    system_label: str = ""
    selected_emulator: str = ""
    selected_preset: str = ""
    availability: str = "available"

    @classmethod
    def from_record(cls, value: Mapping[str, Any], kind: str = "game") -> "UIItem":
        identifier = value.get("game_id", value.get("tool_id", value.get("id", "")))
        availability = value.get("availability", "available")
        available = value.get("available", availability == "available") is True
        return cls(
            id=_text(identifier, 1024),
            title=_text(value.get("display_name", value.get("title", value.get("label", identifier))), 512),
            subtitle=_text(value.get("subtitle", value.get("description", value.get("system_id", ""))), 1024),
            kind=kind,
            system_id=_text(value.get("system_id", ""), 128),
            artwork=_text(value.get("artwork_ref", value.get("artwork", "")), 4096),
            available=available,
            resume_available=value.get("resume_available", False) is True,
            reason=_text(value.get("resume_reason", value.get("reason", "")), 2048),
            favorite=value.get("favorite", False) is True,
            state_recorded_at=_text(value.get("state_recorded_at", ""), 64),
            system_label=_text(value.get("system_label", ""), 128),
            selected_emulator=_text(value.get("selected_emulator", ""), 256),
            selected_preset=_text(value.get("selected_preset", ""), 256),
            availability=_text(availability, 128),
        )


@dataclass(frozen=True)
class UICommand:
    serial: int
    method: str
    params: Mapping[str, Any] = field(default_factory=dict)
    context: str = ""


@dataclass(frozen=True)
class DialogChoice:
    title: str
    action: str = "close"
    method: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)
    context: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "params", MappingProxyType(dict(self.params)))


@dataclass(frozen=True)
class Dialog:
    title: str
    message: str
    choices: tuple[DialogChoice, ...] = (DialogChoice("Back"),)
    selected: int = 0
    error: bool = False
    message_page: int = 0
    artwork: str = ""
    system_id: str = ""


@dataclass(frozen=True)
class Keyboard:
    text: str
    selected: int
    keys: tuple[str, ...] = KEYBOARD_KEYS
    preferred_column: float | None = None


@dataclass(frozen=True)
class UISnapshot:
    category: int
    categories: tuple[str, ...]
    title: str
    breadcrumb: str
    items: tuple[UIItem, ...]
    selected: int
    total: int
    offset: int
    preferences: Preferences
    dialog: Dialog | None
    keyboard: Keyboard | None
    status: str
    empty_message: str
    loading: bool
    demo: bool
    exit_request: str | None
    display_clock: str = ""
    artwork_generation: int = 0

    @property
    def selected_item(self) -> UIItem | None:
        return self.items[self.selected] if 0 <= self.selected < len(self.items) else None


@dataclass
class _Page:
    items: tuple[UIItem, ...] = ()
    selected: int = 0
    offset: int = 0
    total: int = 0

    def replace(self, items: Iterable[UIItem], *, offset: int = 0,
                total: int | None = None, keep_focus: bool = True) -> None:
        previous_index = self.selected if keep_focus else 0
        previous = self.items[self.selected].id if keep_focus and 0 <= self.selected < len(self.items) else None
        self.items = tuple(items)
        self.offset = max(0, offset)
        self.total = len(self.items) if total is None else max(0, total)
        # Keep the same game through reordering. If it disappeared during a
        # refresh, its nearest surviving neighbor keeps the list in place.
        # A fresh page/query explicitly starts at zero via keep_focus=False.
        fallback = max(0, min(previous_index, len(self.items) - 1))
        self.selected = next((i for i, item in enumerate(self.items)
                              if keep_focus and item.id == previous), fallback)


def _menu(identifier: str, title: str, subtitle: str = "") -> UIItem:
    return UIItem(identifier, title, subtitle, "menu")


class NavigationModel:
    """Backend-independent focus, dialogs, search and preference previews.

    ``handle`` and ``receive`` return requests for the app coordinator. No method
    here performs I/O. Applications may alternatively populate views directly
    with ``set_category_items`` when embedding in the existing PyUI menu models.
    """

    PAGE_SIZE = 40

    def __init__(self, demo: bool = False, preferences: Mapping[str, Any] | None = None,
                 restored_state: Mapping[str, Any] | None = None, session_id: str | None = None):
        self.demo = bool(demo)
        self.preferences = Preferences.from_mapping(preferences)
        self.generation = 0
        self.category = 0
        self._pages = [_Page() for _ in CATEGORIES]
        self._systems = _Page()
        self._games_view = "systems"
        self._system_id = ""
        self._system_label = ""
        self._search = ""
        self._history_filters = {"recent": "", "favorites": ""}
        self._history_records: dict[str, tuple[UIItem, ...]] = {}
        self._history_serial: dict[str, int] = {}
        self._game_information: Mapping[str, Any] = {}
        self._performance_status: Mapping[str, Any] = {}
        self._performance_generation = 0
        self._performance_transaction = ""
        self._performance_transaction_game = ""
        self._keyboard: Keyboard | None = None
        self._artwork_generation = 0
        self._dialog: Dialog | None = None
        self._serial = 0
        if session_id is not None and (not isinstance(session_id, str) or not 1 <= len(session_id) <= 64 or
                                       any(not (c.isascii() and (c.isalnum() or c in "_-")) for c in session_id)):
            raise ValueError("Invalid UI session identity")
        self._session_id = session_id or uuid.uuid4().hex
        self._pending: set[int] = set()
        self._query_serial = 0
        self._query_last_focus = False
        self._query_keep_focus = False
        self._favorites: set[str] = set()
        self._last_transaction = ""
        self._settings_view = "root"
        self._settings_parent_focus = ""
        self._controls_generation = 0
        self._controls_transaction = ""
        self._appearance_generation = 0
        self._appearance_transaction = ""
        self._hardware_generation = 0
        self._hardware_status: Mapping[str, Any] = {}
        self._experience_generation = 0
        self._experience_profile = ""
        self._experience_transaction = ""
        self._capabilities: Mapping[str, Any] = {}
        self._snapshot: Mapping[str, Any] = {}
        self._status = ""
        self.exit_request: str | None = None
        self._restored_focus: dict[str, str] = {}
        self._set_systems([])
        self._rebuild_settings()
        if restored_state and restored_state.get("schema", 1) == 1:
            value = restored_state.get("category", 0)
            self.category = value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 4 else 0
            focus = restored_state.get("focus", {})
            if isinstance(focus, Mapping):
                self._restored_focus = {str(k): _text(v, 1024) for k, v in focus.items()}
            view = restored_state.get("games_view", "systems")
            if view in ("systems", "all", "system", "favorites", "search"):
                self._games_view = view
            self._system_id = _text(restored_state.get("system_id", ""), 128)
            self._system_label = _text(restored_state.get("system_label", ""), 512)
            self._search = _text(restored_state.get("search", ""), 128).replace("\n", "")
            filters = restored_state.get("history_filters", {})
            if isinstance(filters, Mapping):
                self._history_filters = {key: _text(filters.get(key, ""), 128) for key in self._history_filters}
            if self._games_view == "system" and not self._system_id:
                self._games_view = "systems"

    def _request(self, method: str, params: Mapping[str, Any] | None = None,
                 context: str = "") -> UICommand:
        self._serial += 1
        self._pending.add(self._serial)
        return UICommand(self._serial, method, dict(params or {}), context)

    def initial_commands(self, *, preserve_focus: bool = False) -> list[UICommand]:
        commands = [self._request(method, {"refresh": True} if preserve_focus and method == "library.systems" else None,
                                  context=context) for method, context in (
            ("settings.get", "settings"), ("system.capabilities", "capabilities"),
            ("system.snapshot", "snapshot"), ("library.systems", "systems"),
            ("library.favorites", "favorites_cache"),
            ("tools.list", "tools"), ("hardware.status", "hardware_cache"))]
        commands.append(self._history_query("recent"))
        if self._games_view == "favorites":
            commands.append(self._history_query("favorites"))
        elif self._games_view != "systems":
            commands.append(self._query(self._pages[0].offset if preserve_focus else 0,
                                        keep_focus=preserve_focus))
        return commands

    def _page(self) -> _Page:
        if self.category == 0 and self._games_view == "systems":
            return self._systems
        return self._pages[self.category]

    def _focus_key(self) -> str:
        return "systems" if self.category == 0 and self._games_view == "systems" else str(self.category)

    def _restore_focus(self, page: _Page, key: str) -> None:
        identifier = self._restored_focus.pop(key, "")
        if identifier:
            page.selected = next((i for i, item in enumerate(page.items) if item.id == identifier), page.selected)

    def export_state(self) -> dict[str, Any]:
        focus = {}
        for key, page in [("systems", self._systems)] + [(str(i), page) for i, page in enumerate(self._pages)]:
            if 0 <= page.selected < len(page.items):
                focus[key] = page.items[page.selected].id
        return {"schema": 1, "category": self.category, "focus": focus,
                "games_view": self._games_view, "system_id": self._system_id,
                "system_label": self._system_label, "search": self._search,
                "history_filters": dict(self._history_filters)}

    def set_category_items(self, category: int | str, items: Iterable[UIItem | Mapping[str, Any]],
                           *, offset: int = 0, total: int | None = None) -> None:
        if isinstance(category, str):
            category = CATEGORIES.index(category)
        if not 0 <= category < 4:
            raise ValueError("Unknown category")
        kind = "tool" if category == 2 else "game"
        parsed = [item if isinstance(item, UIItem) else UIItem.from_record(item, kind) for item in items]
        self._pages[category].replace(parsed, offset=offset, total=total)
        if category == 0:
            self._games_view = "all"
        self._restore_focus(self._pages[category], str(category))

    def _set_systems(self, records: Iterable[Mapping[str, Any]]) -> None:
        items = [_menu("all", "All games", "Your existing collection"),
                 _menu("favorites", "Favorites", "The games you keep close"),
                 _menu("search", "Find a game", "Search across your collection"),
                 _menu("random", "Surprise me", "Choose an available game")]
        for value in records:
            identifier = _text(value.get("system_id", value.get("id", "")), 128)
            if not identifier:
                continue
            count = value.get("game_count", 0)
            count = count if isinstance(count, int) and count >= 0 else 0
            items.append(UIItem(identifier, _text(value.get("label", identifier)),
                                f"{count} games", "system", identifier,
                                available=value.get("availability", "available") == "available"))
        items.append(_menu("library_filters", "Library filters", "Combine a system with search, favorites or recents"))
        items.append(_menu("refresh_library", "Refresh library", "Reload game lists and changed artwork"))
        self._systems.replace(items)
        self._restore_focus(self._systems, "systems")

    def _query(self, offset: int = 0, *, keep_focus: bool = False,
               last_focus: bool = False) -> UICommand:
        params: dict[str, Any] = {"offset": offset, "limit": self.PAGE_SIZE}
        if self._system_id:
            params["system_id"] = self._system_id
        if self._search and self._games_view in ("system", "search", "all"):
            params["search"] = self._search
        command = self._request("library.query", params, "games")
        self._query_serial = command.serial
        self._query_keep_focus = keep_focus
        self._query_last_focus = last_focus
        return command

    def _history_query(self, kind: str) -> UICommand:
        params = {"system_id": self._history_filters[kind]} if self._history_filters[kind] else {}
        command = self._request("library." + kind, params, kind)
        self._history_serial[kind] = command.serial
        return command

    def _show_history_page(self, kind: str, offset: int = 0, *, keep_focus: bool = True,
                           last_focus: bool = False) -> None:
        items = self._history_records.get(kind, ())
        page = self._pages[1 if kind == "recent" else 0]
        previous = page.items[page.selected].id if keep_focus and 0 <= page.selected < len(page.items) else None
        absolute_focus = next((index for index, item in enumerate(items) if item.id == previous), None) if previous else None
        if absolute_focus is not None:
            offset = (absolute_focus // self.PAGE_SIZE) * self.PAGE_SIZE
        offset = min(max(0, offset), ((len(items) - 1) // self.PAGE_SIZE) * self.PAGE_SIZE) if items else 0
        page.replace(items[offset:offset + self.PAGE_SIZE], offset=offset,
                     total=len(items), keep_focus=keep_focus)
        if absolute_focus is not None:
            page.selected = absolute_focus - offset
        if last_focus and page.items:
            page.selected = len(page.items) - 1

    def _filter_dialog(self) -> None:
        target = "recent" if self.category == 1 else "favorites" if self._games_view == "favorites" else "games"
        selected = self._history_filters.get(target, self._system_id)
        choices = tuple(DialogChoice(label, "set_filter", params={"target": target, "system_id": system,
                                                                   "label": label})
                        for system, label in (("", "All systems"), ("PSP", "PSP"), ("PS", "PS1")))
        self._dialog = Dialog("Filter " + ("Continue Playing" if target == "recent" else "Favorites" if target == "favorites" else "Games"),
            "Current system: " + ({"": "All systems", "PSP": "PSP", "PS": "PS1"}.get(selected, selected)) +
            ("\nYour search stays combined with the selected system." if target == "games" else "\nExisting game identities and history order stay in place."),
            choices + (DialogChoice("Cancel"),))

    def receive(self, command: UICommand, result: Any) -> list[UICommand]:
        self._pending.discard(command.serial)
        context = command.context
        if context in ("settings", "apply", "undo"):
            if not isinstance(result, Mapping):
                raise ValueError("Settings reply must be an object")
            self.preferences = Preferences.from_mapping(result.get("preferences"))
            generation = result.get("generation", self.generation)
            if isinstance(generation, int) and generation >= 0:
                self.generation = generation
            if context == "apply":
                self._last_transaction = _text(result.get("transaction_id"), 256)
                self.notice("Preference updated. Undo is available in Settings.")
            elif context == "undo":
                self._last_transaction = ""
                self.notice("The previous preference was restored.")
            if self._settings_view == "root":
                self._rebuild_settings()
        elif context == "capabilities":
            self._capabilities = result if isinstance(result, Mapping) else {}
        elif context == "snapshot":
            self._snapshot = result if isinstance(result, Mapping) else {}
        elif context == "hardware_cache" or context.startswith("hardware:"):
            self._hardware_status = result if isinstance(result, Mapping) else {}
            generation = self._hardware_status.get("generation", 0)
            self._hardware_generation = generation if type(generation) is int and generation >= 0 else 0
            if context.startswith("hardware:"):
                keep_focus = self._settings_view == context
                self._settings_view = context
                self._rebuild_hardware(keep_focus=keep_focus)
            elif self._settings_view == "root":
                self._rebuild_settings()
        elif context == "hardware_preview":
            before = result.get("before")
            operation = result.get("operation")
            change = (("On" if result.get("after") else "Off") if operation == "toggle"
                      else "one level lower" if operation == "lower" else "one level higher")
            value = "On" if before is True else "Off" if before is False else str(before)
            message = "Current setting: " + value + "\nChange to " + change + ".\n" + _text(result.get("scope"))
            self._dialog = Dialog("Change " + _text(result.get("label", "device setting")).lower(), message,
                (DialogChoice("Apply through spruce", "request", "hardware.apply", {
                    "preview_id": result["preview_id"], "request_id": f"ui-{self._session_id}-hardware-{command.serial}",
                    "expected_generation": self._hardware_generation}, "hardware_apply"), DialogChoice("Cancel")), selected=1)
        elif context == "hardware_apply":
            generation = result.get("generation", self._hardware_generation)
            self._hardware_generation = generation if type(generation) is int and generation >= 0 else self._hardware_generation
            self.notice("Sent to spruce. Refresh status to see the current setting.")
            return [self._request("hardware.status", context=self._settings_view)]
        elif context == "hardware_route":
            if isinstance(result, Mapping) and result.get("state") == "releasing_ui":
                self.notice("Opening the existing spruce screen…")
        elif context == "game_info":
            if isinstance(result, Mapping):
                self._game_info_dialog(result)
        elif context == "performance_status":
            if isinstance(result, Mapping):
                self._performance_dialog(result)
        elif context == "performance_preview":
            rows = ["Candidate performance setting · untested."]
            for change in result.get("diff", [])[:8]:
                if isinstance(change, Mapping):
                    label = _text(change.get("label", change.get("option_id", "Setting")), 128)
                    before, after = change.get("before"), change.get("after")
                    rows.append(label + ": " + ("Use global setting" if before is None else str(before)) +
                                " → " + ("Use global setting" if after is None else str(after)))
            rows.extend(_text(warning, 512) for warning in result.get("warnings", [])[:8] if isinstance(warning, str))
            rows.append("Only the selected per-game options change. Review image quality and motion tradeoffs before applying.")
            self._dialog = Dialog("Review performance change", "\n".join(rows), (
                DialogChoice("Apply per-game change", "request", "performance.apply", {
                    "preview_id": result["preview_id"], "request_id": f"ui-{self._session_id}-performance-{command.serial}",
                    "expected_generation": self._performance_generation}, "performance_apply"), DialogChoice("Cancel")), selected=1)
        elif context in ("performance_apply", "performance_undo"):
            if result.get("applied") is not True:
                raise ValueError("The performance change was not confirmed")
            self._performance_transaction = _text(result.get("transaction_id"), 256) if context == "performance_apply" else ""
            self._performance_transaction_game = _text(result.get("game_id", self._performance_status.get("game_id", "")), 1024) if context == "performance_apply" else ""
            self.notice("Per-game performance setting updated. Candidate remains untested." if context == "performance_apply" else "The previous per-game settings were restored.")
            return [self._request("performance.status", {"game_id": result.get("game_id", self._performance_status.get("game_id", ""))}, "performance_status")]
        elif context == "backup_status":
            if isinstance(result, Mapping):
                self._backup_dialog(result)
        elif context == "backup_action":
            if isinstance(result, Mapping):
                if "status" in result:
                    self._backup_dialog(result)
                elif result.get("path"):
                    self._dialog = Dialog("Diagnostic report saved", _text(result["path"], 2048))
                else:
                    self._dialog = Dialog("Recovery instructions", _text(result.get("message"), 8192) or "Use the existing verified recovery tools and expendable media.")
        elif context == "game_options":
            if isinstance(result, Mapping) and result.get("state") == "releasing_ui":
                self.notice("Opening this game's existing spruce options…")
            else:
                self.notice("The game-options screen has not been accepted.")
        elif context == "experience":
            keep_focus = self._settings_view == context
            self._settings_view = "experience"
            generation = result.get("generation", 0)
            self._experience_generation = generation if type(generation) is int and generation >= 0 else 0
            self._experience_profile = _text(result.get("profile_id"), 256)
            available = result.get("adoption_available") is True
            reason = _text(result.get("reason")) or "PPSSPP menu matching is unavailable for this installed version. Its current settings stay in place."
            confirm = result.get("configured_confirm")
            theme = _text(result.get("theme"), 128)
            current = ("Confirm: " + self._format_preference(confirm) + (" · " + theme if theme else "")) if confirm in ("south", "east") else "One review for Confirm, theme and background motion"
            items = [UIItem("experience_match", "Match controls & appearance", current,
                            "experience_profile", available=available, reason=reason)]
            if self._experience_transaction:
                items.append(_menu("experience_undo", "Undo last matching change", "Restore only this combined menu transaction"))
            self._pages[3].replace(items, keep_focus=keep_focus)
        elif context == "experience_preview":
            if result.get("adoption_available") is not True:
                self._dialog = Dialog("PPSSPP matching unavailable", "This PPSSPP version is not ready for shared menu changes. Continue using its current menus.")
                return []
            rows = []
            for entry in result.get("diff", [])[:8]:
                if isinstance(entry, Mapping):
                    label = _text(entry.get("key", entry.get("field", "Setting")), 128)
                    rows.append(label + ": " + _text(str(entry.get("before")), 128) + " → " + _text(str(entry.get("after")), 128))
            message = "\n".join(rows) or "Match the current interface's Confirm button, original theme and background motion."
            message += "\nGameplay controls stay separate. Apply while PPSSPP is stopped."
            overrides = result.get("per_game_overrides", [])
            if isinstance(overrides, (list, dict)) and overrides:
                message += f"\n{len(overrides)} per-game profile(s) keep their existing overrides; those may take precedence."
            params = {"preview_id": result["preview_id"], "request_id": f"ui-{self._session_id}-experience-{command.serial}",
                      "expected_generation": self._experience_generation}
            if result.get("overwrites_existing_theme") is True:
                message += "\nThis replaces an existing theme file; a backup is retained."
                params["confirm_overwrite"] = True
            self._dialog = Dialog("Review PPSSPP matching", message,
                (DialogChoice("Apply combined changes", "request", "experience.ppsspp.apply", params, "experience_apply"),
                 DialogChoice("Cancel")), selected=1)
        elif context in ("experience_apply", "experience_undo"):
            generation = result.get("generation", self._experience_generation)
            self._experience_generation = generation if type(generation) is int and generation >= 0 else self._experience_generation
            self._experience_transaction = _text(result.get("transaction_id"), 256) if context == "experience_apply" else ""
            self.notice("PPSSPP menu controls and appearance updated together." if context == "experience_apply" else "The previous PPSSPP menu settings were restored together.")
            return [self._request("experience.ppsspp.status", context="experience")]
        elif context == "systems":
            self._set_systems(value for value in result if isinstance(value, Mapping))
        elif context == "games":
            if command.serial != self._query_serial:
                return []
            values = result.get("items", []) if isinstance(result, Mapping) else []
            items = [UIItem.from_record(value) for value in values if isinstance(value, Mapping)]
            offset = result.get("offset", 0)
            total = result.get("total", len(items))
            if (self._query_keep_focus and not items and type(total) is int and
                    type(offset) is int and 0 < total <= offset):
                # A refreshed collection can shrink past the old page. Retain
                # its focus until the last surviving page is available.
                last_page = ((total - 1) // self.PAGE_SIZE) * self.PAGE_SIZE
                return [self._query(last_page, keep_focus=True)]
            self._pages[0].replace(items, offset=offset, total=total, keep_focus=self._query_keep_focus)
            if self._query_last_focus and items:
                self._pages[0].selected = len(items) - 1
            self._query_last_focus = False
            self._query_keep_focus = False
            self._restore_focus(self._pages[0], "0")
        elif context in ("recent", "favorites", "favorites_cache"):
            if context != "favorites_cache" and command.serial != self._history_serial.get(context, command.serial):
                return []
            items = tuple(UIItem.from_record(value) for value in result if isinstance(value, Mapping))
            if context == "favorites_cache" or (context == "favorites" and not self._history_filters["favorites"]):
                self._favorites = {item.id for item in items}
            elif context == "favorites":
                self._favorites.update(item.id for item in items)
            if context != "favorites_cache":
                self._history_records[context] = items
                page = self._pages[1 if context == "recent" else 0]
                self._show_history_page(context, page.offset)
                self._restore_focus(page, "1" if context == "recent" else "0")
        elif context == "tools":
            self._pages[2].replace(UIItem.from_record(value, "tool") for value in result if isinstance(value, Mapping))
            self._restore_focus(self._pages[2], "2")
        elif context == "random":
            self._launch_dialog(UIItem.from_record(result))
        elif context == "favorite_set":
            identifier = command.params.get("game_id", "")
            if command.params.get("enabled"):
                self._favorites.add(identifier)
                self.notice("Added to Favorites.")
            else:
                self._favorites.discard(identifier)
                self.notice("Removed from Favorites.")
            if self._games_view == "favorites":
                return [self._history_query("favorites")]
        elif context == "preview":
            key = next(iter(command.params["changes"]))
            diff = result.get("diff", [])
            message = "Only this interface preference will change. Gameplay mappings stay as they are."
            if diff:
                message = f"{self._format_preference(diff[0].get('before'))}  →  {self._format_preference(diff[0].get('after'))}\n" + message
            choice = DialogChoice("Apply", "request", "settings.apply", {
                "preview_id": result["preview_id"], "request_id": f"ui-{self._session_id}-apply-{command.serial}",
                "expected_generation": self.generation}, "apply")
            self._dialog = Dialog("Change " + self._preference_label(key).lower(), message,
                                  (choice, DialogChoice("Cancel")))
        elif context == "launch":
            if isinstance(result, Mapping) and result.get("state") == "releasing_ui":
                self.exit_request = "launch"
            else:
                self.notice("The launch has not been accepted. Your current interface remains active.")
        elif context == "switch":
            if isinstance(result, Mapping) and (result.get("state") == "releasing_ui" or result.get("interface") == "classic"):
                self.exit_request = "classic"
            else:
                self.notice("The interface switch has not been accepted.")
        elif context == "support":
            location = _text(result.get("path", result.get("output", ""))) if isinstance(result, Mapping) else ""
            self._dialog = Dialog("Diagnostic report saved", location or "The redacted report is ready.", (DialogChoice("Done"),))
        elif context == "controls":
            keep_focus = self._settings_view == context
            self._settings_view = "controls"
            generation = result.get("generation", 0)
            self._controls_generation = generation if isinstance(generation, int) and generation >= 0 else 0
            profiles = result.get("profiles", [])
            items = []
            for entry in profiles:
                if not isinstance(entry, Mapping):
                    continue
                identifier = _text(entry.get("profile_id"), 256)
                if not identifier:
                    continue
                writable = entry.get("writable", False) is True
                error = entry.get("error", {})
                reason = _text(error.get("message", ""), 2048) if isinstance(error, Mapping) else ""
                surface = _text(entry.get("surface", ""), 128)
                configured = entry.get("configured_confirm")
                state = (("Confirm: " + self._format_preference(configured))
                         if entry.get("configuration_effective") is True and configured in ("south", "east")
                         else "Ready to configure" if writable else "Unavailable on this profile")
                items.append(UIItem(identifier, _text(entry.get("label", identifier)),
                                    (surface + " · " if surface else "") + state,
                                    "control_profile", available=writable, reason=reason))
            if not items:
                items.append(_menu("controls_info", "No qualified menu profiles", _text(result.get("reason")) or "Your existing emulator mappings remain unchanged"))
            if self._controls_transaction:
                items.append(_menu("controls_undo", "Undo last menu change", "Restore only the menu keys changed by this interface"))
            self._pages[3].replace(items, keep_focus=keep_focus)
        elif context == "controls_preview":
            diff = result.get("diff", [])
            lines = [_text(result.get("profile_id"), 256)]
            for entry in diff[:3]:
                before = entry.get("before")
                after = entry.get("after")
                show = lambda value: "Unset" if value is None else "On" if value is True else "Off" if value is False else str(value)
                label = {"IndependentMenuControls": "Independent menu controls",
                         "NativeMenuConfirm": "Confirm button", "NativeMenuBack": "Back button"}.get(entry.get("key"), _text(entry.get("key")))
                lines.append(f"{label}: {show(before)} → {show(after)}")
            lines.append("Gameplay mappings stay unchanged. Apply only while the emulator is stopped.")
            self._dialog = Dialog("Review emulator menu changes", "\n".join(lines),
                (DialogChoice("Apply menu changes", "request", "controls.apply", {
                    "preview_id": result["preview_id"], "request_id": f"ui-{self._session_id}-controls-apply-{command.serial}",
                    "expected_generation": self._controls_generation}, "controls_apply"), DialogChoice("Cancel")))
        elif context in ("controls_apply", "controls_undo"):
            generation = result.get("generation", self._controls_generation)
            self._controls_generation = generation if isinstance(generation, int) and generation >= 0 else self._controls_generation
            self._controls_transaction = _text(result.get("transaction_id"), 256) if context == "controls_apply" else ""
            self.notice("Emulator menu controls updated. Gameplay mappings were preserved." if context == "controls_apply" else "The previous emulator menu controls were restored.")
            return [self._request("controls.capabilities", context="controls")]
        elif context == "appearance":
            keep_focus = self._settings_view == context
            self._settings_view = "appearance"
            generation = result.get("generation", 0)
            self._appearance_generation = generation if type(generation) is int and generation >= 0 else 0
            current = _text(result.get("theme")) or "Unverified"
            preview_available = result.get("preview_available") is True
            reason = _text(result.get("reason")) or "The installed PPSSPP version, paths and configuration writers need verification."
            items = [UIItem("appearance_match", "Match this interface", "Current PPSSPP theme: " + current,
                            "appearance_profile", available=preview_available, reason=reason)]
            if self._appearance_transaction:
                items.append(_menu("appearance_undo", "Undo last PPSSPP appearance change", "Restore the previous theme and background motion"))
            self._pages[3].replace(items, keep_focus=keep_focus)
        elif context == "appearance_preview":
            if result.get("adoption_available") is not True:
                self._dialog = Dialog("PPSSPP appearance unavailable", "The installed emulator and its configuration writers must be verified and stopped before applying appearance changes.")
                return []
            theme = _text(command.params.get("theme"))
            motion = command.params.get("motion") is True
            message = theme + "\n" + ("Animated waves" if motion else "Still background")
            overwrite = result.get("overwrites_existing_theme") is True
            if overwrite:
                message += "\nAn existing Spruce Midnight palette will be replaced. A backup will be kept for Undo."
            message += "\nPPSSPP will use these choices next time it starts."
            self._dialog = Dialog("Review PPSSPP appearance", message,
                (DialogChoice("Replace palette and apply" if overwrite else "Apply appearance", "request", "appearance.ppsspp.apply", {
                    "preview_id": result["preview_id"], "request_id": f"ui-{self._session_id}-appearance-apply-{command.serial}",
                    "expected_generation": self._appearance_generation, "confirm_overwrite": overwrite}, "appearance_apply"),
                 DialogChoice("Cancel")), selected=1 if overwrite else 0)
        elif context in ("appearance_apply", "appearance_undo"):
            if result.get("applied") is not True:
                raise ValueError("The PPSSPP appearance change was not confirmed")
            generation = result.get("generation", self._appearance_generation)
            if type(generation) is int and generation >= 0:
                self._appearance_generation = generation
            self._appearance_transaction = _text(result.get("transaction_id"), 256) if context == "appearance_apply" else ""
            self.notice("PPSSPP appearance updated for its next start." if context == "appearance_apply" else "The previous PPSSPP appearance was restored.")
            return [self._request("appearance.ppsspp.status", context="appearance")]
        return []

    def error(self, command: UICommand | None, code: str, message: str) -> None:
        if command:
            self._pending.discard(command.serial)
        self._dialog = Dialog("Unable to complete that action", _text(message, 2048) + "\n" + _text(code, 128), error=True)

    def notice(self, message: str) -> None:
        self._status = _text(message, 512)

    @staticmethod
    def _preference_label(key: str) -> str:
        return {"confirm": "Confirm button", "motion": "Background motion", "sound": "Interface sounds",
                "text_scale": "Text size", "high_contrast": "High contrast"}.get(key, key)

    @staticmethod
    def _format_preference(value: Any) -> str:
        if isinstance(value, bool):
            return "On" if value else "Off"
        if isinstance(value, (float, int)):
            return f"{value * 100:.0f}%"
        return {"south": "South button", "east": "East button"}.get(str(value), str(value))

    def _rebuild_settings(self) -> None:
        items = [UIItem(key, self._preference_label(key), self._format_preference(getattr(self.preferences, key)), "setting")
                 for key in ("confirm", "motion", "sound", "text_scale", "high_contrast")]
        items.extend((_menu("controls", "Emulator menu controls", "Keep gameplay mappings separate"),
                      _menu("appearance", "PPSSPP appearance", "Match the theme, contrast and background motion"),
                      _menu("experience", "Match PPSSPP menus", "Review controls and appearance together"),
                      _menu("hardware_display", "Display", "Screen brightness and existing display settings"),
                      _menu("hardware_sound", "Sound", "System volume and audio-device settings"),
                      _menu("hardware_network", "Network", "Wi-Fi, Bluetooth and existing pairing screens"),
                      _menu("hardware_controllers", "Controllers", "Existing input and calibration authorities"),
                      _menu("hardware_power", "Power & USB", "Save-aware power and clean-unmount storage routes"),
                      _menu("backup", "Backups & recovery", "Verified backup readbacks and supported recovery actions"),
                      _menu("device", "System status", "Capabilities and firmware availability"),
                      _menu("support", "Save diagnostic report", "Redacted component and failure information"),
                      _menu("about", "About & credits", "Version, source credits and license information")))
        advanced = next((row for row in self._hardware_status.get("routes", [])
                         if isinstance(row, Mapping) and row.get("route_id") == "advanced"), {})
        items.append(UIItem("advanced", "All spruce settings", "Keep advanced settings in their existing authority",
                            "hardware_route", available=advanced.get("available") is True,
                            reason=_text(advanced.get("reason")) or "Open the existing full settings screen from classic spruce."))
        if self._last_transaction:
            items.append(_menu("undo", "Undo last preference change", "Restore only the setting this interface changed"))
        items.append(_menu("classic", "Return to spruce", "Use the existing interface"))
        self._pages[3].replace(items)
        self._restore_focus(self._pages[3], "3")

    def _rebuild_hardware(self, *, keep_focus: bool = True) -> None:
        group = self._settings_view.split(":", 1)[1]
        items = []
        for row in self._hardware_status.get("controls", []):
            if not isinstance(row, Mapping) or row.get("group") != group:
                continue
            items.append(UIItem(_text(row.get("control_id"), 64), _text(row.get("label")),
                _text(row.get("value_text", "Unavailable")), "hardware_control",
                available=row.get("writable") is True, reason=_text(row.get("reason"))))
        route_groups = {"display": ("advanced",), "sound": ("bluetooth", "advanced"),
                        "network": ("wifi", "bluetooth"), "controllers": ("controllers",),
                        "power": ("power", "usb")}
        for row in self._hardware_status.get("routes", []):
            if not isinstance(row, Mapping) or row.get("route_id") not in route_groups.get(group, ()):
                continue
            items.append(UIItem(_text(row.get("route_id"), 64), _text(row.get("label")),
                _text(row.get("description")), "hardware_route", available=row.get("available") is True,
                reason=_text(row.get("reason"))))
        items.append(_menu("hardware_refresh", "Refresh status", "Read current values from the existing authority"))
        self._pages[3].replace(items, keep_focus=keep_focus)

    def _game_info_dialog(self, value: Mapping[str, Any]) -> None:
        self._game_information = value
        item = UIItem.from_record(value)
        rows = ["System: " + (item.system_label or item.system_id or "Unavailable"),
                "Emulator: " + (item.selected_emulator or "Current system emulator"),
                "Preset: " + (item.selected_preset or "Current system setting"),
                "Availability: " + item.availability.replace("_", " ")]
        if value.get("preset_repair_required") is True:
            rows.append("The saved emulator choice is unavailable. Review existing Game options before launching.")
        if item.resume_available and not self.demo:
            rows.append("Resume available for this boot.")
            recorded = _checkpoint_utc(item.state_recorded_at)
            if recorded:
                rows.append("Checkpoint verified " + recorded)
        else:
            rows.append("Sample Resume card" if self.demo and item.resume_available else "Recently played · Resume unavailable" if self.category == 1 else "Resume unavailable")
            rows.append(item.reason or "No authenticated compatible checkpoint is available. Start normally to use in-game saves.")
        disc_set = value.get("disc_set", {})
        if isinstance(disc_set, Mapping) and disc_set.get("kind") not in (None, "none"):
            count = disc_set.get("disc_count")
            if type(count) is int:
                rows.append(f"Disc set: {count} disc(s)")
            discs = disc_set.get("discs", [])
            if isinstance(discs, list):
                for number, disc in enumerate(discs[:20], 1):
                    if isinstance(disc, Mapping):
                        rows.append(f"Disc {number}: " + _text(disc.get("label", disc.get("relative_path", "")), 256) +
                                    (" · available" if disc.get("available") is True else " · missing"))
                if len(discs) > 20:
                    rows.append(f"{len(discs) - 20} further disc entries; inspect the existing playlist for the complete set.")
            warnings = disc_set.get("warnings", [])
            if isinstance(warnings, list):
                rows.extend("Disc warning: " + _warning_message(warning) for warning in warnings[:12] if isinstance(warning, str))
            management = value.get("disc_management", {})
            if isinstance(management, Mapping):
                rows.append(_text(management.get("description"), 1024) or "Change discs in the selected emulator's existing in-game menu.")
        warnings = value.get("warnings", [])
        disc_warnings = disc_set.get("warnings", []) if isinstance(disc_set, Mapping) else []
        if isinstance(warnings, list):
            rows.extend("Warning: " + _warning_message(warning) for warning in warnings[:8]
                        if isinstance(warning, str) and warning not in disc_warnings)
        choices = []
        if item.available and not value.get("preset_repair_required"):
            if item.resume_available:
                choices.append(DialogChoice("Resume", "demo_launch" if self.demo else "request", "game.launch",
                    {"game_id": item.id, "preset_id": "", "mode": "resume"}, "launch"))
            choices.append(DialogChoice("Fresh start" if item.resume_available or self.category == 1 else "Start game",
                "demo_launch" if self.demo else "request", "game.launch",
                {"game_id": item.id, "preset_id": "", "mode": "fresh" if item.resume_available or self.category == 1 else "normal"}, "launch"))
        if item.system_id.casefold() == "psp":
            choices.append(DialogChoice("Performance options", "request", "performance.status", {"game_id": item.id}, "performance_status"))
        if self._capabilities.get("game_options") is True:
            choices.append(DialogChoice("Existing emulator options", "demo_launch" if self.demo else "request", "game.options",
                {"game_id": item.id}, "game_options"))
        choices.append(DialogChoice("Back"))
        self._dialog = Dialog(item.title, "\n".join(row for row in rows if row), tuple(choices),
                              artwork=item.artwork, system_id=item.system_id)

    def _performance_dialog(self, value: Mapping[str, Any]) -> None:
        self._performance_status = value
        generation = value.get("generation", 0)
        self._performance_generation = generation if type(generation) is int and generation >= 0 else 0
        rows = ["Per-game settings · candidate presets untested.",
                "No measured gameplay improvement is claimed. Native settings apply the next time this game starts."]
        choices = []
        if value.get("writable") is True:
            for option in value.get("options", [])[:8]:
                if not isinstance(option, Mapping):
                    continue
                label = _text(option.get("label", option.get("id", "")), 128)
                current = option.get("value")
                current_label = "Use global setting" if current is None else str(current)
                for choice in option.get("choices", []):
                    if isinstance(choice, Mapping) and choice.get("value") == current:
                        current_label = _text(choice.get("label")) or current_label
                        break
                rows.append(label + ": " + current_label)
                choices.append(DialogChoice(label, "performance_option", params={"option_id": option.get("id", "")}))
            if self._performance_transaction and self._performance_transaction_game == value.get("game_id"):
                choices.append(DialogChoice("Undo last performance change", "request", "performance.undo",
                    {"transaction_id": self._performance_transaction,
                     "request_id": f"ui-{self._session_id}-performance-undo-{self._serial + 1}",
                     "expected_generation": self._performance_generation}, "performance_undo"))
        else:
            rows.append(_text(value.get("reason"), 2048) or "This installed emulator profile is not qualified for settings changes. Use its existing options.")
        choices.append(DialogChoice("Back"))
        self._dialog = Dialog("Per-game performance", "\n".join(rows), tuple(choices))

    def _performance_option_dialog(self, identifier: str) -> None:
        option = next((value for value in self._performance_status.get("options", [])
                       if isinstance(value, Mapping) and value.get("id") == identifier), None)
        if option is None:
            return
        game_id = _text(self._performance_status.get("game_id"), 1024)
        choices = []
        descriptions = [_text(option.get("description"), 2048), "Candidate setting · untested on this device."]
        for value in option.get("choices", [])[:12]:
            if not isinstance(value, Mapping):
                continue
            label = _text(value.get("label"), 128)
            explanation = _text(value.get("description"), 512)
            if explanation:
                descriptions.append(label + ": " + explanation)
            choices.append(DialogChoice(label, "request", "performance.preview",
                {"game_id": game_id, "changes": {identifier: value.get("value")},
                 "expected_generation": self._performance_generation}, "performance_preview"))
        choices.append(DialogChoice("Cancel"))
        self._dialog = Dialog(_text(option.get("label", identifier)), "\n".join(descriptions), tuple(choices))

    def _backup_dialog(self, value: Mapping[str, Any]) -> None:
        status = _text(value.get("status", "unavailable"), 64)
        rows = ["Verified backup bytes" if status == "verified" else "Some backup scopes verified" if status == "partial" else "Verified backup unavailable"]
        timestamp = _checkpoint_utc(value.get("verified_at_utc", ""))
        if timestamp and status in ("verified", "partial"):
            rows.append("Backup readback verified " + timestamp)
        scope = value.get("scope", "")
        scope_labels = {"card-files": "Card files", "saves": "Saves", "internal-files": "Internal files"}
        if isinstance(scope, list):
            scope = ", ".join(scope_labels.get(entry, _text(entry, 128)) for entry in scope if isinstance(entry, str))
        if isinstance(scope, str) and scope:
            rows.append("Scope: " + _text(scope, 1024))
        for readback in value.get("readbacks", [])[:8]:
            if isinstance(readback, Mapping):
                label = scope_labels.get(readback.get("scope"), "Selected scope")
                rows.append(label + ": " + ("backup bytes verified" if readback.get("status") == "verified" else "backup unavailable"))
                if readback.get("status") != "verified" and readback.get("reason"):
                    rows.append(_text(readback["reason"], 512))
        rows.append(_text(value.get("reason"), 2048))
        rows.append("Backup byte verification does not establish independent-media retention or physical restoration.")
        choices = []
        for action in value.get("supported_actions", [])[:8]:
            if isinstance(action, Mapping) and action.get("available") is True:
                identifier = action.get("id", action.get("action_id"))
                if identifier in ("recheck", "recovery_guide", "support_export"):
                    choices.append(DialogChoice(_text(action.get("label", identifier), 128), "request", "backup.action",
                                                {"action_id": identifier}, "backup_action"))
        choices.append(DialogChoice("Back"))
        self._dialog = Dialog("Backups & recovery", "\n".join(row for row in rows if row), tuple(choices))

    def _launch_dialog(self, item: UIItem) -> None:
        if not item.available:
            choices = ((DialogChoice("Game information", "request", "game.info", {"game_id": item.id}, "game_info"), DialogChoice("Back"))
                       if self._capabilities.get("game_information") is True else (DialogChoice("Back"),))
            self._dialog = Dialog(item.title, item.reason or "This entry needs a reviewed launcher or dependency. Your files remain unchanged.",
                                  choices, error=True, artwork=item.artwork, system_id=item.system_id)
            return
        choices: list[DialogChoice] = []
        message = "System: " + (item.system_label or item.system_id)
        if item.selected_emulator:
            message += "\nEmulator: " + item.selected_emulator
        if item.selected_preset:
            message += "\nPreset: " + item.selected_preset
        message += "\nAvailability: " + item.availability.replace("_", " ")
        if item.resume_available:
            choices.append(DialogChoice("Resume", "demo_launch" if self.demo else "request", "game.launch",
                                         {"game_id": item.id, "preset_id": "", "mode": "resume"}, "launch"))
            message += ("\nSample resume card. This demonstration is not an emulator state." if self.demo else
                        "\nResume available · verified for this boot.")
            recorded = _checkpoint_utc(item.state_recorded_at) if not self.demo else ""
            if recorded:
                message += "\nCheckpoint verified " + recorded
        elif self.category == 1:
            message += "\nRecently played · Resume unavailable.\n" + (item.reason or "No verified resume state is available. Start normally to use your in-game saves.")
        fresh = self.category == 1 or item.resume_available
        choices.append(DialogChoice("Fresh start" if fresh else "Start game", "demo_launch" if self.demo else "request", "game.launch",
                                     {"game_id": item.id, "preset_id": "", "mode": "fresh" if fresh else "normal"}, "launch"))
        if self._capabilities.get("game_information") is True:
            choices.append(DialogChoice("Game information", "request", "game.info", {"game_id": item.id}, "game_info"))
        elif self._capabilities.get("game_options") is True:
            choices.append(DialogChoice("Game options", "demo_launch" if self.demo else "request", "game.options",
                                        {"game_id": item.id}, "game_options"))
        choices.append(DialogChoice("Cancel"))
        self._dialog = Dialog(item.title, message, tuple(choices), artwork=item.artwork, system_id=item.system_id)

    def _activate(self, item: UIItem) -> list[UICommand]:
        if self.category == 3 and self._settings_view == "root":
            self._settings_parent_focus = item.id
        if item.kind == "game":
            self._launch_dialog(item)
        elif item.kind == "system":
            self._games_view = "system"
            self._system_id, self._system_label = item.system_id, item.title
            self._pages[0] = _Page()
            return [self._query()]
        elif item.kind == "tool":
            if not item.available:
                self._dialog = Dialog(item.title, item.reason or "Open this tool from the classic spruce interface until its handoff is verified.",
                                      (DialogChoice("Return to spruce", "classic"), DialogChoice("Back")), selected=1)
            else:
                self._dialog = Dialog(item.title, "This installed tool keeps its own interface.",
                                      (DialogChoice("Open tool", "demo_launch" if self.demo else "request", "tool.launch", {"tool_id": item.id}, "launch"),
                                       DialogChoice("Cancel")))
        elif item.kind == "control_profile":
            if not item.available:
                self._dialog = Dialog(item.title, item.reason or "This emulator profile is not qualified for independent menu changes. Its existing mappings stay unchanged.", error=True)
            else:
                self._dialog = Dialog(item.title, "Choose the physical Confirm button for this emulator's menu. The existing gameplay mapping stays unchanged.", (
                    DialogChoice("South Confirm", "request", "controls.preview", {"profile_id": item.id, "confirm": "south", "expected_generation": self._controls_generation}, "controls_preview"),
                    DialogChoice("East Confirm", "request", "controls.preview", {"profile_id": item.id, "confirm": "east", "expected_generation": self._controls_generation}, "controls_preview"),
                    DialogChoice("Cancel")))
        elif item.kind == "appearance_profile":
            if not item.available:
                self._dialog = Dialog("PPSSPP appearance unavailable", item.reason)
            else:
                from ..ppsspp import THEME_NAMES
                return [self._request("appearance.ppsspp.preview", {
                    "theme": THEME_NAMES[1 if self.preferences.high_contrast else 0],
                    "motion": self.preferences.motion,
                    "expected_generation": self._appearance_generation}, "appearance_preview")]
        elif item.kind == "hardware_control":
            if not item.available:
                self._dialog = Dialog(item.title + " unavailable", item.reason or "Use the existing spruce controls for this setting.",
                                      (DialogChoice("Return to spruce", "classic"), DialogChoice("Back")), selected=1)
            else:
                row = next((row for row in self._hardware_status.get("controls", []) if row.get("control_id") == item.id), {})
                if row.get("kind") == "toggle":
                    return [self._request("hardware.preview", {"control_id": item.id, "operation": "toggle",
                        "expected_generation": self._hardware_generation}, "hardware_preview")]
                self._dialog = Dialog(item.title, "Current setting: " + item.subtitle + "\nEach change uses one step of the existing spruce control.", (
                    DialogChoice("Lower one step", "request", "hardware.preview", {"control_id": item.id, "operation": "lower", "expected_generation": self._hardware_generation}, "hardware_preview"),
                    DialogChoice("Raise one step", "request", "hardware.preview", {"control_id": item.id, "operation": "raise", "expected_generation": self._hardware_generation}, "hardware_preview"),
                    DialogChoice("Cancel")), selected=2)
        elif item.kind == "hardware_route":
            if not item.available:
                self._dialog = Dialog(item.title, item.reason or "Open this screen from classic spruce.",
                    (DialogChoice("Return to spruce", "classic"), DialogChoice("Back")), selected=1)
            else:
                self._dialog = Dialog(item.title, item.subtitle + ".\nThis screen retains its existing spruce controls.",
                    (DialogChoice("Open spruce screen", "request", "hardware.route", {"route_id": item.id}, "hardware_route"),
                     DialogChoice("Cancel")), selected=1)
        elif item.kind == "experience_profile":
            if not item.available:
                self._dialog = Dialog("PPSSPP matching unavailable", item.reason)
            else:
                from ..ppsspp import THEME_NAMES
                return [self._request("experience.ppsspp.preview", {"profile_id": self._experience_profile,
                    "confirm": self.preferences.confirm, "theme": THEME_NAMES[1 if self.preferences.high_contrast else 0],
                    "motion": self.preferences.motion, "expected_generation": self._experience_generation}, "experience_preview")]
        elif item.kind == "setting":
            value = getattr(self.preferences, item.id)
            if isinstance(value, bool):
                value = not value
            elif item.id == "confirm":
                value = "east" if value == "south" else "south"
            elif item.id == "text_scale":
                value = 1.15 if value < 1.1 else 1.3 if value < 1.25 else 1.5 if value < 1.45 else 1.0
            return [self._request("settings.preview", {"changes": {item.id: value}, "expected_generation": self.generation}, "preview")]
        elif item.id == "all":
            self._system_id, self._system_label, self._search = "", "", ""
            self._games_view = "all"
            self._pages[0] = _Page()
            return [self._query()]
        elif item.id == "favorites":
            self._games_view = "favorites"
            self._pages[0] = _Page()
            return [self._history_query("favorites")]
        elif item.id == "search":
            self._keyboard = Keyboard(self._search, 0)
        elif item.id == "random":
            return [self._request("library.random", context="random")]
        elif item.id == "library_filters":
            self._filter_dialog()
        elif item.id == "backup":
            return [self._request("backup.status", context="backup_status")]
        elif item.id == "refresh_library":
            return self.handle("refresh")
        elif item.id == "undo":
            return [self._request("settings.undo", {"transaction_id": self._last_transaction,
                        "request_id": f"ui-{self._session_id}-undo-{self._serial + 1}", "expected_generation": self.generation}, "undo")]
        elif item.id == "controls":
            return [self._request("controls.capabilities", context="controls")]
        elif item.id == "appearance":
            return [self._request("appearance.ppsspp.status", context="appearance")]
        elif item.id == "experience":
            return [self._request("experience.ppsspp.status", context="experience")]
        elif item.id == "experience_undo":
            return [self._request("experience.ppsspp.undo", {"transaction_id": self._experience_transaction,
                "request_id": f"ui-{self._session_id}-experience-undo-{self._serial + 1}",
                "expected_generation": self._experience_generation}, "experience_undo")]
        elif item.id.startswith("hardware_") and item.id != "hardware_refresh":
            return [self._request("hardware.status", context="hardware:" + item.id[len("hardware_"):])]
        elif item.id == "hardware_refresh":
            return [self._request("hardware.status", context=self._settings_view)]
        elif item.id == "appearance_undo":
            return [self._request("appearance.ppsspp.undo", {"transaction_id": self._appearance_transaction,
                        "request_id": f"ui-{self._session_id}-appearance-undo-{self._serial + 1}",
                        "expected_generation": self._appearance_generation}, "appearance_undo")]
        elif item.id == "controls_info":
            self._dialog = Dialog("Menu controls keep games intact", "No installed emulator profile is qualified for this action. "
                                  "RetroArch can expose independent menu controls; PPSSPP needs a verified independent mapping. "
                                  "Your current gameplay and menu settings remain unchanged.", (DialogChoice("Done"),))
        elif item.id == "controls_undo":
            return [self._request("controls.undo", {"transaction_id": self._controls_transaction,
                        "request_id": f"ui-{self._session_id}-controls-undo-{self._serial + 1}",
                        "expected_generation": self._controls_generation}, "controls_undo")]
        elif item.id == "device":
            profile = _text(self._snapshot.get("profile_id", self._snapshot.get("profile", "No verified device profile")))
            self._dialog = Dialog("System status", profile + "\n" + ("Desktop preview with sample data. Hardware readings are unavailable." if self.demo else
                                  "Only verified firmware functions are exposed. Unavailable readings remain unknown."), (DialogChoice("Done"),))
        elif item.id == "power_usb":
            self._dialog = Dialog("Power & USB", "A safe handoff must close games and storage users first. "
                                  "Use the existing spruce controls until these device transitions are verified.", (DialogChoice("Back"),))
        elif item.id == "support":
            return [self._request("support.export", context="support")]
        elif item.id == "about":
            from .. import __version__
            self._dialog = Dialog("About & credits", f"Version {__version__}\nOriginal interface for spruce.\n"
                                  "PyUI — Copyright (c) 2025 Christopher Jacobs.\nUsed under its non-commercial license.\n"
                                  "Optional PPSSPP changes retain separate GPL notices.\n"
                                  "Original Smart Pro hardware qualification is pending.", (DialogChoice("Done"),))
        elif item.id == "classic":
            self._dialog = Dialog("Return to spruce?", "Your existing games, saves and emulator settings stay in place.",
                                  (DialogChoice("Return to spruce", "classic"), DialogChoice("Stay here")), selected=1)
        return []

    def _activate_choice(self, choice: DialogChoice) -> list[UICommand]:
        self._dialog = None
        if choice.action == "set_filter":
            target = choice.params.get("target", "games")
            system = _text(choice.params.get("system_id"), 128)
            if target in self._history_filters:
                self._history_filters[target] = system
                self._pages[1 if target == "recent" else 0] = _Page()
                return [self._history_query(target)]
            self._system_id = system
            self._system_label = _text(choice.params.get("label")) if system else ""
            self._games_view = "search" if self._search else "system" if system else "all"
            self._pages[0] = _Page()
            return [self._query()]
        if choice.action == "performance_option":
            self._performance_option_dialog(choice.params.get("option_id", ""))
            return []
        if choice.action == "request":
            return [self._request(choice.method, choice.params, choice.context)]
        if choice.action == "demo_launch":
            self._dialog = Dialog("Sample collection", "This preview never starts games or changes your device. "
                                  "Use your installed spruce library through a verified production adapter.", (DialogChoice("Done"),))
        elif choice.action == "classic":
            if self.demo:
                self.notice("The desktop preview cannot switch the device interface.")
            else:
                return [self._request("interface.switch", {"interface": "classic"}, "switch")]
        return []

    def _submit_search(self) -> list[UICommand]:
        self._search = self._keyboard.text if self._keyboard else self._search
        self._keyboard = None
        self.category = 0
        self._games_view = "search"
        self._pages[0] = _Page()
        return [self._query()]

    def handle(self, action: str, text: str = "") -> list[UICommand]:
        self._status = ""
        if self.exit_request:
            return []
        if action == "quit":
            self.exit_request = "quit"
            return []
        if self._keyboard:
            keyboard = self._keyboard
            if action == "back":
                self._keyboard = None
            elif action in ("left", "right", "up", "down"):
                selected, column = move_keyboard_focus(keyboard.selected, action,
                                                       keyboard.preferred_column, keyboard.keys)
                self._keyboard = replace(keyboard, selected=selected, preferred_column=column)
            elif action in ("text", "delete_text"):
                value = keyboard.text[:-1] if action == "delete_text" else keyboard.text + keyboard_text(text)
                self._keyboard = replace(keyboard, text=keyboard_text(value))
            elif action == "submit_text":
                return self._submit_search()
            elif action == "confirm":
                key = keyboard.keys[keyboard.selected]
                if key == "Find":
                    return self._submit_search()
                if key == "Cancel":
                    self._keyboard = None
                elif key == "Delete":
                    self._keyboard = replace(keyboard, text=keyboard.text[:-1])
                else:
                    self._keyboard = replace(keyboard, text=keyboard_text(keyboard.text + (" " if key == "Space" else key)))
            return []
        if self._dialog:
            dialog = self._dialog
            if action == "back":
                self._dialog = None
            elif action in ("up", "left", "down", "right"):
                delta = -1 if action in ("up", "left") else 1
                self._dialog = replace(dialog, selected=(dialog.selected + delta) % max(1, len(dialog.choices)))
            elif action in ("search", "favorite"):
                self._dialog = replace(dialog, message_page=dialog.message_page + (1 if action == "search" else -1))
            elif action == "confirm" and dialog.choices:
                return self._activate_choice(dialog.choices[dialog.selected])
            return []
        if action == "menu" and self.category in (0, 1):
            self._filter_dialog()
            return []
        if action in ("left", "right"):
            self.category = (self.category + (-1 if action == "left" else 1)) % 4
            return []
        if action == "search":
            self._keyboard = Keyboard(self._search, 0)
            return []
        if action == "back":
            if self.category == 0 and self._games_view != "systems":
                self._games_view = "systems"
            elif self.category == 3 and self._settings_view != "root":
                self._settings_view = "root"
                self._rebuild_settings()
                page = self._pages[3]
                page.selected = next((i for i, item in enumerate(page.items)
                                      if item.id == self._settings_parent_focus), page.selected)
            else:
                return self._activate(_menu("classic", "Return to spruce"))
            return []
        page = self._page()
        if action == "up" and page.items:
            if page.selected > 0:
                page.selected -= 1
            elif (self.category == 1 or self.category == 0 and self._games_view == "favorites") and page.offset >= self.PAGE_SIZE:
                self._show_history_page("recent" if self.category == 1 else "favorites", page.offset - self.PAGE_SIZE, keep_focus=False, last_focus=True)
            elif self.category == 0 and self._games_view != "systems" and page.offset >= self.PAGE_SIZE:
                return [self._query(page.offset - self.PAGE_SIZE, last_focus=True)]
        elif action == "down" and page.items:
            if page.selected + 1 < len(page.items):
                page.selected += 1
            elif (self.category == 1 or self.category == 0 and self._games_view == "favorites") and page.offset + len(page.items) < page.total:
                self._show_history_page("recent" if self.category == 1 else "favorites", page.offset + len(page.items), keep_focus=False)
            elif self.category == 0 and self._games_view != "systems" and page.offset + len(page.items) < page.total:
                return [self._query(page.offset + len(page.items))]
        elif action == "confirm" and page.items:
            return self._activate(page.items[page.selected])
        elif action == "favorite" and page.items:
            item = page.items[page.selected]
            if item.kind == "game":
                return [self._request("library.favorite.set", {"game_id": item.id, "enabled": item.id not in self._favorites}, "favorite_set")]
        elif action == "refresh":
            self._artwork_generation += 1
            return self.initial_commands(preserve_focus=True)
        return []

    def snapshot(self, now: float = 0.0, *, display_clock: str = "") -> UISnapshot:
        """Accept the coordinator's clock text without reading wall time here."""
        del now  # Presentation alone owns animation time.
        page = self._page()
        if self.category == 1:
            title, breadcrumb = "Pick up where you left off", "Continue Playing"
            if self._history_filters["recent"]:
                breadcrumb += "  /  " + ("PS1" if self._history_filters["recent"] == "PS" else self._history_filters["recent"])
            empty = "Your recently played games will appear here. A compatible state is required for Resume."
        elif self.category == 2:
            title, breadcrumb = "Your tools, together", "Tools"
            empty = "No app entries were found. Your installed tools remain available in classic spruce."
        elif self.category == 3:
            title, breadcrumb = {"controls": ("Emulator menu controls", "Settings  /  Controls"),
                                 "appearance": ("PPSSPP appearance", "Settings  /  Appearance"),
                                 "experience": ("Match PPSSPP menus", "Settings  /  PPSSPP")}.get(self._settings_view, ("Make it yours", "Settings"))
            if self._settings_view.startswith("hardware:"):
                label = {"display": "Display", "sound": "Sound", "network": "Network", "controllers": "Controllers", "power": "Power & USB"}.get(self._settings_view.split(":", 1)[1], "Device")
                title, breadcrumb = label, "Settings  /  " + label
            empty = "No emulator menu profile is qualified." if self._settings_view == "controls" else "Settings are unavailable. Return to the classic interface to check your configuration."
        else:
            title = {"systems": "Your games", "all": "All games", "favorites": "Favorites", "search": "Search results"}.get(self._games_view, self._system_label)
            breadcrumb = "Games  /  " + ("Collection" if self._games_view == "systems" else title)
            if self._games_view == "favorites" and self._history_filters["favorites"]:
                breadcrumb += "  /  " + ("PS1" if self._history_filters["favorites"] == "PS" else self._history_filters["favorites"])
            elif self._games_view != "systems":
                if self._system_id and self._games_view != "system":
                    breadcrumb += "  /  " + (self._system_label or self._system_id)
                if self._search:
                    breadcrumb += "  /  " + self._search
            empty = {"favorites": "Save a game with Favorite to keep it here.", "search": "No games match this search. Try another title."}.get(self._games_view,
                     "No available games were found. Keep ROMs in their existing spruce folders and refresh the library.")
        items = tuple(replace(item, favorite=item.id in self._favorites or item.favorite,
                              subtitle=("Resume available" if item.resume_available and not self.demo else "Recently played")
                              if self.category == 1 and item.kind == "game" else item.subtitle)
                      for item in page.items)
        return UISnapshot(self.category, CATEGORIES, title, breadcrumb, items, page.selected,
                          page.total, page.offset, self.preferences, self._dialog, self._keyboard,
                          self._status, "Loading your collection…" if self._pending and not items else empty,
                          bool(self._pending), self.demo, self.exit_request, _text(display_clock, 32),
                          self._artwork_generation)
