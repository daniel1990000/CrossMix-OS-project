"""Original monochrome pictograms for the crossbar presentation.

All coordinates are on a 64-unit canvas. These are project-drawn geometry,
not extracted console artwork. SPDX-License-Identifier: MIT
"""
from __future__ import annotations


# Primitives: polygon, stroked path, rectangle, circle, and their shaded variants.
# Keeping artwork as geometry also supports the embedded SDL-only renderer.
DRAWINGS = {
    "game": (
        ("polygon", ((17, 19), (47, 19), (52, 24), (59, 45), (57, 50),
                     (49, 50), (40, 41), (24, 41), (15, 50), (7, 50),
                     (5, 45), (12, 24))),
        ("shade_rect", (15, 27, 15, 5)), ("shade_rect", (20, 22, 5, 15)),
        ("shade_circle", (46, 27, 2.5)), ("shade_circle", (51, 32, 2.5)),
        ("shade_circle", (41, 32, 2.5)), ("shade_circle", (46, 37, 2.5)),
        ("shade_rect", (29, 30, 6, 2)),
    ),
    "settings": (
        ("path", ((16, 12), (16, 53))),
        ("path", ((32, 12), (32, 53))),
        ("path", ((48, 12), (48, 53))),
        ("rect", (9, 23, 14, 8)), ("rect", (25, 37, 14, 8)),
        ("rect", (41, 18, 14, 8)),
        ("shade_rect", (11, 25, 10, 2)), ("shade_rect", (27, 39, 10, 2)),
        ("shade_rect", (43, 20, 10, 2)),
    ),
    "recent": (
        ("ring", (32, 32, 24, 3)),
        ("path", ((32, 17), (32, 33), (43, 39))),
        ("polygon", ((9, 6), (9, 24), (25, 22))),
    ),
    "tool": (
        ("rect", (8, 23, 48, 30)), ("path", ((22, 22), (22, 14), (42, 14), (42, 22))),
        ("shade_rect", (9, 32, 46, 2)), ("shade_rect", (28, 29, 8, 9)),
        ("rect", (30, 30, 4, 6)),
    ),
    "all": (
        ("polygon", ((22, 8), (43, 8), (48, 13), (48, 53), (44, 57), (21, 57), (17, 53), (17, 13))),
        ("shade_rect", (22, 10, 21, 11)), ("shade_rect", (23, 35, 18, 3)),
        ("shade_rect", (23, 41, 18, 3)), ("shade_rect", (23, 47, 12, 3)),
        ("rect", (25, 11, 2, 7)), ("rect", (30, 11, 2, 7)),
        ("rect", (35, 11, 2, 7)), ("rect", (40, 11, 2, 7)),
    ),
    "favorites": (
        ("polygon", ((32, 7), (39, 23), (57, 25), (43, 37), (47, 55),
                     (32, 46), (17, 55), (21, 37), (7, 25), (25, 23))),
    ),
    "search": (
        ("ring", (27, 26, 18, 4)), ("path", ((40, 40), (56, 56))),
    ),
    "system": (
        ("polygon", ((10, 15), (54, 15), (59, 20), (59, 44), (54, 49), (10, 49), (5, 44), (5, 20))),
        ("shade_rect", (18, 21, 29, 22)), ("shade_rect", (8, 30, 8, 3)),
        ("shade_rect", (10.5, 27.5, 3, 8)),
        ("shade_circle", (53, 28, 1.7)), ("shade_circle", (53, 36, 1.7)),
    ),
    "folder": (
        ("polygon", ((7, 15), (25, 15), (30, 21), (57, 21), (57, 51), (7, 51))),
        ("shade_rect", (8, 24, 48, 2)),
    ),
    "display": (
        ("path", ((7, 13), (57, 13), (57, 46), (7, 46), (7, 13))),
        ("rect", (28, 46, 8, 8)), ("rect", (20, 53, 24, 3)),
        ("circle", (32, 30, 8)),
        ("path", ((32, 17), (32, 19))), ("path", ((32, 41), (32, 43))),
        ("path", ((19, 30), (21, 30))), ("path", ((43, 30), (45, 30))),
    ),
    "volume": (
        ("polygon", ((8, 25), (19, 25), (33, 14), (33, 51), (19, 40), (8, 40))),
        ("path", ((40, 23), (44, 28), (44, 37), (40, 43))),
        ("path", ((48, 16), (54, 24), (56, 32), (54, 41), (48, 49))),
    ),
    "wifi": (
        ("path", ((6, 23), (16, 15), (27, 12), (37, 12), (48, 15), (58, 23))),
        ("path", ((15, 32), (23, 26), (32, 24), (41, 26), (49, 32))),
        ("path", ((24, 41), (32, 37), (40, 41))),
        ("circle", (32, 50, 4)),
    ),
    "bluetooth": (
        ("path", ((29, 6), (47, 21), (16, 45), (29, 56), (29, 6))),
        ("path", ((16, 18), (47, 42), (29, 56))),
    ),
    "power": (
        ("arc", (32, 34, 23, -.32, 1.32)),
        ("path", ((32, 6), (32, 31))),
    ),
    "usb": (
        ("path", ((31, 51), (31, 14))),
        ("path", ((31, 39), (17, 29), (17, 19))),
        ("path", ((31, 32), (45, 22), (45, 16))),
        ("polygon", ((31, 5), (24, 16), (38, 16))),
        ("circle", (17, 16, 5)), ("rect", (41, 8, 9, 9)), ("circle", (31, 53, 6)),
    ),
    "text": (
        ("path", ((8, 51), (24, 12), (40, 51))),
        ("path", ((14, 37), (34, 37))),
        ("path", ((44, 51), (52, 30), (60, 51))),
        ("path", ((47, 44), (57, 44))),
    ),
    "contrast": (
        ("ring", (32, 32, 23, 3)),
        ("polygon", ((32, 10), (42, 13), (50, 21), (54, 32), (50, 43), (42, 51), (32, 54))),
    ),
    "wave": (
        ("path", ((5, 24), (14, 20), (23, 20), (41, 30), (50, 30), (59, 26))),
        ("path", ((5, 37), (14, 33), (23, 33), (41, 43), (50, 43), (59, 39))),
    ),
    "info": (
        ("ring", (32, 32, 24, 3)), ("circle", (32, 20, 3)),
        ("rect", (29, 29, 6, 19)),
    ),
}


ALIASES = {
    "Games": "game", "Continue Playing": "recent", "Tools": "tool", "Settings": "settings",
    "random": "recent", "backlight": "display", "hardware_display": "display",
    "hardware_sound": "volume", "hardware_network": "wifi", "hardware_controllers": "game",
    "controllers": "game", "controls": "game", "hardware_power": "power",
    "hardware_usb": "usb", "appearance": "display", "experience": "system",
    "classic": "system", "collections": "folder", "advanced": "settings",
    "setting": "settings", "experience_profile": "system", "menu": "folder",
    "confirm": "game", "sound": "volume", "motion": "wave", "text_scale": "text",
    "high_contrast": "contrast", "device": "system", "support": "info", "about": "info", "undo": "recent",
}
