# --- Owner: (assign, see docs/TEAM_SPLIT.md) | tests for the decorative illustrations ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
from leasecheck.art import ART_CSS, compact_skyline_svg, hero_skyline_svg, scanning_house_html


def test_svgs_are_single_line():
    # Streamlit markdown turns indented or multi-line HTML into a code block
    for markup in (hero_skyline_svg(), compact_skyline_svg(), scanning_house_html()):
        assert "\n" not in markup and markup.count("<svg") == 1


def test_loader_message_is_escaped():
    assert "<b>" not in scanning_house_html("<b>hi</b>")


def test_reduced_motion_is_respected():
    assert "prefers-reduced-motion" in ART_CSS
