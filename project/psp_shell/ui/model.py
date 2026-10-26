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
    state_verification_required: bool = False

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
            state_verification_required=value.get("state_verification_required") is True,
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
    title: str = "Find a game"
    submit_label: str = "Find"


@dataclass(frozen=True)
class BrowseScope:
    """Only presentation choices; native managers retain library ownership."""
    source: str = "all"
    system_id: str = ""
    search: str = ""
    sort: str = "native"
    collection_id: str = ""

    @classmethod
    def from_mapping(cls, value: Any, source: str = "all") -> "BrowseScope":
        value = value if isinstance(value, Mapping) else {}
        order = value.get("sort", "native")
        return cls(source, _text(value.get("system_id", ""), 128),
                   keyboard_text(value.get("search", "")),
                   order if order in ("native", "title_asc", "title_desc", "system") else "native",
                   _text(value.get("collection_id", ""), 256))

    def params(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.source != "all":
            result["source"] = self.source
        for key in ("system_id", "search", "collection_id"):
            if getattr(self, key):
                result[key] = getattr(self, key)
        if self.sort != "native":
            result["sort"] = self.sort
        return result


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
        self._history_search = {"recent": "", "favorites": ""}
        self._sorts = {"all": "native", "recent": "native", "favorites": "native", "collection": "native"}
        self._collection_id = ""
        self._collection_label = ""
        self._collections = _Page()
        self._system_records: tuple[Mapping[str, Any], ...] = ()
        self._keyboard_purpose = "search"
        self._keyboard_scope = "all"
        self._random_scope = BrowseScope()
        self._random_game_id = ""
        self._details: tuple[tuple[str, str], ...] = ()
        self._details_return: Dialog | None = None
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
        self._pending_commands: dict[int, UICommand] = {}
        self._request_epochs: dict[int, int] = {}
        self._view_epoch = 0
        self._latest_reads: dict[str, int] = {}
        self._mutation_messages: list[str] = []
        self._favorites_loaded = False
        self._favorite_overrides: dict[str, bool] = {}
        self._favorite_override_serial: dict[str, int] = {}
        self._restored_offsets: dict[str, int] = {}
        self._restored_indices: dict[str, int] = {}
        self._backup_generation = 0
        self._backup_entries: tuple[Mapping[str, Any], ...] = ()
        self._backup_history_offset = 0
        self._backup_history_reason = ""
        self._backup_entry_id = ""
        self._backup_detail: Mapping[str, Any] = {}
        self._backup_job: Mapping[str, Any] = {}
        self._backup_poll_due = 0.0
        self._backup_poll_pending = False
        self._backup_poll_serial = 0
        self._query_serial = 0
        self._query_last_focus = False
        self._query_keep_focus = False
        self._pending_jump = ""
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
        if restored_state and restored_state.get("schema", 1) in (1, 2):
            value = restored_state.get("category", 0)
            self.category = value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 4 else 0
            focus = restored_state.get("focus", {})
            if isinstance(focus, Mapping):
                self._restored_focus = {str(k): _text(v, 1024) for k, v in focus.items()}
            view = restored_state.get("games_view", "systems")
            if view in ("systems", "all", "system", "favorites", "search", "collections", "collection"):
                self._games_view = view
            self._system_id = _text(restored_state.get("system_id", ""), 128)
            self._system_label = _text(restored_state.get("system_label", ""), 512)
            self._search = _text(restored_state.get("search", ""), 128).replace("\n", "")
            filters = restored_state.get("history_filters", {})
            if isinstance(filters, Mapping):
                self._history_filters = {key: _text(filters.get(key, ""), 128) for key in self._history_filters}
            scopes = restored_state.get("scopes", {})
            if isinstance(scopes, Mapping):
                for source in self._sorts:
                    if source not in scopes:
                        continue
                    scope = BrowseScope.from_mapping(scopes.get(source), source)
                    self._sorts[source] = scope.sort
                    if source in self._history_filters:
                        self._history_filters[source] = scope.system_id
                        self._history_search[source] = scope.search
                collection = BrowseScope.from_mapping(scopes.get("collection"), "collection")
                self._collection_id = collection.collection_id
                self._collection_label = _text(restored_state.get("collection_label", ""), 512)
            positions = restored_state.get("positions", {})
            if isinstance(positions, Mapping):
                for key, position in positions.items():
                    if key not in ("0", "1", "2", "3", "systems", "collections") or not isinstance(position, Mapping):
                        continue
                    offset, selected = position.get("offset", 0), position.get("selected", 0)
                    if type(offset) is int and 0 <= offset <= 100000:
                        self._restored_offsets[key] = offset - offset % self.PAGE_SIZE
                    if type(selected) is int and 0 <= selected < self.PAGE_SIZE:
                        self._restored_indices[key] = selected
            if self._games_view == "system" and not self._system_id:
                self._games_view = "systems"
            if self._games_view == "collection" and not self._collection_id:
                self._games_view = "collections"

    def _request(self, method: str, params: Mapping[str, Any] | None = None,
                 context: str = "") -> UICommand:
        self._serial += 1
        self._pending.add(self._serial)
        command = UICommand(self._serial, method, dict(params or {}), context)
        self._pending_commands[command.serial] = command
        self._request_epochs[command.serial] = self._view_epoch
        if not self._is_mutation(command):
            self._latest_reads[context] = command.serial
        return command

    @staticmethod
    def _is_mutation(command: UICommand) -> bool:
        return (command.context in ("apply", "undo", "favorite_set", "launch", "switch", "hardware_apply",
                                    "controls_apply", "controls_undo", "appearance_apply", "appearance_undo",
                                    "experience_apply", "experience_undo", "performance_apply", "performance_undo",
                                    "backup_rename", "backup_remove", "backup_cancel") or
                command.method.endswith((".apply", ".undo")))

    def _leave_view(self) -> None:
        self._view_epoch += 1

    def _scope(self, source: str | None = None) -> BrowseScope:
        source = source or ("recent" if self.category == 1 else "favorites" if self._games_view == "favorites"
                            else "collection" if self._games_view == "collection" else "all")
        if source in self._history_filters:
            return BrowseScope(source, self._history_filters[source], self._history_search[source], self._sorts[source])
        return BrowseScope(source, self._system_id, self._search, self._sorts[source],
                           self._collection_id if source == "collection" else "")

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
        elif self._games_view == "collections":
            commands.append(self._request("library.collections", context="collections"))
        elif self._games_view != "systems":
            commands.append(self._query(self._pages[0].offset if preserve_focus else self._restored_offsets.get("0", 0),
                                        keep_focus=preserve_focus or "0" in self._restored_offsets))
        return commands

    def refresh_commands(self) -> list[UICommand]:
        """Refresh after a native handoff without changing its return focus."""
        self._leave_view()
        self._artwork_generation += 1
        return self.initial_commands(preserve_focus=True)

    def _page(self) -> _Page:
        if self.category == 0 and self._games_view == "systems":
            return self._systems
        if self.category == 0 and self._games_view == "collections":
            return self._collections
        return self._pages[self.category]

    def _focus_key(self) -> str:
        return "systems" if self.category == 0 and self._games_view == "systems" else str(self.category)

    def _restore_focus(self, page: _Page, key: str) -> None:
        index = self._restored_indices.pop(key, None)
        if index is not None and page.items:
            page.selected = min(index, len(page.items) - 1)
        identifier = self._restored_focus.pop(key, "")
        if identifier:
            page.selected = next((i for i, item in enumerate(page.items) if item.id == identifier), page.selected)

    def export_state(self) -> dict[str, Any]:
        focus = {}
        positions = {}
        for key, page in [("systems", self._systems), ("collections", self._collections)] + [(str(i), page) for i, page in enumerate(self._pages)]:
            if 0 <= page.selected < len(page.items):
                focus[key] = page.items[page.selected].id
            positions[key] = {"offset": page.offset, "selected": page.selected}
        return {"schema": 2, "category": self.category, "focus": focus, "positions": positions,
                "games_view": self._games_view, "system_id": self._system_id,
                "system_label": self._system_label, "search": self._search,
                "history_filters": dict(self._history_filters),
                "collection_label": self._collection_label,
                "scopes": {source: self._scope(source).params() for source in self._sorts}}

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
        self._system_records = tuple(records)
        items = [_menu("all", "All games", "Your existing collection"),
                 _menu("favorites", "Favorites", "The games you keep close"),
                 _menu("search", "Find a game", "Search across your collection"),
                 _menu("random", "Surprise me", "Choose an available game")]
        for value in self._system_records:
            identifier = _text(value.get("system_id", value.get("id", "")), 128)
            if not identifier:
                continue
            count = value.get("game_count", 0)
            count = count if type(count) is int and count >= 0 else None
            items.append(UIItem(identifier, _text(value.get("label", identifier)),
                                f"{count} games" if count is not None else "Browse games", "system", identifier,
                                available=value.get("availability", "available") == "available"))
        items.append(_menu("collections", "Collections", "Browse your existing spruce collections"))
        items.append(_menu("library_filters", "Library tools", "Filter, sort, jump or choose a game"))
        items.append(_menu("help", "Controls & help", "Buttons, browsing and safe ways to continue"))
        items.append(_menu("refresh_library", "Refresh library", "Reload game lists and changed artwork"))
        self._systems.replace(items)
        self._restore_focus(self._systems, "systems")

    def _query(self, offset: int = 0, *, keep_focus: bool = False,
               last_focus: bool = False) -> UICommand:
        params: dict[str, Any] = {"offset": offset, "limit": self.PAGE_SIZE,
                                  **self._scope("collection" if self._games_view == "collection" else "all").params()}
        page = self._pages[0]
        focus_id = (page.items[page.selected].id if keep_focus and 0 <= page.selected < len(page.items)
                    else self._restored_focus.get("0", ""))
        if focus_id:
            params["focus_game_id"] = focus_id
        command = self._request("library.query", params, "games")
        if self._pending_jump:
            params["jump"] = self._pending_jump
            command = replace(command, params=params)
            self._pending_commands[command.serial] = command
            self._pending_jump = ""
        self._query_serial = command.serial
        self._query_keep_focus = keep_focus
        self._query_last_focus = last_focus
        return command

    def _history_query(self, kind: str) -> UICommand:
        params = {"system_id": self._history_filters[kind]} if self._history_filters[kind] else {}
        if self._history_search[kind]:
            params["search"] = self._history_search[kind]
        command = self._request("library." + kind, params, kind)
        self._history_serial[kind] = command.serial
        return command

    def _show_history_page(self, kind: str, offset: int = 0, *, keep_focus: bool = True,
                           last_focus: bool = False) -> None:
        items = self._history_records.get(kind, ())
        page = self._pages[1 if kind == "recent" else 0]
        key = "1" if kind == "recent" else "0"
        previous = (page.items[page.selected].id if keep_focus and 0 <= page.selected < len(page.items)
                    else self._restored_focus.get(key))
        if not page.items:
            offset = self._restored_offsets.get(key, offset)
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
        if self.category == 0 and self._games_view in ("systems", "collections"):
            self._system_id = self._system_label = self._search = ""
        scope = self._scope()
        label = {"all": "Games", "favorites": "Favorites", "recent": "Continue Playing", "collection": self._collection_label or "Collection"}[scope.source]
        system = next((_text(row.get("label", scope.system_id)) for row in self._system_records
                       if row.get("system_id", row.get("id")) == scope.system_id), scope.system_id) or "All systems"
        order = {"native": "Original order" if scope.source in ("recent", "favorites", "collection") else "Title A–Z",
                 "title_asc": "Title A–Z", "title_desc": "Title Z–A", "system": "System, then title"}[scope.sort]
        choices = [DialogChoice("System: " + system, "system_filter"),
                   DialogChoice("Search this view", "search_view"),
                   DialogChoice("Clear filters", "clear_filters"),
                   DialogChoice("Sort: " + order, "sort_menu"),
                   DialogChoice("Surprise me", "random_view")]
        page = self._page()
        if page.offset:
            choices.append(DialogChoice("Previous page", "page", params={"delta": -1}))
        if page.offset + len(page.items) < page.total:
            choices.append(DialogChoice("Next page", "page", params={"delta": 1}))
        choices.append(DialogChoice("Jump to letter", "jump_menu"))
        if scope.source == "collection":
            choices.append(DialogChoice("Manage in spruce", "manage_collections"))
        choices.append(DialogChoice("Back"))
        self._dialog = Dialog("Library tools", label + " · " + system +
                              ("\nSearch: " + scope.search if scope.search else "\nNo search filter"), tuple(choices))

    def _system_filter_dialog(self) -> None:
        target = self._scope().source
        choices = [DialogChoice("All systems", "set_filter", params={"target": target, "system_id": "", "label": "All systems"})]
        seen = set()
        for row in self._system_records[:256]:
            identifier = _text(row.get("system_id", row.get("id", "")), 128)
            if identifier and identifier not in seen:
                seen.add(identifier)
                choices.append(DialogChoice(_text(row.get("label", identifier)), "set_filter",
                    params={"target": target, "system_id": identifier, "label": _text(row.get("label", identifier))}))
        choices.append(DialogChoice("Cancel"))
        self._dialog = Dialog("Choose system", "Your search stays combined with this system.", tuple(choices))

    def _reload_scope(self, *, offset: int = 0, keep_focus: bool = False) -> list[UICommand]:
        source = self._scope().source
        if source in self._history_filters:
            page = self._pages[1 if source == "recent" else 0]
            if not keep_focus:
                page.replace((), offset=offset, keep_focus=False)
            return [self._history_query(source)]
        if self._games_view in ("systems", "collections"):
            self._games_view = "search" if self._search else "system" if self._system_id else "all"
        if not keep_focus:
            self._pages[0] = _Page(offset=offset)
        return [self._query(offset, keep_focus=keep_focus)]

    def _open_search(self, *, global_search: bool = False) -> None:
        scope = self._scope()
        self._keyboard_purpose = "search"
        self._keyboard_scope = "global" if global_search else scope.source
        self._keyboard = Keyboard("" if global_search else scope.search, 0,
                                  title="Find a game" if global_search else "Search this view")

    def _page_commands(self, delta: int) -> list[UICommand]:
        page = self._page()
        target = max(0, min(page.offset + delta * self.PAGE_SIZE,
                            max(0, (page.total - 1) // self.PAGE_SIZE * self.PAGE_SIZE)))
        source = self._scope().source
        if source in self._history_filters:
            self._show_history_page(source, target, keep_focus=False, last_focus=delta < 0)
            return []
        return [self._query(target, last_focus=delta < 0)]

    def _random_commands(self, *, another: bool = False) -> list[UICommand]:
        if not another:
            self._random_scope = self._scope()
            self._random_game_id = ""
        params = self._random_scope.params()
        if another and self._random_game_id:
            params["exclude_game_id"] = self._random_game_id
        return [self._request("library.random", params, "random")]

    _MODAL_READS = frozenset(("game_info", "performance_status", "performance_preview", "backup_status",
        "backup_action", "hardware_preview", "experience", "experience_preview", "preview", "controls",
        "controls_preview", "appearance", "appearance_preview", "random", "support", "backup_history",
        "backup_detail", "backup_verify", "backup_job"))

    def receive(self, command: UICommand, result: Any) -> list[UICommand]:
        epoch = self._request_epochs.pop(command.serial, self._view_epoch)
        self._pending_commands.pop(command.serial, None)
        self._pending.discard(command.serial)
        stale = epoch != self._view_epoch
        mutation = self._is_mutation(command)
        if not mutation:
            if self._latest_reads.get(command.context, command.serial) != command.serial:
                if command.context == "backup_verify" and isinstance(result, Mapping) and result.get("job_id"):
                    return [self._request("backup.cancel", {"job_id": result["job_id"]}, "backup_cancel_background")]
                return []
            if stale and (command.context in self._MODAL_READS or command.context.startswith("hardware:")):
                if command.context == "backup_job" and command.serial == self._backup_poll_serial:
                    self._backup_poll_pending = False
                if command.context == "backup_verify" and isinstance(result, Mapping) and result.get("job_id"):
                    return [self._request("backup.cancel", {"job_id": result["job_id"]}, "backup_cancel_background")]
                return []
        if mutation and stale:
            # Receipts still update transaction/generation state. They must not
            # navigate back into an abandoned screen or open its next dialog.
            dialog, view, page = self._dialog, self._settings_view, replace(self._pages[3])
            followups = self._receive_current(command, result)
            self._dialog, self._settings_view, self._pages[3] = dialog, view, page
            message = self._status or "The earlier action completed."
            self._mutation_messages = (self._mutation_messages + [message])[-12:]
            self.notice(message + " Details remain in Recent actions.")
            retained = []
            for request in followups:
                if request.context in ("favorites", "recent", "favorites_cache"):
                    retained.append(request)
                else:
                    self._pending.discard(request.serial)
                    self._pending_commands.pop(request.serial, None)
                    self._request_epochs.pop(request.serial, None)
            return retained
        return self._receive_current(command, result)

    def _receive_current(self, command: UICommand, result: Any) -> list[UICommand]:
        self._pending.discard(command.serial)
        context = command.context
        if context in ("settings", "apply", "undo"):
            if not isinstance(result, Mapping):
                raise ValueError("Settings reply must be an object")
            self.preferences = Preferences.from_mapping(result.get("preferences"))
            if context in ("apply", "undo"):
                self._latest_reads["settings"] = command.serial
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
        elif context == "backup_history":
            if isinstance(result, Mapping):
                self._backup_history_dialog(result)
        elif context == "backup_detail":
            if isinstance(result, Mapping):
                self._backup_detail_dialog(result)
        elif context in ("backup_rename", "backup_remove"):
            if isinstance(result, Mapping) and type(result.get("generation")) is int:
                self._backup_generation = result["generation"]
            self.notice("Backup label updated." if context == "backup_rename" else "Removed from history. Backup files were kept.")
            return [self._request("backup.detail", {"entry_id": command.params["entry_id"]}, "backup_detail")] if context == "backup_rename" else [self._request("backup.history", context="backup_history")]
        elif context in ("backup_verify", "backup_job"):
            self._backup_poll_pending = False
            if isinstance(result, Mapping):
                self._backup_job = dict(result)
                if result.get("state") == "running":
                    self._backup_job_dialog()
                else:
                    self._backup_job = {}
                    self.notice("Backup bytes verified just now." if result.get("state") == "verified" else
                                _text(result.get("reason"), 512) or "Backup verification did not complete.")
                    return [self._request("backup.detail", {"entry_id": result.get("entry_id", self._backup_entry_id)}, "backup_detail")]
        elif context == "backup_cancel":
            if self._backup_job.get("job_id") and self._backup_job.get("job_id") != command.params.get("job_id"):
                # A delayed cancellation acknowledgement belongs to its old
                # job, even if another verification has since been started.
                return []
            self._backup_poll_pending = False
            state = result.get("state") if isinstance(result, Mapping) else "cancelled"
            if state == "running":
                if self._backup_job:
                    self._backup_job = dict(result)
                    self._backup_job_dialog()
                self.notice("The check is finishing. Its final result will be available in backup history.")
            else:
                self._backup_job = {}
                self.notice("Backup verification cancelled. Backup files were kept." if state == "cancelled" else
                            "The check already completed. Its result is available in backup history.")
        elif context == "backup_cancel_background":
            pass
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
        elif context == "collections":
            items = [UIItem(_text(value.get("collection_id", value.get("id", "")), 256),
                            _text(value.get("label", "Collection")),
                            f"{value['game_count']} games" if type(value.get("game_count")) is int else "Browse games",
                            "collection") for value in result if isinstance(value, Mapping)]
            items.append(_menu("manage_collections", "Manage in spruce", "Use the existing collection tools"))
            self._collections.replace(items)
            self._restore_focus(self._collections, "collections")
        elif context == "games":
            # Games and Favorites share a page. A background query can finish
            # after navigation has selected Favorites or returned to systems.
            if command.serial != self._query_serial or self._games_view not in ("all", "system", "search", "collection"):
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
            if isinstance(result.get("focus_id"), str):
                self._pages[0].selected = next((index for index, item in enumerate(items)
                    if item.id == result["focus_id"]), self._pages[0].selected)
            self._restored_offsets.pop("0", None)
        elif context in ("recent", "favorites", "favorites_cache"):
            if context != "favorites_cache" and command.serial != self._history_serial.get(context, command.serial):
                return []
            items = tuple(UIItem.from_record(value) for value in result if isinstance(value, Mapping))
            if context == "favorites_cache" or (context == "favorites" and not self._history_filters["favorites"] and not self._history_search["favorites"]):
                self._favorites = {item.id for item in items}
                self._favorites_loaded = True
                for identifier, serial in tuple(self._favorite_override_serial.items()):
                    if command.serial > serial:
                        self._favorite_overrides.pop(identifier, None)
                        self._favorite_override_serial.pop(identifier, None)
            elif context == "favorites":
                self._favorites.update(item.id for item in items)
            if context != "favorites_cache":
                order = self._sorts[context]
                if order != "native":
                    items = tuple(sorted(items, key=(lambda item: (item.system_label.casefold() or item.system_id.casefold(), item.title.casefold(), item.id))
                                         if order == "system" else (lambda item: (item.title.casefold(), item.id)),
                                         reverse=order == "title_desc"))
                self._history_records[context] = items
                if context == "recent" or self._games_view == "favorites":
                    page = self._pages[1 if context == "recent" else 0]
                    self._show_history_page(context, page.offset)
                    self._restore_focus(page, "1" if context == "recent" else "0")
                    self._restored_offsets.pop("1" if context == "recent" else "0", None)
        elif context == "tools":
            self._pages[2].replace(UIItem.from_record(value, "tool") for value in result if isinstance(value, Mapping))
            self._restore_focus(self._pages[2], "2")
        elif context == "random":
            item = UIItem.from_record(result)
            self._random_game_id = item.id
            self._launch_dialog(item)
            if self._dialog:
                self._dialog = replace(self._dialog, choices=self._dialog.choices[:-1] +
                    (DialogChoice("Pick another", "pick_another"), self._dialog.choices[-1]))
        elif context == "favorite_set":
            identifier = command.params.get("game_id", "")
            self._favorite_overrides[identifier] = command.params.get("enabled") is True
            self._favorite_override_serial[identifier] = command.serial
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
            self._pending_commands.pop(command.serial, None)
            epoch = self._request_epochs.pop(command.serial, self._view_epoch)
            if command.context == "backup_cancel_background":
                self._mutation_messages = (self._mutation_messages + ["Background verification cancellation: " + _text(message, 512)])[-12:]
                return
            if command.context == "backup_job" and command.serial == self._backup_poll_serial:
                self._backup_poll_pending = False
            stale = epoch != self._view_epoch or (not self._is_mutation(command) and
                self._latest_reads.get(command.context, command.serial) != command.serial)
            if stale:
                if self._is_mutation(command):
                    self._mutation_messages = (self._mutation_messages + [_text(message, 2048) + " · " + _text(code, 128)])[-12:]
                    self.notice("An earlier action failed. Open Recent actions in Settings for details.")
                return
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
                      _menu("about", "About & credits", "Version, source credits and license information"),
                      _menu("help", "Controls & help", "Buttons, browsing and safe ways to continue"),
                      _menu("recent_actions", "Recent actions", "Results of actions completed after you moved on")))
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

    @staticmethod
    def _detail_pages(title: str, rows: Iterable[str]) -> tuple[tuple[str, str], ...]:
        pages, current = [], ""
        for row in rows:
            row = _text(row, 1024)
            if len(current) + len(row) + 1 > 1500 and current:
                pages.append((title, current))
                current = ""
            current += ("\n" if current else "") + row
        if current:
            pages.append((title, current))
        return tuple(pages)

    def _show_detail(self, index: int) -> None:
        if not self._details:
            return
        index = max(0, min(index, len(self._details) - 1))
        title, message = self._details[index]
        choices = []
        if index:
            choices.append(DialogChoice("Previous details", "info_detail", params={"index": index - 1}))
        if index + 1 < len(self._details):
            choices.append(DialogChoice("Next details", "info_detail", params={"index": index + 1}))
        choices.append(DialogChoice("Back to information", "info_return"))
        self._dialog = Dialog(title + f" ({index + 1}/{len(self._details)})", message, tuple(choices))

    def _game_info_dialog(self, value: Mapping[str, Any]) -> None:
        self._game_information = value
        item = UIItem.from_record(value)
        disc_set = value.get("disc_set", {})
        disc_set = disc_set if isinstance(disc_set, Mapping) else {}
        raw_warnings = value.get("warnings", [])
        disc_warnings = disc_set.get("warnings", [])
        codes = list(dict.fromkeys(code for code in (raw_warnings[:64] if isinstance(raw_warnings, list) else []) +
                    (disc_warnings[:64] if isinstance(disc_warnings, list) else []) if isinstance(code, str)))
        warnings = [_warning_message(code) for code in codes]
        if value.get("preset_repair_required") is True and "SAVED_PRESET_UNAVAILABLE" not in codes:
            warnings.insert(0, _warning_message("SAVED_PRESET_UNAVAILABLE"))
        # Warnings precede optional metadata and full disc names. Every bounded
        # detail page stays below the renderer's text limit.
        rows = ["Warning: " + warning for warning in warnings[:4]]
        if len(warnings) > 4:
            rows.append(f"{len(warnings) - 4} further warnings are listed in Details.")
        rows.extend(("System: " + (item.system_label or item.system_id or "Unavailable"),
                     "Emulator: " + (item.selected_emulator[:160] or "Current system emulator"),
                     "Preset: " + (item.selected_preset[:160] or "Current system setting"),
                     "Availability: " + item.availability.replace("_", " ")))
        if item.resume_available and not self.demo:
            rows.append("Resume available for this boot.")
            recorded = _checkpoint_utc(item.state_recorded_at)
            if recorded:
                rows.append("Checkpoint verified " + recorded)
        else:
            rows.append("Sample Resume card" if self.demo and item.resume_available else "Recently played · Resume unavailable" if self.category == 1 else "Resume unavailable")
            rows.append(item.reason[:256] or "No authenticated compatible checkpoint is available. Start normally to use in-game saves.")
        details = list(self._detail_pages("Warnings", warnings))
        discs = disc_set.get("discs", [])
        disc_rows = []
        if disc_set.get("kind") not in (None, "none"):
            count = disc_set.get("disc_count")
            if type(count) is int:
                rows.append(f"Disc set: {count} disc(s)")
            if isinstance(discs, list):
                for number, disc in enumerate(discs[:256], 1):
                    if isinstance(disc, Mapping):
                        disc_rows.append(f"Disc {number}: " + _text(disc.get("label", disc.get("relative_path", "")), 256) +
                                         (" · available" if disc.get("available") is True else " · missing"))
                if len(discs) > 256:
                    disc_rows.append("Further discs exceed this view's limit; inspect the existing playlist.")
            if len("\n".join(rows + disc_rows)) < 1350:
                rows.extend(disc_rows)
            elif disc_rows:
                rows.append("Full disc names and availability are listed in Details.")
            details.extend(self._detail_pages("Disc details", disc_rows))
            management = value.get("disc_management", {})
            management = management if isinstance(management, Mapping) else {}
            rows.append(_text(management.get("description"), 240) or "Change discs in the selected emulator's existing in-game menu.")
        self._details = tuple(details)
        choices = []
        if item.available and not value.get("preset_repair_required"):
            if item.resume_available:
                choices.append(DialogChoice("Resume", "demo_launch" if self.demo else "request", "game.launch",
                    {"game_id": item.id, "preset_id": "", "mode": "resume"}, "launch"))
            choices.append(DialogChoice("Start normally" if self.category == 1 and not item.resume_available else "Fresh start" if item.resume_available else "Start game",
                "demo_launch" if self.demo else "request", "game.launch",
                {"game_id": item.id, "preset_id": "", "mode": "fresh" if item.resume_available or self.category == 1 else "normal"}, "launch"))
        if self._details:
            choices.append(DialogChoice("Details", "info_detail", params={"index": 0}))
        if item.system_id.casefold() == "psp":
            choices.append(DialogChoice("Performance options", "request", "performance.status", {"game_id": item.id}, "performance_status"))
        if self._capabilities.get("game_options") is True:
            choices.append(DialogChoice("Existing emulator options", "demo_launch" if self.demo else "request", "game.options",
                {"game_id": item.id}, "game_options"))
        choices.append(DialogChoice("Back"))
        self._dialog = Dialog(item.title, "\n".join(row for row in rows if row), tuple(choices),
                              artwork=item.artwork, system_id=item.system_id)
        self._details_return = self._dialog

    def _manage_collections(self) -> list[UICommand]:
        available = self._capabilities.get("collections_manage") is True or any(
            item.id == "route:collections" and item.available for item in self._pages[2].items)
        if available:
            self._dialog = Dialog("Manage collections", "Create and organize collections in the existing spruce screen. Your collection list refreshes when you return.",
                (DialogChoice("Open spruce collections", "request", "tool.launch", {"tool_id": "route:collections"}, "hardware_route"), DialogChoice("Cancel")), selected=1)
        else:
            self._dialog = Dialog("Collections in this preview", "You can browse collection metadata here. Create collections or add and remove games through Collections and Game options in your installed spruce interface.")
        return []

    def _help_dialog(self) -> None:
        confirm = "South" if self.preferences.confirm == "south" else "East"
        back = "East" if self.preferences.confirm == "south" else "South"
        mode = ("This sample preview cannot launch games. Sample artwork and checkpoints are demonstrations." if self.demo else
                "Mounted-card inspection is read-only. Your original games and saves stay with spruce." if not self._capabilities.get("game_launch") else
                "Games and advanced screens use the existing spruce and emulator controls.")
        self._dialog = Dialog("Controls & help", f"{confirm}: choose · {back}: back\nLeft/right: categories · Up/down: games\n"
            "West: search this view · North: toggle Favorite\nStart: Library tools (desktop Tab)\n"
            "Desktop Enter: choose · Escape: back · X: search · Y: Favorite\n"
            "Use Library tools to filter, sort, change pages or choose a random game.\n"
            "Start normally uses in-game saves. Resume appears only after a compatible checkpoint is freshly verified.\n" + mode,
            (DialogChoice("Text size", "text_size"), DialogChoice("Done")), selected=1)

    def _empty_dialog(self) -> None:
        self._dialog = Dialog("No matching games", "Try another search, clear filters, or refresh after changing your library.",
            (DialogChoice("Search this view", "search_view"), DialogChoice("Clear filters", "clear_filters"),
             DialogChoice("Refresh library", "refresh"), DialogChoice("Controls & help", "help"), DialogChoice("Back")))

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
        if value.get("history_available") is True:
            choices.append(DialogChoice("Named backup history", "request", "backup.history", context="backup_history"))
        for action in value.get("supported_actions", [])[:8]:
            if isinstance(action, Mapping) and action.get("available") is True:
                identifier = action.get("id", action.get("action_id"))
                if identifier in ("recheck", "recovery_guide", "support_export"):
                    choices.append(DialogChoice(_text(action.get("label", identifier), 128), "request", "backup.action",
                                                {"action_id": identifier}, "backup_action"))
        choices.append(DialogChoice("Back"))
        self._dialog = Dialog("Backups & recovery", "\n".join(row for row in rows if row), tuple(choices))

    def _backup_history_dialog(self, value: Mapping[str, Any]) -> None:
        generation = value.get("generation", 0)
        self._backup_generation = generation if type(generation) is int and generation >= 0 else 0
        entries = value.get("entries", [])
        self._backup_entries = tuple(entry for entry in entries[:1000] if isinstance(entry, Mapping)) if isinstance(entries, list) else ()
        self._backup_history_reason = _text(value.get("reason"), 512)
        selected = next((index for index, entry in enumerate(self._backup_entries)
                         if entry.get("entry_id") == self._backup_entry_id), None)
        offset = selected // 20 * 20 if selected is not None else self._backup_history_offset
        self._show_backup_history_page(offset)

    def _show_backup_history_page(self, offset: int) -> None:
        total = len(self._backup_entries)
        offset = max(0, min(offset, max(0, (total - 1) // 20 * 20)))
        self._backup_history_offset = offset
        choices = [DialogChoice(_text(entry.get("label", "Unnamed backup"), 64), "request", "backup.detail",
                   {"entry_id": _text(entry.get("entry_id"), 128)}, "backup_detail") for entry in self._backup_entries[offset:offset + 20]]
        if offset:
            choices.append(DialogChoice("Previous backups", "backup_history_page", params={"offset": offset - 20}))
        if offset + 20 < total:
            choices.append(DialogChoice("Next backups", "backup_history_page", params={"offset": offset + 20}))
        choices.append(DialogChoice("Back"))
        selected = next((index for index, choice in enumerate(choices)
                         if choice.params.get("entry_id") == self._backup_entry_id), 0)
        self._dialog = Dialog("Named backup history", (f"Backups {offset + 1}–{min(offset + 20, total)} of {total}.\nChoose a backup to inspect its scope or check its bytes again. A previous successful check is historical evidence." if self._backup_entries else
            self._backup_history_reason or "No verified backup manifests have been registered. Use the existing offline backup tools, then register a manifest; this screen never creates a save state."), tuple(choices), selected=selected)

    def _backup_detail_dialog(self, value: Mapping[str, Any]) -> None:
        self._backup_detail = value
        self._backup_entry_id = _text(value.get("entry_id"), 128)
        generation = value.get("generation", self._backup_generation)
        if type(generation) is int and generation >= 0:
            self._backup_generation = generation
        status = value.get("status", "unchecked")
        rows = [{"previously_verified": "Previously checked backup · recheck for current byte verification",
                 "unavailable": "Backup unavailable at its registered location", "unchecked": "Backup has not been checked"}.get(status, "Backup verification is unavailable")]
        scope = value.get("scope", "")
        if isinstance(scope, list):
            scope = ", ".join(_text(part, 64) for part in scope)
        rows.append("Scope: " + _text(scope, 256))
        if type(value.get("bytes")) is int:
            rows.append(f"Registered size: {max(0, value['bytes']):,} bytes")
        for key, label in (("captured_at_utc", "Backup captured"), ("registered_at_utc", "Registered"), ("last_verified_at_utc", "Last successful check")):
            stamp = _checkpoint_utc(value.get(key, ""))
            if stamp:
                rows.append(label + " " + stamp)
        last = value.get("last_check", {})
        if isinstance(last, Mapping):
            stamp = _checkpoint_utc(last.get("checked_at_utc", ""))
            if stamp:
                rows.append("Last check " + stamp + " · " + {"verified": "bytes verified then", "unavailable": "unavailable"}.get(last.get("status"), "incomplete"))
        if isinstance(last, Mapping) and last.get("reason"):
            rows.append(_text(last["reason"], 256))
        if value.get("note"):
            rows.append("Note: " + _text(value["note"], 512))
        rows.append("Byte verification does not prove independent-media retention or physical restoration. This history never renames or deletes the backup files.")
        self._dialog = Dialog(_text(value.get("label", "Backup"), 64), "\n".join(rows), (
            DialogChoice("Check backup bytes", "request", "backup.verify", {"entry_id": self._backup_entry_id, "expected_generation": self._backup_generation}, "backup_verify"),
            DialogChoice("Rename label", "backup_rename_label"),
            DialogChoice("Remove from history", "backup_remove_review"),
            DialogChoice("Recovery instructions", "request", "backup.action", {"action_id": "recovery_guide"}, "backup_action"),
            DialogChoice("Back to history", "request", "backup.history", context="backup_history")))

    def _backup_job_dialog(self) -> None:
        job = self._backup_job
        files, byte_count = job.get("files_checked", 0), job.get("bytes_checked", 0)
        files = files if type(files) is int and files >= 0 else 0
        byte_count = byte_count if type(byte_count) is int and byte_count >= 0 else 0
        cancellable = job.get("cancellable", True) is not False
        self._dialog = Dialog("Checking backup bytes", _text(job.get("phase", "Verifying"), 128) +
            f"\n{files:,} files · {byte_count:,} bytes checked\n" +
            ("You can cancel. Backup files stay unchanged." if cancellable else "Finishing the verification record. Backup files stay unchanged."),
            (DialogChoice("Cancel verification", "request", "backup.cancel", {"job_id": job.get("job_id", "")}, "backup_cancel")
             if cancellable else DialogChoice("Back", "backup_detach"),))

    def poll_commands(self, now: float) -> list[UICommand]:
        if self._backup_job.get("state") != "running" or self._backup_poll_pending or now < self._backup_poll_due:
            return []
        self._backup_poll_due = now + .25
        self._backup_poll_pending = True
        command = self._request("backup.job", {"job_id": self._backup_job["job_id"]}, "backup_job")
        self._backup_poll_serial = command.serial
        return [command]

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
        choices.append(DialogChoice("Fresh start" if item.resume_available else "Start normally" if fresh else "Start game", "demo_launch" if self.demo else "request", "game.launch",
                                     {"game_id": item.id, "preset_id": "", "mode": "fresh" if fresh else "normal"}, "launch"))
        if self._capabilities.get("game_options") is True:
            choices.append(DialogChoice("Game options", "demo_launch" if self.demo else "request", "game.options",
                                        {"game_id": item.id}, "game_options"))
        if self._capabilities.get("game_information") is True:
            choices.append(DialogChoice("Game information", "request", "game.info", {"game_id": item.id}, "game_info"))
        choices.append(DialogChoice("Cancel"))
        self._dialog = Dialog(item.title, message, tuple(choices), artwork=item.artwork, system_id=item.system_id)

    def _activate(self, item: UIItem) -> list[UICommand]:
        if self.category == 3 and self._settings_view == "root":
            self._settings_parent_focus = item.id
        if item.kind == "game":
            if item.state_verification_required and self._capabilities.get("game_information") is True:
                return [self._request("game.info", {"game_id": item.id}, "game_info")]
            self._launch_dialog(item)
        elif item.kind == "system":
            self._games_view = "system"
            self._system_id, self._system_label = item.system_id, item.title
            self._search = ""
            self._pages[0] = _Page()
            return [self._query()]
        elif item.kind == "collection":
            self._games_view = "collection"
            self._collection_id, self._collection_label = item.id, item.title
            self._system_id, self._system_label, self._search = "", "", ""
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
                choices = tuple(DialogChoice(f"{round(scale * 100)}%", "request", "settings.preview",
                    {"changes": {"text_scale": scale}, "expected_generation": self.generation}, "preview")
                    for scale in (.75, 1.0, 1.15, 1.3, 1.5, 1.75))
                selected = min(range(6), key=lambda index: abs((.75, 1, 1.15, 1.3, 1.5, 1.75)[index] - value))
                self._dialog = Dialog("Text size", "Choose a readable size. Review before applying; Undo remains available.",
                                      choices + (DialogChoice("Cancel"),), selected=selected)
                return []
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
            self._open_search(global_search=True)
        elif item.id == "random":
            self._random_scope = BrowseScope()
            self._random_game_id = ""
            return [self._request("library.random", context="random")]
        elif item.id == "collections":
            self._games_view = "collections"
            return [self._request("library.collections", context="collections")]
        elif item.id == "manage_collections":
            return self._manage_collections()
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
        elif item.id == "help":
            self._help_dialog()
        elif item.id == "recent_actions":
            self._dialog = Dialog("Recent actions", "\n\n".join(self._mutation_messages) or "No earlier action needs attention.")
        elif item.id == "classic":
            self._dialog = Dialog("Return to spruce?", "Your existing games, saves and emulator settings stay in place.",
                                  (DialogChoice("Return to spruce", "classic"), DialogChoice("Stay here")), selected=1)
        return []

    def _activate_choice(self, choice: DialogChoice) -> list[UICommand]:
        self._dialog = None
        if choice.action == "info_detail":
            self._show_detail(choice.params.get("index", 0))
            return []
        if choice.action == "info_return":
            self._dialog = self._details_return
            return []
        if choice.action == "backup_rename_label":
            self._keyboard_purpose = "backup_label"
            self._keyboard = Keyboard(_text(self._backup_detail.get("label", ""), 64), 0,
                                      title="Rename backup label", submit_label="Save label")
            return []
        if choice.action == "backup_remove_review":
            self._dialog = Dialog("Remove from history?", "Only this history entry is removed. The backup files and your game saves are kept.",
                (DialogChoice("Remove history entry", "request", "backup.remove", {"entry_id": self._backup_entry_id,
                    "expected_generation": self._backup_generation}, "backup_remove"), DialogChoice("Cancel")), selected=1)
            return []
        if choice.action == "backup_detach":
            self._backup_job = {}
            return []
        if choice.action == "backup_history_page":
            self._show_backup_history_page(choice.params.get("offset", 0))
            return []
        if choice.action == "system_filter":
            self._system_filter_dialog()
            return []
        if choice.action == "search_view":
            self._open_search(global_search=self.category not in (0, 1) or self._games_view == "systems" and self.category == 0)
            return []
        if choice.action == "clear_filters":
            source = self._scope().source
            if source in self._history_filters:
                self._history_filters[source] = self._history_search[source] = ""
            else:
                self._system_id = self._system_label = self._search = ""
            return self._reload_scope()
        if choice.action == "sort_menu":
            self._dialog = Dialog("Sort games", "Recent and favorite lists keep their original order unless you choose another sort.",
                tuple(DialogChoice(label, "set_sort", params={"sort": value}) for value, label in (
                    ("native", "Original order"), ("title_asc", "Title A–Z"), ("title_desc", "Title Z–A"), ("system", "System, then title"))) + (DialogChoice("Cancel"),))
            return []
        if choice.action == "set_sort":
            self._sorts[self._scope().source] = choice.params["sort"]
            return self._reload_scope()
        if choice.action == "page":
            return self._page_commands(choice.params["delta"])
        if choice.action in ("random_view", "pick_another"):
            return self._random_commands(another=choice.action == "pick_another")
        if choice.action == "jump_menu":
            self._dialog = Dialog("Jump to letter", "Jump uses Title A–Z order. Choose the start of a title.",
                tuple(DialogChoice(letter, "jump", params={"letter": letter}) for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ") + (DialogChoice("Cancel"),))
            return []
        if choice.action == "jump":
            source, letter = self._scope().source, choice.params["letter"]
            self._sorts[source] = "title_asc"
            if source in self._history_filters:
                items = tuple(sorted(self._history_records.get(source, ()), key=lambda item: (item.title.casefold(), item.id)))
                self._history_records[source] = items
                index = next((i for i, item in enumerate(items) if item.title.casefold() >= letter.casefold()), max(0, len(items) - 1))
                self._show_history_page(source, index // self.PAGE_SIZE * self.PAGE_SIZE, keep_focus=False)
                if items:
                    self._page().selected = index % self.PAGE_SIZE
                return []
            self._pending_jump = letter
            return self._reload_scope()
        if choice.action == "manage_collections":
            return self._manage_collections()
        if choice.action == "help":
            self._help_dialog()
            return []
        if choice.action == "text_size":
            return self._activate(UIItem("text_scale", "Text size", kind="setting"))
        if choice.action == "refresh":
            return self.refresh_commands()
        if choice.action == "set_filter":
            target = choice.params.get("target", "games")
            system = _text(choice.params.get("system_id"), 128)
            if target in self._history_filters:
                self._history_filters[target] = system
                self._pages[1 if target == "recent" else 0] = _Page()
                return [self._history_query(target)]
            self._system_id = system
            self._system_label = _text(choice.params.get("label")) if system else ""
            if self._games_view != "collection":
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
        text = self._keyboard.text if self._keyboard else ""
        self._keyboard = None
        if self._keyboard_purpose == "backup_label":
            return [self._request("backup.rename", {"entry_id": self._backup_entry_id, "label": text,
                "expected_generation": self._backup_generation}, "backup_rename")]
        source = self._keyboard_scope
        if source in self._history_filters:
            self._history_search[source] = text
            return self._reload_scope()
        self._search = text
        if source == "global":
            self._system_id = self._system_label = ""
        self.category = 0
        if source != "collection":
            self._games_view = "search"
        self._pages[0] = _Page()
        return [self._query()]

    def _cancel_keyboard(self) -> None:
        self._keyboard = None
        if self._keyboard_purpose == "backup_label":
            self._backup_detail_dialog(self._backup_detail)
        self._keyboard_purpose = "search"

    def handle(self, action: str, text: str = "") -> list[UICommand]:
        self._status = ""
        if self.exit_request:
            return []
        if action == "quit":
            self.exit_request = "quit"
            return []
        if (action in ("back", "submit_text") or
                action == "confirm" and self._keyboard is None or
                action in ("search", "menu") and self._dialog is None and self._keyboard is None or
                action in ("left", "right", "up", "down") and self._dialog is None and self._keyboard is None):
            self._leave_view()
        if self._keyboard:
            keyboard = self._keyboard
            if action == "back":
                self._cancel_keyboard()
            elif action in ("left", "right", "up", "down"):
                selected, column = move_keyboard_focus(keyboard.selected, action,
                                                       keyboard.preferred_column, keyboard.keys)
                self._keyboard = replace(keyboard, selected=selected, preferred_column=column)
            elif action in ("text", "delete_text"):
                value = keyboard.text[:-1] if action == "delete_text" else keyboard.text + keyboard_text(text)
                if self._keyboard_purpose == "backup_label":
                    value = value[:64]
                self._keyboard = replace(keyboard, text=keyboard_text(value))
            elif action == "submit_text":
                return self._submit_search()
            elif action == "confirm":
                key = keyboard.keys[keyboard.selected]
                if key == "Find":
                    return self._submit_search()
                if key == "Cancel":
                    self._cancel_keyboard()
                elif key == "Delete":
                    self._keyboard = replace(keyboard, text=keyboard.text[:-1])
                else:
                    value = keyboard_text(keyboard.text + (" " if key == "Space" else key))
                    self._keyboard = replace(keyboard, text=value[:64] if self._keyboard_purpose == "backup_label" else value)
            return []
        if self._dialog:
            dialog = self._dialog
            if action == "back":
                if self._backup_job.get("state") == "running":
                    job_id = self._backup_job.get("job_id")
                    self._backup_job = {}
                    self._dialog = None
                    return [self._request("backup.cancel", {"job_id": job_id}, "backup_cancel")]
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
            if self.category == 3 and self._settings_view == "root":
                self._rebuild_settings()
            return []
        if action == "search":
            self._open_search(global_search=self.category not in (0, 1) or self.category == 0 and self._games_view in ("systems", "collections"))
            return []
        if action == "back":
            if self.category == 0 and self._games_view != "systems":
                self._games_view = "collections" if self._games_view == "collection" else "systems"
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
        elif action == "confirm" and not page.items and self.category in (0, 1):
            self._empty_dialog()
        elif action == "favorite" and page.items:
            item = page.items[page.selected]
            if item.kind == "game":
                favorite = self._favorite_overrides.get(item.id, item.id in self._favorites if self._favorites_loaded else item.favorite or item.id in self._favorites)
                return [self._request("library.favorite.set", {"game_id": item.id, "enabled": not favorite}, "favorite_set")]
        elif action == "refresh":
            return self.refresh_commands()
        elif action in ("page_previous", "page_next") and self.category in (0, 1):
            return self._page_commands(-1 if action == "page_previous" else 1)
        return []

    def snapshot(self, now: float = 0.0, *, display_clock: str = "") -> UISnapshot:
        """Accept the coordinator's clock text without reading wall time here."""
        del now  # Presentation alone owns animation time.
        page = self._page()
        if self.category == 1:
            title, breadcrumb = "Pick up where you left off", "Continue Playing"
            if self._history_filters["recent"]:
                breadcrumb += "  /  " + ("PS1" if self._history_filters["recent"] == "PS" else self._history_filters["recent"])
            if self._history_search["recent"]:
                breadcrumb += "  /  " + self._history_search["recent"]
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
            title = {"systems": "Your games", "all": "All games", "favorites": "Favorites", "search": "Search results",
                     "collections": "Collections", "collection": self._collection_label or "Collection"}.get(self._games_view, self._system_label)
            breadcrumb = "Games  /  " + ("Collection" if self._games_view == "systems" else title)
            if self._games_view == "favorites" and self._history_filters["favorites"]:
                breadcrumb += "  /  " + ("PS1" if self._history_filters["favorites"] == "PS" else self._history_filters["favorites"])
            elif self._games_view not in ("systems", "collections", "favorites"):
                if self._system_id and self._games_view != "system":
                    breadcrumb += "  /  " + (self._system_label or self._system_id)
                if self._search:
                    breadcrumb += "  /  " + self._search
            if self._games_view == "favorites" and self._history_search["favorites"]:
                breadcrumb += "  /  " + self._history_search["favorites"]
            empty = {"favorites": "Save a game with Favorite to keep it here.", "search": "No games match this search. Try another title."}.get(self._games_view,
                     "No available games were found. Keep ROMs in their existing spruce folders and refresh the library.")
        items = tuple(replace(item, favorite=self._favorite_overrides.get(item.id,
                              item.id in self._favorites if self._favorites_loaded else item.id in self._favorites or item.favorite),
                              subtitle=("Checkpoint recorded · verify to Resume" if item.state_verification_required else
                                        "Resume available" if item.resume_available and not self.demo else "Recently played")
                              if self.category == 1 and item.kind == "game" else item.subtitle)
                      for item in page.items)
        loading = any(self._request_epochs.get(serial) == self._view_epoch for serial in self._pending)
        return UISnapshot(self.category, CATEGORIES, title, breadcrumb, items, page.selected,
                          page.total, page.offset, self.preferences, self._dialog, self._keyboard,
                          self._status, "Loading your collection…" if loading and not items else empty,
                          loading, self.demo, self.exit_request, _text(display_clock, 32),
                          self._artwork_generation)
