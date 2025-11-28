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

st.set_page_config(page_title='Humbucker Wiring Assistant', layout='centered')

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

# Change handlers that auto-collapse the expander only when two colors are selected
def _on_neck_north_changed():
    sel = st.session_state.get('neck_north_colors', [])
    if isinstance(sel, (list, tuple)) and len(sel) == 2:
        st.session_state['exp_neck_north'] = False
        _safe_rerun()

def _on_neck_south_changed():
    sel = st.session_state.get('neck_south_colors', [])
    if isinstance(sel, (list, tuple)) and len(sel) == 2:
        st.session_state['exp_neck_south'] = False
        _safe_rerun()

def _on_bridge_north_changed():
    sel = st.session_state.get('bridge_north_colors', [])
    if isinstance(sel, (list, tuple)) and len(sel) == 2:
        st.session_state['exp_bridge_north'] = False
        _safe_rerun()

def _on_bridge_south_changed():
    sel = st.session_state.get('bridge_south_colors', [])
    if isinstance(sel, (list, tuple)) and len(sel) == 2:
        st.session_state['exp_bridge_south'] = False
        _safe_rerun()

# (Removed swap helper at user's request)

st.title('Humbucker Wiring Assistant — Bare Knuckle')
st.write('A minimal interactive app to map 4-conductor humbuckers (Slug = North, Screw = South).')
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
question = st.sidebar.text_input('Ask about soldering, hum-cancelling, wiring, or diagnostics', '')

# Small health-check for local Ollama / local AI server
def check_local_ai(host: str = None, timeout: float = 1.0) -> dict:
    """Return dict with keys: available (bool), url (str), details (str).

    Tries to query the local Ollama server root endpoint configured via
    OLLAMA_HOST or falls back to http://127.0.0.1:11434.
    """
    # Determine host from env (keeps consistent with Ollama logs)
    env_host = None
    try:
        env_host = os.environ.get('OLLAMA_HOST')
    except Exception:
        env_host = None
    url = (host or env_host or 'http://127.0.0.1:11434').rstrip('/')
    result = {'available': False, 'url': url, 'details': ''}
    # Prefer requests if available, otherwise try urllib
    if requests is None:
        try:
            from urllib.request import urlopen
            from urllib.error import URLError, HTTPError
            try:
                with urlopen(url + '/', timeout=timeout) as r:
                    code = getattr(r, 'status', None) or getattr(r, 'getcode', lambda: None)()
                    result['available'] = True if code and int(code) < 500 else False
                    result['details'] = f'HTTP {code}'
            except HTTPError as e:
                result['details'] = f'HTTP Error: {e.code} {e.reason}'
            except URLError as e:
                result['details'] = f'URL Error: {e.reason}'
            except Exception as e:
                result['details'] = str(e)
        except Exception as e:
            result['details'] = f'No HTTP client available: {e}'
        return result

    try:
        # Query a lightweight endpoint; root serves a small landing page in Ollama
        r = requests.get(url + '/', timeout=timeout)
        result['available'] = r.status_code < 500
        result['details'] = f'Status {r.status_code}'
    except requests.exceptions.RequestException as e:
        result['details'] = str(e)
    except Exception as e:
        result['details'] = str(e)
    return result

# Show local AI connection status in the sidebar (small, non-blocking)
try:
    status = check_local_ai()
    if status.get('available'):
        st.sidebar.success(f"Local AI available — {status.get('url')} ({status.get('details')})")
    else:
        st.sidebar.warning(f"Local AI not reachable — {status.get('url')} ({status.get('details')})")
except Exception as e:
    try:
        st.sidebar.error(f"Local AI status check failed: {e}")
    except Exception:
        pass


# Generic caller that attempts a few common Ollama endpoints to get text output.
def call_local_ai(prompt: str, model: str = 'mistral:7b', timeout: float = 6.0) -> dict:
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
    for a in attempts:
        diag_lines.append(f"- {a.get('url')} -> {a.get('status')} ; body=" + (str(a.get('body'))[:200] if a.get('body') else '<empty>'))
    for m in fallback_msgs:
        diag_lines.append(f"- fallback: {m}")

    return {'ok': False, 'text': '', 'error': '\n'.join(diag_lines)}

# Sidebar: allow opting into direct AI responses from a local model
try:
    use_ai = st.sidebar.checkbox('Use AI responses (experimental)', value=False, key='use_ai_responses')
    ai_model = st.sidebar.text_input('Model name', value=st.session_state.get('ai_model', 'mistral:7b'), key='ai_model')
    st.session_state['ai_model'] = ai_model
except Exception:
    use_ai = False
    ai_model = 'mistral'

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

if st.sidebar.button('Ask'):
    # If user opted into AI responses, send the raw question to the local model
    if st.session_state.get('use_ai_responses'):
        model = st.session_state.get('ai_model', 'mistral')
        try:
            resp = call_local_ai(question, model=model)
            if resp.get('ok'):
                st.sidebar.markdown(resp.get('text') or '_(no text returned)_')
            else:
                # Fallback to a short error then the canned FAQ
                st.sidebar.error(f"AI call failed: {resp.get('error')}")
                answer = _ai_helper_answer(question)
                st.sidebar.markdown(answer)
        except Exception as e:
            st.sidebar.error(f"AI call exception: {e}")
            answer = _ai_helper_answer(question)
            st.sidebar.markdown(answer)
    else:
        answer = _ai_helper_answer(question)
        # show as markdown for readability
        st.sidebar.markdown(answer)

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
    try:
        if value is None:
            return 0
        return options.index(value)
    except Exception:
        return 0
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

with st.expander('Step 1 — Welcome', expanded=(step == 1)):
    st.header('Welcome')
    st.write('Welcome — click the top "Next" to begin wire mapping for your pickups.')

with st.expander('Step 2 — Define wire colors', expanded=(step == 2)):
    st.header('Step 2 — Define wire colors')
    st.write('Choose up to 4 conductor colors for each pickup (and check bare if present).')
    COLOR_OPTIONS = ['Red', 'White', 'Green', 'Black', 'Yellow', 'Blue', 'Bare']
    col1 = st.multiselect('Neck wire colors (ordered)', COLOR_OPTIONS,
                          default=_safe_default_list(COLOR_OPTIONS, st.session_state.get('neck_wire_colors', ['Red', 'White', 'Green', 'Black'])),
                          key='neck_wire_colors')
    col2 = st.multiselect('Bridge wire colors (ordered)', COLOR_OPTIONS,
                          default=_safe_default_list(COLOR_OPTIONS, st.session_state.get('bridge_wire_colors', ['Red', 'White', 'Green', 'Black'])),
                          key='bridge_wire_colors')
    bare = st.checkbox('Bare (ground) present', value=st.session_state.get('bare', False), key='bare')


with st.expander('Step 3 — Polarity (top of pickup)', expanded=(step == 3)):
    st.header('Step 3 — Polarity (top of pickup)')
    st.write('Use a compass over the pickup (top of pickup). Slug = North coil; Screw = South coil.')
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

with st.expander('Step 4 — Measurements', expanded=(step == 4)):
    st.header('Step 4 — Measurements')
    st.write('Enter coil resistances found in Step 5 measurement (kΩ).')
    n_up = st.number_input('Neck — upper coil (kΩ)', min_value=0.0, format='%.2f', value=st.session_state.get('n_up', 0.0), key='n_up')
    n_lo = st.number_input('Neck — lower coil (kΩ)', min_value=0.0, format='%.2f', value=st.session_state.get('n_lo', 0.0), key='n_lo')
    b_up = st.number_input('Bridge — upper coil (kΩ)', min_value=0.0, format='%.2f', value=st.session_state.get('b_up', 0.0), key='b_up')
    b_lo = st.number_input('Bridge — lower coil (kΩ)', min_value=0.0, format='%.2f', value=st.session_state.get('b_lo', 0.0), key='b_lo')
    st.markdown('---')
    st.subheader('Map wires to coils')
    st.write('Select which wire colors belong to the Top/Upper coil and Bottom/Lower coil for each pickup.')
    neck_colors = st.session_state.get('neck_wire_colors', [])
    bridge_colors = st.session_state.get('bridge_wire_colors', [])
    default_neck_top = _safe_default_list(neck_colors, st.session_state.get('neck_north_colors', neck_colors[:2]))
    default_neck_bottom = _safe_default_list(neck_colors, st.session_state.get('neck_south_colors', neck_colors[2:4]))
    default_bridge_top = _safe_default_list(bridge_colors, st.session_state.get('bridge_north_colors', bridge_colors[:2]))
    default_bridge_bottom = _safe_default_list(bridge_colors, st.session_state.get('bridge_south_colors', bridge_colors[2:4]))


    # Neck — Top / Upper selector: hidden by default; use an expander to edit
    cols = st.columns([6, 1])
    cols[0].markdown(_render_color_badges(st.session_state.get('neck_north_colors', [])), unsafe_allow_html=True)
    cols[1].markdown('')
    with st.expander('Edit Neck — Top wire colors', expanded=st.session_state.get('exp_neck_north', False)):
        st.multiselect('', neck_colors, default=default_neck_top, key='neck_north_colors', on_change=_on_neck_north_changed)
    

    # Neck — Bottom / Lower selector: edit via expander
    cols = st.columns([6, 1])
    cols[0].markdown(_render_color_badges(st.session_state.get('neck_south_colors', [])), unsafe_allow_html=True)
    cols[1].markdown('')
    with st.expander('Neck — Bottom wire colors', expanded=st.session_state.get('exp_neck_south', False)):
        st.multiselect(' ', [c for c in neck_colors if c not in st.session_state.get('neck_north_colors', [])], default=default_neck_bottom, key='neck_south_colors', on_change=_on_neck_south_changed)

    # Bridge — Top / Upper selector: edit via expander
    cols = st.columns([6, 1])
    cols[0].markdown(_render_color_badges(st.session_state.get('bridge_north_colors', [])), unsafe_allow_html=True)
    cols[1].markdown('')
    with st.expander('Bridge — Top wire colors', expanded=st.session_state.get('exp_bridge_north', False)):
        st.multiselect('', bridge_colors, default=default_bridge_top, key='bridge_north_colors', on_change=_on_bridge_north_changed)

    # Bridge — Bottom / Lower selector: edit via expander
    cols = st.columns([6, 1])
    cols[0].markdown(_render_color_badges(st.session_state.get('bridge_south_colors', [])), unsafe_allow_html=True)
    cols[1].markdown('')
    with st.expander('Bridge — Bottom wire colors', expanded=st.session_state.get('exp_bridge_south', False)):
        st.multiselect('', [c for c in bridge_colors if c not in st.session_state.get('bridge_north_colors', [])], default=default_bridge_bottom, key='bridge_south_colors', on_change=_on_bridge_south_changed)
    # validate mapping
    mapping_ok = True
    if len(st.session_state.get('neck_north_colors', [])) != 2 or len(st.session_state.get('neck_south_colors', [])) != 2:
        st.warning('Please select exactly 2 colors for each neck coil (top and bottom).')
        mapping_ok = False
    if len(st.session_state.get('bridge_north_colors', [])) != 2 or len(st.session_state.get('bridge_south_colors', [])) != 2:
        st.warning('Please select exactly 2 colors for each bridge coil (top and bottom).')
        mapping_ok = False
    if mapping_ok:
        st.info('Mapping looks good — use the top "Next" button to proceed to Phase checks.')
    else:
        st.info('Please fix the mapping warnings above. Select exactly 2 colors per coil before proceeding.')
with st.expander('Step 5 — Phase checks', expanded=(step == 5)):
    st.header('Step 5 — Phase checks (touch pole piece)')
    # Probe→Wire mapping: let the user indicate which wire each probe contacted
    st.subheader('Probe → Wire mapping')
    st.write(f"Start from NECK-{n_pol['top']} and finish mapping to BRIDGE-{n_pol['bottom']}. Select which wire the RED probe touched and which wire the BLACK probe touched.")
    st.write('For each coil, select which wire the RED probe touched and which wire the BLACK probe touched. Use these to verify phase mapping.')


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
        # show compact badges under the radios for immediate confirmation
        badge_cols = st.columns([1, 3])
        badge_cols[0].markdown('')
        badge_cols[1].markdown(f"Red: {_color_badge_html(st.session_state.get(red_key) or '--')}  &nbsp;&nbsp; Black: {_color_badge_html(st.session_state.get(black_key) or '--')}", unsafe_allow_html=True)
        # Phase check radio directly under this coil's selection
        phase_opts = ['Normal Phase', 'Reverse Phase']
        # default to existing session value if present
        default_idx = 0 if st.session_state.get(phase_key, 'Resistance increase') == 'Resistance increase' else 1
        st.radio(f'{title}: Touch coil with metal. If resistance increased when touched: Phase is normal.', phase_opts, index=default_idx, key=phase_key)

    _coil_probe_row('Neck — Upper coil', neck_top_wires, 'n_up_probe_red_wire', 'n_up_probe_black_wire', 'n_up_probe')
    _coil_probe_row('Neck — Lower coil', neck_bottom_wires, 'n_lo_probe_red_wire', 'n_lo_probe_black_wire', 'n_lo_probe')
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

        st.markdown('---')
        st.subheader('Inferred mapping (preview)')
        st.markdown('**Neck pickup**')
        st.write(f"NORTH Start HOT: {neck_upper_map.get('start')}")
        st.write(f"NORTH End SERIES: {neck_upper_map.get('finish')}")
        st.write(f"SOUTH End SERIES: {neck_lower_map.get('finish')}")
        st.write(f"SOUTH Start GROUND: {neck_lower_map.get('start')}")
        

        st.markdown('**Bridge pickup**')
        st.write(f"NORTH Start HOT: {bridge_upper_map.get('start')}")
        st.write(f"NORTH End SERIES: {bridge_upper_map.get('finish')}")
        st.write(f"SOUTH End SERIES: {bridge_lower_map.get('finish')}")
        st.write(f"SOUTH Start : {bridge_lower_map.get('start')}")
        
    except Exception:
        # best-effort preview; ignore errors
        pass

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
        st.session_state['step'] = 6
        _safe_rerun()

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


# Step 6: Show analysis
def _compute_wiring_order(upper_map: dict, lower_map: dict, wiring_type: str, bare_present: bool = False) -> dict:
    """Compute wiring order for given wiring_type.

    upper_map / lower_map are expected to have keys 'start' and 'finish' (wire color names).
    wiring_type: 'series' | 'parallel' | 'slug_only' | 'screw_only'

    Returns a dict with keys: 'output' (list), 'series' (list, only for series), 'ground' (list), 'notes' (str|None).
    """
    u_start = upper_map.get('start')
    u_finish = upper_map.get('finish')
    l_start = lower_map.get('start')
    l_finish = lower_map.get('finish')

    order = {'output': [], 'series': [], 'ground': [], 'notes': None}

    if wiring_type == 'series':
        # Typical series humbucker wiring: North START -> output (hot), North END + South END -> series link, South START -> ground
        if u_start:
            order['output'] = [u_start]
        order['series'] = [w for w in (u_finish, l_finish) if w]
        order['ground'] = [w for w in ([l_start] + (['Bare'] if bare_present else [])) if w]

    elif wiring_type == 'parallel':
        # Parallel humbucking: tie the two coil starts to output, tie the two finishes to ground (plus bare)
        order['output'] = [w for w in (u_start, l_start) if w]
        order['ground'] = [w for w in (u_finish, l_finish) if w]
        if bare_present:
            order['ground'].append('Bare')
        order['notes'] = 'Parallel humbucking: ensure coils are in-phase before paralleling; use insulating joins as needed.'

    elif wiring_type == 'slug_only':
        # Use only the slug coil (upper coil in this app's mapping).
        # User expectation: Red -> output; Black/Green/White (+ Bare) -> ground when present.
        present = {v for v in (u_start, u_finish, l_start, l_finish) if v}
        # Preferred single-hot colour for slug-only
        if 'Red' in present:
            order['output'] = ['Red']
        else:
            # fallback to Upper start/finish if Red not present
            if u_start:
                order['output'].append(u_start)
            if u_finish and u_finish not in order['output']:
                order['output'].append(u_finish)

        # Grounds: prefer Black, then Green, White, and Bare (if present)
        grounds = []
        for g in ('Black', 'Green', 'White'):
            if g in present:
                grounds.append(g)
        if bare_present and 'Bare' not in grounds:
            grounds.append('Bare')
        # fallback: if still empty, use any available other upper coil wire
        if not grounds:
            for cand in (u_finish, u_start):
                if cand and cand not in grounds:
                    grounds.append(cand)
        order['ground'] = grounds
        order['notes'] = 'Slug-only: use the slug (upper) coil. Typical mapping: Red → output; Black/Green/White (and Bare) → ground.'

    elif wiring_type == 'screw_only':
        # Use only the screw coil (bottom/lower coil in this app's mapping)
        # Many users expect screw-only wiring where Red, Green and White are tied to output and Black (and Bare) go to ground.
        # We'll prefer that canonical mapping when those colour names are present; otherwise fall back to the lower coil's start as output.
        present = {v for v in (u_start, u_finish, l_start, l_finish) if v}
        # Preferred output colours for screw-only (ordered)
        preferred_outputs = [c for c in ('Red', 'Green', 'White') if c in present]
        if preferred_outputs:
            order['output'] = preferred_outputs
        else:
            # fallback: use lower coil start/finish
            if l_start:
                order['output'].append(l_start)
            if l_finish and l_finish not in order['output']:
                order['output'].append(l_finish)

        # Ground should include Black and Bare if present; otherwise use other remaining lower-coil wire
        grounds = []
        if 'Black' in present:
            grounds.append('Black')
        if bare_present:
            grounds.append('Bare')
        # if nothing matched, fall back to lower finish/start
        if not grounds:
            for cand in (l_finish, l_start):
                if cand and cand not in grounds:
                    grounds.append(cand)
        order['ground'] = grounds
        order['notes'] = 'Screw-only: use the screw (lower) coil. Typical wiring ties Red, Green and White to output and Black/Bare to ground if present.'

    else:
        order['notes'] = 'Unknown wiring variant requested.'

    return order

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
                # vertical offset for polarity text (Start/End) relative to the ball radius
                # increase this to move the text higher above the ball
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
                    # short stub from left edge to the left anchor so the overlay wires appear connected to the pickup
                    parts.append(f'<line x1="0" y1="{y}" x2="{left_x}" y2="{y}" stroke="{line_color}" stroke-width="1" stroke-opacity="0.75" />')
                    parts.append(f'<line x1="{left_x}" y1="{y}" x2="{line_end}" y2="{y}" stroke="{line_color}" stroke-width="1" stroke-opacity="0.75" />')
                    circle_x = line_end + r + 6
                    polarity_word = 'Start' if 'start' in labels[i].lower() else 'End'
                    pol_text_fill = '#ffffff' if f.lower() not in ('#ffffff', '#ffbf00') else '#111111'
                    # small polarity labels removed (keep descriptive labels on the right)
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
                    # shorten series connector to avoid overlapping descriptive labels
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
if st.session_state['step'] == 6:
    st.header('Analysis & Wiring Guidance')
    analysis = st.session_state.get('analysis', {})
    neck = analysis.get('neck')
    bridge = analysis.get('bridge')
    st.subheader('Neck pickup')
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

        # Helper to map start/finish from which multimeter lead was on which wire
        def _map_start_finish_from_probes(red_wire, black_wire, probe_choice, swap_flag, fallback_map):
            r = red_wire
            b = black_wire
            # If both probe-wire names are present and a probe reading exists, use the user's rule:
            if r and b and probe_choice:
                if _probe_is_reverse(probe_choice):
                    # reverse: negative lead wire (black probe) is Start, positive lead (red probe) is Finish
                    start, finish = b, r
                else:
                    # normal: positive lead wire (red probe) is Start, negative lead is Finish
                    start, finish = r, b
            else:
                # fall back to previous inference
                start = fallback_map.get('start')
                finish = fallback_map.get('finish')

            if swap_flag:
                start, finish = finish, start

            return start, finish

        # Neck upper (north) mapping
        n_up_red = _none_if_dash(st.session_state.get('n_up_probe_red_wire'))
        n_up_black = _none_if_dash(st.session_state.get('n_up_probe_black_wire'))
        north_start, north_finish = _map_start_finish_from_probes(
            n_up_red,
            n_up_black,
            st.session_state.get('n_up_probe'),
            st.session_state.get('n_up_swap', False),
            neck_upper_map
        )

        # Neck lower (south) mapping
        n_lo_red = _none_if_dash(st.session_state.get('n_lo_probe_red_wire'))
        n_lo_black = _none_if_dash(st.session_state.get('n_lo_probe_black_wire'))
        south_start, south_finish = _map_start_finish_from_probes(
            n_lo_red,
            n_lo_black,
            st.session_state.get('n_lo_probe'),
            st.session_state.get('n_lo_swap', False),
            neck_lower_map
        )

        # Mapping: North START == HOT, North END == Series, South END == SERIES, South START == GROUND
        hot = north_start or '<unknown>'
        series_link = [s for s in ([north_finish, south_finish]) if s]
        ground = [g for g in ([south_start, 'Bare'] if st.session_state.get('bare') else [south_start]) if g]

        st.markdown('**Suggested wiring (Neck)**')
        st.write(f"{hot}-HOT -> SWITCH: ")
        if series_link:
            st.write(f"- Series link (solder together and insulate): {', '.join(series_link)}")
        else:
            st.write('- Series link: <none>')
        if ground:
            st.write(f"- Ground : {', '.join(ground)}")
        else:
            st.write('- Ground: <none>')

        # Small illustrative SVG showing HOT (red), Series connector, and Ground (black)
        try:
            hot_col = COLOR_HEX.get(hot, '#d62728') if isinstance(hot, str) else '#d62728'
            # pick series colors (use first two in series_link or defaults)
            s1 = series_link[0] if series_link and len(series_link) > 0 else 'White'
            s2 = series_link[1] if series_link and len(series_link) > 1 else 'Green'
            s1_col = COLOR_HEX.get(s1, '#ffffff')
            s2_col = COLOR_HEX.get(s2, '#2ca02c')
            ground_col = '#111111'
            wiring_svg = f'''<div style="width:320px;">
<svg viewBox="0 0 320 140" xmlns="http://www.w3.org/2000/svg" width="320" height="140">
  <!-- HOT line to switch -->
  <line x1="10" y1="30" x2="220" y2="30" stroke="{hot_col}" stroke-width="8" stroke-linecap="round" />
  <circle cx="230" cy="30" r="12" fill="{hot_col}" stroke="#222" />
  <text x="250" y="34" font-family="sans-serif" font-size="14" fill="#ffffff">HOT → SWITCH</text>

  <!-- Series link: two coloured balls and short vertical connector -->
  <line x1="140" y1="50" x2="140" y2="95" stroke="#ffffff" stroke-width="3" stroke-linecap="round" />
  <circle cx="140" cy="50" r="12" fill="{s2_col}" stroke="#222" />
  <circle cx="140" cy="95" r="12" fill="{s1_col}" stroke="#222" />
  <text x="80" y="72" font-family="sans-serif" font-size="13" fill="#ffffff">Series</text>

  <!-- Ground (black) line from lower series ball down-left -->
  <line x1="140" y1="95" x2="60" y2="120" stroke="{ground_col}" stroke-width="6" stroke-linecap="round" />
  <circle cx="52" cy="120" r="8" fill="{ground_col}" stroke="#222" />
  <text x="62" y="124" font-family="sans-serif" font-size="13" fill="#ffffff">Ground</text>
</svg>
</div>'''
            components.html(wiring_svg, height=160)
        except Exception:
            pass
        st.markdown('**Neck — Step-by-step**')
        st.write('1. Solder the HOT wire to SWITCH.')
        if series_link:
            st.write('2. Solder the two series-link wires together to the switch. (This forms the coil series). Insulate this join with heatshrink or tape unless it is the output.')
        st.write('3. Solder the GROUND wire and BARE to the pot.')
        st.markdown('---')
    except Exception:
        pass

    st.subheader('Bridge pickup')
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

    # Show explicit wiring suggestion for the bridge based on analysis result
    try:
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

        # Bridge: auto-map Start/Finish from probes using same rules as neck
        b_up_red = _none_if_dash(st.session_state.get('b_up_probe_red_wire'))
        b_up_black = _none_if_dash(st.session_state.get('b_up_probe_black_wire'))
        b_north_start, b_north_finish = _map_start_finish_from_probes(
            b_up_red,
            b_up_black,
            st.session_state.get('b_up_probe'),
            st.session_state.get('b_up_swap', False),
            bridge_upper_map
        )

        b_lo_red = _none_if_dash(st.session_state.get('b_lo_probe_red_wire'))
        b_lo_black = _none_if_dash(st.session_state.get('b_lo_probe_black_wire'))
        b_south_start, b_south_finish = _map_start_finish_from_probes(
            b_lo_red,
            b_lo_black,
            st.session_state.get('b_lo_probe'),
            st.session_state.get('b_lo_swap', False),
            bridge_lower_map
        )

        # Mapping: North START == HOT, North END == Series, South START == GROUND, South END == SERIES
        hot = b_north_start or '<unknown>'
        series_link = [s for s in ([b_north_finish, b_south_finish]) if s]
        ground = [g for g in ([b_south_start, 'Bare'] if st.session_state.get('bare') else [b_south_start]) if g]

        st.markdown('**Suggested wiring (Bridge)**')
        st.write(f"{hot}-HOT -> SWITCH: ")
        if series_link:
            st.write(f"- Series link (solder together and insulate): {', '.join(series_link)}")
        else:
            st.write('- Series link: <none>')
        if ground:
            st.write(f"- Ground (pot back): {', '.join(ground)}")
        else:
            st.write('- Ground: <none>')

        st.markdown('**Bridge — Step-by-step**')
        st.write('1. Solder the HOT wire to SWITCH.')
        if series_link:
            st.write('2. Solder the two series-link wires together (this forms the coil join). Insulate this join with heatshrink or tape unless it is the output.')
        st.write('3. Tie the ground wires (and bare) to the pot.')
        st.markdown('---')
    except Exception:
        pass

    # New UI: Wiring order selector (Series / Parallel / Slug only / Screw only)
    try:
        st.subheader('Generate wiring order for alternate configurations')
        wiring_choice = st.selectbox('Choose wiring variant', ['series', 'parallel', 'slug_only', 'screw_only'], index=0)
        bare_present = bool(st.session_state.get('bare', False))

        # recompute maps for this pickup (reuse previously-defined helpers)
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

        if st.button('Compute wiring order'):
            order = _compute_wiring_order(upper_map, lower_map, wiring_choice, bare_present=bare_present)
            st.markdown(f"**Wiring variant:** {wiring_choice.replace('_', ' ').title()}")
            if 'series' in order:
                st.write(f"Hot (to switch): {', '.join(order.get('output', [])) or '<unknown>'}")
                st.write(f"Series link (join together): {', '.join(order.get('series', [])) or '<none>'}")
                st.write(f"Grounds: {', '.join(order.get('ground', [])) or '<unknown>'}")
            else:
                st.write(f"Output wires (to output/switch): {', '.join(order.get('output', [])) or '<unknown>'}")
                st.write(f"Ground wires: {', '.join(order.get('ground', [])) or '<unknown>'}")
            if order.get('notes'):
                st.info(order.get('notes'))

            # Render a small SVG visual showing which wires are output (hot) and which are ground.
            try:
                COLOR_HEX = {
                    'Red': '#d62728',
                    'White': '#ffffff',
                    'Green': '#2ca02c',
                    'Black': '#111111',
                    'Yellow': '#ffbf00',
                    'Blue': '#1f77b4',
                    'Bare': '#888888'
                }

                # Build a unique ordered list of wires present in the pickup mapping
                wire_candidates = [upper_map.get('start'), upper_map.get('finish'), lower_map.get('start'), lower_map.get('finish')]
                wires = []
                for w in wire_candidates:
                    if w and w not in wires:
                        wires.append(w)

                # If we have no explicit wire names, fallback to showing known output/ground lists
                if not wires:
                    wires = list(dict.fromkeys((order.get('output', []) + order.get('ground', []))))

                # Layout
                width = 520
                height = 160
                margin_x = 40
                y = 60
                n = max(1, len(wires))
                spacing = (width - 2 * margin_x) / max(1, n - 1) if n > 1 else 0

                circles_svg = ''
                labels_svg = ''
                out_lines = ''
                ground_lines = ''

                for i, w in enumerate(wires):
                    x = margin_x + i * spacing
                    fill = COLOR_HEX.get(w, '#cccccc')
                    is_output = w in order.get('output', [])
                    is_ground = w in order.get('ground', [])
                    stroke = '#222222' if not is_output else '#ffd700'
                    stroke_w = 3 if is_output else 1

                    circles_svg += f'<circle cx="{x}" cy="{y}" r="14" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}" />'
                    labels_svg += f'<text x="{x + 18}" y="{y + 6}" font-family="sans-serif" font-size="13" fill="#ffffff">{w}</text>'

                    # Draw connector for output wires to a central output bus on the right
                    if is_output:
                        out_x = width - 80
                        out_lines += f'<line x1="{x + 14}" y1="{y}" x2="{out_x}" y2="{y}" stroke="#ffd700" stroke-width="3" stroke-linecap="round" />'
                    # Ground wires: draw a slanted line down-left to a ground icon
                    if is_ground:
                        gx = 40
                        gy = height - 20
                        ground_lines += f'<line x1="{x - 6}" y1="{y + 14}" x2="{gx}" y2="{gy}" stroke="#111111" stroke-width="4" stroke-linecap="round" />'

                # Output bus and label
                out_bus = f'<rect x="{width - 100}" y="{y - 12}" width="16" height="24" fill="#ffd700" stroke="#222" />'
                out_label = f'<text x="{width - 72}" y="{y + 6}" font-family="sans-serif" font-size="13" fill="#ffffff">Output</text>'

                # Ground icon
                ground_icon = f'<circle cx="40" cy="{height - 20}" r="10" fill="#111111" stroke="#222" /> <text x="56" y="{height - 16}" font-family="sans-serif" font-size="13" fill="#ffffff">Ground</text>'

                # UI controls for visual styling: allow user to pick colors and wire width
                try:
                    marker_outline_color = st.color_picker('Marker outline color', '#222222', key='wiring_marker_outline')
                except Exception:
                    marker_outline_color = '#222222'
                try:
                    output_color = st.color_picker('Output highlight color', '#ffd700', key='wiring_output_color')
                except Exception:
                    output_color = '#ffd700'
                try:
                    wire_color = st.color_picker('Wire/connector color', '#ffffff', key='wiring_wire_color')
                except Exception:
                    wire_color = '#ffffff'
                try:
                    ground_color = st.color_picker('Ground marker color', '#111111', key='wiring_ground_color')
                except Exception:
                    ground_color = '#111111'
                try:
                    wire_width = int(st.slider('Wire stroke width', min_value=1, max_value=8, value=3, key='wiring_wire_width'))
                except Exception:
                    wire_width = 3

                # Prefer overlaying these markers on the actual pickup SVG if present
                try:
                    # choose bridge image according to user's image choice
                    bridge_choice = st.session_state.get('bridge_img_choice', 'north')
                    north_svg = _find_candidate('humbuckerNORTH')
                    south_svg = _find_candidate('humbuckerSOUTH')
                    pick_path = north_svg if bridge_choice == 'north' else south_svg
                    if pick_path and os.path.exists(pick_path) and pick_path.lower().endswith('.svg'):
                        with open(pick_path, 'r', encoding='utf-8') as f:
                            base_svg = f.read()

                        # Build overlay that uses the same layout as the sidebar overlay
                        # Values and positions copied from colour_svg_overlay above so markers align
                        # r: radius of the coloured ball markers
                        r = 12
                        # left_x: x coordinate where the left stub meets the pickup-art edge
                        left_x = 18
                        # default_circle_x: nominal x coordinate where the coloured balls would be placed
                        default_circle_x = 140
                        # line_fraction: fraction of the distance between left_x and default circle where we stop the stub
                        line_fraction = 0.6
                        # y coordinates for the four markers. Order corresponds to the `vals` list below.
                        # Tune these values if your pickup SVG artwork requires vertical adjustments.
                        y_a1 = 36   # North Start (upper coil start)
                        y_a2 = 76   # North End (upper coil end)
                        y_b1 = 194  # South Start (lower coil start)
                        y_b2 = 156  # South End (lower coil end)
                        y_positions = [y_a1, y_a2, y_b1, y_b2]

                        # Use canonical coil ordering: Coil1 Start, Coil1 End, Coil2 Start, Coil2 End
                        vals = [upper_map.get('start'), upper_map.get('finish'), lower_map.get('start'), lower_map.get('finish')]
                        fills = [COLOR_HEX.get(v, '#cccccc') if v else '#cccccc' for v in vals]

                        # compute circle positions
                        # line_end_full: ideal x where stub meets circle center if drawn fully
                        line_end_full = default_circle_x - r - 6
                        # line_end: actual x where the horizontal stub stops (a fraction of the full distance)
                        line_end = left_x + int((line_end_full - left_x) * line_fraction)
                        # circle_x: x coordinate for the centre of marker circles
                        circle_x = line_end + r + 6
                        # Note: all circles share the same x position here (matches sidebar overlay behaviour)

                        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 220" preserveAspectRatio="xMinYMin meet" width="320" height="220">']
                        # draw connector stubs and coloured balls, store positions by wire name
                        pos_by_wire = {}
                        for i, (v, fcol, y) in enumerate(zip(vals, fills, y_positions)):
                            # Choose a contrasting line colour for white/yellow/black markers
                            try:
                                fl = fcol.lower()
                                if fl in ('#ffffff', '#ffbf00'):
                                    line_color = '#cccccc'
                                elif fl in ('#111111', '#000000'):
                                    line_color = '#000000'
                                else:
                                    line_color = fcol
                            except Exception:
                                line_color = '#cccccc'

                            # Draw the left stub that visually connects the pickup art to the overlay
                            # Use the chosen wire color and width for stubs
                            parts.append(f'<line x1="0" y1="{y}" x2="{left_x}" y2="{y}" stroke="{wire_color}" stroke-width="{wire_width}" stroke-opacity="0.75" />')
                            parts.append(f'<line x1="{left_x}" y1="{y}" x2="{line_end}" y2="{y}" stroke="{wire_color}" stroke-width="{wire_width}" stroke-opacity="0.75" />')

                            # Draw the coloured ball marker at (circle_x, y)
                            # Marker outline uses the chosen outline color
                            parts.append(f'<circle cx="{circle_x}" cy="{y}" r="{r}" fill="{fcol}" stroke="{marker_outline_color}" stroke-width="1" />')

                            # Text on top of ball: single-character identifier (first char of wire name) for quick read
                            text_fill = '#111111' if fcol.lower() in ('#ffffff', '#ffbf00') else '#ffffff'
                            parts.append(f'<text x="{circle_x}" y="{y}" text-anchor="middle" dominant-baseline="middle" font-family="sans-serif" font-size="12" fill="{text_fill}">{(v[0] if v else "?")}</text>')

                            # Detailed label to the right: use the app's coil naming (North/South Start/End)
                            pos_labels = ['North Start', 'North End', 'South Start', 'South End']
                            pos_label = pos_labels[i] if i < len(pos_labels) else f'Coil{i+1}'
                            parts.append(f'<text x="{circle_x + r + 10}" y="{y+4}" font-family="sans-serif" font-size="12" fill="#ffffff">{pos_label}: {(v or "<unknown>")}</text>')

                            # Record known positions for later connector drawing (series, output, ground)
                            if v:
                                pos_by_wire[v] = (circle_x, y)

                        # Draw series connectors (vertical) between the two middle balls if present in order
                        # `order['series']` should list the two wires that form the series join (north_end, south_end).
                        try:
                            for i in range(len(order.get('series', [])) - 1):
                                a = order['series'][i]
                                b = order['series'][i+1]
                                pa = pos_by_wire.get(a)
                                pb = pos_by_wire.get(b)
                                if pa and pb:
                                            # Series join uses the selected wire color and width
                                            parts.append(f'<line x1="{pa[0]}" y1="{pa[1]}" x2="{pb[0]}" y2="{pb[1]}" stroke="{wire_color}" stroke-width="{max(2, wire_width)}" stroke-linecap="round" />')
                        except Exception:
                            pass

                        # Highlight output wires: draw an Output box with chosen color and connect output markers to it
                        out_bus_x = 220
                        out_bus_y = 60
                        parts.append(f'<rect x="{out_bus_x}" y="{out_bus_y - 12}" width="16" height="24" fill="{output_color}" stroke="{marker_outline_color}" />')
                        # choose contrasting text color for output label
                        out_text_fill = '#111111' if output_color.lower() in ('#ffffff', '#ffbf00', '#ffff00') else '#ffffff'
                        parts.append(f'<text x="{out_bus_x + 28}" y="{out_bus_y + 6}" font-family="sans-serif" font-size="12" fill="{out_text_fill}">Output</text>')
                        for w in order.get('output', []):
                            p = pos_by_wire.get(w)
                            if p:
                                # Line from marker to output box uses output_color
                                parts.append(f'<line x1="{p[0] + r}" y1="{p[1]}" x2="{out_bus_x}" y2="{out_bus_y}" stroke="{output_color}" stroke-width="{wire_width}" stroke-linecap="round" />')
                                # Outline the marker to highlight it as an output
                                parts.append(f'<circle cx="{p[0]}" cy="{p[1]}" r="{r + 4}" fill="none" stroke="{output_color}" stroke-width="3" />')

                        # Ground icon and connectors
                        # Use the selected ground_color for the icon fill and connectors
                        ground_x = 220
                        ground_y = 180
                        g_fill = ground_color
                        parts.append(f'<circle cx="{ground_x}" cy="{ground_y}" r="10" fill="{g_fill}" stroke="{marker_outline_color}" stroke-width="3"/>')
                        # Use white text if the chosen ground color is dark-ish; otherwise use dark text.
                        text_fill = '#ffffff' if g_fill.lower() not in ('#ffffff', '#ffbf00', '#ffff00') else '#111111'
                        parts.append(f'<text x="{ground_x + 18}" y="{ground_y + 4}" font-family="sans-serif" font-size="12" fill="{text_fill}">Ground</text>')
                        for w in order.get('ground', []):
                            p = pos_by_wire.get(w)
                            if p:
                                # Connector from marker down-left to the ground icon; use ground_color for stroke
                                parts.append(f'<line x1="{p[0] - 6}" y1="{p[1] + 14}" x2="{ground_x}" y2="{ground_y}" stroke="{g_fill}" stroke-width="{wire_width}" stroke-linecap="round" />')

                        parts.append('</svg>')
                        overlay_html = '\n'.join(parts)

                        html = f"""
                        <div style="position:relative; width:100%; max-width:720px;">
                          <div style="position:relative; z-index:1;">{base_svg}</div>
                          <div style="position:absolute; right:8px; top:8px; z-index:2; pointer-events:none;">{overlay_html}</div>
                        </div>
                        """
                        components.html(html, height=260)
                    else:
                        # fallback to the compact visualization if pickup SVG not found
                        svg_html = f'''<div style="width:100%; max-width:640px;">
<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  {circles_svg}
  {labels_svg}
  {out_lines}
  {ground_lines}
  {out_bus}
  {out_label}
  {ground_icon}
</svg>
</div>'''
                        components.html(svg_html, height=height + 20)
                except Exception as e:
                    st.error(f"Could not render wiring visual on pickup SVG: {e}")
            except Exception as e:
                st.error(f"Could not render wiring visual: {e}")
    except Exception:
        pass

    # Polarity diagnostics and one-click fix
    try:
        st.subheader('Electrical polarity check')
        # Compute electrical polarity for each coil using the helper
        neck_upper_pol = compute_electrical_polarity_from_probe(
            st.session_state.get('neck_north_colors', []),
            _none_if_dash(st.session_state.get('n_up_probe_red_wire')),
            _none_if_dash(st.session_state.get('n_up_probe_black_wire')),
            st.session_state.get('n_up_probe'),
            st.session_state.get('n_up_swap', False)
        )
        neck_lower_pol = compute_electrical_polarity_from_probe(
            st.session_state.get('neck_south_colors', []),
            _none_if_dash(st.session_state.get('n_lo_probe_red_wire')),
            _none_if_dash(st.session_state.get('n_lo_probe_black_wire')),
            st.session_state.get('n_lo_probe'),
            st.session_state.get('n_lo_swap', False)
        )
        bridge_upper_pol = compute_electrical_polarity_from_probe(
            st.session_state.get('bridge_north_colors', []),
            _none_if_dash(st.session_state.get('b_up_probe_red_wire')),
            _none_if_dash(st.session_state.get('b_up_probe_black_wire')),
            st.session_state.get('b_up_probe'),
            st.session_state.get('b_up_swap', False)
        )
        bridge_lower_pol = compute_electrical_polarity_from_probe(
            st.session_state.get('bridge_south_colors', []),
            _none_if_dash(st.session_state.get('b_lo_probe_red_wire')),
            _none_if_dash(st.session_state.get('b_lo_probe_black_wire')),
            st.session_state.get('b_lo_probe'),
            st.session_state.get('b_lo_swap', False)
        )

        cols = st.columns(2)
        cols[0].markdown('**Neck polarity**')
        cols[0].write(f"Upper positive: {neck_upper_pol.get('positive_wire')}, start={neck_upper_pol.get('start')} ({neck_upper_pol.get('start_sign')}), finish={neck_upper_pol.get('finish')} ({neck_upper_pol.get('finish_sign')})")
        cols[0].write(f"Lower positive: {neck_lower_pol.get('positive_wire')}, start={neck_lower_pol.get('start')} ({neck_lower_pol.get('start_sign')}), finish={neck_lower_pol.get('finish')} ({neck_lower_pol.get('finish_sign')})")

        cols[1].markdown('**Bridge polarity**')
        cols[1].write(f"Upper positive: {bridge_upper_pol.get('positive_wire')}, start={bridge_upper_pol.get('start')} ({bridge_upper_pol.get('start_sign')}), finish={bridge_upper_pol.get('finish')} ({bridge_upper_pol.get('finish_sign')})")
        cols[1].write(f"Lower positive: {bridge_lower_pol.get('positive_wire')}, start={bridge_lower_pol.get('start')} ({bridge_lower_pol.get('start_sign')}), finish={bridge_lower_pol.get('finish')} ({bridge_lower_pol.get('finish_sign')})")

        def _apply_polarity_fix():
            # Decide whether to flip swap flags so the app mapping matches expected HOT/Series/Ground mapping.
            # For Neck: expectation is North START -> HOT (i.e., north_start should be the positive wire)
            changed = False
            # neck upper
            if neck_upper_pol.get('positive_wire') and neck_upper_pol.get('start') and neck_upper_pol.get('positive_wire') != neck_upper_pol.get('start'):
                # swap to make start equal to positive_wire
                st.session_state['n_up_swap'] = not st.session_state.get('n_up_swap', False)
                changed = True
            # neck lower: expectation is South START -> Series (but ground is south finish), we ensure south_start is correct polarity
            if neck_lower_pol.get('positive_wire') and neck_lower_pol.get('start') and neck_lower_pol.get('positive_wire') != neck_lower_pol.get('start'):
                st.session_state['n_lo_swap'] = not st.session_state.get('n_lo_swap', False)
                changed = True
            # bridge upper
            if bridge_upper_pol.get('positive_wire') and bridge_upper_pol.get('start') and bridge_upper_pol.get('positive_wire') != bridge_upper_pol.get('start'):
                st.session_state['b_up_swap'] = not st.session_state.get('b_up_swap', False)
                changed = True
            # bridge lower
            if bridge_lower_pol.get('positive_wire') and bridge_lower_pol.get('start') and bridge_lower_pol.get('positive_wire') != bridge_lower_pol.get('start'):
                st.session_state['b_lo_swap'] = not st.session_state.get('b_lo_swap', False)
                changed = True

            if changed:
                # recompute analysis
                neck_pair = st.session_state.get('neck_north_colors', [])
                south_pair = st.session_state.get('neck_south_colors', [])
                bridge_north = st.session_state.get('bridge_north_colors', [])
                bridge_south = st.session_state.get('bridge_south_colors', [])
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
                st.success('Applied polarity fixes and recomputed analysis.')
                _safe_rerun()
            else:
                st.info('No polarity fixes needed.')

        st.button('Apply polarity fix', on_click=_apply_polarity_fix)
    except Exception:
        pass

    # Wiring order helper moved earlier in the file to ensure it's defined before use.

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
