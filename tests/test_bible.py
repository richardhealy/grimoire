"""Character and style record tests — no API calls."""
import pytest
from pathlib import Path
from grimoire.bible.character import CharacterRecord
from grimoire.bible.style import StyleRecord
from grimoire.bible.panel import PanelSpec, BalloonSpec, MAX_CHARACTERS_PER_PANEL

BIBLE_PATH  = Path(__file__).parent.parent / "data/bible/xara/character.yaml"
STYLE_PATH  = Path(__file__).parent.parent / "data/style/sharran_noir.yaml"


# ── Character record ───────────────────────────────────────────────────────────

def test_character_loads_from_yaml():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    assert char.id == "xara_nightwhisper"
    assert char.canon_version == 4
    assert char.display_name == "Xara Nightwhisper"

def test_invariants_loaded():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    assert len(char.visual.invariants) == 6
    assert any("scar" in inv for inv in char.visual.invariants)

def test_descriptor_block_verbatim():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    desc = char.descriptor_for_prompt()
    assert "Xara Nightwhisper" in desc
    assert "obsidian teardrop" in desc
    assert "grey left eye" in desc

def test_wardrobe_state_lookup():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    ws = char.visual.wardrobe("hood_up")
    assert ws is not None
    assert "hood_up" in ws.refs[0]

def test_wardrobe_default_fallback():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    refs = char.refs_for_wardrobe("nonexistent_state")
    assert refs == char.visual.canonical_refs

def test_voice_card_loaded():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    assert "shadow" in char.voice.lexicon_yes
    assert "amazing" in char.voice.lexicon_no
    assert len(char.voice.gold_lines) == 4

def test_drift_failure_accumulates_in_negative():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    original_neg = char.visual.negative_block
    char.add_drift_failure_to_negative("no brown eyes")
    assert "no brown eyes" in char.visual.negative_block

def test_drift_failure_no_duplicate():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    char.add_drift_failure_to_negative("no blue eyes")  # already in the block
    # Should not add a duplicate
    count = char.visual.negative_block.lower().count("no blue eyes")
    assert count == 1

def test_serialize_to_yaml_round_trip():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    yaml_str = char.to_yaml()
    assert "xara_nightwhisper" in yaml_str
    assert "obsidian teardrop" in yaml_str


# ── Style record ───────────────────────────────────────────────────────────────

def test_style_loads():
    style = StyleRecord.from_yaml(STYLE_PATH)
    assert style.style_id == "sharran_noir"
    assert "cross-hatching" in style.style_block

def test_style_negative_block_has_no_text():
    style = StyleRecord.from_yaml(STYLE_PATH)
    assert "no text" in style.negative_block
    assert "no speech bubbles" in style.negative_block

def test_ratio_roles():
    style = StyleRecord.from_yaml(STYLE_PATH)
    assert style.role_for_ratio("21:9") == "establishing_shot"
    assert style.role_for_ratio("9:16") == "vertical_drama"
    assert style.role_for_ratio("1:1") == "reaction_shot"


# ── Panel spec ────────────────────────────────────────────────────────────────

def make_panel(**kwargs) -> PanelSpec:
    defaults = dict(
        panel_id="p01_01", page=1, panel_number=1,
        aspect="3:2", cast=["xara_nightwhisper"],
        wardrobe={"xara_nightwhisper": "default"},
        camera="medium_shot", staging="Xara centre frame",
        negative_space="upper third clear for balloon",
        accent_hue="#B4322A",
        balloons=[BalloonSpec(speaker="xara_nightwhisper", anchor="left", order=1, text="Don't.")],
    )
    defaults.update(kwargs)
    return PanelSpec(**defaults)

def test_panel_validates_clean():
    panel = make_panel()
    assert panel.validate() == []

def test_panel_rejects_too_many_characters():
    panel = make_panel(cast=["a","b","c","d","e","f"])
    errors = panel.validate()
    assert any("hard ceiling" in e for e in errors)

def test_panel_warns_on_3_plus_characters():
    panel = make_panel(cast=["a","b","c","d"])
    errors = panel.validate()
    assert any("soft limit" in e for e in errors)

def test_panel_rejects_bad_balloon_order():
    panel = make_panel(balloons=[
        BalloonSpec("xara_nightwhisper", "left", order=1, text="A"),
        BalloonSpec("kellan", "right", order=3, text="B"),  # gap in order
    ])
    errors = panel.validate()
    assert any("sequential" in e for e in errors)

def test_panel_rejects_bad_accent_hue():
    panel = make_panel(accent_hue="red")
    errors = panel.validate()
    assert any("hex" in e for e in errors)
