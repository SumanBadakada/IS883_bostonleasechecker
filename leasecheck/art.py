# --- Owner: (assign, see docs/TEAM_SPLIT.md) | decorative house illustrations and their animations ---
# AI-assisted: drafted with Claude Code. The owner must review it and be able to explain it (IS883 §9).
"""Inline SVG illustrations of Boston rowhouses, animated with CSS.

Drawn in code rather than loaded as images: nothing to license or host, nothing extra to download,
and they scale cleanly at any screen size. All motion is slow and decorative, and it switches off for
visitors whose device asks for reduced motion.

Streamlit's markdown treats indented lines as code blocks, so every SVG is returned as a single line.
"""
from __future__ import annotations

import re

WINDOW = "#FDE68A"  # warm lit-window yellow


def _one_line(svg: str) -> str:
    return re.sub(r">\s+<", "><", re.sub(r"\s*\n\s*", " ", svg)).strip()


def _windows(x0: float, y0: float, cols: int, rows: int, w: float, h: float, gx: float, gy: float,
             seed: int) -> str:
    """A grid of windows; each gets one of six staggered glow animations."""
    out = []
    for r in range(rows):
        for c in range(cols):
            n = (seed + r * cols + c * 2) % 6
            out.append(f'<rect class="win w{n}" x="{x0 + c * gx:.1f}" y="{y0 + r * gy:.1f}" '
                       f'width="{w}" height="{h}" rx="1.5"/>')
    return "".join(out)


def _skyline_buildings() -> str:
    """Six Boston-style houses on a 600x220 canvas, ground at y=220."""
    return "".join([
        # 1. Back Bay brownstone: mansard roof, bay window, stoop
        '<g class="bld b1"><polygon points="18,72 30,48 100,48 112,72"/><rect x="18" y="72" width="94" height="148"/>'
        '<rect class="bay" x="28" y="88" width="34" height="132"/>'
        '<rect class="door" x="76" y="186" width="20" height="34" rx="9"/>'
        '<rect class="stoop" x="70" y="214" width="32" height="6"/></g>',
        _windows(33, 96, 2, 4, 10, 16, 14, 24, 0), _windows(78, 96, 1, 3, 14, 18, 0, 28, 3),
        # 2. Triple-decker: gable roof, stacked porches
        '<g class="bld b2"><polygon points="120,58 160,26 200,58"/><rect x="120" y="58" width="80" height="162"/>'
        '<rect class="porch" x="120" y="108" width="80" height="4"/><rect class="porch" x="120" y="158" width="80" height="4"/>'
        '<rect class="door" x="151" y="190" width="18" height="30" rx="2"/></g>',
        _windows(130, 70, 2, 3, 14, 20, 46, 50, 1),
        # 3. Flat-roofed brownstone with a cornice
        '<g class="bld b3"><rect x="206" y="80" width="88" height="140"/><rect class="cornice" x="202" y="74" width="96" height="8"/>'
        '<rect class="door" x="240" y="188" width="20" height="32" rx="9"/></g>',
        _windows(216, 92, 3, 4, 12, 17, 26, 24, 2),
        # 4. Tall brick building with a chimney
        '<g class="bld b4"><rect x="302" y="44" width="72" height="176"/><rect x="352" y="28" width="10" height="18"/>'
        '<rect class="cornice" x="298" y="40" width="80" height="6"/></g>',
        _windows(312, 56, 3, 6, 10, 15, 20, 26, 4),
        # 5. Queen Anne house with a turret
        '<g class="bld b5"><rect x="382" y="86" width="96" height="134"/><polygon points="382,86 430,58 478,86"/>'
        '<rect x="452" y="70" width="26" height="150"/><polygon points="448,72 465,40 482,72"/>'
        '<rect class="door" x="408" y="186" width="20" height="34" rx="2"/></g>',
        _windows(392, 100, 2, 3, 12, 18, 26, 28, 5), _windows(459, 84, 1, 4, 12, 16, 0, 30, 2),
        # 6. Small cottage with a tree
        '<g class="bld b6"><polygon points="486,128 530,96 574,128"/><rect x="490" y="128" width="80" height="92"/>'
        '<rect class="door" x="522" y="184" width="16" height="36" rx="2"/></g>',
        _windows(498, 142, 2, 1, 14, 16, 48, 0, 1),
        '<g class="tree"><rect x="586" y="176" width="4" height="44"/><circle cx="588" cy="166" r="16"/>'
        '<circle cx="578" cy="176" r="10"/><circle cx="598" cy="176" r="10"/></g>',
    ])


def hero_skyline_svg() -> str:
    clouds = ('<g transform="translate(0,22)"><g class="cloud c1"><ellipse cx="0" cy="0" rx="28" ry="9"/>'
              '<ellipse cx="18" cy="-6" rx="18" ry="9"/></g></g>'
              '<g transform="translate(0,10)"><g class="cloud c2"><ellipse cx="0" cy="0" rx="22" ry="7"/>'
              '<ellipse cx="-12" cy="-5" rx="14" ry="7"/></g></g>'
              '<g transform="translate(0,34)"><g class="cloud c3"><ellipse cx="0" cy="0" rx="34" ry="10"/>'
              '<ellipse cx="20" cy="-7" rx="20" ry="10"/></g></g>')
    return _one_line(f"""
    <svg class="blc-skyline" viewBox="0 0 614 224" role="img" aria-label="Illustration of Boston rowhouses">
      <circle class="moon" cx="560" cy="30" r="13"/>
      {clouds}
      {_skyline_buildings()}
      <rect class="ground" x="0" y="219" width="614" height="5" rx="2"/>
    </svg>""")


def compact_skyline_svg() -> str:
    return _one_line(f"""
    <svg class="blc-skyline small" viewBox="0 0 614 224" preserveAspectRatio="xMaxYMax meet" aria-hidden="true">
      {_skyline_buildings()}
    </svg>""")


def scanning_house_html(message: str = "Reading your lease") -> str:
    """Shown while a lease is being checked: a house with a scan line sweeping over it."""
    from html import escape

    svg = _one_line("""
    <svg viewBox="0 0 160 150" class="blc-scan" aria-hidden="true">
      <defs><linearGradient id="scanGrad" x1="0" x2="0" y1="0" y2="1">
        <stop offset="0" stop-color="#2E6DA4" stop-opacity="0"/><stop offset="1" stop-color="#2E6DA4" stop-opacity=".55"/>
      </linearGradient><clipPath id="houseClip"><polygon points="20,62 80,14 140,62 140,140 20,140"/></clipPath></defs>
      <polygon class="roof" points="12,66 80,10 148,66"/>
      <rect class="walls" x="24" y="62" width="112" height="78" rx="3"/>
      <rect class="pane" x="38" y="78" width="24" height="22" rx="2"/><rect class="pane" x="98" y="78" width="24" height="22" rx="2"/>
      <rect class="pane door" x="68" y="100" width="24" height="40" rx="3"/>
      <rect class="chim" x="108" y="24" width="12" height="26"/>
      <g clip-path="url(#houseClip)"><rect class="beam" x="0" y="-30" width="160" height="30" fill="url(#scanGrad)"/></g>
    </svg>""")
    return (f'<div class="blc-loader">{svg}<div><div class="blc-loader-t">{escape(message)}</div>'
            f'<div class="blc-muted">Checking each clause against Massachusetts tenant law. '
            f'This usually takes 20 to 60 seconds on the free tier.</div></div></div>')


ART_CSS = f"""
.blc-hero {{ position: relative; overflow: hidden; display: flex; align-items: flex-end; gap: 24px; }}
.blc-hero-text {{ flex: 1 1 48%; position: relative; z-index: 1; padding-bottom: 6px; }}
.blc-hero-art {{ flex: 1 1 50%; min-width: 280px; margin: -8px -14px -36px 0; }}
.blc-skyline {{ width: 100%; height: auto; display: block; }}
.blc-skyline .bld {{ fill: rgba(255,255,255,.16); }}
.blc-skyline .b2, .blc-skyline .b5 {{ fill: rgba(255,255,255,.22); }}
.blc-skyline .b4 {{ fill: rgba(255,255,255,.11); }}
.blc-skyline .bay, .blc-skyline .cornice, .blc-skyline .porch {{ fill: rgba(255,255,255,.12); }}
.blc-skyline .door {{ fill: rgba(11,37,69,.55); }}
.blc-skyline .stoop, .blc-skyline .ground {{ fill: rgba(255,255,255,.25); }}
.blc-skyline .win {{ fill: {WINDOW}; opacity: .25; animation: blc-glow 9s ease-in-out infinite; }}
.blc-skyline .w1 {{ animation-delay: -1.5s; }} .blc-skyline .w2 {{ animation-delay: -3s; }}
.blc-skyline .w3 {{ animation-delay: -4.5s; }} .blc-skyline .w4 {{ animation-delay: -6s; }}
.blc-skyline .w5 {{ animation-delay: -7.5s; animation-duration: 11s; }}
.blc-skyline .moon {{ fill: #FEF3C7; opacity: .85; filter: drop-shadow(0 0 6px rgba(254,243,199,.6)); }}
.blc-skyline .cloud {{ fill: rgba(255,255,255,.22); }}
.blc-skyline .c1 {{ animation: blc-drift 70s linear infinite; animation-delay: -10s; }}
.blc-skyline .c2 {{ animation: blc-drift 90s linear infinite; animation-delay: -55s; }}
.blc-skyline .c3 {{ animation: blc-drift 110s linear infinite; animation-delay: -30s; }}
.blc-skyline .tree {{ fill: rgba(255,255,255,.2); transform-origin: 588px 220px; transform-box: view-box;
                     animation: blc-sway 6s ease-in-out infinite; }}
.blc-hero.compact {{ align-items: center; }}
.blc-hero.compact .blc-hero-art {{ flex: 0 0 300px; min-width: 0; margin: -18px -26px -24px 0; height: 90px; }}
.blc-hero.compact .blc-skyline {{ height: 100%; }}
@keyframes blc-glow {{ 0%, 100% {{ opacity: .22; }} 40%, 60% {{ opacity: .95; }} }}
@keyframes blc-drift {{ from {{ transform: translateX(-80px); }} to {{ transform: translateX(700px); }} }}
@keyframes blc-sway {{ 0%, 100% {{ transform: rotate(-2deg); }} 50% {{ transform: rotate(2deg); }} }}

.blc-loader {{ display: flex; gap: 20px; align-items: center; background: #FFFFFF; border: 1px solid #EAECF0;
               border-radius: 14px; padding: 16px 22px; margin: 10px 0; color: #101828; }}
.blc-loader-t {{ font-weight: 600; font-size: 1.05rem; margin-bottom: 2px; }}
.blc-scan {{ width: 96px; height: 90px; flex: 0 0 96px; }}
.blc-scan .roof {{ fill: #1F4E79; }} .blc-scan .chim {{ fill: #1F4E79; }}
.blc-scan .walls {{ fill: #E8F0F9; stroke: #1F4E79; stroke-width: 3; }}
.blc-scan .pane {{ fill: {WINDOW}; animation: blc-glow 2.4s ease-in-out infinite; }}
.blc-scan .door {{ fill: #1F4E79; animation: none; }}
.blc-scan .beam {{ animation: blc-scanline 1.8s ease-in-out infinite; }}
@keyframes blc-scanline {{ from {{ transform: translateY(0); }} to {{ transform: translateY(180px); }} }}

@media (max-width: 800px) {{
  .blc-hero {{ flex-direction: column; align-items: stretch; }}
  .blc-hero-art {{ margin: 4px -12px -36px -12px; min-width: 0; }}
  .blc-hero.compact .blc-hero-art {{ display: none; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .blc-skyline *, .blc-scan * {{ animation: none !important; }}
  .blc-skyline .win {{ opacity: .7; }}
}}
"""
