"""
Character record — the source of truth for visual and voice identity.

A character is not a prompt. It is a versioned record of invariants,
descriptor blocks, palette, reference image paths, and voice card.
Everything the pipeline generates is compiled from this record.
A drift failure is a failed build, not a bad prompt.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import yaml
from pathlib import Path


@dataclass
class WardrobeState:
    id: str
    refs: list[str]
    note: Optional[str] = None


@dataclass
class VoiceCard:
    register: str
    cadence: str
    lexicon_yes: list[str] = field(default_factory=list)
    lexicon_no: list[str] = field(default_factory=list)
    tics: list[str] = field(default_factory=list)
    never_says: list[str] = field(default_factory=list)
    gold_lines: list[str] = field(default_factory=list)


@dataclass
class VisualRecord:
    invariants: list[str]
    descriptor_block: str
    negative_block: str
    palette: dict[str, str]
    canonical_refs: list[str]
    expression_refs: list[str] = field(default_factory=list)
    detail_refs: list[str] = field(default_factory=list)
    wardrobe_states: list[WardrobeState] = field(default_factory=list)

    def wardrobe(self, state_id: str) -> Optional[WardrobeState]:
        return next((w for w in self.wardrobe_states if w.id == state_id), None)


@dataclass
class Relationship:
    character_id: str
    description: str


@dataclass
class BehaviourCard:
    wants: str
    fears: str
    under_pressure: str
    relationships: list[Relationship] = field(default_factory=list)


@dataclass
class CharacterRecord:
    id: str
    canon_version: int
    display_name: str
    visual: VisualRecord
    voice: VoiceCard
    behaviour: BehaviourCard

    def descriptor_for_prompt(self, wardrobe_state: str = "default") -> str:
        """
        Compile the invariant descriptor block for injection into a prompt.
        The descriptor is never paraphrased — it is injected verbatim.
        If a wardrobe state is specified, appends the wardrobe note.
        """
        base = self.visual.descriptor_block.strip()
        ws = self.visual.wardrobe(wardrobe_state)
        if ws and ws.note:
            base += f" [{ws.note}]"
        return base

    def negative_for_prompt(self) -> str:
        return self.visual.negative_block.strip()

    def refs_for_wardrobe(self, state_id: str = "default") -> list[str]:
        ws = self.visual.wardrobe(state_id)
        if ws:
            return ws.refs
        return self.visual.canonical_refs

    def add_drift_failure_to_negative(self, failure: str) -> None:
        """
        Accumulate confirmed drift failures into the negative block.
        The bible is a learning system; every failure improves future renders.
        """
        existing = self.visual.negative_block.strip().rstrip(",")
        addition = failure.strip().rstrip(",")
        if addition.lower() not in existing.lower():
            self.visual.negative_block = existing + f",\n    {addition}"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CharacterRecord":
        data = yaml.safe_load(Path(path).read_text())
        v = data["visual"]
        refs = v.get("refs", {})

        wardrobe = [
            WardrobeState(
                id=w["id"],
                refs=w.get("refs", []),
                note=w.get("note"),
            )
            for w in v.get("wardrobe_states", [])
        ]

        voice_data = data["voice"]
        voice = VoiceCard(
            register=voice_data["register"],
            cadence=voice_data["cadence"],
            lexicon_yes=voice_data.get("lexicon_yes", []),
            lexicon_no=voice_data.get("lexicon_no", []),
            tics=voice_data.get("tics", []),
            never_says=voice_data.get("never_says", []),
            gold_lines=voice_data.get("gold_lines", []),
        )

        beh_data = data.get("behaviour", {})
        relationships = [
            Relationship(character_id=k, description=v_)
            for k, v_ in beh_data.get("relationships", {}).items()
        ]
        behaviour = BehaviourCard(
            wants=beh_data.get("wants", ""),
            fears=beh_data.get("fears", ""),
            under_pressure=beh_data.get("under_pressure", ""),
            relationships=relationships,
        )

        return cls(
            id=data["id"],
            canon_version=data["canon_version"],
            display_name=data["display_name"],
            visual=VisualRecord(
                invariants=v["invariants"],
                descriptor_block=v["descriptor_block"],
                negative_block=v["negative_block"],
                palette=v.get("palette", {}),
                canonical_refs=refs.get("canonical", []),
                expression_refs=refs.get("expressions", []),
                detail_refs=refs.get("detail", []),
                wardrobe_states=wardrobe,
            ),
            voice=voice,
            behaviour=behaviour,
        )

    def to_yaml(self) -> str:
        """Serialize back to YAML for saving updated negative blocks."""
        relationships_dict = {
            r.character_id: r.description for r in self.behaviour.relationships
        }
        data = {
            "id": self.id,
            "canon_version": self.canon_version,
            "display_name": self.display_name,
            "visual": {
                "invariants": self.visual.invariants,
                "descriptor_block": self.visual.descriptor_block,
                "negative_block": self.visual.negative_block,
                "palette": self.visual.palette,
                "refs": {
                    "canonical": self.visual.canonical_refs,
                    "expressions": self.visual.expression_refs,
                    "detail": self.visual.detail_refs,
                },
                "wardrobe_states": [
                    {"id": w.id, "refs": w.refs, **({"note": w.note} if w.note else {})}
                    for w in self.visual.wardrobe_states
                ],
            },
            "voice": {
                "register": self.voice.register,
                "cadence": self.voice.cadence,
                "lexicon_yes": self.voice.lexicon_yes,
                "lexicon_no": self.voice.lexicon_no,
                "tics": self.voice.tics,
                "never_says": self.voice.never_says,
                "gold_lines": self.voice.gold_lines,
            },
            "behaviour": {
                "wants": self.behaviour.wants,
                "fears": self.behaviour.fears,
                "under_pressure": self.behaviour.under_pressure,
                "relationships": relationships_dict,
            },
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True)
