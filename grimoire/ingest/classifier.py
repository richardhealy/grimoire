"""
Transcript classifier — stage [2] of the pipeline.

Splits a D&D session transcript into six utterance types.
This is the hardest stage. See spec §6.

Classification is deterministic-first (keyword + speaker rules),
with LLM fallback for ambiguous cases.

Key insight from the spec:
- DECLARED_ACTION is where the comic lives, not IN_CHARACTER
- MECHANICS are kept as intensity signal, then discarded
- TABLE_TALK is discarded
"""
from __future__ import annotations
import asyncio
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class UtteranceType(str, Enum):
    IN_CHARACTER     = "IN_CHARACTER"      # dialogue spoken as the PC
    DECLARED_ACTION  = "DECLARED_ACTION"   # third-person intent → panel action
    DM_NARRATION     = "DM_NARRATION"      # caption boxes / panel description
    DM_NPC           = "DM_NPC"            # NPC dialogue
    MECHANICS        = "MECHANICS"         # dice, rules — keep as signal, discard
    TABLE_TALK       = "TABLE_TALK"        # discard


@dataclass
class Utterance:
    speaker_id: str         # "Speaker_1", "DM", or mapped character name
    speaker_name: Optional[str]   # resolved character name after speaker map
    raw_text: str
    utterance_type: UtteranceType
    intensity_signal: float = 0.0   # 0-1, from mechanics (nat 20, near-TPK, etc.)
    classified_by: str = "rule"     # "rule" | "llm"


@dataclass
class ClassifiedTranscript:
    utterances: list[Utterance]

    def in_character(self) -> list[Utterance]:
        return [u for u in self.utterances if u.utterance_type == UtteranceType.IN_CHARACTER]

    def declared_actions(self) -> list[Utterance]:
        return [u for u in self.utterances if u.utterance_type == UtteranceType.DECLARED_ACTION]

    def narration(self) -> list[Utterance]:
        return [u for u in self.utterances if u.utterance_type == UtteranceType.DM_NARRATION]

    def intensity_curve(self) -> list[tuple[int, float]]:
        """Returns (utterance_index, intensity) for mechanics beats."""
        return [
            (i, u.intensity_signal)
            for i, u in enumerate(self.utterances)
            if u.utterance_type == UtteranceType.MECHANICS and u.intensity_signal > 0
        ]


# ── Deterministic rules ────────────────────────────────────────────────────────

_MECHANICS_PATTERNS = [
    re.compile(r'\b(nat(?:ural)?\s*(?:1|20)|critical\s+(?:hit|fail))\b', re.IGNORECASE),
    re.compile(r'\broll(?:s|ed|ing)?\b.*\b\d+\b', re.IGNORECASE),
    re.compile(r'\b(initiative|saving\s+throw|perception\s+check|advantage|disadvantage)\b', re.IGNORECASE),
    re.compile(r'\bac\s*\d+\b', re.IGNORECASE),
    re.compile(r'\b\d+d\d+\b'),   # e.g. 2d6
]

_HIGH_INTENSITY_PATTERNS = [
    re.compile(r'\bnat(?:ural)?\s*20\b', re.IGNORECASE),
    re.compile(r'\bcritical\s+hit\b', re.IGNORECASE),
    re.compile(r'\b(down|dying|unconscious|dead|tpk|total\s+party)\b', re.IGNORECASE),
]

_DECLARED_ACTION_PATTERNS = [
    re.compile(r'\b(I|he|she|they)\s+(try\s+to|attempt\s+to|want\s+to|decide\s+to)\b', re.IGNORECASE),
    re.compile(r'\b(Kellan|Xara|the\s+party|\w+)\s+would\s+(probably|try|want|go)\b', re.IGNORECASE),
    re.compile(r'\bI\s+(check|search|examine|attack|cast|move|run|hide|sneak)\b', re.IGNORECASE),
]

_TABLE_TALK_PATTERNS = [
    re.compile(r'\b(pizza|snack|bathroom|brb|afk|irl|oven)\b', re.IGNORECASE),
    re.compile(r'\b(sorry|hold\s+on|one\s+sec|wait\s+a|my\s+bad)\b', re.IGNORECASE),
    re.compile(r'^\s*lol\s*$', re.IGNORECASE),
    re.compile(r'\b(rules\s+question|rules\s+as\s+written|raf|raw|how\s+does\s+that\s+work)\b', re.IGNORECASE),
    re.compile(r'\bhow\s+does\s+\w+\s+work\b', re.IGNORECASE),
    re.compile(r'\bwait[,.]?\s+how\b', re.IGNORECASE),
]


def _mechanics_intensity(text: str) -> float:
    """Return intensity signal for a mechanics utterance."""
    for pat in _HIGH_INTENSITY_PATTERNS:
        if pat.search(text):
            return 1.0
    return 0.3  # low-intensity mechanics


def _classify_by_rule(speaker_id: str, text: str, dm_id: str) -> Optional[UtteranceType]:
    """
    Apply deterministic classification rules.
    Returns None if the utterance needs LLM disambiguation.
    """
    # TABLE_TALK check first — fastest discard
    for pat in _TABLE_TALK_PATTERNS:
        if pat.search(text):
            return UtteranceType.TABLE_TALK

    # MECHANICS
    for pat in _MECHANICS_PATTERNS:
        if pat.search(text):
            return UtteranceType.MECHANICS

    # DM utterances
    if speaker_id == dm_id:
        # Quoted speech within DM narration → NPC
        if re.search(r'[""][^""]+[""]', text) or re.search(r'"[^"]{5,}"', text):
            return UtteranceType.DM_NPC
        return UtteranceType.DM_NARRATION

    # DECLARED_ACTION
    for pat in _DECLARED_ACTION_PATTERNS:
        if pat.search(text):
            return UtteranceType.DECLARED_ACTION

    # Short, first-person statements without action verbs → IN_CHARACTER dialogue
    if len(text.split()) < 20 and text.strip().endswith((".", "!", "?")):
        if not any(v in text.lower() for v in ["roll", "check", "d20", "d6"]):
            return UtteranceType.IN_CHARACTER

    return None   # needs LLM


def classify_transcript(
    raw_lines: list[tuple[str, str]],   # [(speaker_id, text), ...]
    dm_id: str = "DM",
    speaker_map: Optional[dict[str, str]] = None,
) -> ClassifiedTranscript:
    """
    Classify a list of (speaker_id, text) pairs.
    Deterministic rules first; ambiguous utterances labelled TABLE_TALK
    pending LLM disambiguation (in a real pipeline, batch those separately).
    """
    utterances = []
    speaker_map = speaker_map or {}

    for speaker_id, text in raw_lines:
        text = text.strip()
        if not text:
            continue

        utype = _classify_by_rule(speaker_id, text, dm_id)
        classified_by = "rule"

        if utype is None:
            # Default to IN_CHARACTER if no rule matched; LLM would handle edge cases
            utype = UtteranceType.IN_CHARACTER
            classified_by = "default"

        intensity = 0.0
        if utype == UtteranceType.MECHANICS:
            intensity = _mechanics_intensity(text)

        utterances.append(Utterance(
            speaker_id=speaker_id,
            speaker_name=speaker_map.get(speaker_id, speaker_id),
            raw_text=text,
            utterance_type=utype,
            intensity_signal=intensity,
            classified_by=classified_by,
        ))

    return ClassifiedTranscript(utterances=utterances)
