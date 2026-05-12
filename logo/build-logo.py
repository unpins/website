#!/usr/bin/env python3
"""Build the unpins logo: render 'unpins' from a rounded mono font and
extend the 'u' glyph's right stem into an arrow that fuses with the letter.

Paths can be configured via env vars FONT_PATH and OUT_SVG; defaults point at
the Makefile-managed target/ tree.
"""
import os
from fontTools.ttLib import TTFont
from fontTools.varLib.mutator import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.recordingPen import RecordingPen

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WEBSITE_DIR = os.path.dirname(SCRIPT_DIR)
FONT_PATH = os.environ.get(
    "FONT_PATH",
    os.path.join(WEBSITE_DIR, "target/fonts/fonts/ttf/JetBrainsMono-Bold.ttf"),
)
OUT_SVG = os.environ.get(
    "OUT_SVG",
    os.path.join(WEBSITE_DIR, "unpins-logo.svg"),
)
OUT_FAVICON = os.environ.get(
    "OUT_FAVICON",
    os.path.join(WEBSITE_DIR, "favicon.svg"),
)
WEIGHT = 700          # Bold
WORD = "unpins"

# Visual tuning — expressed as multiples of the detected stem thickness so the
# proportions stay consistent regardless of the font's units-per-em.
SHAFT_DIAG_MULT = 3.0      # diagonal shaft length / stem thickness
ARM_LEN_MULT = 1.5         # head arm length / stem thickness
RISER_HEIGHT_MULT = 0.05   # tiny vertical riser before the bend (so the butt
                           # cap at the start is horizontal and aligns exactly
                           # with the stem top — width matches stem width).


def get_outline_points(glyph, glyph_set):
    """Return list of (x, y) points sampled from the glyph outline."""
    pen = RecordingPen()
    glyph.draw(pen)
    pts = []
    for op, args in pen.value:
        if op in ("moveTo", "lineTo"):
            pts.append(args[0])
        elif op == "qCurveTo":
            for p in args:
                if p is not None:
                    pts.append(p)
        elif op == "curveTo":
            for p in args:
                pts.append(p)
    return pts


def find_right_stem_top(glyph, glyph_set):
    """Find the (x, y) at the top of the right stem of a 'u'-shaped glyph.

    Heuristic: among the rightmost points (within ~5% of max x), pick the
    one with the highest y that is still below the glyph's max y plus a
    small tolerance. For a 'u' that's the top-right corner of the right stem.
    """
    pts = get_outline_points(glyph, glyph_set)
    if not pts:
        return None
    max_x = max(p[0] for p in pts)
    max_y = max(p[1] for p in pts)
    # Tolerance: points within 5% of max_x and 5% of max_y.
    x_tol = max_x * 0.05
    y_tol = max_y * 0.05
    candidates = [p for p in pts if p[0] >= max_x - x_tol and p[1] >= max_y - y_tol]
    if not candidates:
        return (max_x, max_y)
    # Among them, choose the leftmost (the inner corner of the right stem cap).
    candidates.sort(key=lambda p: (-p[1], p[0]))
    return candidates[0]


def inkscape_union(svg_path):
    """Convert arrow strokes to filled paths and union them with the u glyph.

    Operates on the IDs `u-glyph`, `arrow-1`, `arrow-2` — both the wordmark
    and the favicon emit those IDs so the same union pass works for both.
    """
    import subprocess
    actions = ";".join([
        "select-by-id:arrow-1,arrow-2",
        "object-stroke-to-path",
        "select-by-id:u-glyph,arrow-1,arrow-2",
        "path-union",
        "export-overwrite",
        "export-do",
    ])
    result = subprocess.run(
        [
            "inkscape", "--actions", actions,
            "--export-type=svg",
            "--export-plain-svg=false",
            f"--export-filename={svg_path}",
            svg_path,
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("Inkscape stderr:", result.stderr)


def detect_stem_thickness(glyph, glyph_set):
    """Estimate the right stem thickness by looking at points near the top.

    Walks the unique x-coordinates of top-region points from the right edge
    inward until it finds a gap large enough to clearly mark the inner edge
    of the right stem. We do NOT round here — round(525, -1) is 520 under
    banker's rounding, which silently shaves 5 units off the stem and leaves
    a gap at the arrow/stem junction.
    """
    pts = get_outline_points(glyph, glyph_set)
    if not pts:
        return None
    max_y = max(p[1] for p in pts)
    top_pts = [p for p in pts if p[1] >= max_y * 0.85]
    if not top_pts:
        return None
    xs = sorted({p[0] for p in top_pts}, reverse=True)
    if len(xs) < 2:
        return None
    outer = xs[0]
    # Find the first x clearly inside the right stem (gap > ~25% of outer-most).
    for x in xs[1:]:
        if outer - x >= outer * 0.05:
            return outer - x
    return None


def main():
    font = TTFont(FONT_PATH)
    if "fvar" in font:
        font = instantiateVariableFont(font, {"wght": WEIGHT})

    upm = font["head"].unitsPerEm
    ascender = font["hhea"].ascender
    descender = font["hhea"].descender
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"]

    # Extract each letter's path and advance.
    letters = []
    x_cursor = 0
    for ch in WORD:
        gid = cmap[ord(ch)]
        glyph = glyph_set[gid]
        pen = SVGPathPen(glyph_set)
        glyph.draw(pen)
        d = pen.getCommands()
        advance = hmtx[gid][0]
        letters.append({"char": ch, "x": x_cursor, "d": d, "gid": gid, "glyph": glyph})
        x_cursor += advance

    total_width = x_cursor
    glyph_height = ascender - descender

    # Locate the right-stem top of the 'u' for arrow anchor.
    u = letters[0]
    anchor = find_right_stem_top(u["glyph"], glyph_set)
    stem_thick = detect_stem_thickness(u["glyph"], glyph_set) or 250
    print(f"u anchor (font units, glyph-local): {anchor}", flush=True)
    print(f"stem thickness ~ {stem_thick:.0f}", flush=True)
    print(f"advance(u)={hmtx[u['gid']][0]}, upm={upm}, asc={ascender}, desc={descender}", flush=True)

    # Arrow as a stroked open path. Trick: start the path with a tiny vertical
    # riser segment so the stroke's butt cap at the start is HORIZONTAL and
    # exactly matches the u's stem top edge (perfect alignment on both sides).
    # Then the path bends to 45° for the diagonal shaft, then meets the L-head
    # corner. The L-head's two arms are drawn as a continuation (top arm) and
    # a second path (down arm).
    import math
    ax, ay = anchor                       # top-right of u's right stem
    thick = stem_thick
    stem_top_y = ay
    cx = ax - thick / 2                   # horizontal centre of the right stem

    riser = RISER_HEIGHT_MULT * thick     # tiny vertical riser (small)
    shaft_diag = SHAFT_DIAG_MULT * thick  # length of the 45° diagonal segment
    arm_len = ARM_LEN_MULT * thick        # length of each L-head arm

    start = (cx, stem_top_y)
    bend = (cx, stem_top_y + riser)
    diag = math.cos(math.radians(45))
    corner = (bend[0] + shaft_diag * diag, bend[1] + shaft_diag * diag)
    left_arm_end = (corner[0] - arm_len, corner[1])
    down_arm_end = (corner[0], corner[1] - arm_len)

    # Path 1: start → riser → 45° shaft → top (left) arm. One continuous path,
    # so the bend and the L-head corner are stroke-linejoins (no caps there).
    path1_d = (
        f"M {start[0]:.1f} {start[1]:.1f} "
        f"L {bend[0]:.1f} {bend[1]:.1f} "
        f"L {corner[0]:.1f} {corner[1]:.1f} "
        f"L {left_arm_end[0]:.1f} {left_arm_end[1]:.1f}"
    )
    # Path 2: down arm of the L-head.
    path2_d = (
        f"M {corner[0]:.1f} {corner[1]:.1f} "
        f"L {down_arm_end[0]:.1f} {down_arm_end[1]:.1f}"
    )

    # Gradient (matches the reference avatar SVG): blue → green, drawn along
    # the diagonal of the u-and-arrow shape so the colour follows the motion.
    # Coords are in the local (font Y-up) space of the scaled group.
    grad_x1 = 75
    grad_y1 = 0
    grad_x2 = corner[0]
    grad_y2 = corner[1]

    # Letter paths: each translated by its x_cursor. The 'u' glyph gets a
    # stable ID and the gradient fill (so after the Inkscape union the
    # combined path inherits it). The trailing 's' (last letter) gets the
    # green endpoint of the gradient.
    letter_paths = []
    last = len(letters) - 1
    for i, L in enumerate(letters):
        if i == 0:
            attrs = 'id="u-glyph" fill="url(#logo-grad)"'
        elif i == last:
            attrs = f'id="letter-{i}" fill="#0969da"'
        else:
            attrs = f'id="letter-{i}"'
        letter_paths.append(
            f'<path {attrs} d="{L["d"]}" transform="translate({L["x"]}, 0)" />'
        )

    # Compute SVG viewBox from the ACTUAL drawn content (not the font's
    # ascender/descender — those reserve space for glyphs we don't draw, which
    # leaves visible whitespace above/below the wordmark in the rendered SVG).
    word_min_y = float("inf")
    word_max_y = float("-inf")
    for L in letters:
        for _, py in get_outline_points(L["glyph"], glyph_set):
            if py < word_min_y:
                word_min_y = py
            if py > word_max_y:
                word_max_y = py
    arrow_top_y = corner[1] + thick / 2     # stroke extends thick/2 above the centre-line
    arrow_right_x = corner[0] + thick / 2
    content_top_y = max(word_max_y, arrow_top_y)
    content_bot_y = word_min_y
    pad_v = 30                              # small vertical padding (font units)
    pad_h = 80                              # horizontal padding
    vb_x = -pad_h
    vb_y = -(content_top_y + pad_v)
    vb_w = max(total_width, arrow_right_x) + 2 * pad_h
    vb_h = (content_top_y - content_bot_y) + 2 * pad_v

    # Output SVG. We flip Y with scale(1,-1) so font Y-up becomes SVG Y-down,
    # and translate so y=0 in font space sits at the baseline.
    # The arrow's strokes:
    #   - linecap="butt" at path starts/ends (so start cap is perpendicular
    #     to the first vertical segment → horizontal → matches stem top width)
    #   - linejoin="miter" for sharp arrow-tip aesthetic
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb_x:.0f} {vb_y:.0f} {vb_w:.0f} {vb_h:.0f}">
  <defs>
    <linearGradient id="logo-grad" gradientUnits="userSpaceOnUse" x1="{grad_x1}" y1="{grad_y1}" x2="{grad_x2:.0f}" y2="{grad_y2:.0f}">
      <stop offset="0" stop-color="#0969da" />
      <stop offset="1" stop-color="#3fb950" />
    </linearGradient>
  </defs>
  <g transform="scale(1, -1)" fill="#1f2328">
    {chr(10).join(letter_paths)}
    <path id="arrow-1" d="{path1_d}" fill="none" stroke="url(#logo-grad)" stroke-width="{thick:.0f}" stroke-linecap="round" stroke-linejoin="round" />
    <path id="arrow-2" d="{path2_d}" fill="none" stroke="url(#logo-grad)" stroke-width="{thick:.0f}" stroke-linecap="round" stroke-linejoin="round" />
  </g>
</svg>
'''
    svg_path = OUT_SVG
    os.makedirs(os.path.dirname(svg_path), exist_ok=True)
    with open(svg_path, "w") as f:
        f.write(svg)
    print(f"Wrote {svg_path} (pre-union)")

    # Use Inkscape to (a) convert the arrow strokes to filled paths and
    # (b) union the 'u' glyph with the two arrow paths into a single path.
    # This way the gradient applied later flows across one continuous shape.
    inkscape_union(svg_path)
    print("Unioned u glyph with arrow paths into a single path")

    # Re-inject the gradient fill on the unioned u-glyph path: Inkscape drops
    # the fill="url(#logo-grad)" attribute during stroke-to-path + union.
    import re
    with open(svg_path) as f:
        svg_out = f.read()
    svg_out = re.sub(
        r'(<path\s+)id="u-glyph"',
        r'\1id="u-glyph"\n       fill="url(#logo-grad)"',
        svg_out, count=1,
    )

    # Make the SVG theme-aware: replace the static letter fill on the parent
    # <g> with a class, and inject a <style> with a prefers-color-scheme dark
    # variant. Works when the SVG is loaded via <img> — media queries inside
    # the SVG still resolve against the system theme.
    style_block = (
        '    <style>\n'
        '      .letters { fill: #1f2328; }\n'
        '      @media (prefers-color-scheme: dark) {\n'
        '        .letters { fill: #c9d1d9; }\n'
        '      }\n'
        '    </style>\n'
    )
    svg_out = re.sub(r'(<defs[^>]*>)\n', r'\1\n' + style_block, svg_out, count=1)
    svg_out = re.sub(r'fill="#1f2328"', 'class="letters"', svg_out, count=1)
    with open(svg_path, "w") as f:
        f.write(svg_out)
    print("Re-applied gradient fill on u-glyph + injected theme-aware style")

    # === Favicon: just the 'u' + arrow on a tight square viewBox ===
    # Bounding box of the 'u' glyph alone.
    u_pts = get_outline_points(u["glyph"], glyph_set)
    u_min_x = min(p[0] for p in u_pts)
    u_max_x = max(p[0] for p in u_pts)
    u_min_y = min(p[1] for p in u_pts)
    u_max_y = max(p[1] for p in u_pts)
    # Arrow extends a half-stroke beyond its endpoints (round caps).
    arrow_min_x = left_arm_end[0] - thick / 2
    arrow_max_x = corner[0] + thick / 2
    arrow_min_y = down_arm_end[1] - thick / 2
    arrow_max_y = corner[1] + thick / 2
    fav_min_x = min(u_min_x, arrow_min_x)
    fav_max_x = max(u_max_x, arrow_max_x)
    fav_min_y = min(u_min_y, arrow_min_y)
    fav_max_y = max(u_max_y, arrow_max_y)
    side = max(fav_max_x - fav_min_x, fav_max_y - fav_min_y)
    fav_pad = side * 0.10
    side_p = side + 2 * fav_pad
    cx_box = (fav_min_x + fav_max_x) / 2
    cy_box = (fav_min_y + fav_max_y) / 2
    fav_vb_x = cx_box - side_p / 2
    fav_vb_y = -(cy_box + side_p / 2)  # Y flipped (font Y-up → SVG Y-down)

    fav_svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{fav_vb_x:.0f} {fav_vb_y:.0f} {side_p:.0f} {side_p:.0f}">
  <defs>
    <linearGradient id="logo-grad" gradientUnits="userSpaceOnUse" x1="{grad_x1}" y1="{grad_y1}" x2="{grad_x2:.0f}" y2="{grad_y2:.0f}">
      <stop offset="0" stop-color="#0969da" />
      <stop offset="1" stop-color="#3fb950" />
    </linearGradient>
  </defs>
  <g transform="scale(1, -1)">
    <path id="u-glyph" fill="url(#logo-grad)" d="{letters[0]["d"]}" />
    <path id="arrow-1" d="{path1_d}" fill="none" stroke="url(#logo-grad)" stroke-width="{thick:.0f}" stroke-linecap="round" stroke-linejoin="round" />
    <path id="arrow-2" d="{path2_d}" fill="none" stroke="url(#logo-grad)" stroke-width="{thick:.0f}" stroke-linecap="round" stroke-linejoin="round" />
  </g>
</svg>
'''
    with open(OUT_FAVICON, "w") as f:
        f.write(fav_svg)
    inkscape_union(OUT_FAVICON)
    with open(OUT_FAVICON) as f:
        fav_out = f.read()
    fav_out = re.sub(
        r'(<path\s+)id="u-glyph"',
        r'\1id="u-glyph"\n       fill="url(#logo-grad)"',
        fav_out, count=1,
    )
    with open(OUT_FAVICON, "w") as f:
        f.write(fav_out)
    print(f"Wrote {OUT_FAVICON}")


if __name__ == "__main__":
    main()
