import streamlit as st
import streamlit.components.v1 as components

def _ensure_keys(prefix: str):
    left_key = f"{prefix}_left"
    right_key = f"{prefix}_right"
    if left_key not in st.session_state:
        # default: left = S, right = N
        st.session_state[left_key] = 'S'
    if right_key not in st.session_state:
        st.session_state[right_key] = 'N'
    return left_key, right_key


def render_humbucker(prefix: str, title: str = None, width: int = 320, height: int = 140, show_controls: bool = True):
    """Render a small humbucker-like visual with two coil shapes and S/N labels.

    The component stores its state in `st.session_state` keys:
      - `{prefix}_left`  (value 'S' or 'N')
      - `{prefix}_right` (value 'S' or 'N')

    A button labeled 'Käännä' swaps the two labels (visually flipping the coils).
    Returns a tuple (left_label, right_label).
    """
    left_key, right_key = _ensure_keys(prefix)

    left = st.session_state[left_key]
    right = st.session_state[right_key]

    # Container with title and svg visual
    cont = st.container()
    if title:
        cont.markdown(f"**{title}**")

    # Define actions as callbacks so we can place the visible buttons
    # below the SVG while ensuring state updates happen before the next
    # rerun builds the SVG (Streamlit runs callbacks before the script
    # reruns and re-renders).
    def _flip_cb(pk=prefix, lk=left_key, rk=right_key):
        st.session_state[lk], st.session_state[rk] = st.session_state[rk], st.session_state[lk]

    def _save_cb(pk=prefix, lk=left_key, rk=right_key):
        if pk == 'neck':
            st.session_state['upper_polarity'] = st.session_state[lk]
            st.session_state['lower_polarity'] = st.session_state[rk]
        elif pk == 'bridge':
            st.session_state['bridge_upper_polarity'] = st.session_state[lk]
            st.session_state['bridge_lower_polarity'] = st.session_state[rk]
        else:
            st.session_state[f"{pk}_upper"] = st.session_state[lk]
            st.session_state[f"{pk}_lower"] = st.session_state[rk]
        # Provide a small success flag in session state; show message below
        st.session_state[f"{pk}_saved"] = True

    # Build SVG from the current session state and render it
    left = st.session_state[left_key]
    right = st.session_state[right_key]
    svg, svg_h = _build_svg(left, right, width=width, height=height)
    components.html(svg, height=int(svg_h) + 16, scrolling=False)

    # Optionally render action buttons below the SVG, centered
    if show_controls:
        btn_cols = cont.columns([1, 3, 1])
        with btn_cols[1]:
            st.button("Käännä", key=f"{prefix}_flip_btn", on_click=_flip_cb)
            st.button("Tallenna", key=f"{prefix}_save_btn", on_click=_save_cb)

        # Show current polarity as text for accessibility (Finnish labels)
        cont.write(f"Yläkela: **{st.session_state[left_key]}**, Alakela: **{st.session_state[right_key]}**")

        # Show a small confirmation message if recently saved
        if st.session_state.get(f"{prefix}_saved"):
            cont.success("Napaisuudet tallennettu.")
    else:
        # If controls are hidden, still display static polarity labels (no actions)
        cont.markdown(f"Yläkela: **{st.session_state[left_key]}**, Alakela: **{st.session_state[right_key]}**")

    return st.session_state[left_key], st.session_state[right_key]


def _build_svg(left_label: str, right_label: str, width: int = 320, height: int = 140):
    """Return an inline SVG string and its computed height representing
    two stacked coil-like boxes (one above the other). Each box is
    approximately 300x50 (configurable via the `width`/`height` arguments)
    and contains a single letter ('S' or 'N') shown on a colored badge in
    the box center.

    Returns: (svg_string, svg_height)
    """
    # Colors: S -> red, N -> blue
    color_map = {'S': '#c62828', 'N': '#1e88e5'}
    left_color = color_map.get(left_label, '#777')
    right_color = color_map.get(right_label, '#777')

    # Desired coil box size
    box_w = min(300, width - 24)
    box_h = 50
    pad = 12
    total_h = pad + box_h + 8 + box_h + pad
    svg_h = max(height, total_h)

    cx = width / 2
    top_y = pad
    bottom_y = pad + box_h + 8

    svg = f'''<svg width="{width}" height="{svg_h}" viewBox="0 0 {width} {svg_h}" xmlns="http://www.w3.org/2000/svg">

    <!-- Top coil box (transparent background behind boxes) -->
    <rect x="{cx - box_w/2}" y="{top_y}" width="{box_w}" height="{box_h}" rx="6" ry="6" fill="none" stroke="#ddd"/>
    <!-- Bottom coil box -->
    <rect x="{cx - box_w/2}" y="{bottom_y}" width="{box_w}" height="{box_h}" rx="6" ry="6" fill="none" stroke="#ddd"/>

    <!-- Colored badges centered inside boxes (badge centered at box center) -->
    <rect x="{cx - 18}" y="{top_y + box_h/2 - 18}" width="36" height="36" rx="6" ry="6" fill="{left_color}"/>
    <text x="{cx}" y="{top_y + box_h/2 + 6}" font-family="Arial, Helvetica, sans-serif" font-size="20" fill="#fff" text-anchor="middle">{left_label}</text>

    <rect x="{cx - 18}" y="{bottom_y + box_h/2 - 18}" width="36" height="36" rx="6" ry="6" fill="{right_color}"/>
    <text x="{cx}" y="{bottom_y + box_h/2 + 6}" font-family="Arial, Helvetica, sans-serif" font-size="20" fill="#fff" text-anchor="middle">{right_label}</text>

    <!-- Small labels for accessibility -->
    <text x="{cx + box_w/2 + 6}" y="{top_y + box_h/2 + 6}" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#666">Yläkela</text>
    <text x="{cx + box_w/2 + 6}" y="{bottom_y + box_h/2 + 6}" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#666">Alakela</text>
</svg>'''
    return svg, svg_h


def get_polarities(prefix: str):
    left_key = f"{prefix}_left"
    right_key = f"{prefix}_right"
    return st.session_state.get(left_key), st.session_state.get(right_key)
