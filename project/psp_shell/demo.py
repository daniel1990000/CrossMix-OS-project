"""Original, synthetic collection for the desktop proof. No game data.

SPDX-License-Identifier: MIT
"""
from __future__ import annotations

import copy
import random


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
                    ("harbor", "Wind Harbor", "A quiet adventure by the sea."),
                    ("orbit", "Orbit Runner", "Find your line through the stars."),
                    ("paper", "Paper Kingdom", "A small world with room to explore.")],
            "PS": [("rally", "Alpine Rally", "Take the long way home."),
                   ("echo", "Echo Valley", "Return to where your story began."),
                   ("night", "Neon Evening", "The city is still awake.")],
            "PORTS": [("summit", "Summit", "A little further, a little higher."),
                      ("garden", "Pocket Garden", "Make something grow."),
                      ("vector", "Vector Sprint", "Keep your momentum.")],
            "GBA": [("moon", "Moonlit Post", "There is always another letter."),
                    ("wild", "Wildwood Trail", "A path worth following."),
                    ("island", "Small Island", "Stay for the sunset.")],
        }
        self._games = []
        for system, records in samples.items():
            for slug, title, subtitle in records:
                self._games.append({
                    "id": f"sample:{system}:{slug}", "game_id": f"sample:{system}:{slug}",
                    "system_id": system, "label": title, "display_name": title,
                    "subtitle": subtitle, "availability": "available", "artwork": "",
                    "relative_path": f"{slug}.sample", "resume_available": slug in ("skyline", "echo"),
                    "resume_reason": "Synthetic fixture, not a real emulator state",
                })
        self._favorites = {"sample:PSP:skyline", "sample:PS:echo", "sample:PORTS:summit"}

    def systems(self):
        return copy.deepcopy(self._systems)

    def games(self, system_id=None, search="", offset=0, limit=50):
        records = [self._record(g) for g in self._games
                   if (not system_id or g["system_id"] == system_id)
                   and search.casefold() in (g["label"] + " " + g["system_id"]).casefold()]
        records.sort(key=lambda g: (g["label"].casefold(), g["id"]))
        return {"items": records[offset:offset + limit], "total": len(records), "offset": offset, "limit": limit}

    def _record(self, value):
        result = copy.deepcopy(value)
        result["favorite"] = result["id"] in self._favorites
        return result

    def favorites(self):
        return [self._record(g) for g in self._games if g["id"] in self._favorites]

    def recent(self):
        wanted = ("sample:PSP:skyline", "sample:PS:echo", "sample:PORTS:summit", "sample:GBA:wild")
        return [self._record(next(g for g in self._games if g["id"] == key)) for key in wanted]

    def random(self):
        return self._record(random.choice(self._games))

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
