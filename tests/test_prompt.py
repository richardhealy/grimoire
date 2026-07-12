"""Prompt compiler tests — deterministic, no API calls."""
import pytest
from pathlib import Path
from grimoire.bible.character import CharacterRecord
from grimoire.bible.style import StyleRecord
from grimoire.bible.panel import PanelSpec, BalloonSpec
from grimoire.prompt.compiler import compile_prompt, assert_under_reference_budget

BIBLE_PATH = Path(__file__).parent.parent / "data/bible/xara/character.yaml"
STYLE_PATH = Path(__file__).parent.parent / "data/style/sharran_noir.yaml"


def make_panel(**kwargs) -> PanelSpec:
    defaults = dict(
        panel_id="p01_01", page=1, panel_number=1,
        aspect="3:2", cast=["xara_nightwhisper"],
        wardrobe={"xara_nightwhisper": "default"},
        camera="medium_shot", staging="Xara centre frame",
        negative_space="upper third clear",
        accent_hue="#B4322A",
    )
    defaults.update(kwargs)
    return PanelSpec(**defaults)


def test_compile_injects_descriptor_verbatim():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel()
    result = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    # Descriptor block must appear verbatim in the positive prompt
    assert "obsidian teardrop pendant at her throat" in result.positive

def test_compile_injects_style_block():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel()
    result = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    assert "cross-hatching" in result.positive
    assert "European graphic-novel" in result.positive

def test_compile_negative_includes_style_and_character():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel()
    result = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    assert "no text" in result.negative
    assert "no blue eyes" in result.negative

def test_compile_no_text_in_negative():
    """Critical: style negative block must always include no-text directive."""
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel()
    result = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    assert "no speech bubbles" in result.negative

def test_compile_includes_aspect_ratio():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel(aspect="9:16")
    result = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    assert "9:16" in result.positive

def test_compile_includes_accent_hue():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel(accent_hue="#FF0000")
    result = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    assert "#FF0000" in result.positive

def test_compile_negative_space_in_prompt():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel(negative_space="upper quarter clear sky for balloon")
    result = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    assert "upper quarter clear sky" in result.positive

def test_compile_raises_on_unknown_character():
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel(cast=["unknown_char"])
    with pytest.raises(ValueError, match="not found in bible"):
        compile_prompt(panel, {}, style)

def test_same_inputs_produce_same_output():
    """Prompt compilation must be deterministic."""
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel()
    r1 = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    r2 = compile_prompt(panel, {"xara_nightwhisper": char}, style)
    assert r1.positive == r2.positive
    assert r1.negative == r2.negative

def test_reference_budget_check():
    char = CharacterRecord.from_yaml(BIBLE_PATH)
    style = StyleRecord.from_yaml(STYLE_PATH)
    panel = make_panel(cast=["a","b","c","d","e","f"],
                       wardrobe={})
    chars = {cid: char for cid in panel.cast}
    with pytest.raises(ValueError, match="exceeds"):
        result = compile_prompt(panel, chars, style)
        assert_under_reference_budget(result)
