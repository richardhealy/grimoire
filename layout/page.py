"""
Page layout engine — stage [10] of the pipeline.

Places panels into a page grid as SVG.
Works from the supported aspect ratios and a panel plan.
Never calls an image model.

Print spec (§10):
  Trim:   6.625" × 10.25"
  Bleed:  0.125" all round
  Live:   0.25" inside trim on all sides
  DPI:    300 minimum
  At 300 DPI: 1987.5 × 3075 px (trim), +75px bleed all round → 2137.5 × 3225 px
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
from grimoire.bible.panel import PanelSpec


# ── Print dimensions in pixels at 300 DPI ────────────────────────────────────

DPI = 300
TRIM_W_IN = 6.625
TRIM_H_IN = 10.25
BLEED_IN  = 0.125
LIVE_MARGIN_IN = 0.25

TRIM_W_PX  = int(TRIM_W_IN  * DPI)   # 1987
TRIM_H_PX  = int(TRIM_H_IN  * DPI)   # 3075
BLEED_PX   = int(BLEED_IN   * DPI)   # 37
LIVE_PX    = int(LIVE_MARGIN_IN * DPI)   # 75

TOTAL_W = TRIM_W_PX + 2 * BLEED_PX  # 2062
TOTAL_H = TRIM_H_PX + 2 * BLEED_PX  # 3150

GUTTER_PX = 12   # gutter between panels


@dataclass
class LayoutPanel:
    panel_spec: PanelSpec
    image_path: str    # path to the rendered PNG
    x: int             # position in SVG (from live area top-left)
    y: int
    w: int
    h: int


@dataclass
class PageLayout:
    page_number: int
    panels: list[LayoutPanel] = field(default_factory=list)

    def to_svg(self) -> str:
        """
        Produce an SVG for this page.
        - Canvas is full bleed (TOTAL_W × TOTAL_H)
        - Images are clipped to their panel rect
        - Panel borders are not drawn (they go in the print marks, not here)
        - No text, no balloons (lettering engine adds those as a separate layer)
        """
        root = ET.Element("svg", {
            "xmlns": "http://www.w3.org/2000/svg",
            "xmlns:xlink": "http://www.w3.org/1999/xlink",
            "width": str(TOTAL_W),
            "height": str(TOTAL_H),
            "viewBox": f"0 0 {TOTAL_W} {TOTAL_H}",
        })

        # Black background
        ET.SubElement(root, "rect", {
            "width": str(TOTAL_W), "height": str(TOTAL_H), "fill": "#000000"
        })

        # Trim marks layer (crop marks at corners)
        _add_trim_marks(root)

        # Panel images
        live_x = BLEED_PX + LIVE_PX
        live_y = BLEED_PX + LIVE_PX

        for lp in self.panels:
            abs_x = live_x + lp.x
            abs_y = live_y + lp.y

            # Clip path per panel
            clip_id = f"clip_{lp.panel_spec.panel_id}"
            defs = root.find("defs")
            if defs is None:
                defs = ET.SubElement(root, "defs")
            cp = ET.SubElement(defs, "clipPath", {"id": clip_id})
            ET.SubElement(cp, "rect", {
                "x": str(abs_x), "y": str(abs_y),
                "width": str(lp.w), "height": str(lp.h),
            })

            # Panel image
            ET.SubElement(root, "image", {
                "x": str(abs_x), "y": str(abs_y),
                "width": str(lp.w), "height": str(lp.h),
                "href": lp.image_path,
                "clip-path": f"url(#{clip_id})",
                "preserveAspectRatio": "xMidYMid slice",
            })

        ET.indent(root, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")


def _add_trim_marks(root: ET.Element) -> None:
    """Add crop marks at trim corners (standard print marks)."""
    mark_len = 30
    offset = BLEED_PX
    stroke = {"stroke": "#000000", "stroke-width": "1", "fill": "none"}

    corners = [
        (offset, offset, -mark_len, 0, 0, -mark_len),        # top-left
        (TOTAL_W - offset, offset, mark_len, 0, 0, -mark_len),  # top-right
        (offset, TOTAL_H - offset, -mark_len, 0, 0, mark_len),  # bottom-left
        (TOTAL_W - offset, TOTAL_H - offset, mark_len, 0, 0, mark_len),  # bottom-right
    ]
    for cx, cy, dx1, dy1, dx2, dy2 in corners:
        ET.SubElement(root, "line", {
            "x1": str(cx), "y1": str(cy),
            "x2": str(cx + dx1), "y2": str(cy + dy1),
            **stroke,
        })
        ET.SubElement(root, "line", {
            "x1": str(cx), "y1": str(cy),
            "x2": str(cx + dx2), "y2": str(cy + dy2),
            **stroke,
        })


def layout_six_panel_grid(
    page_number: int,
    panels: list[tuple[PanelSpec, str]],  # (spec, image_path)
) -> PageLayout:
    """
    Classic 6-panel grid: 2 columns × 3 rows.
    Each panel is a 3:2 landscape ratio.
    """
    live_w = TRIM_W_PX - 2 * LIVE_PX
    live_h = TRIM_H_PX - 2 * LIVE_PX

    cols, rows = 2, 3
    panel_w = (live_w - (cols - 1) * GUTTER_PX) // cols
    panel_h = (live_h - (rows - 1) * GUTTER_PX) // rows

    layout = PageLayout(page_number=page_number)
    for i, (spec, img_path) in enumerate(panels[:6]):
        col = i % cols
        row = i // cols
        x = col * (panel_w + GUTTER_PX)
        y = row * (panel_h + GUTTER_PX)
        layout.panels.append(LayoutPanel(
            panel_spec=spec,
            image_path=img_path,
            x=x, y=y, w=panel_w, h=panel_h,
        ))

    return layout


def layout_splash(
    page_number: int,
    panel: PanelSpec,
    image_path: str,
) -> PageLayout:
    """Full-page splash panel."""
    live_w = TRIM_W_PX - 2 * LIVE_PX
    live_h = TRIM_H_PX - 2 * LIVE_PX
    layout = PageLayout(page_number=page_number)
    layout.panels.append(LayoutPanel(
        panel_spec=panel,
        image_path=image_path,
        x=0, y=0, w=live_w, h=live_h,
    ))
    return layout
