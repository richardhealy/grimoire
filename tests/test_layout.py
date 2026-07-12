"""Layout and lettering tests — no API calls, no image files needed."""
import pytest
from grimoire.bible.panel import PanelSpec, BalloonSpec
from grimoire.layout.page import (
    PageLayout, LayoutPanel, layout_six_panel_grid, layout_splash,
    TRIM_W_PX, TRIM_H_PX, BLEED_PX, TOTAL_W, TOTAL_H,
)
from grimoire.letter.balloons import place_balloons, composite_lettering


def make_panel_spec(pid="p01_01", cast=None, balloons=None) -> PanelSpec:
    return PanelSpec(
        panel_id=pid, page=1, panel_number=1,
        aspect="3:2", cast=cast or ["xara_nightwhisper"],
        wardrobe={},
        camera="medium_shot",
        staging="Xara centre",
        negative_space="upper third",
        accent_hue="#B4322A",
        balloons=balloons or [],
    )


def make_layout_panel(pid="p01_01", x=0, y=0, w=400, h=300, text="") -> LayoutPanel:
    balloons = []
    if text:
        balloons = [BalloonSpec(speaker="xara_nightwhisper", anchor="left", order=1, text=text)]
    spec = make_panel_spec(pid=pid, balloons=balloons)
    return LayoutPanel(panel_spec=spec, image_path="placeholder.png", x=x, y=y, w=w, h=h)


# ── Dimensions ────────────────────────────────────────────────────────────────

def test_total_canvas_adds_bleed():
    assert TOTAL_W == TRIM_W_PX + 2 * BLEED_PX
    assert TOTAL_H == TRIM_H_PX + 2 * BLEED_PX

def test_trim_dimensions_correct():
    assert TRIM_W_PX == int(6.625 * 300)
    assert TRIM_H_PX == int(10.25 * 300)


# ── Six-panel grid ────────────────────────────────────────────────────────────

def test_six_panel_grid_places_six_panels():
    panels = [(make_panel_spec(f"p01_{i:02d}"), f"panel_{i}.png") for i in range(6)]
    layout = layout_six_panel_grid(1, panels)
    assert len(layout.panels) == 6

def test_six_panel_grid_truncates_to_six():
    panels = [(make_panel_spec(f"p01_{i:02d}"), f"panel_{i}.png") for i in range(8)]
    layout = layout_six_panel_grid(1, panels)
    assert len(layout.panels) == 6

def test_six_panel_grid_panels_do_not_overlap():
    panels = [(make_panel_spec(f"p01_{i:02d}"), f"panel_{i}.png") for i in range(6)]
    layout = layout_six_panel_grid(1, panels)
    for i, a in enumerate(layout.panels):
        for j, b in enumerate(layout.panels):
            if i == j:
                continue
            overlap_x = a.x < b.x + b.w and a.x + a.w > b.x
            overlap_y = a.y < b.y + b.h and a.y + a.h > b.y
            assert not (overlap_x and overlap_y), f"panels {i} and {j} overlap"

def test_splash_layout_fills_live_area():
    panel = make_panel_spec("p00_splash")
    panel.is_splash = True
    layout = layout_splash(1, panel, "splash.png")
    assert len(layout.panels) == 1
    lp = layout.panels[0]
    assert lp.x == 0 and lp.y == 0


# ── SVG output ────────────────────────────────────────────────────────────────

def test_svg_output_is_valid():
    panels = [(make_panel_spec(f"p01_{i:02d}"), f"panel_{i}.png") for i in range(6)]
    layout = layout_six_panel_grid(1, panels)
    svg = layout.to_svg()
    assert svg.startswith("<?xml")
    assert "<svg" in svg
    assert "</svg>" in svg

def test_svg_has_no_text_elements():
    """The layout SVG must have no text — lettering is a separate pass."""
    panels = [(make_panel_spec(f"p01_{i:02d}"), f"panel_{i}.png") for i in range(4)]
    layout = layout_six_panel_grid(1, panels)
    svg = layout.to_svg()
    assert "<text" not in svg


# ── Lettering ─────────────────────────────────────────────────────────────────

def test_balloons_placed_in_reading_order():
    lp = make_layout_panel(text="Don't.")
    lp.panel_spec.balloons = [
        BalloonSpec("xara_nightwhisper", "left",  order=1, text="Don't."),
        BalloonSpec("kellan",             "right", order=2, text="Why not?"),
    ]
    placed = place_balloons(lp, abs_x=100, abs_y=100)
    assert len(placed) == 2
    # First balloon should be above the second
    assert placed[0].y < placed[1].y

def test_balloon_anchor_left_positions_left():
    lp = make_layout_panel(w=600, h=400)
    lp.panel_spec.balloons = [
        BalloonSpec("xara_nightwhisper", "left", order=1, text="I've been in worse rooms."),
    ]
    placed = place_balloons(lp, abs_x=0, abs_y=0)
    assert placed[0].x < 300   # positioned in left half

def test_composite_lettering_adds_text_layer():
    panels = [(make_panel_spec("p01_01"), "img.png")]
    layout = layout_six_panel_grid(1, panels)
    base_svg = layout.to_svg()

    # Add text to the panel
    layout.panels[0].panel_spec.balloons = [
        BalloonSpec("xara_nightwhisper", "left", order=1, text="Don't.")
    ]

    from grimoire.layout.page import BLEED_PX, LIVE_PX
    composited = composite_lettering(base_svg, layout.panels, BLEED_PX, LIVE_PX)
    assert "lettering-layer" in composited
    assert "Don't." in composited
