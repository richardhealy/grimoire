"""
Render stub — the renderer interface.

The renderer is a plugin, not the architecture (spec §2).
This stub implements the interface so all other stages can
be built and tested without a live image API.

To swap in Gemini: replace _call_api() with the real call.
The CompiledPrompt schema is model-agnostic.
"""
from __future__ import annotations
import os
import asyncio
import base64
from dataclasses import dataclass
from pathlib import Path
from grimoire.prompt.compiler import CompiledPrompt


@dataclass
class RenderResult:
    panel_id: str
    image_path: str     # where the PNG was saved
    model_used: str
    resolution: str
    success: bool
    error: Optional[str] = None


from typing import Optional


async def render_panel(
    prompt: CompiledPrompt,
    output_dir: str | Path,
    attempt: int = 1,
) -> RenderResult:
    """
    Render one panel from a compiled prompt.

    In production: calls the Gemini image API with the positive prompt,
    negative prompt, reference images, and resolution setting.

    In this stub: writes a placeholder PNG so the rest of the pipeline
    (layout, lettering, drift gate with stub LLM) can be exercised end-to-end.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    image_path = output_dir / f"{prompt.panel_id}_attempt{attempt}.png"

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key and not os.environ.get("CANON_USE_STUB", ""):
        result = await _call_gemini(prompt, image_path, api_key)
    else:
        result = _write_placeholder(prompt, image_path)

    return result


def _write_placeholder(prompt: CompiledPrompt, image_path: Path) -> RenderResult:
    """Write a minimal valid PNG placeholder (1×1 white pixel)."""
    # Minimal valid 1×1 white PNG
    PNG_1x1 = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwADhQGAWjR9awAAAABJRU5ErkJggg=="
    )
    image_path.write_bytes(PNG_1x1)
    return RenderResult(
        panel_id=prompt.panel_id,
        image_path=str(image_path),
        model_used="stub",
        resolution=prompt.resolution,
        success=True,
    )


async def _call_gemini(
    prompt: CompiledPrompt,
    image_path: Path,
    api_key: str,
) -> RenderResult:
    """
    Real Gemini image generation call.
    Model: gemini-3.1-flash-image (standard panels)
           gemini-3-pro-image (splash pages)
    """
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)

        # Build the parts list: prompt text + reference images
        parts: list = [prompt.positive]

        for ref_path in prompt.reference_image_paths + prompt.style_ref_paths:
            if Path(ref_path).exists():
                img_bytes = Path(ref_path).read_bytes()
                parts.append({
                    "inline_data": {
                        "mime_type": "image/png",
                        "data": base64.b64encode(img_bytes).decode(),
                    }
                })

        model = genai.GenerativeModel(prompt.model)
        response = await asyncio.to_thread(
            model.generate_content,
            parts,
            generation_config={
                "response_modalities": ["IMAGE"],
                "image_config": {
                    "negative_prompt": prompt.negative,
                    "resolution": prompt.resolution,
                },
            },
        )

        # Extract image bytes from response
        for part in response.parts:
            if hasattr(part, "inline_data") and part.inline_data:
                img_bytes = base64.b64decode(part.inline_data.data)
                image_path.write_bytes(img_bytes)
                return RenderResult(
                    panel_id=prompt.panel_id,
                    image_path=str(image_path),
                    model_used=prompt.model,
                    resolution=prompt.resolution,
                    success=True,
                )

        return RenderResult(
            panel_id=prompt.panel_id,
            image_path=str(image_path),
            model_used=prompt.model,
            resolution=prompt.resolution,
            success=False,
            error="No image in response",
        )

    except Exception as e:
        return RenderResult(
            panel_id=prompt.panel_id,
            image_path=str(image_path),
            model_used=prompt.model,
            resolution=prompt.resolution,
            success=False,
            error=str(e),
        )
