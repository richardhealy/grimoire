"""
Prompt compiler — stage [7] of the pipeline.

Pure deterministic assembly. Zero creativity here.
The output is a complete, reproducible prompt for any given panel spec
and character bible state. Same inputs → same prompt, always.

Structure of a compiled prompt:
  1. Style block (verbatim from StyleRecord)
  2. For each character in cast: descriptor_block (verbatim)
  3. Negative block = style_negative + all character negatives
  4. Shot specification (camera, staging, action)
  5. Negative space instruction (for balloon placement)
  6. Accent hue instruction
  7. Resolution and format instructions
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from grimoire.bible.character import CharacterRecord
from grimoire.bible.style import StyleRecord
from grimoire.bible.panel import PanelSpec


@dataclass
class CompiledPrompt:
    panel_id: str
    positive: str
    negative: str
    reference_image_paths: list[str]   # paths to inject as reference images
    style_ref_paths: list[str]
    model: str
    resolution: str
    thinking: str
    estimated_ref_count: int            # must be ≤ 5 (renderer budget)


def compile_prompt(
    panel: PanelSpec,
    characters: dict[str, CharacterRecord],   # id → record
    style: StyleRecord,
    extra_refs: Optional[list[str]] = None,   # location/prop refs
) -> CompiledPrompt:
    """
    Compile a complete prompt from a panel spec + character records + style.

    The descriptor blocks are injected VERBATIM. Never paraphrased.
    """
    # ── Positive prompt ───────────────────────────────────────────────────────
    parts = []

    # 1. Style block
    parts.append(style.style_block.strip())

    # 2. Character descriptors — one per cast member, verbatim
    for char_id in panel.cast:
        char = characters.get(char_id)
        if not char:
            raise ValueError(f"Character '{char_id}' in panel cast not found in bible")
        wardrobe_state = panel.wardrobe.get(char_id, "default")
        parts.append(char.descriptor_for_prompt(wardrobe_state))

    # 3. Shot specification
    shot_parts = [f"Camera: {panel.camera.replace('_', ' ')}."]
    if panel.action:
        shot_parts.append(f"Action: {panel.action}")
    shot_parts.append(f"Staging: {panel.staging}")
    parts.append(" ".join(shot_parts))

    # 4. Negative space for balloon placement
    if panel.negative_space:
        parts.append(f"Composition note: {panel.negative_space}")

    # 5. Accent hue
    parts.append(f"Accent colour for this panel: {panel.accent_hue}")

    # 6. Format
    parts.append(f"Aspect ratio: {panel.aspect}. No text, no speech bubbles, no panel borders.")

    positive = "\n\n".join(parts)

    # ── Negative prompt ───────────────────────────────────────────────────────
    neg_parts = [style.negative_block.strip()]
    for char_id in panel.cast:
        char = characters.get(char_id)
        if char:
            neg_parts.append(char.negative_for_prompt())

    negative = ", ".join(p.strip().strip(",") for p in neg_parts if p.strip())

    # ── Reference images ──────────────────────────────────────────────────────
    ref_paths: list[str] = []
    for char_id in panel.cast:
        char = characters.get(char_id)
        if char:
            wardrobe_state = panel.wardrobe.get(char_id, "default")
            char_refs = char.refs_for_wardrobe(wardrobe_state)
            # Limit per-character refs to keep under the 5-item budget
            ref_paths.extend(char_refs[:2])

    if extra_refs:
        ref_paths.extend(extra_refs)

    # Hard cap: renderer supports max 5 characters/14 objects but we budget conservatively
    if len(ref_paths) > 14:
        ref_paths = ref_paths[:14]

    return CompiledPrompt(
        panel_id=panel.panel_id,
        positive=positive,
        negative=negative,
        reference_image_paths=ref_paths,
        style_ref_paths=style.style_refs,
        model=style.render_config.model,
        resolution=style.render_config.resolution,
        thinking=style.render_config.thinking,
        estimated_ref_count=len(panel.cast),
    )


def assert_under_reference_budget(prompt: CompiledPrompt) -> None:
    """Raise if the reference count exceeds the renderer's character budget."""
    if prompt.estimated_ref_count > 5:
        raise ValueError(
            f"Panel {prompt.panel_id}: {prompt.estimated_ref_count} characters "
            f"exceeds the renderer's 5-character reference budget"
        )
