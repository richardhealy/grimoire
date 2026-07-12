"""
Lettering engine — stage [11] of the pipeline.

Balloons, tails, and captions as SVG vector overlays.
Composited onto the page layout SVG as a separate layer.

Design rules:
- Balloons are SVG; type is real type at print resolution
- Text is editable after the fact — a typo costs nothing
- Reading order is ENFORCED by the 'order' field, never by hope
- Tail anchors to the declared side of the balloon
- No text is ever in the rendered image (enforced by the negative block)
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
import textwrap
from dataclasses import dataclass
from typing import Literal
from grimoire.bible.panel import BalloonSpec, PanelSpec
from grimoire.layout.page import LayoutPanel, GUTTER_PX


BALLOON_FONT = "Komika Title"          # fallback to system sans-serif
BALLOON_FONT_SIZE = 28                 # px at 300 DPI
BALLOON_PADDING_X = 24
BALLOON_PADDING_Y = 18
BALLOON_FILL = "#FFFFFF"
BALLOON_STROKE = "#000000"
BALLOON_STROKE_WIDTH = 3
TAIL_LENGTH = 40
CHARS_PER_LINE = 20


@dataclass
class PlacedBalloon:
    balloon_spec: BalloonSpec
    x: float          # centre x
    y: float          # centre y
    width: float
    height: float
    tail_x: float     # tail tip (pointing toward character)
    tail_y: float


def _wrap_text(text: str, chars: int = CHARS_PER_LINE) -> list[str]:
    return textwrap.wrap(text, width=chars) or [""]


def _balloon_dimensions(text: str) -> tuple[float, float]:
    """Estimate balloon width and height from text."""
    lines = _wrap_text(text)
    w = max(len(l) for l in lines) * (BALLOON_FONT_SIZE * 0.55) + 2 * BALLOON_PADDING_X
    h = len(lines) * (BALLOON_FONT_SIZE * 1.3) + 2 * BALLOON_PADDING_Y
    return w, h


def place_balloons(
    panel: LayoutPanel,
    abs_x: int = 0,
    abs_y: int = 0,
) -> list[PlacedBalloon]:
    """
    Place balloons for a panel in reading order.
    Each balloon is anchored to the declared side of its speaker.
    """
    placed = []
    balloons_sorted = sorted(panel.panel_spec.balloons, key=lambda b: b.order)

    # Stack balloons top-to-bottom in the negative space
    y_cursor = abs_y + BALLOON_PADDING_Y * 2

    for i, bal in enumerate(balloons_sorted):
        if not bal.text:
            continue

        w, h = _balloon_dimensions(bal.text)

        # X position based on anchor side
        if bal.anchor in ("left",):
            cx = abs_x + w / 2 + BALLOON_PADDING_X
            tail_x = abs_x + w * 0.3
        elif bal.anchor in ("right",):
            cx = abs_x + panel.w - w / 2 - BALLOON_PADDING_X
            tail_x = abs_x + panel.w - w * 0.3
        else:  # centre or top/bottom
            cx = abs_x + panel.w / 2
            tail_x = cx

        cy = y_cursor + h / 2
        tail_y = cy + h / 2 + TAIL_LENGTH * 0.6

        placed.append(PlacedBalloon(
            balloon_spec=bal,
            x=cx, y=cy,
            width=w, height=h,
            tail_x=tail_x, tail_y=tail_y,
        ))

        y_cursor += h + GUTTER_PX

    return placed


def render_balloon_svg(pb: PlacedBalloon) -> ET.Element:
    """Render a single balloon as an SVG group."""
    g = ET.Element("g", {"class": "balloon"})

    x0 = pb.x - pb.width / 2
    y0 = pb.y - pb.height / 2
    rx = pb.height * 0.4   # rounded corners

    # Tail polygon (simple triangle)
    tail_pts = (
        f"{pb.x - 8},{pb.y + pb.height / 2} "
        f"{pb.x + 8},{pb.y + pb.height / 2} "
        f"{pb.tail_x},{pb.tail_y}"
    )
    ET.SubElement(g, "polygon", {
        "points": tail_pts,
        "fill": BALLOON_FILL,
        "stroke": BALLOON_STROKE,
        "stroke-width": str(BALLOON_STROKE_WIDTH),
        "stroke-linejoin": "round",
    })

    # Balloon body (rounded rect)
    ET.SubElement(g, "rect", {
        "x": str(x0), "y": str(y0),
        "width": str(pb.width), "height": str(pb.height),
        "rx": str(rx), "ry": str(rx),
        "fill": BALLOON_FILL,
        "stroke": BALLOON_STROKE,
        "stroke-width": str(BALLOON_STROKE_WIDTH),
    })

    # Text lines
    lines = _wrap_text(pb.balloon_spec.text)
    line_h = BALLOON_FONT_SIZE * 1.3
    text_y0 = pb.y - (len(lines) * line_h) / 2 + BALLOON_FONT_SIZE * 0.8

    for i, line in enumerate(lines):
        t = ET.SubElement(g, "text", {
            "x": str(pb.x),
            "y": str(text_y0 + i * line_h),
            "text-anchor": "middle",
            "font-family": f'"{BALLOON_FONT}", sans-serif',
            "font-size": str(BALLOON_FONT_SIZE),
            "fill": "#000000",
        })
        t.text = line

    return g


def composite_lettering(
    page_svg: str,
    panels: list[LayoutPanel],
    bleed_px: int,
    live_px: int,
) -> str:
    """
    Composite balloon SVG elements onto a page SVG.
    Returns the composited SVG string.
    """
    root = ET.fromstring(page_svg.split("?>", 1)[-1].strip())

    live_x = bleed_px + live_px
    live_y = bleed_px + live_px

    letter_group = ET.SubElement(root, "g", {"id": "lettering-layer"})

    for panel_layout in panels:
        abs_x = live_x + panel_layout.x
        abs_y = live_y + panel_layout.y

        placed = place_balloons(panel_layout, abs_x, abs_y)
        for pb in placed:
            balloon_el = render_balloon_svg(pb)
            letter_group.append(balloon_el)

    ET.indent(root, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
