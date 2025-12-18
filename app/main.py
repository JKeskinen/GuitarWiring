import os
import streamlit as st
import streamlit.components.v1 as components
import json
import re
try:
    # preferred when running from project root
    from app.wiring import (
        MANUFACTURER_COLORS,
        WIRING_PRESETS,
        simple_humbucker_svg,
        analyze_pickup,
        infer_start_finish_from_probes,
        compute_electrical_polarity_from_probe,
    )
except Exception:
    # fallback when Streamlit runs this file directly (app/ on sys.path)
    from wiring import (
        MANUFACTURER_COLORS,
        WIRING_PRESETS,
        simple_humbucker_svg,
        analyze_pickup,
        infer_start_finish_from_probes,
        compute_electrical_polarity_from_probe,
    )
    from ai_assistant import render_ai_sidebar, init_ai_session_state

# Ensure AI helper functions are importable regardless of import path used above
try:
    from app.ai_assistant import render_ai_sidebar, init_ai_session_state
except Exception:
    try:
        from ai_assistant import render_ai_sidebar, init_ai_session_state
    except Exception:
        # If import fails, define safe no-op placeholders to avoid NameError during runs
        def init_ai_session_state():
            return

        def render_ai_sidebar():
            return

# HTTP helper for local AI health check
try:
    import requests
except Exception:
    requests = None

# Global color map for small UI badges (used across steps)
GLOBAL_COLOR_HEX = {
    'Red': '#d62728',
    'White': '#ffffff',
    'Green': '#2ca02c',
    'Black': '#111111',
    'Yellow': '#ffbf00',
    'Blue': '#1f77b4',
    'Bare': '#888888'
}

# Alias used in several helpers (kept for compatibility with earlier code)
COLOR_HEX = GLOBAL_COLOR_HEX

def _render_color_badges(colors: list) -> str:
    """Return HTML for inline badges matching the given color names."""
    if not colors:
        return ''
    parts = []
    for c in colors:
        hexcol = GLOBAL_COLOR_HEX.get(c, '#cccccc')
        # Use dark text on very light fills (white/yellow), otherwise white text
        text_color = '#111111' if hexcol.lower() in ('#ffffff', '#ffbf00') else '#ffffff'
        # Add a subtle border for white so it is visible on light backgrounds
        border_css = 'border:1px solid #ddd;' if hexcol.lower() == '#ffffff' else ''
        # Show the color name in uppercase for better visual matching
        parts.append(
            f"<span style='display:inline-block;margin-right:8px;padding:6px 12px;border-radius:6px;background:{hexcol};color:{text_color};font-family:sans-serif;font-size:13px;font-weight:600;{border_css}'>" +
            f"{c.upper()}</span>"
        )
    return ''.join(parts)


def _collect_streamed_json_text(resp):
    """Collect streamed JSON objects from a requests Response and return concatenated 'response' fields.

    Handles newline-delimited JSON chunks and simple concatenated JSON objects. Returns empty
    string on failure.
    """
    parts = []
    try:
        # Prefer iter_lines for streamed responses
        for raw in resp.iter_lines(decode_unicode=True):
            if not raw:
                continue
            s = raw.strip()
            if not s:
                continue
            # Try to parse the entire line as JSON first
            try:
                obj = json.loads(s)
            except Exception:
                # Fallback: extract any JSON object substrings on the line
                matches = re.findall(r'\{.*?\}', s)
                obj = None
                for m in matches:
                    try:
                        o = json.loads(m)
                        if isinstance(o, dict) and 'response' in o:
                            parts.append(o.get('response') or '')
                    except Exception:
                        continue
                # continue to next line
                continue

            if isinstance(obj, dict):
                # collect 'response' if present
                if 'response' in obj and isinstance(obj.get('response'), str):
                    parts.append(obj.get('response'))
                elif 'text' in obj and isinstance(obj.get('text'), str):
                    parts.append(obj.get('text'))
                # stop when done==true
                if obj.get('done') is True:
                    break
            else:
                parts.append(str(obj))
        return ''.join(parts).strip()
    except Exception:
        return ''

st.set_page_config(page_title='Humbucker Solver', layout='wide')

if 'step' not in st.session_state:
    st.session_state['step'] = 1
# Ensure orientation keys persist and have sensible defaults so changing other widgets
# doesn't accidentally reset pickup orientation.
if 'neck_orientation' not in st.session_state:
    st.session_state['neck_orientation'] = 'Top = NORTH / Bottom = SOUTH'
if 'bridge_orientation' not in st.session_state:
    st.session_state['bridge_orientation'] = 'Top = NORTH / Bottom = SOUTH'
# Explicit boolean flags (more robust than parsing strings) to choose which image to show
if 'neck_is_north_up' not in st.session_state:
    st.session_state['neck_is_north_up'] = True
if 'bridge_is_north_up' not in st.session_state:
    st.session_state['bridge_is_north_up'] = True
if 'neck_img_choice' not in st.session_state:
    st.session_state['neck_img_choice'] = 'north'
if 'bridge_img_choice' not in st.session_state:
    st.session_state['bridge_img_choice'] = 'north'

# Handlers to update image-choice when toggles change (prevents accidental overrides elsewhere)
def _on_neck_toggle():
    st.session_state['neck_img_choice'] = 'north' if st.session_state.get('neck_is_north_up', True) else 'south'
    st.session_state['neck_orientation'] = 'Top = NORTH / Bottom = SOUTH' if st.session_state.get('neck_is_north_up', True) else 'Top = SOUTH / Bottom = NORTH'

def _on_bridge_toggle():
    st.session_state['bridge_img_choice'] = 'north' if st.session_state.get('bridge_is_north_up', True) else 'south'
    st.session_state['bridge_orientation'] = 'Top = NORTH / Bottom = SOUTH' if st.session_state.get('bridge_is_north_up', True) else 'Top = Screw (S) / Bottom = NORTH'

# We use native Streamlit expanders (collapsed by default) to edit color selections.
# This avoids fragile widget-key handling and ensures selectors are visible only
# when the user explicitly opens the expander.

# Per-selector expander state flags (used to open/close edit expanders programmatically)
for _flag in ('edit_neck_north_expanded', 'edit_neck_south_expanded', 'edit_bridge_north_expanded', 'edit_bridge_south_expanded'):
    if _flag not in st.session_state:
        st.session_state[_flag] = False

def _open_edit(flag_name: str):
    try:
        st.session_state[flag_name] = True
    except Exception:
        pass

def _on_multiselect_changed(which_key: str, flag_name: str):
    # Auto-collapse the corresponding expander when exactly 2 colors are selected.
    vals = st.session_state.get(which_key, []) or []
    if isinstance(vals, (list, tuple)) and len(vals) == 2:
        try:
            st.session_state[flag_name] = False
        except Exception:
            pass
    else:
        # Keep the expander open so the user can finish selection
        try:
            st.session_state[flag_name] = True
        except Exception:
            pass

# Expander state flags so we can programmatically close them when the user
# has completed a valid selection (exactly 2 colors). Keys are persisted so
# the UI behaves consistently across reruns/backups.
for _ek in ('exp_neck_north', 'exp_neck_south', 'exp_bridge_north', 'exp_bridge_south'):
    if _ek not in st.session_state:
        st.session_state[_ek] = False

# (Removed swap helper at user's request)

# Title and intro moved to Step 1 (Welcome) so other steps stay compact

# Background music - always embedded, controlled by user
st.markdown(
    """
    <style>
    #music-player {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 9999;
        background: rgba(30, 30, 30, 0.95);
        padding: 10px 15px;
        border-radius: 25px;
        box-shadow: 0 4px 12px rgba(0,255,255,0.3);
        border: 1px solid rgba(0,255,255,0.5);
    }
    #music-player audio {
        height: 30px;
    }
    #music-player:hover {
        box-shadow: 0 6px 16px rgba(0,255,255,0.5);
    }
    </style>
    <div id="music-player">
        <audio controls loop preload="auto" volume="0.15">
            <source src="https://assets.mixkit.co/music/preview/mixkit-tech-house-vibes-130.mp3" type="audio/mpeg">
            <source src="https://www.bensound.com/bensound-music/bensound-scifi.mp3" type="audio/mpeg">
            Your browser does not support audio.
        </audio>
    </div>
    """,
    unsafe_allow_html=True
)

# Make inline SVG labels/text visible on dark theme (white)
st.markdown(
    """
    <style>
    svg text { fill: white !important; }
    svg { color: white !important; }
    /* Prevent button labels from wrapping and give buttons a sensible min-width */
    .stButton>button {
        white-space: nowrap;
        min-width: 120px;
        padding: 6px 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# Persistent preview in the sidebar: pickup image + current top/bottom mapping + small SVG
def _map_top_bottom_from_choice(choice: str):
    if choice and isinstance(choice, str) and choice.startswith('Top = Slug'):
        return {'top': 'Slug (N)', 'bottom': 'Screw (S)'}
    return {'top': 'Screw (S)', 'bottom': 'Slug (N)'}

# determine image path (fall back to repo root image if available)
def _pickup_image_path():
    # look for humbucker images inside the app package (avoid repo-root screenshots)
    candidates = [
        os.path.join('app', 'static', 'humbuckerNORTH.svg'),
        os.path.join('app', 'humbuckerNORTH.svg'),
        os.path.join('humbuckerNORTH.svg'),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

img_path = _pickup_image_path()
with st.sidebar:
    st.header('Pickup Preview')
    # increase sidebar width so inline SVG previews have enough room
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {width: 460px;}
        @media (max-width: 991px) { [data-testid="stSidebar"] {width: 100% !important;} }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # show current mapping labels (use session state defaults if not set)
    neck_choice = st.session_state.get('neck_orientation', 'Top = Slug (N) / Bottom = Screw (S)')
    bridge_choice = st.session_state.get('bridge_orientation', 'Top = Slug (N) / Bottom = Screw (S)')
    n_pol = _map_top_bottom_from_choice(neck_choice)
    b_pol = _map_top_bottom_from_choice(bridge_choice)
    if img_path:
        # The user provides two images in the repo: humbuckerNORTH.* and humbuckerSOUTH.*
        # Show the correct image for each pickup depending on whether the pickup is North-up or South-up.
        def _find_candidate(base_name):
            exts = ['.svg', '.png', '.jpg', '.jpeg']
            places = [os.path.join('app', 'static'), os.path.join('app'), os.path.join('.')]
            for p in places:
                for e in exts:
                    cand = os.path.join(p, base_name + e)
                    if os.path.exists(cand):
                        return cand
            return None

        north_img = _find_candidate('humbuckerNORTH')
        south_img = _find_candidate('humbuckerSOUTH')

        # helper to render a single image path (svg inlined, raster via st.image)
        def _render_image(path, height=260, which='neck'):
            """Render image; if SVG, inline it and overlay coloured wire-end balls based on session state.

            `which` is 'neck' or 'bridge' used to pick session_state keys.
            """
            if not path:
                st.info('Image not found')
                return
            if path.lower().endswith('.svg'):
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        svg_html = f.read()
                    # Attempt to tint the pickup SVG to match the user's selected top-coil colour.
                    try:
                        # Determine a primary colour from session state for this pickup
                        if which == 'neck':
                            primary_name = (st.session_state.get('neck_north_colors', []) or [None])[0]
                        else:
                            primary_name = (st.session_state.get('bridge_north_colors', []) or [None])[0]
                        primary_hex = COLOR_HEX.get(primary_name)
                        if primary_hex:
                            # Replace the default red used in the bundled SVG with the chosen colour.
                            svg_html = svg_html.replace('#d62728', primary_hex)
                    except Exception:
                        pass

                    # Compute inferred mapping for this pickup to decide ball colours
                    def _none_if_dash(val):
                        return None if (val is None or (isinstance(val, str) and val.strip() == '--')) else val

                    if which == 'neck':
                        upper_map = infer_start_finish_from_probes(
                            st.session_state.get('neck_north_colors', []),
                            _none_if_dash(st.session_state.get('n_up_probe_red_wire')),
                            _none_if_dash(st.session_state.get('n_up_probe_black_wire')),
                            st.session_state.get('n_up_probe'),
                            st.session_state.get('n_up_swap', False)
                        )
                        lower_map = infer_start_finish_from_probes(
                            st.session_state.get('neck_south_colors', []),
                            _none_if_dash(st.session_state.get('n_lo_probe_red_wire')),
                            _none_if_dash(st.session_state.get('n_lo_probe_black_wire')),
                            st.session_state.get('n_lo_probe'),
                            st.session_state.get('n_lo_swap', False)
                        )
                    else:
                        upper_map = infer_start_finish_from_probes(
                            st.session_state.get('bridge_north_colors', []),
                            _none_if_dash(st.session_state.get('b_up_probe_red_wire')),
                            _none_if_dash(st.session_state.get('b_up_probe_black_wire')),
                            st.session_state.get('b_up_probe'),
                            st.session_state.get('b_up_swap', False)
                        )
                        lower_map = infer_start_finish_from_probes(
                            st.session_state.get('bridge_south_colors', []),
                            _none_if_dash(st.session_state.get('b_lo_probe_red_wire')),
                            _none_if_dash(st.session_state.get('b_lo_probe_black_wire')),
                            st.session_state.get('b_lo_probe'),
                            st.session_state.get('b_lo_swap', False)
                        )

                    # map colour names to hex
                    COLOR_HEX = {
                        'Red': '#d62728',
                        'White': '#ffffff',
                        'Green': '#2ca02c',
                        'Black': '#111111',
                        'Yellow': '#ffbf00',
                        'Blue': '#1f77b4',
                        'Bare': '#888888'
                    }

                    # Build overlay SVG that will sit on the right side of the image
                    # Use percentage positioning so it scales with the image container
                    # Determine coil polarity labels dynamically from session state
                    if which == 'neck':
                        top_is_north = st.session_state.get('neck_is_north_up', True)
                    else:
                        top_is_north = st.session_state.get('bridge_is_north_up', True)
                    # Use magnetic polarity names 'North' / 'South' for overlay labels
                    coilA_pol = 'North' if top_is_north else 'South'
                    coilB_pol = 'South' if top_is_north else 'North'

                    def colour_svg_overlay(upper, lower):
                        # Define CoilA = upper, CoilB = lower
                        # Desired visual order (top->bottom): CoilA START, CoilA END, CoilB END, CoilB START
                        vals = [upper.get('start'), upper.get('finish'), lower.get('finish'), lower.get('start')]
                        # default to grey if unknown
                        fills = [COLOR_HEX.get(v, '#cccccc') if v else '#cccccc' for v in vals]
                        texts = [v[0].upper() if v else '?' for v in vals]
                        # overlay SVG sized to 260x200 box
                        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 200" preserveAspectRatio="xMinYMin meet" width="220" height="200">']
                        # Group A positions (CoilA Start, CoilA End)
                        # We'll draw the line from a left anchor to a right anchor where the coloured ball sits.
                        r = 12
                        # move anchors left so balls sit closer to the pickup wires
                        left_x = 18
                        # default right-side anchor for the ball (used to compute full line end)
                        default_circle_x = 140
                        # visible fraction of the full connector line (0..1)
                        line_fraction = 0.6
                        # vertical offset for polarity text (Start/End) relative to the ball radius
                        pol_text_offset = 8
                        pol_font_size = 10
                        # raise the circles a bit so they sit on top of the wires visually
                        y_a1 = 18
                        y_a2 = 58
                        # Group B positions (increased space between CoilA and CoilB)
                        y_b1 = 98
                        y_b2 = 138
                        y_positions = [y_a1, y_a2, y_b1, y_b2]
                        labels = [
                            f'{coilA_pol} START +',
                            f'{coilA_pol} END -',
                            f'{coilB_pol} END -',
                            f'{coilB_pol} START +',
                        ]
                        for i, (f, t, y) in enumerate(zip(fills, texts, y_positions)):
                            # colour the connector line to match the dot; use a neutral fallback for white
                            try:
                                fl = f.lower()
                                # Use a light connector for white/yellow and for very dark fills (black)
                                if fl in ('#ffffff', '#ffbf00'):
                                    line_color = '#cccccc'
                                elif fl in ('#111111', '#000000'):
                                    line_color = '#cccccc'
                                else:
                                    line_color = f
                            except Exception:
                                line_color = '#cccccc'
                            # draw the connector line from left anchor to a shortened visible end
                            # compute the full end (just left of the ball) and then shorten by `line_fraction`
                            line_end_full = default_circle_x - r - 6
                            line_end = left_x + int((line_end_full - left_x) * line_fraction)
                            # short stub from left edge to the left anchor so it visually connects to the pickup
                            parts.append(f'<line x1="0" y1="{y}" x2="{left_x}" y2="{y}" stroke="{line_color}" stroke-width="5" stroke-opacity="0.75" />')
                            parts.append(f'<line x1="{left_x}" y1="{y}" x2="{line_end}" y2="{y}" stroke="{line_color}" stroke-width="5" stroke-opacity="0.75" />')
                            # place the coloured ball just to the right of the visible line end so it moves with it
                            circle_x = line_end + r + 6
                            # draw a small polarity label above the line (Start / End)
                            polarity_word = 'Start' if 'start' in labels[i].lower() else 'End'
                            # choose polarity text color for contrast against background
                            pol_text_fill = '#ffffff' if f.lower() not in ('#ffffff', '#ffbf00') else "#FFFFFF"
                            # small polarity labels removed (keep descriptive labels on the right)
                            # draw the coloured ball at the right end of the visible connector (it follows the line)
                            parts.append(f'<circle cx="{circle_x}" cy="{y}" r="{r}" fill="{f}" stroke="#222" stroke-width="1" />')
                            # choose text color for contrast inside the ball (dark on white/yellow)
                            text_fill = '#111111' if f.lower() in ('#ffffff', '#ffbf00') else '#ffffff'
                            parts.append(f'<text x="{circle_x}" y="{y}" text-anchor="middle" dominant-baseline="middle" font-family="sans-serif" font-size="12" fill="{text_fill}">{t}</text>')
                            # right-side label
                            parts.append(f'<text x="{circle_x + r + 10}" y="{y+4}" font-family="sans-serif" font-size="12" fill="#ffffff">{labels[i]}</text>')
                        # Draw a visible connector between the two middle circles (series link)
                        try:
                            # compute the shared circle x coordinate (same for all entries)
                            line_end_full = default_circle_x - r - 6
                            line_end = left_x + int((line_end_full - left_x) * line_fraction)
                            connector_x = line_end + r + 6
                            y1 = y_positions[1]
                            y2 = y_positions[2]
                            # draw a slightly thinner connector but shorten it a bit so it doesn't overlap nearby labels
                            gap = max(6, int((y2 - y1) * 0.18))
                            y1s = y1 + gap
                            y2s = y2 - gap
                            parts.append(f'<line x1="{connector_x}" y1="{y1s}" x2="{connector_x}" y2="{y2s}" stroke="#ffffff" stroke-width="2" stroke-linecap="round" />')
                            mid_y = int((y1s + y2s) / 2)
                            # place the Series label to the left of the connector so it doesn't overlap right-side text
                            series_x = max(left_x + 6, connector_x - (r + 64))
                            parts.append(f'<text x="{series_x}" y="{mid_y + 4}" font-family="sans-serif" font-size="12" fill="#ffffff">Series</text>')
                        except Exception:
                            pass
                        parts.append('</svg>')
                        return '\n'.join(parts)

                    overlay_html = colour_svg_overlay(upper_map, lower_map)

                    # Compose container HTML: inline original SVG then absolutely positioned overlay
                    html = f"""
                    <div style="position:relative; width:100%; max-width:560px;">
                      <div style="position:relative; z-index:1;">{svg_html}</div>
                      <div style="position:absolute; right:8px; top:8px; z-index:2; pointer-events:none;">{overlay_html}</div>
                    </div>
                    """
                    components.html(html, height=height)
                except Exception:
                    st.image(path, use_column_width=True)
            else:
                st.image(path, use_column_width=True)

        # Decide which image to use for each pickup based on explicit image-choice keys
        neck_choice = st.session_state.get('neck_img_choice', 'north')
        bridge_choice = st.session_state.get('bridge_img_choice', 'north')
        neck_img_path = north_img if neck_choice == 'north' else south_img
        bridge_img_path = north_img if bridge_choice == 'north' else south_img

        st.markdown('**NECK**')
        _render_image(neck_img_path, height=240, which='neck')
        st.markdown('**BRIDGE**')
        _render_image(bridge_img_path, height=240, which='bridge')
    else:
        st.info('Pickup image not found in repo; SVG preview shown instead.')

    # (Intentionally left minimal) — pickup images shown above.

# Sidebar AI helper — small keyword-driven knowledge base for soldering and hum-cancelling
st.sidebar.header('AI helper (soldering & hum-cancelling)')

# Define FAQ knowledge base and helper function before using them
FAQ_KB = {
    'soldering_tools': (
        '**Soldering — Tools & safety**\n'
        '- Use a temperature-controlled iron (350–380°C / 660–715°F for electronics).\n'
        '- Use rosin-core 60/40 or 63/37 solder for electronics; 0.7–1.0 mm diameter is convenient.\n'
        '- Work in a well-ventilated area and wear eye protection.\n'
        '- Keep tip clean with a damp sponge and tin the tip before and after use.\n'
        '- Pre-tin wires and pads: heat the part, then apply solder to make a small shiny cone — then join.\n'
    ),
    'soldering_steps': (
        '**Soldering — Basic steps**\n'
        '1) Strip ~3–6 mm of insulation.\n'
        '2) Twist stranded wire or tin it lightly.\n'
        '3) Heat the joint (pad or lug) with the iron, apply solder to the joint (not directly to the iron).\n'
        '4) Withdraw solder, then iron, and let the joint cool without moving.\n'
        '5) Inspect for a smooth, shiny, concave joint ("volcano").\n'
    ),
    'hum_cancelling_overview': (
        '**Hum-cancelling — Overview**\n'
        '- Humbuckers cancel mains hum by combining two coils with opposite magnetic polarity and opposite electrical phase.\n'
        '- To cancel hum, coils must be reverse-wound *and* reverse-polarity (RWRP).\n'
        '- If one coil is reversed only electrically (phase) but not magnetically, cancellation fails.\n'
    ),
    'hum_cancelling_when_wiring': (
        '**Wiring tips to preserve hum-cancelling**\n'
        '- Wire the two coils in series or parallel as intended by the pickup design. Modern humbuckers use series for full output.\n'
        '- When splitting coils (coil-split), you lose one coil and thus the hum cancellation — use noise-free split circuits or stacking designs if you need single-coil tone without hum.\n'
        '- For phase switching (series ↔ parallel ↔ split) use proper switching that preserves magnetic/ electrical relationships.\n'
    ),
    'grounding': (
        '**Grounding & shielding**\n'
        '- Ground (pot backs, chassis) must be connected to pickup ground (bare or black depending on manufacturer).\n'
        '- Solder the bare (shield) to ground; do not rely on friction contacts.\n'
        '- Use shielding (copper tape, conductive paint) in control cavities and connect it to ground to reduce hum.\n'
    ),
    'phase_checks': (
        '**Phase checking (practical)**\n'
        '- Use a multimeter: measure DC resistance of coils to identify which wires are which.\n'
        '- Use a small metal probe to touch pole pieces while measuring resistance: if resistance goes up when touched, that coil end is the positive lead for that polarity test.\n'
        '- Swap coil connections if you detect reversed electrical polarity so North START == HOT mapping matches expected wiring.\n'
    ),
    'coil_split_hum': (
        '**Coil-splitting & hum**\n'
        '- Coil split disables one coil; hum cancellation is lost and single-coil hum will reappear.\n'
        '- To reduce hum while split: use resistor or phase-cancellation circuits, or use stacked noiseless pickups that emulate single-coil tone without hum.\n'
    ),
}

def _ai_helper_answer(q: str) -> str:
    ql = (q or '').lower()
    if not ql.strip():
        return 'Ask a specific question about soldering, grounding, or hum-cancelling (e.g. "How do I solder a pot lug?", "Why does my coil hum after splitting?").'
    # keyword matching
    if any(k in ql for k in ('solder', 'soldering', 'iron', 'tin', 'solder tip', 'desolder')):
        return FAQ_KB['soldering_tools'] + '\n\n' + FAQ_KB['soldering_steps']
    if any(k in ql for k in ('hum', 'hum cancelling', 'hum-cancelling', 'noise cancelling', 'hum cancel')):
        return FAQ_KB['hum_cancelling_overview'] + '\n\n' + FAQ_KB['hum_cancelling_when_wiring']
    if any(k in ql for k in ('ground', 'shield', 'shielding', 'bare', 'grounding')):
        return FAQ_KB['grounding']
    if any(k in ql for k in ('phase', 'phase check', 'polarity', 'probe', 'resistance increase', 'reverse')):
        return FAQ_KB['phase_checks']
    if any(k in ql for k in ('split', 'coil split', 'coil-split', 'splitting')):
        return FAQ_KB['coil_split_hum']
    # fallback: give general guidance + resources
    return (
        "I don't have a perfect match for that question. Here are general tips:\n\n"
        "- Be specific: mention if it's about a pot lug, jack, soldering stranded wire, coil-splitting wiring, or shielding.\n"
        "- For step-by-step soldering: use a temperature-controlled iron, clean/tin the tip, pre-tin wires, heat the joint, apply solder to the joint, and let cool.\n\n"
        "Useful references: StewMac (stewmac.com) and Seymour Duncan (seymourduncan.com) have practical wiring and soldering guides."
    )

# Initialize AI session state and render interactive AI sidebar
init_ai_session_state()
render_ai_sidebar()

# Compact UI toggle: reduces padding, font-size and image heights to show more content
if 'compact_ui' not in st.session_state:
    st.session_state['compact_ui'] = False

with st.sidebar:
    # Create the checkbox widget with a key; do not assign its return into session_state
    st.checkbox('Compact UI (less spacing)', value=st.session_state.get('compact_ui', False), key='compact_ui')

def _apply_compact_css():
    css = """
    <style>
    /* Ultra-tight global spacing for compact view */
    .block-container { padding: 4px 6px !important; }
    .stApp { font-size: 11px !important; line-height:1.05 !important; }
    h1 { font-size: 18px !important; margin:4px 0 !important; }
    h2 { font-size: 14px !important; margin:3px 0 !important; }
    h3, h4 { font-size: 12px !important; margin:2px 0 !important; }
    .stMarkdown, .css-1d391kg { margin: 2px 0 !important; }
    .stButton>button { padding: 3px 6px !important; min-width: 70px !important; font-size:11px !important; }
    .stTextInput>div>div>input, .stNumberInput>div>div>input, textarea { padding:3px 4px !important; font-size:11px !important }
    .stRadio, .stCheckbox { margin: 1px 0 !important; }
    img, svg { max-height: 120px !important; height: auto !important; }
    .stSidebar .block-container { padding: 4px 6px !important; }
    /* Reduce column gaps */
    .stColumns [class*='stColumn'] { padding: 2px !important; }
    /* Tighter table and json displays */
    .stDataFrame table { font-size:11px !important; }
    .stJson { font-size:11px !important; }
    /* Try to reduce sidebar width slightly */
    [data-testid='stSidebar'] { max-width: 300px !important; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

if st.session_state.get('compact_ui'):
    _apply_compact_css()


# Top navigation for steps (Previous / Next)
MAX_STEP = 6
def _safe_rerun():
    """Call Streamlit rerun if available; otherwise no-op."""
    try:
        # some Streamlit versions expose experimental_rerun
        rerun = getattr(st, 'experimental_rerun', None)
        if callable(rerun):
            rerun()
    except Exception:
        # ignore if not supported in this Streamlit build
        pass

    """Try to call a local Ollama-like server and return {'ok':bool,'text':str,'error':str}.

    The function tries multiple common endpoints (/api/generate, /api/chat, /api/completions)
    and returns the first successful textual result. It sends the raw `prompt` as-is so
    there's no added pre-coding of the user's question.
    """
    base = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/')
    # First, query /v1/models to discover available model ids and prefer an exact match
    try:
        models_url = base + '/v1/models'
        if requests is not None:
            mresp = requests.get(models_url, timeout=2.0)
            if mresp.status_code == 200:
                try:
                    mj = mresp.json()
                    if isinstance(mj, dict) and 'data' in mj and isinstance(mj['data'], list) and len(mj['data']) > 0:
                        available = [d.get('id') for d in mj['data'] if isinstance(d, dict) and 'id' in d]
                        # prefer explicit mistral id if present
                        if model and model in available:
                            model = model
                        elif 'mistral:7b' in available:
                            model = 'mistral:7b'
                        elif len(available) > 0:
                            model = available[0]
                except Exception:
                    pass
    except Exception:
        pass

    # Try a variety of common endpoint paths and payload shapes (OpenAI-style first)
    endpoints = [
        # OpenAI-compatible chat completions
        ('/v1/chat/completions', lambda p: {'model': model, 'messages': [{'role': 'user', 'content': p}]}),
        # OpenAI-compatible completions
        ('/v1/completions', lambda p: {'model': model, 'prompt': p, 'max_tokens': 512}),
        # Older Ollama API shapes
        ('/api/generate', lambda p: {'model': model, 'prompt': p, 'max_tokens': 512}),
        ('/api/completions', lambda p: {'model': model, 'prompt': p, 'max_tokens': 512}),
        ('/api/chat', lambda p: {'model': model, 'messages': [{'role': 'user', 'content': p}]}),
        # fallback variations
        ('/v1/generate', lambda p: {'model': model, 'prompt': p}),
        ('/v1/chat', lambda p: {'model': model, 'messages': [{'role': 'user', 'content': p}]}),
    ]
    if requests is None:
        return {'ok': False, 'text': '', 'error': 'requests library not available'}

    headers = {'Content-Type': 'application/json'}
    attempts = []
    for path, payload_fn in endpoints:
        url = base + path
        try:
            payload = payload_fn(prompt)
            r = requests.post(url, json=payload, timeout=timeout)
        except requests.exceptions.RequestException as e:
            attempts.append({'url': url, 'status': 'request-failed', 'error': str(e)})
            # try next endpoint
            continue

        # Record response for diagnostics
        resp_text = ''
        try:
            resp_text = r.text or ''
        except Exception:
            resp_text = ''

        if 200 <= r.status_code < 300:
            # First attempt: try to decode as standard JSON (most OpenAI-compatible responses)
            j = None
            try:
                j = r.json()
            except Exception:
                j = None

            # If normal JSON parsed, extract common fields
            if isinstance(j, dict):
                if 'completion' in j and isinstance(j['completion'], str):
                    return {'ok': True, 'text': j['completion'], 'error': ''}
                if 'result' in j and isinstance(j['result'], str):
                    return {'ok': True, 'text': j['result'], 'error': ''}
                if 'output' in j and isinstance(j['output'], str):
                    return {'ok': True, 'text': j['output'], 'error': ''}
                if 'choices' in j and isinstance(j['choices'], list) and len(j['choices']) > 0:
                    first = j['choices'][0]
                    if isinstance(first, dict):
                        if 'text' in first and isinstance(first['text'], str):
                            return {'ok': True, 'text': first['text'], 'error': ''}
                        if 'message' in first and isinstance(first['message'], dict) and 'content' in first['message']:
                            return {'ok': True, 'text': first['message']['content'], 'error': ''}
                for k in ('results', 'generations'):
                    if k in j and isinstance(j[k], list) and len(j[k]) > 0:
                        first = j[k][0]
                        if isinstance(first, dict):
                            for kk in ('text', 'output', 'content'):
                                if kk in first and isinstance(first[kk], str):
                                    return {'ok': True, 'text': first[kk], 'error': ''}

            # If we failed to parse standard JSON, attempt to extract streamed JSON objects from the full text body
            try:
                collected = ''
                # find all JSON object substrings and parse them individually
                matches = re.findall(r'\{.*?\}', resp_text, flags=re.S)
                for m in matches:
                    try:
                        o = json.loads(m)
                        if isinstance(o, dict):
                            if 'response' in o and isinstance(o.get('response'), str):
                                collected += o.get('response')
                            elif 'text' in o and isinstance(o.get('text'), str):
                                collected += o.get('text')
                    except Exception:
                        continue
                # If regex-based collection returned something, return it
                if collected.strip():
                    return {'ok': True, 'text': collected.strip(), 'error': ''}
            except Exception:
                pass

            # fallback to raw text body if nothing else worked
            if resp_text.strip():
                return {'ok': True, 'text': resp_text, 'error': ''}

            attempts.append({'url': url, 'status': r.status_code, 'body': resp_text})
            # continue to next endpoint
            continue
        else:
            # Non-2xx — include body for diagnostics
            attempts.append({'url': url, 'status': r.status_code, 'body': resp_text})
            # try next endpoint
            continue

    # If we reach here, none of the endpoints returned usable text. Try using app.llm_client.SimpleLLM if available.
    fallback_msgs = []
    try:
        from app.llm_client import SimpleLLM
        try:
            llm = SimpleLLM(ollama_url=base, model=model)
            res = llm.generate(prompt, max_tokens=512)
            if res and isinstance(res, str) and res.strip():
                return {'ok': True, 'text': res, 'error': ''}
            fallback_msgs.append('SimpleLLM returned empty response')
        except Exception as e:
            fallback_msgs.append(f'SimpleLLM exception: {e}')
    except Exception as e:
        fallback_msgs.append(f'No SimpleLLM available: {e}')

    # Build a helpful error message including collected diagnostics
    diag_lines = [f"Attempt to call local AI failed. Base URL: {base}"]


# Top navigation for steps (Previous / Next)
MAX_STEP = 6
def _safe_rerun():
    """Call Streamlit rerun if available; otherwise no-op."""
    try:
        # some Streamlit versions expose experimental_rerun
        rerun = getattr(st, 'experimental_rerun', None)
        if callable(rerun):
            rerun()
    except Exception:
        # ignore if not supported in this Streamlit build
        pass

def _on_prev():
    step = st.session_state.get('step', 1)
    if step > 1:
        _save_state()
        st.session_state['step'] = step - 1

def _on_next():
    step = st.session_state.get('step', 1)
    if step < MAX_STEP:
        _save_state()
        st.session_state['step'] = step + 1

# Simple JSON backup so progress persists across navigation/reloads
BACKUP_PATH = os.path.join('app', 'session_backup.json')
def _save_state():
    try:
        data = {k: v for k, v in st.session_state.items()}
        # Convert non-serializable values using str()
        for k in list(data.keys()):
            try:
                json.dumps(data[k])
            except Exception:
                data[k] = str(data[k])
        os.makedirs(os.path.dirname(BACKUP_PATH), exist_ok=True)
        with open(BACKUP_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def _load_state():
    try:
        if os.path.exists(BACKUP_PATH):
            with open(BACKUP_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Only set keys that are not already present to avoid overwriting live edits
            for k, v in data.items():
                if k not in st.session_state:
                    st.session_state[k] = v
    except Exception:
        pass

# Load any existing saved progress
_load_state()

# Remove any lingering widget keys that were saved in session backup which would
# conflict with newly-created widget keys (Streamlit forbids pre-setting widget
# keys in session_state). This prevents StreamlitValueAssignmentNotAllowedError
for _k in (
    'open_neck_north', 'open_neck_south', 'open_bridge_north', 'open_bridge_south',
    'edit_neck_north', 'edit_neck_south', 'edit_bridge_north', 'edit_bridge_south',
    'swap_neck_north', 'swap_neck_south', 'swap_bridge_north', 'swap_bridge_south'
):
    if _k in st.session_state:
        try:
            del st.session_state[_k]
        except Exception:
            pass

# Helpers to avoid Streamlit errors when default values are not present in options
def _safe_default_list(options, default):
    """Return only those defaults that exist in options (Streamlit requires this)."""
    if not default:
        return []
    return [d for d in default if d in options]


def _safe_index(options, value):
    """Return index of value in options or 0 when missing/invalid."""
    if value is None or value not in options:
        return 0
    return options.index(value)

# Helper functions for Step 6 analysis
def _compute_wiring_order(upper_map: dict, lower_map: dict, wiring_type: str, bare_present: bool = False, upper_phase: str = 'Normal', lower_phase: str = 'Normal') -> dict:
    """Compute wiring order for given wiring_type.

    upper_map / lower_map are expected to have keys 'start' and 'finish' (wire color names).
    wiring_type: 'series' | 'parallel' | 'slug_only' | 'screw_only'
    upper_phase: 'Normal' | 'Reverse' - phase of upper coil
    lower_phase: 'Normal' | 'Reverse' - phase of lower coil

    Returns a dict with keys: 'output' (list), 'series' (list, only for series), 'ground' (list), 'notes' (str|None).
    """
    u_start = upper_map.get('start')
    u_finish = upper_map.get('finish')
    l_start = lower_map.get('start')
    l_finish = lower_map.get('finish')

    order = {'output': [], 'series': [], 'ground': [], 'notes': None}

    if wiring_type == 'series':
        # SERIES wiring depends on phase:
        # RWRP (different phases): Coil1 start → HOT, Coil1 end + Coil2 end → LINK, Coil2 start → GROUND
        # Same phase (both Normal or both Reverse): Coil1 start → HOT, Coil1 end + Coil2 start → LINK, Coil2 end → GROUND
        if upper_phase != lower_phase:
            # Different phase (RWRP): connect ends together
            if u_start:
                order['output'] = [u_start]
            order['series'] = [w for w in (u_finish, l_finish) if w]
            order['ground'] = [w for w in ([l_start] + (['Bare'] if bare_present else [])) if w]
        else:
            # Same phase: connect end to start
            if u_start:
                order['output'] = [u_start]
            order['series'] = [w for w in (u_finish, l_start) if w]
            order['ground'] = [w for w in ([l_finish] + (['Bare'] if bare_present else [])) if w]

    elif wiring_type == 'parallel':
        # PARALLEL: Coil1 start + Coil2 start → HOT, Coil1 end + Coil2 end → GROUND
        order['output'] = [w for w in (u_start, l_start) if w]
        order['ground'] = [w for w in (u_finish, l_finish) if w]
        if bare_present:
            order['ground'].append('Bare')

    elif wiring_type == 'slug_only':
        # SLUG ONLY: North Start → HOT, North Finish + South Start + South Finish → GROUND
        if u_start:
            order['output'] = [u_start]
        order['ground'] = [w for w in (u_finish, l_start, l_finish) if w]
        if bare_present:
            order['ground'].append('Bare')

    elif wiring_type == 'screw_only':
        # SCREW ONLY: Upper coil only - Upper Start → HOT, Upper Finish + Lower Start + Lower Finish → GROUND
        if u_start:
            order['output'] = [u_start]
        order['ground'] = [w for w in (u_finish, l_start, l_finish) if w]
        if bare_present:
            order['ground'].append('Bare')

    else:
        order['notes'] = 'Unknown wiring variant requested.'

    return order

def _calculate_total_resistance(north_res_kohm, south_res_kohm, wiring_type: str) -> float:
    """Calculate total resistance based on wiring configuration.
    
    Args:
        north_res_kohm: Resistance of north/upper coil in kΩ
        south_res_kohm: Resistance of south/lower coil in kΩ
        wiring_type: 'series' | 'parallel' | 'slug_only' | 'screw_only'
    
    Returns:
        Total resistance in kΩ, or None if data is incomplete
    """
    if north_res_kohm is None or south_res_kohm is None:
        return None
    
    north = float(north_res_kohm) if north_res_kohm else None
    south = float(south_res_kohm) if south_res_kohm else None
    
    if north is None or south is None:
        return None
    
    if wiring_type == 'series':
        # Series: resistances add
        return north + south
    elif wiring_type == 'parallel':
        # Parallel: 1/R_total = 1/R1 + 1/R2
        if north == 0 or south == 0:
            return None
        return (north * south) / (north + south)
    elif wiring_type == 'slug_only':
        # Only north coil is used
        return north
    elif wiring_type == 'screw_only':
        # Only south coil is used
        return south
    else:
        return None

def _find_candidate(base_name):
    exts = ['.svg', '.png', '.jpg', '.jpeg']
    places = [os.path.join('app', 'static'), os.path.join('app'), os.path.join('.')]
    for p in places:
        for e in exts:
            cand = os.path.join(p, base_name + e)
            if os.path.exists(cand):
                return cand
    return None

def render_pickup_preview(which, height=120):
    """Render the original pickup SVG with the same coloured-ball overlay used in the sidebar.

    `which` is 'neck' or 'bridge'.
    """
    north_img = _find_candidate('humbuckerNORTH')
    south_img = _find_candidate('humbuckerSOUTH')
    img_path = north_img if (which == 'neck' and st.session_state.get('neck_img_choice', 'north') == 'north') or (which == 'bridge' and st.session_state.get('bridge_img_choice', 'north') == 'north') else south_img
    if not img_path:
        st.info('Pickup image not found')
        return
    if img_path.lower().endswith('.svg'):
        try:
            with open(img_path, 'r', encoding='utf-8') as f:
                svg_html = f.read()
            # Tint the pickup SVG background to match the selected top-coil color (if available)
            try:
                if which == 'neck':
                    primary_name = (st.session_state.get('neck_north_colors', []) or [None])[0]
                else:
                    primary_name = (st.session_state.get('bridge_north_colors', []) or [None])[0]
                primary_hex = COLOR_HEX.get(primary_name)
                if primary_hex:
                    svg_html = svg_html.replace('#d62728', primary_hex)
            except Exception:
                pass

            def _none_if_dash(val):
                return None if (val is None or (isinstance(val, str) and val.strip() == '--')) else val

            if which == 'neck':
                upper_map = infer_start_finish_from_probes(
                    st.session_state.get('neck_north_colors', []),
                    _none_if_dash(st.session_state.get('n_up_probe_red_wire')),
                    _none_if_dash(st.session_state.get('n_up_probe_black_wire')),
                    st.session_state.get('n_up_probe'),
                    st.session_state.get('n_up_swap', False)
                )
                lower_map = infer_start_finish_from_probes(
                    st.session_state.get('neck_south_colors', []),
                    _none_if_dash(st.session_state.get('n_lo_probe_red_wire')),
                    _none_if_dash(st.session_state.get('n_lo_probe_black_wire')),
                    st.session_state.get('n_lo_probe'),
                    st.session_state.get('n_lo_swap', False)
                )
            else:
                upper_map = infer_start_finish_from_probes(
                    st.session_state.get('bridge_north_colors', []),
                    _none_if_dash(st.session_state.get('b_up_probe_red_wire')),
                    _none_if_dash(st.session_state.get('b_up_probe_black_wire')),
                    st.session_state.get('b_up_probe'),
                    st.session_state.get('b_up_swap', False)
                )
                lower_map = infer_start_finish_from_probes(
                    st.session_state.get('bridge_south_colors', []),
                    _none_if_dash(st.session_state.get('b_lo_probe_red_wire')),
                    _none_if_dash(st.session_state.get('b_lo_probe_black_wire')),
                    st.session_state.get('b_lo_probe'),
                    st.session_state.get('b_lo_swap', False)
                )

            COLOR_HEX = {
                'Red': '#d62728',
                'White': '#ffffff',
                'Green': '#2ca02c',
                'Black': '#111111',
                'Yellow': '#ffbf00',
                'Blue': '#1f77b4',
                'Bare': '#888888'
            }

            if which == 'neck':
                top_is_north = st.session_state.get('neck_is_north_up', True)
            else:
                top_is_north = st.session_state.get('bridge_is_north_up', True)
            coilA_pol = 'North' if top_is_north else 'South'
            coilB_pol = 'South' if top_is_north else 'North'

            def colour_svg_overlay(upper, lower):
                # Desired visual order (top->bottom): CoilA START, CoilA END, CoilB END, CoilB START
                vals = [upper.get('start'), upper.get('finish'), lower.get('finish'), lower.get('start')]
                fills = [COLOR_HEX.get(v, '#cccccc') if v else '#cccccc' for v in vals]
                texts = [v[0].upper() if v else '?' for v in vals]
                parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 200" preserveAspectRatio="xMinYMin meet" width="220" height="200">']
                r = 12
                left_x = 18
                default_circle_x = 140
                line_fraction = 0.6
                pol_text_offset = 50
                pol_font_size = 10
                y_a1 = 36
                y_a2 = 76
                y_b1 = 156
                y_b2 = 196
                y_positions = [y_a1, y_a2, y_b1, y_b2]

                labels = [
                    f'{coilA_pol} START +',
                    f'{coilA_pol} END -',
                    f'{coilB_pol} END -',
                    f'{coilB_pol} START +',
                ]

                for i, (f, t, y) in enumerate(zip(fills, texts, y_positions)):
                    try:
                        fl = f.lower()
                        if fl in ('#ffffff', '#ffbf00'):
                            line_color = '#cccccc'
                        elif fl in ('#111111', '#000000'):
                            line_color = "#000000"
                        else:
                            line_color = f
                    except Exception:
                        line_color = '#cccccc'
                    line_end_full = default_circle_x - r - 6
                    line_end = left_x + int((line_end_full - left_x) * line_fraction)
                    parts.append(f'<line x1="0" y1="{y}" x2="{left_x}" y2="{y}" stroke="{line_color}" stroke-width="1" stroke-opacity="0.75" />')
                    parts.append(f'<line x1="{left_x}" y1="{y}" x2="{line_end}" y2="{y}" stroke="{line_color}" stroke-width="1" stroke-opacity="0.75" />')
                    circle_x = line_end + r + 6
                    polarity_word = 'Start' if 'start' in labels[i].lower() else 'End'
                    pol_text_fill = '#ffffff' if f.lower() not in ('#ffffff', '#ffbf00') else '#111111'
                    parts.append(f'<circle cx="{circle_x}" cy="{y}" r="{r}" fill="{f}" stroke="#222" stroke-width="1" />')
                    text_fill = '#111111' if f.lower() in ('#ffffff', '#ffbf00') else '#ffffff'
                    parts.append(f'<text x="{circle_x}" y="{y}" text-anchor="middle" dominant-baseline="middle" font-family="sans-serif" font-size="12" fill="{text_fill}">{t}</text>')
                    parts.append(f'<text x="{circle_x + r + 10}" y="{y+4}" font-family="sans-serif" font-size="12" fill="#ffffff">{labels[i]}</text>')
                # Draw a visible connector between the two middle circles (series link)
                try:
                    line_end_full = default_circle_x - r - 6
                    line_end = left_x + int((line_end_full - left_x) * line_fraction)
                    connector_x = line_end + r + 6
                    y1 = y_positions[1]
                    y2 = y_positions[2]
                    gap = max(6, int((y2 - y1) * 0.18))
                    y1s = y1 + gap
                    y2s = y2 - gap
                    parts.append(f'<line x1="{connector_x}" y1="{y1s}" x2="{connector_x}" y2="{y2s}" stroke="#ffffff" stroke-width="2" stroke-linecap="round" />')
                    mid_y = int((y1s + y2s) / 2)
                    series_x = max(left_x + 6, connector_x - (r + 64))
                    parts.append(f'<text x="{series_x}" y="{mid_y + 4}" font-family="sans-serif" font-size="12" fill="#ffffff">Series</text>')
                except Exception:
                    pass
                parts.append('</svg>')
                return '\n'.join(parts)

            overlay_html = colour_svg_overlay(upper_map, lower_map)
            html = f"""
            <div style="position:relative; width:100%; max-width:560px;">
              <div style="position:relative; z-index:1;">{svg_html}</div>
              <div style="position:absolute; right:8px; top:8px; z-index:2; pointer-events:none;">{overlay_html}</div>
            </div>
            """
            components.html(html, height=height)
        except Exception:
            st.image(img_path, use_column_width=True)
    else:
        st.image(img_path, use_column_width=True)

def _check_easter_egg_hints(user_input: str) -> str:
    """Check if user input contains easter egg triggers and return witty response or empty string."""
    if not isinstance(user_input, str):
        return ''
    
    text = user_input.lower().strip()
    
    # Easter egg triggers with guitar/wiring themed responses
    easter_eggs = {
        '42': '🎸 **The Answer to Life, The Universe, and Guitar Wiring?** Forty-two. Also the resistance of my patience when I measure wires. ⚡',
        'hello there': '🎸 **General Kenobi!** You are a bold one. Also, use a compass on your pickups — it helps.',
        'sudo': '🎸 **Nice try, hacker.** This is a guitar app, not a terminal. Though I respect the attempt to bypass physics. 🔐',
        'is this the real life': '🎸 **Is this just fantasy?** No, this is your wiring diagram. And yes, you *are* caught in a landslide. ⚡',
        'winter is coming': '🎸 **And so is your hum-cancelling test!** The North coil sends its regards. ❄️',
        'i am your father': '🎸 **No, the BARE WIRE is your father.** It grounds everything. Accept your heritage. 👨‍⚡',
        'muffin man': '🎸 **Do you know the man on Drury Lane?** He wires pickups, and he\'s *excellent*. You should be like him. 🧁',
        'what is your name': '🎸 **I\'m just a humble wire-color assistant.** But you can call me... *The Hum Whisperer*. 🎵',
        'matrix': '🎸 **There is no series wiring.** There is only... parallel. Also, the red pill tastes like pickup solder. 💊',
        'beer': '🎸 **Ah yes, the fuel of late-night guitar projects.** May your solder joints be as smooth as your taste in beverages. 🍺',
    }
    
    # Check for exact matches or substring matches
    for trigger, response in easter_eggs.items():
        if trigger in text:
            return response
    
    return ''

def _render_step_nav():
    # Use on_click callbacks so Streamlit handles the rerun and UI updates immediately
    cols = st.columns([1, 6, 1])
    cols[0].button('Previous', on_click=_on_prev)
    step = st.session_state.get('step', 1)
    cols[1].markdown(f"**Step {step} / {MAX_STEP}**")
    cols[2].button('Next', on_click=_on_next)

# render nav at top of page so it's visible for every step
_render_step_nav()

# Simple stepper — render all widgets inside expanders so they are instantiated every run
step = st.session_state.get('step', 1)

if step == 1:
    st.title('🎸 Humbucker Solver — with AI & Questionable Life Choices')
    st.write('**Your pickup wire colors are a mystery. Your soldering skills are... a work in progress. Let\'s fix at least one.**\n\n'
             'This engineer\'s assistant will guide you through: identifying wire colors, testing magnetic polarity, measuring resistance, '
             'and wiring your pickups so they *actually* cancel hum (instead of adding more). '
             'Follow the steps. Trust the math. Blame the manufacturer if it doesn\'t work.')
    st.caption('⚡ **Why?** Because life\'s too short for mystery wires, reversed coils, and ground loops that hum louder than your amp. '
               'Also, we can\'t guarantee your guitar will sound better, but at least you\'ll know *why* it doesn\'t (and how to fix it). 🎸')
    st.header('Welcome')
    st.write('Welcome — click the top "Next" to begin wire mapping for your pickups.')
    st.info('💡 **Engineer tip:** If this app confuses you, don\'t worry — the wires in your guitar are *already* confused. We\'re just here to mediate.')

if step == 2:
    st.header('Step 2 — Define wire colors')
    st.write('Choose up to 4 conductor colors for each pickup (and check bare if present).')
    st.caption('🌈 Fun fact: Pickup manufacturers use color codes like they\'re playing guitar wire roulette. Red means... something. Probably.')
    st.info('💡 **Hint:** If you\'re not sure which wires are which, use a multimeter to measure resistance between wire pairs. The pairs with similar resistance belong together!')
    st.caption('🎸 *Psst... try typing a famous sci-fi phrase or a number into the AI sidebar. You might discover something fun.* 😉')
    
    COLOR_OPTIONS = ['Red', 'White', 'Green', 'Black', 'Yellow', 'Blue', 'Bare']
    col1 = st.multiselect('Neck wire colors (ordered)', COLOR_OPTIONS,
                          default=_safe_default_list(COLOR_OPTIONS, st.session_state.get('neck_wire_colors', ['Red', 'White', 'Green', 'Black'])),
                          key='neck_wire_colors')
    
    # Easter egg check for neck colors
    easter_response = _check_easter_egg_hints(str(col1))
    if easter_response:
        st.success(easter_response)
    
    col2 = st.multiselect('Bridge wire colors (ordered)', COLOR_OPTIONS,
                          default=_safe_default_list(COLOR_OPTIONS, st.session_state.get('bridge_wire_colors', ['Red', 'White', 'Green', 'Black'])),
                          key='bridge_wire_colors')
    
    # Easter egg check for bridge colors
    easter_response = _check_easter_egg_hints(str(col2))
    if easter_response:
        st.success(easter_response)
    
    bare = st.checkbox('Bare (ground) present', value=st.session_state.get('bare', False), key='bare')


if step == 3:
    st.header('Step 3 — Polarity (top of pickup)')
    st.write('Use a compass over the pickup (top of pickup). Slug = North coil; Screw = South coil.')
    st.caption('🧭 Yes, an actual compass. The same technology that helped Vikings navigate... now helps you wire pickups. Progress!')
    st.info('💡 **Hint:** Hold the compass FLAT over the pole pieces. The needle pointing away = North pole. The needle pointing toward = South pole. Simple physics!')
    neck_toggle = st.checkbox('Neck — top is Slug (N)', value=st.session_state.get('neck_is_north_up', True), key='neck_is_north_up', on_change=_on_neck_toggle)
    bridge_toggle = st.checkbox('Bridge — top is Slug (N)', value=st.session_state.get('bridge_is_north_up', True), key='bridge_is_north_up', on_change=_on_bridge_toggle)
    # Keep the legacy orientation string in session_state for compatibility with other code
    if st.session_state.get('neck_is_north_up', True):
        st.session_state['neck_orientation'] = 'Top = Slug (N) / Bottom = Screw (S)'
        n_pol = {'top': 'NORTH', 'bottom': 'SOUTH'}
        st.session_state['neck_img_choice'] = 'north'
    else:
        st.session_state['neck_orientation'] = 'Top = Screw (S) / Bottom = Slug (N)'
        n_pol = {'top': 'SOUTH', 'bottom': 'NORTH'}
        st.session_state['neck_img_choice'] = 'south'

    if st.session_state.get('bridge_is_north_up', True):
        st.session_state['bridge_orientation'] = 'Top = Slug (N) / Bottom = Screw (S)'
        b_pol = {'top': 'NORTH', 'bottom': 'SOUTH'}
        st.session_state['bridge_img_choice'] = 'north'
    else:
        st.session_state['bridge_orientation'] = 'Top = Screw (S) / Bottom = Slug (N)'
        b_pol = {'top': 'SOUTH', 'bottom': 'NORTH'}
        st.session_state['bridge_img_choice'] = 'south'
    st.write(f"Neck — Top: {n_pol['top']}, Bottom: {n_pol['bottom']}")
    st.write(f"Bridge — Top: {b_pol['top']}, Bottom: {b_pol['bottom']}")
    # Debug helper: show key orientation/image state when needed
    if st.checkbox('Show debug state', value=False, key='show_debug_state'):
        dbg = {k: st.session_state.get(k) for k in ['neck_is_north_up', 'bridge_is_north_up', 'neck_img_choice', 'bridge_img_choice', 'step']}
        st.json(dbg)

if step == 4:
    st.header('Step 4 — Measurements')
    st.write('Enter coil resistances found in Step 5 measurement (kΩ).')
    st.caption('📊 Resistance is NOT futile — it\'s actually around 5-15 kΩ per coil. Physics: 1, Inspirational quotes: 0.')
    st.info('💡 **Hint:** Use an ohmmeter (multimeter on Ω setting). Touch probes to opposite coil wires. Typical humbuckers: 5-15k each coil. If you see wildly different values, check your connections!')
    st.caption('🎸 *Psst... what if one coil measured exactly **42 kΩ**? That would be quite the answer. Try it!* 😉')
    
    # Input fields for resistances with easter egg detection
    n_up = st.number_input('Neck — upper coil (kΩ)', min_value=0.0, format='%.2f', value=st.session_state.get('n_up', 0.0), key='n_up')
    if n_up == 42:
        st.success('🎸 **42?** The answer to everything, including pickup resistance. Well played.')
    
    n_lo = st.number_input('Neck — lower coil (kΩ)', min_value=0.0, format='%.2f', value=st.session_state.get('n_lo', 0.0), key='n_lo')
    b_up = st.number_input('Bridge — upper coil (kΩ)', min_value=0.0, format='%.2f', value=st.session_state.get('b_up', 0.0), key='b_up')
    b_lo = st.number_input('Bridge — lower coil (kΩ)', min_value=0.0, format='%.2f', value=st.session_state.get('b_lo', 0.0), key='b_lo')
    pass
if step == 5:
    st.header('Step 5 — Phase checks (touch pole piece)')
    st.caption('🔬 Time to channel your inner scientist! Touch pole pieces with a multimeter. If the needle goes up, congrats — you found "Normal" phase. If it goes down, you found "Reverse" (or as we call it, "the pickup is feeling rebellious today").')
    st.info('💡 **Hint:** Set multimeter to DC resistance. Connect RED probe to one coil wire, BLACK probe to the other. While connected, touch a POLE PIECE with a screwdriver (or any metal object — yes, that counts as "proper lab technique"). If resistance RISES = Normal phase. If resistance LOWERS = Reverse phase. Test both wires to identify START and FINISH. (And no, the pole piece won\'t bite. Probably.)')
    st.caption('🎸 *Psst... if you ask the AI assistant \"hello there\", it might respond in an *interesting* way. Pop culture references are fair game!* 😉')
    # Probe→Wire mapping + Phase checks (combined header)
    st.subheader('Probe mapping & Phase checks')
    st.write(f"Start from NECK-{n_pol['top']} and finish mapping to BRIDGE-{n_pol['bottom']}. For each coil, select which wire the RED probe touched and which wire the BLACK probe touched, then indicate the phase (resistance change when touching a pole piece).")


    st.markdown('---')
    neck_colors = st.session_state.get('neck_wire_colors', [])
    bridge_colors = st.session_state.get('bridge_wire_colors', [])
    default_neck_top = _safe_default_list(neck_colors, st.session_state.get('neck_north_colors', neck_colors[:2]))
    default_neck_bottom = _safe_default_list(neck_colors, st.session_state.get('neck_south_colors', neck_colors[2:4]))
    default_bridge_top = _safe_default_list(bridge_colors, st.session_state.get('bridge_north_colors', bridge_colors[:2]))
    default_bridge_bottom = _safe_default_list(bridge_colors, st.session_state.get('bridge_south_colors', bridge_colors[2:4]))

    cols = st.columns([6, 1])
    cols[0].markdown(_render_color_badges(st.session_state.get('neck_north_colors', [])), unsafe_allow_html=True)
    cols[1].markdown('')
    with st.expander('Edit Neck — Top wire colors', expanded=st.session_state.get('exp_neck_north', False)):
        st.multiselect('Neck top', neck_colors, default=default_neck_top, key='neck_north_colors', label_visibility='collapsed')

    cols = st.columns([6, 1])
    cols[0].markdown(_render_color_badges(st.session_state.get('neck_south_colors', [])), unsafe_allow_html=True)
    cols[1].markdown('')
    with st.expander('Neck — Bottom wire colors', expanded=st.session_state.get('exp_neck_south', False)):
        st.multiselect('Neck bottom', [c for c in neck_colors if c not in st.session_state.get('neck_north_colors', [])], default=default_neck_bottom, key='neck_south_colors', label_visibility='collapsed')

    cols = st.columns([6, 1])
    cols[0].markdown(_render_color_badges(st.session_state.get('bridge_north_colors', [])), unsafe_allow_html=True)
    cols[1].markdown('')
    with st.expander('Bridge — Top wire colors', expanded=st.session_state.get('exp_bridge_north', False)):
        st.multiselect('Bridge top', bridge_colors, default=default_bridge_top, key='bridge_north_colors', label_visibility='collapsed')

    cols = st.columns([6, 1])
    cols[0].markdown(_render_color_badges(st.session_state.get('bridge_south_colors', [])), unsafe_allow_html=True)
    cols[1].markdown('')
    with st.expander('Bridge — Bottom wire colors', expanded=st.session_state.get('exp_bridge_south', False)):
        st.multiselect('Bridge bottom', [c for c in bridge_colors if c not in st.session_state.get('bridge_north_colors', [])], default=default_bridge_bottom, key='bridge_south_colors', label_visibility='collapsed')

    # validate mapping
    mapping_ok = True
    if len(st.session_state.get('neck_north_colors', [])) != 2 or len(st.session_state.get('neck_south_colors', [])) != 2:
        st.warning('Please select exactly 2 colors for each neck coil (top and bottom).')
        mapping_ok = False
    if len(st.session_state.get('bridge_north_colors', [])) != 2 or len(st.session_state.get('bridge_south_colors', [])) != 2:
        st.warning('Please select exactly 2 colors for each bridge coil (top and bottom).')
        mapping_ok = False
    if mapping_ok:
        st.info('Mapping looks good — proceed with probe checks below.')
    else:
        st.info('Please fix the mapping warnings above. Select exactly 2 colors per coil before proceeding.')

    # Small helper: color name -> hex for badges
    PROBE_COLOR_HEX = {
        'Red': '#d62728',
        'White': '#ffffff',
        'Green': '#2ca02c',
        'Black': '#111111',
        'Yellow': '#ffbf00',
        'Blue': '#1f77b4',
        'Bare': '#888888'
    }

    def _color_badge_html(color_name: str, label: str = '') -> str:
        if not color_name or color_name == '--':
            return f"<span style='padding:2px 6px;border-radius:4px;background:#f0f0f0;color:#333;border:1px solid #ddd'>{label or '—'}</span>"
        hexcol = PROBE_COLOR_HEX.get(color_name, '#cccccc')
        text_color = '#111111' if hexcol.lower() in ('#ffffff', '#ffbf00') else '#ffffff'
        return f"<span style='display:inline-flex;align-items:center;gap:8px'><span style='width:14px;height:14px;background:{hexcol};border:1px solid #222;display:inline-block;border-radius:3px'></span><span style='color:{text_color};background:transparent;padding:2px 6px;border-radius:4px'>{label or color_name}</span></span>"

    # Per-coil probe selection using the previously chosen coil colors
    neck_top_wires = st.session_state.get('neck_north_colors', [])
    neck_bottom_wires = st.session_state.get('neck_south_colors', [])
    bridge_top_wires = st.session_state.get('bridge_north_colors', [])
    bridge_bottom_wires = st.session_state.get('bridge_south_colors', [])

    st.markdown('**Probe picks (per coil)**')
    st.write('Click/select which color the RED and BLACK probes contacted for each coil. Options are limited to the two colors chosen for that coil above.')

    # Helper to render two radios (Red/Black) for a coil
    def _coil_probe_row(title: str, colors: list, red_key: str, black_key: str, phase_key: str):
        if not colors or len(colors) == 0:
            st.info(f'{title} wires not defined yet.')
            return
        opts = colors
        cols = st.columns(2)
        cols[0].radio(f'RED PROBE touched ({title})', opts, index=_safe_index(opts, st.session_state.get(red_key)), key=red_key)
        cols[1].radio(f'BLACK PROBE touched ({title})', opts, index=_safe_index(opts, st.session_state.get(black_key)), key=black_key)
        
        # Easter egg check for probe wire selections
        red_wire = st.session_state.get(red_key, '')
        black_wire = st.session_state.get(black_key, '')
        easter_response = _check_easter_egg_hints(f"{red_wire} {black_wire}")
        if easter_response:
            st.success(easter_response)
        
        # show compact badges under the radios for immediate confirmation
        badge_cols = st.columns([1, 3])
        badge_cols[0].markdown('')
        badge_cols[1].markdown(f"Red: {_color_badge_html(st.session_state.get(red_key) or '--')}  &nbsp;&nbsp; Black: {_color_badge_html(st.session_state.get(black_key) or '--')}", unsafe_allow_html=True)
        # Phase check radio directly under this coil's selection
        phase_opts = ['Normal Phase', 'Reverse Phase']
        # default to existing session value if present
        default_idx = 0 if st.session_state.get(phase_key, 'Resistance increase') == 'Resistance increase' else 1
        st.radio(f'{title}: Touch coil with metal. If resistance increased when touched: Phase is normal.', phase_opts, index=default_idx, key=phase_key)

    st.markdown('### Neck Pickup')
    _coil_probe_row('Neck — Upper coil', neck_top_wires, 'n_up_probe_red_wire', 'n_up_probe_black_wire', 'n_up_probe')
    _coil_probe_row('Neck — Lower coil', neck_bottom_wires, 'n_lo_probe_red_wire', 'n_lo_probe_black_wire', 'n_lo_probe')
    
    st.markdown('### Bridge Pickup')
    _coil_probe_row('Bridge — Upper coil', bridge_top_wires, 'b_up_probe_red_wire', 'b_up_probe_black_wire', 'b_up_probe')
    _coil_probe_row('Bridge — Lower coil', bridge_bottom_wires, 'b_lo_probe_red_wire', 'b_lo_probe_black_wire', 'b_lo_probe')


    # Show inferred START/END mapping (preview) using probe->wire selections
    def _none_if_dash(val):
        return None if (val is None or (isinstance(val, str) and val.strip() == '--')) else val

    try:
        neck_upper_map = infer_start_finish_from_probes(
            st.session_state.get('neck_north_colors', []),
            _none_if_dash(st.session_state.get('n_up_probe_red_wire')),
            _none_if_dash(st.session_state.get('n_up_probe_black_wire')),
            st.session_state.get('n_up_probe'),
            st.session_state.get('n_up_swap', False)
        )
        neck_lower_map = infer_start_finish_from_probes(
            st.session_state.get('neck_south_colors', []),
            _none_if_dash(st.session_state.get('n_lo_probe_red_wire')),
            _none_if_dash(st.session_state.get('n_lo_probe_black_wire')),
            st.session_state.get('n_lo_probe'),
            st.session_state.get('n_lo_swap', False)
        )
        bridge_upper_map = infer_start_finish_from_probes(
            st.session_state.get('bridge_north_colors', []),
            _none_if_dash(st.session_state.get('b_up_probe_red_wire')),
            _none_if_dash(st.session_state.get('b_up_probe_black_wire')),
            st.session_state.get('b_up_probe'),
            st.session_state.get('b_up_swap', False)
        )
        bridge_lower_map = infer_start_finish_from_probes(
            st.session_state.get('bridge_south_colors', []),
            _none_if_dash(st.session_state.get('b_lo_probe_red_wire')),
            _none_if_dash(st.session_state.get('b_lo_probe_black_wire')),
            st.session_state.get('b_lo_probe'),
            st.session_state.get('b_lo_swap', False)
        )


        
    except Exception:
        # best-effort preview; ignore errors
        pass

if step == 6:
    st.header('Step 6 — Analyze Wiring & Generate Diagram')
    st.write('Review your phase testing results and generate the final wiring diagram.')
    st.caption('🎯 The moment of truth! Let\'s see if these pickups will hum-cancel or just... hum. (Spoiler: if they hum, blame the manufacturer, not the app. We\'re just the messenger.)')
    st.info('💡 **Hint:** Your wiring diagram shows START and FINISH for each coil. START wires go to HOT. FINISH wires (and BARE) go to GROUND. Series wires link the two coils together.')
    
    if st.button('Analyze wiring'):
        # Gather inputs and run analysis
        neck_pair = st.session_state.get('neck_north_colors', [])
        south_pair = st.session_state.get('neck_south_colors', [])
        bridge_north = st.session_state.get('bridge_north_colors', [])
        bridge_south = st.session_state.get('bridge_south_colors', [])
        # Normalize probe->wire selections: the selectboxes include a '--' placeholder
        def _none_if_dash(val):
            return None if (val is None or (isinstance(val, str) and val.strip() == '--')) else val

        analysis_neck = analyze_pickup(
            neck_pair,
            south_pair,
            st.session_state.get('n_up_probe'),
            st.session_state.get('n_lo_probe'),
            north_swap=st.session_state.get('n_up_swap'),
            south_swap=st.session_state.get('n_lo_swap'),
            bare=st.session_state.get('bare'),
            north_res_kohm=st.session_state.get('n_up'),
            south_res_kohm=st.session_state.get('n_lo'),
            north_red_wire=_none_if_dash(st.session_state.get('n_up_probe_red_wire')),
            north_black_wire=_none_if_dash(st.session_state.get('n_up_probe_black_wire')),
            south_red_wire=_none_if_dash(st.session_state.get('n_lo_probe_red_wire')),
            south_black_wire=_none_if_dash(st.session_state.get('n_lo_probe_black_wire')),
        )

        analysis_bridge = analyze_pickup(
            bridge_north,
            bridge_south,
            st.session_state.get('b_up_probe'),
            st.session_state.get('b_lo_probe'),
            north_swap=st.session_state.get('b_up_swap'),
            south_swap=st.session_state.get('b_lo_swap'),
            bare=st.session_state.get('bare'),
            north_res_kohm=st.session_state.get('b_up'),
            south_res_kohm=st.session_state.get('b_lo'),
            north_red_wire=_none_if_dash(st.session_state.get('b_up_probe_red_wire')),
            north_black_wire=_none_if_dash(st.session_state.get('b_up_probe_black_wire')),
            south_red_wire=_none_if_dash(st.session_state.get('b_lo_probe_red_wire')),
            south_black_wire=_none_if_dash(st.session_state.get('b_lo_probe_black_wire')),
        )
        st.session_state['analysis'] = {'neck': analysis_neck, 'bridge': analysis_bridge}
        _save_state()
        st.success('✅ Analysis complete! Scroll down to see your wiring diagram.')

    # Display analysis results if available
    analysis = st.session_state.get('analysis', {})
    if analysis:
        neck = analysis.get('neck')
        bridge = analysis.get('bridge')
        
        st.header('Neck pickup')
        # Recompute mapping so we can show explicit START/END labels
        try:
            neck_upper_map = infer_start_finish_from_probes(
                st.session_state.get('neck_north_colors', []),
                st.session_state.get('n_up_probe_red_wire'),
                st.session_state.get('n_up_probe_black_wire'),
                st.session_state.get('n_up_probe'),
                st.session_state.get('n_up_swap', False)
            )
            neck_lower_map = infer_start_finish_from_probes(
                st.session_state.get('neck_south_colors', []),
                st.session_state.get('n_lo_probe_red_wire'),
                st.session_state.get('n_lo_probe_black_wire'),
                st.session_state.get('n_lo_probe'),
                st.session_state.get('n_lo_swap', False)
            )
            st.write(f"NORTH Start: {neck_upper_map.get('start')}")
            st.write(f"NORTH End: {neck_upper_map.get('finish')}")
            st.write(f"SOUTH End: {neck_lower_map.get('finish')}")
            st.write(f"SOUTH Start: {neck_lower_map.get('start')}")
            
        except Exception:
            st.write(neck)
        render_pickup_preview('neck', height=240)

        # Show explicit wiring suggestion for the neck based on analysis result
        try:
            # Recompute start/finish mappings so we can let the user choose which end is HOT
            def _none_if_dash(val):
                return None if (val is None or (isinstance(val, str) and val.strip() == '--')) else val

            neck_upper_map = infer_start_finish_from_probes(
                st.session_state.get('neck_north_colors', []),
                _none_if_dash(st.session_state.get('n_up_probe_red_wire')),
                _none_if_dash(st.session_state.get('n_up_probe_black_wire')),
                st.session_state.get('n_up_probe'),
                st.session_state.get('n_up_swap', False)
            )
            neck_lower_map = infer_start_finish_from_probes(
                st.session_state.get('neck_south_colors', []),
                _none_if_dash(st.session_state.get('n_lo_probe_red_wire')),
                _none_if_dash(st.session_state.get('n_lo_probe_black_wire')),
                st.session_state.get('n_lo_probe'),
                st.session_state.get('n_lo_swap', False)
            )

            # Determine probe polarity (reverse vs normal) using user's rule:
            def _probe_is_reverse(choice):
                if not choice:
                    return False
                c = str(choice).lower()
                return any(k in c for k in ('laskee', 'drop', 'decrease', 'fall', 'reverse', 'käänte'))

            neck_north_phase = 'Reverse' if _probe_is_reverse(st.session_state.get('n_up_probe')) else 'Normal'
            neck_south_phase = 'Reverse' if _probe_is_reverse(st.session_state.get('n_lo_probe')) else 'Normal'

            neck_north_res = st.session_state.get('n_up')
            neck_south_res = st.session_state.get('n_lo')

            # Let user select wiring type for neck pickup
            neck_wiring_choice = st.selectbox(
                'Neck pickup wiring:',
                ['series', 'parallel', 'slug_only', 'screw_only'],
                index=0,
                key='neck_wiring_choice'
            )

            bare_present = st.session_state.get('bare', False)

            # Calculate expected resistance for this configuration
            neck_total_res = _calculate_total_resistance(neck_north_res, neck_south_res, neck_wiring_choice)

            # Show which coil is which magnet type
            neck_north_magnet = 'Slug (North)' if 'Slug' in str(st.session_state.get('neck_north_colors', [''])[0]) else 'Screw (South)'
            neck_south_magnet = 'Screw (South)' if neck_north_magnet == 'Slug (North)' else 'Slug (North)'

            neck_order = _compute_wiring_order(neck_upper_map, neck_lower_map, neck_wiring_choice, bare_present=bare_present, upper_phase=neck_north_phase, lower_phase=neck_south_phase)
            # Wiring details will be shown in summary at bottom

        except Exception as e:
            st.error(f"Error computing neck wiring: {e}")

        st.header('Bridge pickup')
        try:
            bridge_upper_map = infer_start_finish_from_probes(
                st.session_state.get('bridge_north_colors', []),
                st.session_state.get('b_up_probe_red_wire'),
                st.session_state.get('b_up_probe_black_wire'),
                st.session_state.get('b_up_probe'),
                st.session_state.get('b_up_swap', False)
            )
            bridge_lower_map = infer_start_finish_from_probes(
                st.session_state.get('bridge_south_colors', []),
                st.session_state.get('b_lo_probe_red_wire'),
                st.session_state.get('b_lo_probe_black_wire'),
                st.session_state.get('b_lo_probe'),
                st.session_state.get('b_lo_swap', False)
            )
            st.write(f"NORTH Start: {bridge_upper_map.get('start')}")
            st.write(f"NORTH End: {bridge_upper_map.get('finish')}")
            st.write(f"SOUTH End: {bridge_lower_map.get('finish')}")
            st.write(f"SOUTH Start: {bridge_lower_map.get('start')}")
        except Exception:
            st.write(bridge)
        render_pickup_preview('bridge', height=240)

        # Show explicit wiring suggestion for bridge
        try:
            def _none_if_dash(val):
                return None if (val is None or (isinstance(val, str) and val.strip() == '--')) else val

            upper_map = infer_start_finish_from_probes(
                st.session_state.get('bridge_north_colors', []),
                _none_if_dash(st.session_state.get('b_up_probe_red_wire')),
                _none_if_dash(st.session_state.get('b_up_probe_black_wire')),
                st.session_state.get('b_up_probe'),
                st.session_state.get('b_up_swap', False)
            )
            lower_map = infer_start_finish_from_probes(
                st.session_state.get('bridge_south_colors', []),
                _none_if_dash(st.session_state.get('b_lo_probe_red_wire')),
                _none_if_dash(st.session_state.get('b_lo_probe_black_wire')),
                st.session_state.get('b_lo_probe'),
                st.session_state.get('b_lo_swap', False)
            )

            def _probe_is_reverse(choice):
                if not choice:
                    return False
                c = str(choice).lower()
                return any(k in c for k in ('laskee', 'drop', 'decrease', 'fall', 'reverse', 'käänte'))

            bridge_north_phase = 'Reverse' if _probe_is_reverse(st.session_state.get('b_up_probe')) else 'Normal'
            bridge_south_phase = 'Reverse' if _probe_is_reverse(st.session_state.get('b_lo_probe')) else 'Normal'

            bridge_north_res = st.session_state.get('b_up')
            bridge_south_res = st.session_state.get('b_lo')

            bridge_wiring_choice = st.selectbox(
                'Bridge pickup wiring:',
                ['series', 'parallel', 'slug_only', 'screw_only'],
                index=0,
                key='bridge_wiring_choice'
            )

            bare_present = st.session_state.get('bare', False)

            bridge_total_res = _calculate_total_resistance(bridge_north_res, bridge_south_res, bridge_wiring_choice)

            bridge_north_magnet = 'Slug (North)' if 'Slug' in str(st.session_state.get('bridge_north_colors', [''])[0]) else 'Screw (South)'
            bridge_south_magnet = 'Screw (South)' if bridge_north_magnet == 'Slug (North)' else 'Slug (North)'

            order = _compute_wiring_order(upper_map, lower_map, bridge_wiring_choice, bare_present=bare_present, upper_phase=bridge_north_phase, lower_phase=bridge_south_phase)
            # Wiring details will be shown in summary at bottom

        except Exception as e:
            st.error(f"Error computing bridge wiring: {e}")

        # Add inter-pickup connection mode selector
        st.header('Combined Pickup Configuration')
        
        # Let user select connection mode between pickups
        pickups_connection = st.selectbox(
            'How should the pickups be connected together?',
            ['parallel', 'series'],
            index=0,
            help='Parallel: Both pickup outputs go to HOT together. Series: One pickup feeds into the other.',
            key='pickups_connection'
        )

        # Generate complete wiring JSON
        try:
            st.subheader('Complete Wiring JSON')
            st.markdown('This JSON includes all wiring details for both pickups and their inter-pickup connection.')

            # Helper to check for None/'--' placeholder in probe->wire selections
            def _none_if_dash(val):
                return None if (val is None or (isinstance(val, str) and val.strip() == '--')) else val

            # Recompute mappings for both pickups using the helper that avoids '--' placeholders
            neck_upper_map = infer_start_finish_from_probes(
                st.session_state.get('neck_north_colors', []),
                _none_if_dash(st.session_state.get('n_up_probe_red_wire')),
                _none_if_dash(st.session_state.get('n_up_probe_black_wire')),
                st.session_state.get('n_up_probe'),
                st.session_state.get('n_up_swap', False)
            )
            neck_lower_map = infer_start_finish_from_probes(
                st.session_state.get('neck_south_colors', []),
                _none_if_dash(st.session_state.get('n_lo_probe_red_wire')),
                _none_if_dash(st.session_state.get('n_lo_probe_black_wire')),
                st.session_state.get('n_lo_probe'),
                st.session_state.get('n_lo_swap', False)
            )

            upper_map = infer_start_finish_from_probes(
                st.session_state.get('bridge_north_colors', []),
                _none_if_dash(st.session_state.get('b_up_probe_red_wire')),
                _none_if_dash(st.session_state.get('b_up_probe_black_wire')),
                st.session_state.get('b_up_probe'),
                st.session_state.get('b_up_swap', False)
            )
            lower_map = infer_start_finish_from_probes(
                st.session_state.get('bridge_south_colors', []),
                _none_if_dash(st.session_state.get('b_lo_probe_red_wire')),
                _none_if_dash(st.session_state.get('b_lo_probe_black_wire')),
                st.session_state.get('b_lo_probe'),
                st.session_state.get('b_lo_swap', False)
            )

            def _probe_is_reverse(choice):
                if not choice:
                    return False
                c = str(choice).lower()
                return any(k in c for k in ('laskee', 'drop', 'decrease', 'fall', 'reverse', 'käänte'))

            neck_north_phase = 'Reverse' if _probe_is_reverse(st.session_state.get('n_up_probe')) else 'Normal'
            neck_south_phase = 'Reverse' if _probe_is_reverse(st.session_state.get('n_lo_probe')) else 'Normal'
            bridge_north_phase = 'Reverse' if _probe_is_reverse(st.session_state.get('b_up_probe')) else 'Normal'
            bridge_south_phase = 'Reverse' if _probe_is_reverse(st.session_state.get('b_lo_probe')) else 'Normal'

            neck_north_res = st.session_state.get('n_up')
            neck_south_res = st.session_state.get('n_lo')
            bridge_north_res = st.session_state.get('b_up')
            bridge_south_res = st.session_state.get('b_lo')

            neck_wiring_choice = st.session_state.get('neck_wiring_choice', 'series')
            bridge_wiring_choice = st.session_state.get('bridge_wiring_choice', 'series')

            neck_total_res = _calculate_total_resistance(neck_north_res, neck_south_res, neck_wiring_choice)
            bridge_total_res = _calculate_total_resistance(bridge_north_res, bridge_south_res, bridge_wiring_choice)

            bare_present = st.session_state.get('bare', False)

            neck_order = _compute_wiring_order(neck_upper_map, neck_lower_map, neck_wiring_choice, bare_present=bare_present, upper_phase=neck_north_phase, lower_phase=neck_south_phase)

            # Build pickup list for JSON output
            pickups_list = []

            # Check if coil split mode is active (both pickups forced to only upper coil)
            both_coil_split = (neck_wiring_choice in ('slug_only', 'screw_only') and bridge_wiring_choice in ('slug_only', 'screw_only'))

            # Add NECK pickup to the list
            show_neck = True  # Always show neck for now (could be conditional based on switch position)
            if show_neck:
                if both_coil_split:
                    # Coil split mode: determine which magnet pole is upper for NECK
                    neck_upper_is_south = 'Screw' in str(st.session_state.get('neck_north_colors', [''])[0]) if st.session_state.get('neck_north_colors') else False
                    
                    if neck_upper_is_south:
                        # Upper coil is south (screw), so use lower coil
                        coil_name = 'Upper/Screw (South)'
                        coil_map = neck_lower_map
                        coil_res = neck_south_res
                        coil_phase = neck_south_phase
                    else:
                        # Upper coil is north (slug), so use upper coil
                        coil_name = 'Upper/Slug (North)'
                        coil_map = neck_upper_map
                        coil_res = neck_north_res
                        coil_phase = neck_north_phase
                    
                    neck_order = _compute_wiring_order(neck_upper_map, neck_lower_map, neck_wiring_choice, bare_present=bare_present, upper_phase=neck_north_phase, lower_phase=neck_south_phase)
                    pickups_list.append({
                        'pickup': 'NECK (coil split - upper coil)',
                        'variant': neck_wiring_choice,
                        'coils': {
                            'coil_upper': {
                                'name': f'Coil: {coil_name}',
                                'start': coil_map.get('start'),
                                'finish': coil_map.get('finish'),
                                'phase': coil_phase,
                                'resistance_kohm': coil_res
                            }
                        },
                        'wiring_configuration': {
                            'output': neck_order.get('output', []),
                            'series': [],
                            'ground': neck_order.get('ground', []),
                            'bare_present': bare_present,
                            'total_resistance_kohm': round(coil_res, 2) if coil_res else None
                        }
                    })
                else:
                    # Normal mode: NECK with selected wiring type
                    pickups_list.append({
                        'pickup': 'NECK',
                        'variant': neck_wiring_choice,
                        'coils': {
                            'coil1_slug_north': {
                                'name': 'Coil 1: Slug (North/Upper)',
                                'start': neck_upper_map.get('start'),
                                'finish': neck_upper_map.get('finish'),
                                'phase': neck_north_phase,
                                'resistance_kohm': neck_north_res
                            },
                            'coil2_screw_south': {
                                'name': 'Coil 2: Screw (South/Lower)',
                                'start': neck_lower_map.get('start'),
                                'finish': neck_lower_map.get('finish'),
                                'phase': neck_south_phase,
                                'resistance_kohm': neck_south_res
                            }
                        },
                        'wiring_configuration': {
                            'output': neck_order.get('output', []),
                            'series': neck_order.get('series', []),
                            'ground': neck_order.get('ground', []),
                            'bare_present': bare_present,
                            'rwrp': 'Yes' if neck_north_phase != neck_south_phase else 'No',
                            'total_resistance_kohm': round(neck_total_res, 2) if neck_total_res else None
                        }
                    })

            # Add BRIDGE pickup to the list
            show_bridge = True  # Always show bridge for now
            if show_bridge:
                if both_coil_split:
                    # Coil split mode: determine which magnet pole is upper for BRIDGE
                    # BRIDGE uses opposite pole from NECK
                    neck_upper_is_south = 'Screw' in str(st.session_state.get('neck_north_colors', [''])[0]) if st.session_state.get('neck_north_colors') else False
                    
                    if neck_upper_is_south:
                        # NECK upper is south, so BRIDGE upper must be north (slug coil)
                        coil_name = 'Upper/Slug (North)'
                        coil_map = upper_map
                        coil_res = bridge_north_res
                        coil_phase = bridge_north_phase
                    else:
                        # NECK upper is north, so BRIDGE upper must be south (screw coil)
                        coil_name = 'Upper/Screw (South)'
                        coil_map = lower_map
                        coil_res = bridge_south_res
                        coil_phase = bridge_south_phase
                    
                    bridge_order = _compute_wiring_order(upper_map, lower_map, bridge_wiring_choice, bare_present=bare_present, upper_phase=bridge_north_phase, lower_phase=bridge_south_phase)
                    pickups_list.append({
                        'pickup': 'BRIDGE (coil split - upper coil)',
                        'variant': bridge_wiring_choice,
                        'coils': {
                            'coil_upper': {
                                'name': f'Coil: {coil_name}',
                                'start': coil_map.get('start'),
                                'finish': coil_map.get('finish'),
                                'phase': coil_phase,
                                'resistance_kohm': coil_res
                            }
                        },
                        'wiring_configuration': {
                            'output': bridge_order.get('output', []),
                            'series': [],
                            'ground': bridge_order.get('ground', []),
                            'bare_present': bare_present,
                            'parallel_with': 'NECK (upper coil)',
                            'total_resistance_kohm': round(coil_res, 2) if coil_res else None
                        }
                    })
                else:
                    # Normal mode: BRIDGE with selected wiring type
                    order = _compute_wiring_order(upper_map, lower_map, bridge_wiring_choice, bare_present=bare_present, upper_phase=bridge_north_phase, lower_phase=bridge_south_phase)
                    pickups_list.append({
                        'pickup': 'BRIDGE',
                        'variant': bridge_wiring_choice,
                        'coils': {
                            'coil1_slug_north': {
                                'name': 'Coil 1: Slug (North/Upper)',
                                'start': upper_map.get('start'),
                                'finish': upper_map.get('finish'),
                                'phase': bridge_north_phase,
                                'resistance_kohm': bridge_north_res
                            },
                            'coil2_screw_south': {
                                'name': 'Coil 2: Screw (South/Lower)',
                                'start': lower_map.get('start'),
                                'finish': lower_map.get('finish'),
                                'phase': bridge_south_phase,
                                'resistance_kohm': bridge_south_res
                            }
                        },
                        'wiring_configuration': {
                            'output': order.get('output', []),
                            'series': order.get('series', []),
                            'ground': order.get('ground', []),
                            'bare_present': bare_present,
                            'rwrp': 'Yes' if bridge_north_phase != bridge_south_phase else 'No',
                            'total_resistance_kohm': round(bridge_total_res, 2) if bridge_total_res else None
                        }
                    })
            
            # Calculate combined total resistance when both pickups are present
            # Use series or parallel formula depending on how pickups are connected
            combined_total_res = None
            combined_wiring = None
            if show_neck and show_bridge:
                if neck_total_res and bridge_total_res:
                    neck_res = float(neck_total_res)
                    bridge_res = float(bridge_total_res)
                    if neck_res > 0 and bridge_res > 0:
                        if pickups_connection == 'series':
                            # Series: resistances add
                            combined_total_res = neck_res + bridge_res
                        else:
                            # Parallel: use parallel formula
                            combined_total_res = (neck_res * bridge_res) / (neck_res + bridge_res)

                # Add high-level inter-pickup wiring guidance for BOTH modes (non coil-split)
                if pickups_connection in ('series', 'parallel') and not both_coil_split:
                    neck_hot = neck_order.get('output', []) if neck_order else []
                    bridge_hot = order.get('output', []) if order else []
                    neck_ground_raw = neck_order.get('ground', []) if neck_order else []
                    bridge_ground_raw = order.get('ground', []) if order else []

                    # Keep Bare on the ground bus, but avoid mixing it into the inter-pickup link
                    def _split_ground(gs: list):
                        main = [g for g in gs if g and g != 'Bare']
                        has_bare = any(g == 'Bare' for g in gs)
                        return main, has_bare

                    neck_ground, neck_has_bare = _split_ground(neck_ground_raw)
                    bridge_ground, bridge_has_bare = _split_ground(bridge_ground_raw)

                    if pickups_connection == 'series':
                        # Series between pickups: neck ground -> bridge hot; bridge ground to overall ground
                        combined_wiring = {
                            'mode': 'series',
                            'steps': {
                                'hot_to_output': neck_hot,
                                'link_neck_ground_to_bridge_hot': neck_ground + bridge_hot,
                                'ground': bridge_ground + (['Bare'] if (neck_has_bare or bridge_has_bare) else [])
                            }
                            # Include internal series links for clarity when pickups are forced to series
                            if neck_order.get('series') or order.get('series') else None
                        }
                    else:
                        # Parallel between pickups: both hots together, both grounds together
                        ground_bus = neck_ground + bridge_ground
                        if neck_has_bare or bridge_has_bare:
                            ground_bus.append('Bare')
                        
                        # Check if coils within each pickup are in parallel (both output wires to hot)
                        # This happens when both START and FINISH are in the hot bus (full coil parallel)
                        neck_coil_parallel = len(neck_hot) >= 2
                        bridge_coil_parallel = len(bridge_hot) >= 2
                        
                        if neck_coil_parallel or bridge_coil_parallel:
                            # Full parallel mode: coils in parallel within pickup + pickups in parallel to each other
                            combined_wiring = {
                                'mode': 'parallel_full',
                                'steps': {
                                    'all_coil_outputs_to_hot': neck_hot + bridge_hot,
                                    'all_series_links_to_ground': ground_bus,
                                    'note': 'Full parallel: each coil\'s output (RED + BLACK) to HOT, each coil\'s series link (GREEN + WHITE) to GND, pickups in parallel to each other. Low impedance, high output.',
                                    'pickup_internal_parallel_coils': {
                                        'neck_coil_outputs': neck_hot,
                                        'bridge_coil_outputs': bridge_hot
                                    }
                                }
                            }
                        else:
                            # Standard parallel: pickups in parallel, coils internally series
                            combined_wiring = {
                                'mode': 'parallel',
                                'steps': {
                                    'starts_to_hot': neck_hot + bridge_hot,
                                    'ends_to_ground': ground_bus,
                                    'note': 'Parallel rule: north start + south start -> HOT; north end + south end -> GND (each pickup already series internally)',
                                    'pickup_internal_series_links': {
                                        'neck_series_link': neck_order.get('series', []),
                                        'bridge_series_link': order.get('series', [])
                                    }
                                }
                            }
            
            wiring_json = {
                'pickups': pickups_list,
                'coil_split_mode': both_coil_split,
                'combined_total_resistance_kohm': round(combined_total_res, 2) if combined_total_res else None,
                'combined_wiring': combined_wiring
            }
            
            # Add coil split description only when in coil split mode
            if both_coil_split:
                wiring_json['coil_split_description'] = 'NECK upper coil + BRIDGE upper coil in parallel (opposite poles)'
            
            # HUM-CANCELLING VALIDATION
            st.subheader('🔍 Hum-Cancelling Check')
            
            # Add reference diagram info
            with st.expander('📚 Humbucker Configuration Reference'):
                cols = st.columns(2)
                
                with cols[0]:
                    st.markdown("**Config A (Traditional)**")
                    st.markdown("*NECK* - N-S orientation")
                    # Config A: NECK is always N-S (North on top)
                    try:
                        with open('app/humbuckerNORTH.svg', 'r') as f:
                            svg_content = f.read()
                        st.image(svg_content, width=200)
                    except:
                        st.error("Could not load humbuckerNORTH.svg")
                    
                    st.markdown("*BRIDGE* - S-N orientation")
                    # Config A: BRIDGE is always S-N (South on top)
                    try:
                        with open('app/humbuckerSOUTH.svg', 'r') as f:
                            svg_content = f.read()
                        st.image(svg_content, width=200)
                    except:
                        st.error("Could not load humbuckerSOUTH.svg")
                    st.caption("✅ Opposite magnets + same phase")
                
                with cols[1]:
                    st.markdown("**Config B (Symmetrical)**")
                    st.markdown("*NECK* - N-S orientation")
                    # Config B: NECK is N-S (North on top)
                    try:
                        with open('app/humbuckerNORTH.svg', 'r') as f:
                            svg_content = f.read()
                        st.image(svg_content, width=200)
                    except:
                        st.error("Could not load humbuckerNORTH.svg")
                    
                    st.markdown("*BRIDGE* - N-S orientation")
                    # Config B: BRIDGE is also N-S (North on top)
                    try:
                        with open('app/humbuckerNORTH.svg', 'r') as f:
                            svg_content = f.read()
                        st.image(svg_content, width=200)
                    except:
                        st.error("Could not load humbuckerNORTH.svg")
                    st.caption("✅ Same magnets + opposite phase")
                
                st.markdown("---")
                st.markdown("""
                **Notes:**
                - 🔴 **Red Coil** = North magnet
                - ⚫ **Black Coil** = South magnet
                - Hook-up cable always exits the baseplate below the **south coil**, except when a reversed magnet is ordered
                - **Configuration A (Traditional):** Opposite magnet orientations - most common wiring
                - **Configuration B (Symmetrical):** Same magnet orientations - used with symmetrical neck pickup when hum-cancelling is required between inner or outer coils of both pickups
                """)
            
            def _validate_hum_cancelling():
                """
                Check if pickups are configured for proper hum-cancelling.
                Rules:
                1. Within each pickup: opposite phase between coils = hum-cancelling ✅
                2. Between pickups (when both active): must have opposite polarity AND opposite phase
                """
                issues = []
                warnings = []
                
                # Check NECK pickup internal hum-cancelling
                if neck_north_phase == neck_south_phase:
                    issues.append(f"⚠️ **NECK pickup**: Both coils are {neck_north_phase} phase. This will NOT hum-cancel! One coil should be Normal, the other Reverse.")
                else:
                    warnings.append(f"✅ **NECK pickup**: Coils have opposite phase ({neck_north_phase} vs {neck_south_phase}) — hum-cancelling OK")
                
                # Check BRIDGE pickup internal hum-cancelling
                if bridge_north_phase == bridge_south_phase:
                    issues.append(f"⚠️ **BRIDGE pickup**: Both coils are {bridge_north_phase} phase. This will NOT hum-cancel! One coil should be Normal, the other Reverse.")
                else:
                    warnings.append(f"✅ **BRIDGE pickup**: Coils have opposite phase ({bridge_north_phase} vs {bridge_south_phase}) — hum-cancelling OK")
                
                return issues, warnings
            
            try:
                hum_issues, hum_warnings = _validate_hum_cancelling()
                
                if hum_issues:
                    st.error('**Hum-Cancelling Issues Detected:**')
                    for issue in hum_issues:
                        st.markdown(issue)
                    st.markdown('💡 **Fix:** Swap one coil\'s wiring (START ↔ FINISH) to reverse its phase. Or twist the coil\'s wires to reverse polarity.')
                
                if hum_warnings:
                    for warning in hum_warnings:
                        if '✅' in warning:
                            st.success(warning)
                        else:
                            st.warning(warning)
            
            except Exception as e:
                st.info(f"Could not validate hum-cancelling: {e}")
            
            # Display simplified wiring summary
            st.subheader('📋 Wiring Summary')
            
            # Show pickup configuration in readable format
            for i, pickup in enumerate(pickups_list):
                pickup_name = pickup.get('pickup', f'Pickup {i+1}')
                wiring_config = pickup.get('wiring_configuration', {})
                total_res = wiring_config.get('total_resistance_kohm', 'N/A')
                
                with st.expander(f"**{pickup_name}** - {total_res} kΩ"):
                    st.markdown(f"**Wiring Mode:** {pickup.get('variant', 'N/A')}")
                    
                    # Show coil details
                    coils = pickup.get('coils', {})
                    if isinstance(coils, dict):
                        for coil_key, coil in coils.items():
                            if isinstance(coil, dict):
                                coil_name = coil.get('name', coil_key)
                                start = coil.get('start', 'N/A')
                                finish = coil.get('finish', 'N/A')
                                phase = coil.get('phase', 'N/A')
                                st.markdown(f"- **{coil_name}** ({phase}): {start} (START) → {finish} (FINISH)")
                    
                    # Show wiring order
                    if wiring_config:
                        st.markdown("**Connection:**")
                        if wiring_config.get('output'):
                            st.markdown(f"  - HOT: {', '.join(wiring_config['output'])}")
                        if wiring_config.get('ground'):
                            st.markdown(f"  - GROUND: {', '.join(wiring_config['ground'])}")
                        if wiring_config.get('series'):
                            st.markdown(f"  - SERIES LINK: {', '.join(wiring_config['series'])}")
            
            # Show combined wiring if both pickups
            if combined_wiring:
                st.markdown("---")
                st.markdown(f"**Combined Mode:** {combined_wiring.get('mode', 'N/A').upper()}")
                if combined_total_res:
                    st.markdown(f"**Total Resistance:** {round(combined_total_res, 2)} kΩ")
                
                steps = combined_wiring.get('steps', {})
                if steps.get('note'):
                    st.info(steps['note'])
            
            # Show raw JSON in collapsible section for advanced users
            with st.expander('🔧 Technical Details (JSON)'):
                json_str = json.dumps(wiring_json, indent=2)
                st.code(json_str, language='json')
                st.markdown('**For AI Analysis:** Copy this JSON and ask: "Are these humbuckers correctly configured for hum cancelling?"')
        except Exception as e:
            st.error(f"Error computing wiring order: {e}")


# Quick-rule: apply North-reverse assumption
def _apply_north_reverse_rule():
    # mark north (top) coil as reverse and south (bottom) as normal
    st.session_state['north_reverse_phased'] = True
    # set probe radio answers: North reversed, South normal
    # These strings match the options used in the radio widgets
    st.session_state['n_up_probe'] = 'Laskee (käänteinen)'
    st.session_state['n_lo_probe'] = 'Nousee (normaali)'
    # ensure swap flags are off by default (user can adjust)
    st.session_state['n_up_swap'] = False
    st.session_state['n_lo_swap'] = False

    # recompute analysis using existing color selections and probe->wire choices
    def _none_if_dash(val):
        return None if (val is None or (isinstance(val, str) and val.strip() == '--')) else val

    neck_pair = st.session_state.get('neck_north_colors', [])
    south_pair = st.session_state.get('neck_south_colors', [])
    bridge_north = st.session_state.get('bridge_north_colors', [])
    bridge_south = st.session_state.get('bridge_south_colors', [])

    analysis_neck = analyze_pickup(
        neck_pair,
        south_pair,
        st.session_state.get('n_up_probe'),
        st.session_state.get('n_lo_probe'),
        north_swap=st.session_state.get('n_up_swap'),
        south_swap=st.session_state.get('n_lo_swap'),
        bare=st.session_state.get('bare'),
        north_res_kohm=st.session_state.get('n_up'),
        south_res_kohm=st.session_state.get('n_lo'),
        north_red_wire=_none_if_dash(st.session_state.get('n_up_probe_red_wire')),
        north_black_wire=_none_if_dash(st.session_state.get('n_up_probe_black_wire')),
        south_red_wire=_none_if_dash(st.session_state.get('n_lo_probe_red_wire')),
        south_black_wire=_none_if_dash(st.session_state.get('n_lo_probe_black_wire')),
    )

    analysis_bridge = analyze_pickup(
        bridge_north,
        bridge_south,
        st.session_state.get('b_up_probe'),
        st.session_state.get('b_lo_probe'),
        north_swap=st.session_state.get('b_up_swap'),
        south_swap=st.session_state.get('b_lo_swap'),
        bare=st.session_state.get('bare'),
        north_res_kohm=st.session_state.get('b_up'),
        south_res_kohm=st.session_state.get('b_lo'),
        north_red_wire=_none_if_dash(st.session_state.get('b_up_probe_red_wire')),
        north_black_wire=_none_if_dash(st.session_state.get('b_up_probe_black_wire')),
        south_red_wire=_none_if_dash(st.session_state.get('b_lo_probe_red_wire')),
        south_black_wire=_none_if_dash(st.session_state.get('b_lo_probe_black_wire')),
    )

    st.session_state['analysis'] = {'neck': analysis_neck, 'bridge': analysis_bridge}
    _save_state()
    # stay on the same step but show a short success message
    st.success('Applied North-reverse rule and recomputed analysis.')


# Restart button (outside all expanders)
st.markdown('---')
st.caption('💥 **Made a mistake?** We all do. Even Jimi Hendrix probably mis-wired a pickup once (citation needed).')
if st.button('Restart'):
    # Remove saved backup as well
    try:
        if os.path.exists(BACKUP_PATH):
            os.remove(BACKUP_PATH)
    except Exception:
        pass
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    _safe_rerun()

# Persist current state on each run so changes are saved automatically
try:
    _save_state()
except Exception:
    pass
