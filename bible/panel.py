"""
Panel specification — the unit of rendering.

A panel spec is the complete, machine-readable description of one
panel, compiled before any image generation happens. Every field
is explicit. Nothing is improvised at render time.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional

AspectRatio = Literal["1:1","3:2","2:3","3:4","4:3","4:5","5:4","9:16","16:9","21:9"]
CameraType  = Literal[
    "extreme_close_up","close_up","medium_close_up","medium_shot",
    "medium_two_shot","medium_wide","wide","extreme_wide","bird_eye","worm_eye"
]

MAX_CHARACTERS_PER_PANEL = 5   # hard ceiling from the renderer's reference budget
DEFAULT_MAX_CHARACTERS   = 3   # soft limit for clean composition


@dataclass
class BalloonSpec:
    speaker: str        # character id
    anchor: Literal["left","right","top","bottom","centre"]
    order: int          # reading order (1-based)
    text: str = ""      # filled by the lettering stage


@dataclass
class PanelSpec:
    panel_id: str                  # e.g. "p14_03"
    page: int
    panel_number: int              # position on page
    aspect: AspectRatio
    cast: list[str]                # character ids, max 5
    wardrobe: dict[str, str]       # character_id -> wardrobe_state_id
    camera: CameraType
    staging: str                   # natural language staging description
    negative_space: str            # where to leave room for balloons
    accent_hue: str                # hex colour, one per panel
    balloons: list[BalloonSpec] = field(default_factory=list)
    action: str = ""               # what is happening (from DECLARED_ACTION)
    caption: str = ""              # narrator caption if any
    is_splash: bool = False        # true for full-page splash panels

    def validate(self) -> list[str]:
        """Return a list of validation errors. Empty = valid."""
        errors = []
        if len(self.cast) > MAX_CHARACTERS_PER_PANEL:
            errors.append(
                f"panel {self.panel_id}: {len(self.cast)} characters exceeds hard ceiling of {MAX_CHARACTERS_PER_PANEL}"
            )
        if len(self.cast) > DEFAULT_MAX_CHARACTERS and not self.is_splash:
            errors.append(
                f"panel {self.panel_id}: {len(self.cast)} characters exceeds soft limit of {DEFAULT_MAX_CHARACTERS} — consider splitting"
            )
        balloon_orders = [b.order for b in self.balloons]
        if sorted(balloon_orders) != list(range(1, len(balloon_orders) + 1)):
            errors.append(f"panel {self.panel_id}: balloon order values must be sequential from 1")
        if not self.accent_hue.startswith("#") or len(self.accent_hue) not in (4, 7):
            errors.append(f"panel {self.panel_id}: accent_hue must be a hex colour like #B4322A")
        return errors
