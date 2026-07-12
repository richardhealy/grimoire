"""Transcript classifier tests — deterministic, no API calls."""
import pytest
from grimoire.ingest.classifier import classify_transcript, UtteranceType


def classify(lines, dm_id="DM", speaker_map=None):
    return classify_transcript(lines, dm_id=dm_id, speaker_map=speaker_map)


# ── Table talk ────────────────────────────────────────────────────────────────

def test_pizza_is_table_talk():
    result = classify([("Player1", "Anyone want more pizza?")])
    assert result.utterances[0].utterance_type == UtteranceType.TABLE_TALK

def test_rules_question_is_table_talk():
    result = classify([("Player1", "Wait, how does advantage work with sneak attack?")])
    assert result.utterances[0].utterance_type == UtteranceType.TABLE_TALK


# ── Mechanics ─────────────────────────────────────────────────────────────────

def test_nat_20_is_mechanics():
    result = classify([("Player1", "Natural 20!")])
    u = result.utterances[0]
    assert u.utterance_type == UtteranceType.MECHANICS
    assert u.intensity_signal == 1.0

def test_dice_roll_is_mechanics():
    result = classify([("Player1", "I roll 2d6 for damage")])
    assert result.utterances[0].utterance_type == UtteranceType.MECHANICS

def test_low_intensity_mechanics():
    result = classify([("Player1", "rolling perception check, got a 14")])
    u = result.utterances[0]
    assert u.utterance_type == UtteranceType.MECHANICS
    assert u.intensity_signal == 0.3


# ── DM utterances ─────────────────────────────────────────────────────────────

def test_dm_narration():
    result = classify([("DM", "The door creaks open to reveal a long dark corridor.")])
    assert result.utterances[0].utterance_type == UtteranceType.DM_NARRATION

def test_dm_npc_with_quotes():
    result = classify([("DM", 'The innkeeper says "We\'re full up, travellers."')])
    assert result.utterances[0].utterance_type == UtteranceType.DM_NPC


# ── Declared actions ──────────────────────────────────────────────────────────

def test_i_check_the_door_is_declared_action():
    result = classify([("Player1", "I check the door for traps.")])
    assert result.utterances[0].utterance_type == UtteranceType.DECLARED_ACTION

def test_would_probably_is_declared_action():
    result = classify([("Player1", "Kellan would probably try to talk our way in.")])
    assert result.utterances[0].utterance_type == UtteranceType.DECLARED_ACTION

def test_try_to_is_declared_action():
    result = classify([("Player1", "I try to pick the lock.")])
    assert result.utterances[0].utterance_type == UtteranceType.DECLARED_ACTION


# ── Speaker map ───────────────────────────────────────────────────────────────

def test_speaker_map_resolves_names():
    speaker_map = {"Speaker_1": "Xara", "Speaker_2": "Kellan"}
    result = classify(
        [("Speaker_1", "I've been in worse rooms."),
         ("Speaker_2", "That's not reassuring.")],
        speaker_map=speaker_map,
    )
    assert result.utterances[0].speaker_name == "Xara"
    assert result.utterances[1].speaker_name == "Kellan"


# ── Intensity curve ───────────────────────────────────────────────────────────

def test_intensity_curve_peaks_at_nat20():
    lines = [
        ("Player1", "I search the room."),
        ("Player1", "Natural 20!"),
        ("Player1", "I try to open the chest."),
        ("Player1", "rolling perception check, got an 8"),
    ]
    result = classify(lines)
    curve = result.intensity_curve()
    assert len(curve) >= 1
    high_intensity = [sig for _, sig in curve if sig == 1.0]
    assert len(high_intensity) >= 1


# ── Filtering helpers ─────────────────────────────────────────────────────────

def test_in_character_filter():
    lines = [
        ("DM", "You enter the tavern."),
        ("Player1", "I look around."),
        ("Player1", "Don't. Whatever it is, don't."),
    ]
    result = classify(lines)
    in_char = result.in_character()
    # At minimum the clear dialogue line should be in-character
    texts = [u.raw_text for u in in_char]
    assert any("Don't" in t for t in texts)

def test_empty_lines_ignored():
    result = classify([("Player1", ""), ("Player1", "   ")])
    assert len(result.utterances) == 0
