"""Original, synthetic collection for the desktop proof. No game data.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import copy
import random
import unicodedata


class DemoBackend:
    read_only = False
    demo = True

    def __init__(self):
        self._systems = [
            {"id": "PSP", "system_id": "PSP", "label": "PSP", "game_count": 4},
            {"id": "PS", "system_id": "PS", "label": "PlayStation", "game_count": 3},
            {"id": "PORTS", "system_id": "PORTS", "label": "Ports", "game_count": 3},
            {"id": "GBA", "system_id": "GBA", "label": "Game Boy Advance", "game_count": 3},
        ]
        samples = {
            "PSP": [("skyline", "Skyline Circuit", "An open road. One more lap."),
                    ("harbor", "Patapon", "A quiet adventure by the sea."),
                    ("orbit", "Wipeout Pure", "Find your line through the stars."),
                    ("paper", "Lumines", "A small world with room to explore.")],
            "PS": [("rally", "Gran Turismo 2", "Take the long way home."),
                   ("echo", "Final Fantasy IX", "Return to where your story began."),
                   ("night", "Ridge Racer Type 4", "The city is still awake.")],
            "PORTS": [("summit", "Celeste", "A little further, a little higher."),
                      ("garden", "Stardew Valley", "Make something grow."),
                      ("vector", "Shovel Knight", "Keep your momentum.")],
            "GBA": [("moon", "Golden Sun", "There is always another letter."),
                    ("wild", "Metroid Fusion", "A path worth following."),
                    ("island", "Advance Wars", "Stay for the sunset.")],
        }
        self._games = []
        for system, records in samples.items():
            for slug, title, subtitle in records:
                self._games.append({
                    "id": f"sample:{system}:{slug}", "game_id": f"sample:{system}:{slug}",
                    "system_id": system, "label": title, "display_name": title,
                    "subtitle": "Sample title · not installed", "availability": "available", "artwork": "",
                    "relative_path": f"{slug}.sample", "resume_available": slug in ("skyline", "echo"),
                    "resume_reason": "Synthetic fixture, not a real emulator state",
                    "selected_preset": "PPSSPP-SA" if system == "PSP" else "Existing emulator (sample)",
                })
        self._favorites = {"sample:PSP:skyline", "sample:PS:echo", "sample:PORTS:summit"}
        self._collections = {
            "sample:collection:later": ("Play later", ("sample:PSP:harbor", "sample:GBA:moon", "sample:PORTS:garden")),
            "sample:collection:arcade": ("One more round", ("sample:PSP:skyline", "sample:PS:rally", "sample:PORTS:vector")),
        }

    def refresh(self):
        # Demo records are already in memory; no owner files are read or changed.
        pass

    def systems(self):
        return copy.deepcopy(self._systems)

    def games(self, system_id=None, search="", offset=0, limit=50, *, source="all", collection_id="",
              sort="native", available_only=False, jump="", focus_game_id=""):
        search = unicodedata.normalize("NFC", search).casefold()
        if source == "favorites":
            candidates = self.favorites()
        elif source == "recent":
            candidates = self.recent()
        elif source == "collection":
            if collection_id not in self._collections:
                raise ValueError("The sample collection is no longer available")
            identifiers = self._collections[collection_id][1]
            candidates = [g for identifier in identifiers for g in self._games if g["id"] == identifier]
        elif source == "all":
            candidates = self._games
        else:
            raise ValueError("Unknown library source")
        records = [self._record(g) for g in candidates
                   if (not system_id or g["system_id"] == system_id)
                   and search in unicodedata.normalize("NFC", g["label"]).casefold()
                   and (not available_only or g.get("availability") == "available")]
        if sort == "system":
            records.sort(key=lambda g: (g["system_id"].casefold(), g["label"].casefold(), g["id"]))
        elif sort in ("title_asc", "title_desc") or source == "all":
            records.sort(key=lambda g: (g["label"].casefold(), g["id"]), reverse=sort == "title_desc")
        focus_id = ""
        if jump and records:
            index = next((i for i, game in enumerate(records) if game["label"].casefold() >= jump.casefold()), len(records) - 1)
            offset = index // limit * limit
            focus_id = records[index]["id"]
        elif focus_game_id and records:
            index = next((i for i, game in enumerate(records) if game["id"] == focus_game_id), None)
            if index is not None:
                offset = index // limit * limit
                focus_id = focus_game_id
        result = {"items": records[offset:offset + limit], "total": len(records), "offset": offset, "limit": limit}
        if focus_id:
            result["focus_id"] = focus_id
        return result

    def collections(self):
        return [{"id": identifier, "collection_id": identifier, "label": label, "game_count": len(games)}
                for identifier, (label, games) in self._collections.items()]

    def _record(self, value):
        result = copy.deepcopy(value)
        result["favorite"] = result["id"] in self._favorites
        return result

    @staticmethod
    def _matches(game, system_id, search):
        return (not system_id or game["system_id"] == system_id) and (
            unicodedata.normalize("NFC", search).casefold() in unicodedata.normalize("NFC", game["label"]).casefold())

    def favorites(self, system_id=None, search=""):
        return [self._record(g) for g in self._games if g["id"] in self._favorites and self._matches(g, system_id, search)]

    def recent(self, system_id=None, search=""):
        wanted = ("sample:PSP:skyline", "sample:PS:echo", "sample:PORTS:summit", "sample:GBA:wild")
        records = [self._record(next(g for g in self._games if g["id"] == key)) for key in wanted]
        return [g for g in records if self._matches(g, system_id, search)]

    def game_info(self, game_id):
        game = next((g for g in self._games if g["id"] == game_id), None)
        if game is None:
            raise ValueError("Unknown sample game")
        system = next(row for row in self._systems if row["id"] == game["system_id"])
        result = dict(self._record(game), system_label=system["label"],
                      selected_emulator=game["selected_preset"],
                      disc_set={"kind": "none", "discs": [], "warnings": [], "disc_count": 0, "missing_count": 0})
        if game["system_id"] == "PS":
            # Explicit synthetic presentation data; no game or playlist exists.
            result["disc_set"] = {"kind": "playlist", "disc_count": 2, "missing_count": 1,
                                  "warnings": ["MISSING_DISC_FILE"], "sample": True,
                                  "discs": [{"number": 1, "label": "Disc 1 (sample)", "available": True},
                                            {"number": 2, "label": "Disc 2 (sample)", "available": False}]}
            result["disc_management"] = {"route": "native_menu", "game_options_route": "game.options",
                                         "description": "In a real game, use the existing emulator's native menu for disc switching. "
                                                        "This is sample metadata; no emulator or game is running."}
        return result

    def random(self, system_id=None, search="", *, source="all", collection_id="", sort="native",
               available_only=True, exclude_game_id=""):
        records = self.games(system_id, search, limit=len(self._games), source=source,
                             collection_id=collection_id, sort=sort, available_only=True)["items"]
        choices = [game for game in records if game["id"] != exclude_game_id] or records
        if not choices:
            raise ValueError("No available games match this view")
        return random.choice(choices)

    def tools(self):
        return [{"id": identifier, "tool_id": identifier, "label": label,
                 "description": description, "availability": "available"}
                for identifier, label, description in (
                    ("sample:portmaster", "PortMaster", "Keep the installed ports and runtime"),
                    ("sample:files", "File manager", "Your existing files and folders"),
                    ("sample:backup", "Backup & restore", "Keep a verified way back"),
                    ("sample:network", "Network tools", "Use the services already installed"))]

    def set_favorite(self, game_id, enabled):
        if not any(g["id"] == game_id for g in self._games):
            raise ValueError("Unknown sample game")
        if enabled:
            self._favorites.add(game_id)
        else:
            self._favorites.discard(game_id)
        return {"game_id": game_id, "enabled": enabled, "sample": True}

    def resolve_game(self, game_id, preset_id=None, mode="normal"):
        game = next((g for g in self._games if g["id"] == game_id), None)
        if game is None:
            raise ValueError("Unknown sample game")
        return {**self._record(game), "launchable": False, "gate_reason": "DEMO_ONLY",
                "mode": mode, "preset_id": preset_id or ""}

    def resolve_tool(self, tool_id):
        tool = next((t for t in self.tools() if t["id"] == tool_id), None)
        if tool is None:
            raise ValueError("Unknown sample tool")
        return {**tool, "launchable": False, "gate_reason": "DEMO_ONLY"}
