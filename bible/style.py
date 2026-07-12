"""
Style record — global, applied to every panel.

The style is not part of any character. It is a separate lock
so a new character can be added without disturbing the look of the book.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class RenderConfig:
    model: str
    resolution: str           # "1K" | "2K" | "4K"
    thinking: str             # "standard" | "high"
    aspect_ratios: list[str] = field(default_factory=lambda: [
        "1:1", "3:2", "2:3", "3:4", "4:3",
        "4:5", "5:4", "9:16", "16:9", "21:9",
    ])


@dataclass
class StyleRecord:
    style_id: str
    canon_version: int
    style_block: str
    negative_block: str
    palette_accent_rules: list[str]
    style_refs: list[str]
    render_config: RenderConfig

    # Aspect ratio vocabulary — §8
    RATIO_ROLES: dict[str, str] = field(default_factory=lambda: {
        "21:9": "establishing_shot",
        "16:9": "action_wide",
        "9:16": "vertical_drama",
        "3:2":  "standard_panel",
        "2:3":  "portrait_panel",
        "1:1":  "reaction_shot",
        "3:4":  "medium_portrait",
        "4:3":  "medium_landscape",
    })

    def role_for_ratio(self, ratio: str) -> str:
        return self.RATIO_ROLES.get(ratio, "panel")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "StyleRecord":
        data = yaml.safe_load(Path(path).read_text())
        rc = data.get("render_config", {})
        return cls(
            style_id=data["style_id"],
            canon_version=data["canon_version"],
            style_block=data["style_block"],
            negative_block=data["negative_block"],
            palette_accent_rules=data.get("palette_accent_rules", []),
            style_refs=data.get("style_refs", []),
            render_config=RenderConfig(
                model=rc.get("model", "gemini-3.1-flash-image"),
                resolution=rc.get("resolution", "4K"),
                thinking=rc.get("thinking", "high"),
            ),
        )
