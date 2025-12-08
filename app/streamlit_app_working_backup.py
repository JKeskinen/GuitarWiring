"""
AI-avustaja Streamlit-sovellus (uusi versio)

Tämä tiedosto näyttää tervehdyksen ja suorittaa vaiheittaisen alkukartoituksen
H-mikrofonien asentamista varten. Sovellus käyttää paikallista LLM:ää
`app.llm_client.SimpleLLM` (oletuksena Ollama HTTP -palvelin). Oletusmalli on
`mistral:7b`, ja palvelimen URL-osoite oletuksena `http://localhost:11434`.
Voit muuttaa asetuksia ympäristömuuttujilla `LLM_BACKEND`, `OLLAMA_URL` tai
`OLLAMA_MODEL`.

Käynnistä:
    streamlit run app/streamlit_app.py
"""
import sys
import pathlib
import streamlit as st
import time
import os
import json
import streamlit.components.v1 as components
from typing import List, Tuple

# Ensure project root is on sys.path so `from app import ...` works when
# Streamlit runs the script from the `app/` folder.
HERE = pathlib.Path(__file__).resolve()
PROJECT_ROOT = HERE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.llm_client import SimpleLLM
except Exception:
    SimpleLLM = None

try:
    from app.humbucker import render_humbucker
except Exception:
    render_humbucker = None

st.set_page_config(page_title="AI-avustaja: Humbucker Assist", layout="centered")

def lmm_available() -> bool:
    return SimpleLLM is not None


def _build_wiring_svg(colors_list, wire_count, width=520, height=260, title=None, highlight_indices: list = None, role_labels: dict = None):
    """Build a small wiring preview SVG usable across steps.
    highlight_indices: list of 0-based wire indices to emphasize (draw outline).
    role_labels: optional dict mapping role name -> list of 0-based indices to label (e.g. {'HOT':[0], 'SERIES':[1,2], 'GROUND':[3]}).
    """
    pad = 12
    box_w = 220
    box_h = 50
    cx = 140
    top_y = pad
    bottom_y = pad + box_h + 12

    # box right edge
    x_right = cx + box_w/2
    line_len = 80
    spacing = 18

    svg = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    # coils
    svg.append(f'<rect x="{cx - box_w/2}" y="{top_y}" width="{box_w}" height="{box_h}" rx="6" ry="6" fill="none" stroke="#ddd"/>')
    svg.append(f'<rect x="{cx - box_w/2}" y="{bottom_y}" width="{box_w}" height="{box_h}" rx="6" ry="6" fill="none" stroke="#ddd"/>')
    # S/N badges
    svg.append(f'<text x="{cx}" y="{top_y + box_h/2 + 6}" font-family="Arial" font-size="18" text-anchor="middle" fill="#c62828">S</text>')
    svg.append(f'<text x="{cx}" y="{bottom_y + box_h/2 + 6}" font-family="Arial" font-size="18" text-anchor="middle" fill="#1e88e5">N</text>')

    # positions for four wires: two upper (y offsets), two lower
    upper_center = top_y + box_h/2
    lower_center = bottom_y + box_h/2
    offsets = [-6, 6, -6, 6]

    def _resolve_color(inp: str):
        if not inp:
            return '#888888'
        s = str(inp).strip()
        if s.startswith('#'):
            return s
        nm = s.lower()
        mapping = {
            'punainen': '#c62828', 'valkoinen': '#ffffff', 'vihreä': '#2e7d32', 'vihrea': '#2e7d32', 'musta': '#000000',
            'sininen': '#1e88e5', 'keltainen': '#f9a825', 'harmaa': '#9e9e9e',
            'red': '#c62828', 'white': '#ffffff', 'green': '#2e7d32', 'black': '#000000',
            'blue': '#1e88e5', 'yellow': '#f9a825', 'gray': '#9e9e9e', 'grey': '#9e9e9e',
        }
        return mapping.get(nm, '#888888')

    highlight_indices = highlight_indices or []
    role_labels = role_labels or {}
    for i in range(4):
        # determine y: first two -> upper, last two -> lower
        if i < 2:
            y = upper_center + offsets[i]
        else:
            y = lower_center + offsets[i]
        x_start = x_right
        x_end = x_right + line_len

        # draw horizontal line from coil edge to circle
        svg.append(f'<line x1="{x_start}" y1="{y}" x2="{x_end}" y2="{y}" stroke="#aaa" stroke-width="2"/>')

        # determine circle fill: only filled for configured wires
        if i < wire_count and i < len(colors_list):
            col_raw = colors_list[i]
            col = _resolve_color(col_raw)
            fill_attr = col
            opacity = 1.0
            stroke = '#444'
        else:
            fill_attr = 'none'
            opacity = 0.35
            stroke = '#bbb'

        # draw the marker ball at the wire end (filled when configured)
        svg.append(f'<circle cx="{x_end + 12}" cy="{y}" r="8" fill="{fill_attr}" fill-opacity="{opacity}" stroke="{stroke}"/>')

        # draw highlight ring if requested
        if i in highlight_indices:
            svg.append(f'<circle cx="{x_end + 12}" cy="{y}" r="12" fill="none" stroke="#ff9800" stroke-width="3" />')

        # draw role label near the circle if requested
        for role, idxs in role_labels.items():
            if not idxs:
                continue
            if i in idxs and len(idxs) == 1:
                # single-index label: draw above the circle
                svg.append(f'<text x="{x_end + 12}" y="{y - 18}" font-family="Arial" font-size="11" text-anchor="middle" fill="#ffb74d">{role}</text>')

    # optional title
    if title:
        svg.append(f'<text x="{cx}" y="{pad/2}" font-family="Arial" font-size="14" text-anchor="middle" fill="#333">{title}</text>')

    # note about bare
    if st.session_state.get('bare_present'):
        svg.append(f'<text x="{pad}" y="{height - 16}" font-family="Arial" font-size="12" fill="#aaa">Bare-johto: ei piirretä; yhdistetään common groundiin.</text>')

    svg.append('</svg>')
    return '\n'.join(svg)


# Manufacturer color-code presets (module-level so multiple steps can use them)
MANUFACTURER_COLORS = {
    'Seymour Duncan': {
        'north_start': 'Black',
        'north_finish': 'White',
        'south_start': 'Green',
        'south_finish': 'Red',
        'bare': 'Bare'
    }
}

WIRING_PRESETS = {
    'Series (default)': {
        'HOT': ('north_start',),
        'SERIES_LINK': ('north_finish', 'south_finish'),
        'GROUND': ('south_start', 'bare')
    },
    'Parallel': {
        'HOT': ('north_start', 'south_finish'),
        'GROUND': ('north_finish', 'south_start', 'bare')
    },
    'Split to South (keep S)': {
        'HOT': ('south_start',),
        'GROUND': ('north_start', 'north_finish', 'south_finish', 'bare')
    },
    'Split to North (keep N)': {
        'HOT': ('north_start',),
        'GROUND': ('north_finish', 'south_start', 'south_finish', 'bare')
    }
}


def greet():
    st.title("AI-avustaja: Humbucker Wiring Assistant")
    st.markdown(
        """
        Hei! Olen AI-avustaja. Käytän paikallista tekoälyä ja avustan sinua
        asentamaan Humbucker mikrofonit. Suoritetaan vaiheittain alkukartoitus.
        """
    )

    # LLM info moved to page bottom to avoid distracting users; see `show_llm_info()`
        
    # Automatically ping the LLM on first page load/refresh so it can "comment" the welcome.
    # This runs once per session by toggling `auto_ping_on_load` in session_state.
    # Previously this auto-ran on every page load by default. Make it opt-in
    # so users do not spam their local LLM on refresh. Default is False.
    try:
        if lmm_available() and st.session_state.get('auto_ping_on_load', False):
            # Run once and then clear the flag for this session so it doesn't
            # repeat without explicit user action.
            st.session_state['auto_ping_on_load'] = False
            run_llm_ping()
    except Exception:
        # If auto-ping fails for any reason, do not interrupt the rest of the UI.
        st.warning("Automaattinen LLM-pyyntö epäonnistui. Voit kokeilla 'Tarkista paikallinen LLM' painiketta.")


def show_llm_info():
    """Display a small LLM info caption at the bottom of the page."""
    if lmm_available():
        try:
            client = SimpleLLM()
            model = getattr(client, 'model', None) or os.environ.get('OLLAMA_MODEL', 'mistral:7b')
            url = getattr(client, 'ollama_url', None) or os.environ.get('OLLAMA_URL', 'http://localhost:11434')
            st.caption(f"Paikallinen LLM: Ollama ({url}), oletusmalli: `{model}`. Muuta `LLM_BACKEND`, `OLLAMA_URL` tai `OLLAMA_MODEL` ympäristömuuttujilla.")
        except Exception:
            st.caption("Paikallinen LLM on konfiguroitu, mutta tietoja ei voitu lukea.")
    else:
        st.caption("Paikallinen LLM ei ole konfiguroitu.")

    cols = st.columns([1, 1])
    with cols[0]:
        if st.button("Aloita alkukartoitus"):
            # Start interactive, one-question-at-a-time survey
            st.session_state['interactive'] = True
            st.session_state['interactive_step'] = 1
            st.session_state['start_survey'] = True
    with cols[1]:
        if lmm_available():
            # use fixed delay (user can edit code later)
            st.session_state['llm_char_delay'] = 0.01
            # Allow user to enable auto-ping for future page loads (opt-in).
            auto_ping = st.checkbox("Ota automaattinen LLM-tarkistus käyttöön sivun latauksessa (vaikuttaa seuraavalla latauksella)", value=st.session_state.get('auto_ping_on_load', False), key='auto_ping_checkbox')
            st.session_state['auto_ping_on_load'] = bool(auto_ping)

            if st.button("Tarkista paikallinen LLM"):
                run_llm_ping()
        else:
            st.info("Paikallinen LLM ei ole konfiguroitu tai `app.llm_client.SimpleLLM` puuttuu.")


def run_llm_ping():
    """Try a lightweight prompt to verify the local LLM is reachable."""
    if not lmm_available():
        st.error("LLM-kirjasto ei saatavilla.")
        return
    client = SimpleLLM()
    with st.spinner("Kommunikoidaan paikallisen LLM:n kanssa..."):
        try:
            out = client.generate("Hello from GuitarWiring assistant. Ping?", max_tokens=60)
            st.session_state['llm_ok'] = True

            # Stream the response client-side inside a fixed-height scrollable box
            st.success("LLM vastasi onnistuneesti.")
            delay = float(st.session_state.get('llm_char_delay', 0.01) or 0.01)

            # Build safe JSON string for JS
            js_text = json.dumps(out)
            js_delay = int(max(0.0, delay) * 1000)

            # Use a div (not <pre>) and force wrapping; allow vertical scroll only
            html = """
<div style="height:260px; border:1px solid #ddd; background:#f8f9fa; overflow-y:auto; overflow-x:hidden; padding:8px; font-family: monospace;">
    <div id="gw_out" style="margin:0; font-family:monospace; font-size:14px; line-height:1.4; color:#111; white-space:pre-wrap; word-break:break-word; overflow-wrap:break-word;"></div>
</div>
<script>
    const txt = @@JS_TEXT@@;
    const outEl = document.getElementById('gw_out');
    let i = 0;
    function step(){
        if(i < txt.length){
            outEl.textContent += txt.charAt(i);
            i++;
            // keep scroll at bottom
            outEl.parentElement.scrollTop = outEl.parentElement.scrollHeight;
        } else {
            clearInterval(timer);
        }
    }
    const timer = setInterval(step, @@JS_DELAY@@);
</script>
"""
            # Safely substitute JSON and delay into JS using placeholders (avoid f-string braces)
            html = html.replace('@@JS_TEXT@@', js_text).replace('@@JS_DELAY@@', str(js_delay))
            components.html(html, height=280)
        except Exception as e:
            st.error(f"LLM-yhteys epäonnistui: {e}")
            st.session_state['llm_ok'] = False


def run_llm_guidance(prompt: str, max_tokens: int = 400):
    """Ask the local LLM for guided, step-by-step instructions and stream the
    response client-side character-by-character into the same fixed box.
    """
    if not lmm_available():
        st.error("LLM-kirjasto ei saatavilla.")
        return
    client = SimpleLLM()
    with st.spinner("Pyydetään opastusta paikalliselta LLM:ltä..."):
        try:
            out = client.generate(prompt, max_tokens=max_tokens)
            st.session_state['llm_ok'] = True

            st.success("LLM antoi ohjeet.")
            delay = float(st.session_state.get('llm_char_delay', 0.01) or 0.01)

            js_text = json.dumps(out)
            js_delay = int(max(0.0, delay) * 1000)

            html = """
<div style="height:260px; border:1px solid #ddd; background:#f8f9fa; overflow-y:auto; overflow-x:hidden; padding:8px; font-family: monospace;">
    <div id="gw_out" style="margin:0; font-family:monospace; font-size:14px; line-height:1.4; color:#111; white-space:pre-wrap; word-break:break-word; overflow-wrap:break-word;"></div>
</div>
<script>
    const txt = @@JS_TEXT@@;
    const outEl = document.getElementById('gw_out');
    let i = 0;
    function step(){
        if(i < txt.length){
            outEl.textContent += txt.charAt(i);
            i++;
            outEl.parentElement.scrollTop = outEl.parentElement.scrollHeight;
        } else {
            clearInterval(timer);
        }
    }
    const timer = setInterval(step, @@JS_DELAY@@);
</script>
"""
            html = html.replace('@@JS_TEXT@@', js_text).replace('@@JS_DELAY@@', str(js_delay))
            components.html(html, height=280)
        except Exception as e:
            st.error(f"LLM-opastus epäonnistui: {e}")
            st.session_state['llm_ok'] = False


def survey_form():
    st.header("1) Alkukartoitus")
    st.markdown("Täytä alla olevat tiedot, niin jatketaan vaiheeseen mittaukset ja ehdotukset.")

    with st.form("survey_form"):
        pickup_type = st.selectbox("Mikrofoni:", ["H", "single-coil", "other"], index=0)
        wires_input = st.text_input("Johtimien nimet (pilkuilla eroteltuna)", value="Punainen, Vihreä, Valkoinen, Musta")
        wires = [w.strip() for w in wires_input.split(",") if w.strip()]
        # detect bare/ground automatically
        ground_name = None
        for w in wires.copy():
            if w.lower() in ("bare", "maa", "ground"):
                ground_name = w
                wires.remove(w)
        if ground_name:
            st.caption(f"Huom: '{ground_name}' käsitellään automaattisesti maadoituksena.")

        hb_layout = "HH"
        if pickup_type == "Humbucker":
            hb_layout = st.selectbox("Asennus (valitse)", ["HH", "single-H"], index=0, help="Valitse 'HH' jos haluat kaula+talla -tyypin työnkulun")

        notes = st.text_area("Lisätietoja (vapaaehtoinen)")

        submitted = st.form_submit_button("Tallenna ja jatka")

    if submitted:
        st.session_state['pickup_type'] = pickup_type
        st.session_state['wires'] = wires
        st.session_state['ground_name'] = ground_name
        st.session_state['hb_layout'] = hb_layout
        st.session_state['survey_notes'] = notes
        st.success("Alkukartoitus tallennettu. Seuraava: mittausten ohjeistus.")


def interactive_survey():
    """Interactive, one-question-at-a-time survey driven by UI controls.

    Step 1 (implemented): "Valitse mikitys:" (only option: HH)
    Subsequent steps can be added by expanding `interactive_step` handling.
    """
    step = st.session_state.get('interactive_step', 1)

    # Visuals are rendered in-line inside each step so the step header
    # appears above the corresponding microphone visuals (avoid rendering
    # them before the step title). See step-specific rendering below.

    if step == 1:
        st.header("Interaktiivinen alkukartoitus — vaihe 1")
        st.write("Valitse mikitys:")
        # Only one option for now (user requested HH only). Provide a non-empty
        # label to avoid accessibility warnings and hide it visually since we
        # already show surrounding explanatory text.
        choice = st.radio("Mikitysvalinta", ["HH"], index=0, key='interactive_choice_1', label_visibility='hidden')

        if st.button("Seuraava", key='step1_next'):
            # Save choice and advance
            st.session_state['pickup_type'] = 'Humbucker' if choice == 'HH' else choice
            # Also set hb_layout to reflect the HH installation choice so next_steps_view shows correct workflow
            if choice == 'HH':
                st.session_state['hb_layout'] = 'HH'
            st.session_state['interactive_step'] = 2
            st.success(f"Valittu mikitys: {choice}. Siirrytään seuraavaan vaiheeseen.")

    else:
        st.info("Interaktiivinen työnkulku: seuraava vaihe ei ole vielä implementoitu. Voit jatkaa perinteisellä lomakkeella.")

    # Step 2: polarity checks for upper and lower coils (for neck Humbucker)
    if step == 2:
        st.header("Interaktiivinen alkukartoitus — vaihe 2: Kaulamikin napaisuuksien tarkistus")
        st.write("Käytä alla näkyvää mikki-visualisointia: käännä tarvittaessa ja paina 'Tallenna' visualisoinnin oikealla puolella.")

        # Render neck on top, small spacer, then bridge below so the step
        # header appears above the microphones as requested by the user.
        if render_humbucker:
            render_humbucker('neck', 'Kaula', width=360, height=160)
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            render_humbucker('bridge', 'Talla', width=360, height=160)

        # Show current saved polarities for both pickups (neck + bridge)
        n_up = st.session_state.get('upper_polarity') or st.session_state.get('neck_left') or 'Ei määritetty'
        n_lo = st.session_state.get('lower_polarity') or st.session_state.get('neck_right') or 'Ei määritetty'
        b_up = st.session_state.get('bridge_upper_polarity') or st.session_state.get('bridge_left') or 'Ei määritetty'
        b_lo = st.session_state.get('bridge_lower_polarity') or st.session_state.get('bridge_right') or 'Ei määritetty'

        st.write(f"Kaula — Yläkela: {n_up}, Alakela: {n_lo}.")
        st.write(f"Talla — Yläkela: {b_up}, Alakela: {b_lo}.")

        # Allow proceeding only if both saved (visual Tallenna) values are present
        if st.button("Seuraava", key='step2_next'):
            neck_saved = (st.session_state.get('upper_polarity') or st.session_state.get('neck_left')) and (st.session_state.get('lower_polarity') or st.session_state.get('neck_right'))
            bridge_saved = (st.session_state.get('bridge_upper_polarity') or st.session_state.get('bridge_left')) and (st.session_state.get('bridge_lower_polarity') or st.session_state.get('bridge_right'))

            if neck_saved and bridge_saved:
                # Ensure canonical keys exist for both pickups
                if 'upper_polarity' not in st.session_state and 'neck_left' in st.session_state:
                    st.session_state['upper_polarity'] = st.session_state['neck_left']
                if 'lower_polarity' not in st.session_state and 'neck_right' in st.session_state:
                    st.session_state['lower_polarity'] = st.session_state['neck_right']
                if 'bridge_upper_polarity' not in st.session_state and 'bridge_left' in st.session_state:
                    st.session_state['bridge_upper_polarity'] = st.session_state['bridge_left']
                if 'bridge_lower_polarity' not in st.session_state and 'bridge_right' in st.session_state:
                    st.session_state['bridge_lower_polarity'] = st.session_state['bridge_right']
                # Advance directly to measurements (step 4)
                st.session_state['interactive_step'] = 4
                st.success("Napaisuudet tallennettu molemmista mikkeistä. Siirrytään mittausvaiheeseen.")
            elif neck_saved:
                # Only neck complete: go to bridge polarity step
                st.session_state['interactive_step'] = 3
            else:
                st.warning("Tallenna kaulamikin napaisuudet visualisoinnissa ennen siirtymistä eteenpäin.")

    # Step 3: bridge (talla) polarity checks
    if step == 3:
        st.header("Interaktiivinen alkukartoitus — vaihe 3: Tallamikin napaisuuksien tarkistus")
        st.write("Käytä alla näkyvää tallamikki-visualisointia: käännä tarvittaessa ja paina 'Tallenna' visualisoinnin oikealla puolella.")

        # Also render both visuals here so the header appears above them.
        if render_humbucker:
            render_humbucker('neck', 'Kaula', width=360, height=160)
            st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
            render_humbucker('bridge', 'Talla', width=360, height=160)

        b_up = st.session_state.get('bridge_upper_polarity') or st.session_state.get('bridge_left') or 'Ei määritetty'
        b_lo = st.session_state.get('bridge_lower_polarity') or st.session_state.get('bridge_right') or 'Ei määritetty'
        n_up = st.session_state.get('upper_polarity', 'Ei määritetty')
        n_lo = st.session_state.get('lower_polarity', 'Ei määritetty')

        st.write(f"Kaula — Yläkela: {n_up}, Alakela: {n_lo}.")
        st.write(f"Talla — Yläkela: {b_up}, Alakela: {b_lo}.")

        # Offer an optional short combined explanation from the local LLM
        if lmm_available():
            if st.button("Pyydä lyhyt selitys LLM:ltä (valinnainen)"):
                prompt = (
                    f"User checked neck pickup polarities: upper coil={n_up}, lower coil={n_lo} and bridge pickup polarities: upper coil={b_up}, lower coil={b_lo}. "
                    "Please give a short confirmation and next step suggestion.")
                run_llm_guidance(prompt, max_tokens=220)

        if st.button("Valmis — siirry mittauksiin"):
            if (st.session_state.get('bridge_upper_polarity') or st.session_state.get('bridge_left')) and (st.session_state.get('bridge_lower_polarity') or st.session_state.get('bridge_right')):
                # Ensure canonical keys exist
                if 'bridge_upper_polarity' not in st.session_state and 'bridge_left' in st.session_state:
                    st.session_state['bridge_upper_polarity'] = st.session_state['bridge_left']
                if 'bridge_lower_polarity' not in st.session_state and 'bridge_right' in st.session_state:
                    st.session_state['bridge_lower_polarity'] = st.session_state['bridge_right']
                st.session_state['interactive_step'] = 4
                st.success("Napaisuudet tallennettu. Siirrytään mittausvaiheeseen.")
            else:
                st.warning("Tallenna tallamikin napaisuudet visualisoinnissa ennen siirtymistä mittauksiin.")

    # Step 4: Define coil wires (1-4 conductors + optional bare)
    if step == 4:
        st.header("Vaihe 4: Kelojen johdinten määrittäminen")
        st.markdown("Määritä kuinka monta johtoa on jokaisessa mikissä (1–4). Valitse myös, onko bare/maa-johto mukana.")

        wire_count = st.selectbox("Johtojen määrä (ilman bare):", [1, 2, 3, 4], index=min(3, st.session_state.get('wire_count', 4) - 1))
        bare = st.checkbox("Bare-johto (maadoitus) mukana", value=st.session_state.get('bare_present', False), key='bare_checkbox')

        # Clickable color icon choices (showing colored icons instead of text)
        COLOR_OPTIONS = ['Red', 'Green', 'Black', 'Yellow', 'White']
        # emoji icons for the UI (colored circles)
        COLOR_EMOJI = {'Red': '🔴', 'Green': '🟢', 'Black': '⚫', 'Yellow': '🟡', 'White': '⚪'}
        # sensible defaults for first 4 wires
        defaults = ['Red', 'White', 'Green', 'Black']
        colors = st.session_state.get('wire_colors', defaults.copy()) if 'wire_colors' in st.session_state else defaults.copy()

        st.markdown("#### Valitse kunkin johdon väri (ikoneina)")
        for i in range(1, 5):
            row_label = f"Johto {i}"
            used = (i <= wire_count)
            current = colors[i-1] if i-1 < len(colors) else defaults[i-1]

            cols = st.columns([1, 5])
            with cols[0]:
                # show current selection as a large colored emoji (outline if unused)
                emoji = COLOR_EMOJI.get(current, '⚪')
                if used:
                    st.markdown(f"<div style=\"font-size:28px; line-height:1\">{emoji}</div>", unsafe_allow_html=True)
                else:
                    # muted / outline look for unused wires
                    st.markdown(f"<div style=\"font-size:22px; color:#999; line-height:1\">{emoji}</div>", unsafe_allow_html=True)
            with cols[1]:
                # render compact color icon buttons; clicking sets the session_state value
                opt_cols = st.columns(len(COLOR_OPTIONS))
                for ci, opt in enumerate(COLOR_OPTIONS):
                    col_key = f'choose_{i}_{opt}'
                    label = COLOR_EMOJI.get(opt, opt)
                    # disabled if wire not used
                    if used:
                        if opt_cols[ci].button(label, key=col_key):
                            colors[i-1] = opt
                            # persist immediately so UI shows selection
                            st.session_state['wire_colors'] = colors
                    else:
                        # show non-interactive icon for unused wires
                        opt_cols[ci].markdown(f"<div style=\"font-size:18px; color:#bbb; text-align:center\">{label}</div>", unsafe_allow_html=True)

        cols = st.columns([1, 1, 1])
        with cols[0]:
            if st.button("Tallenna johdot ja esikatsele", key='save_wires'):
                st.session_state['wire_count'] = int(wire_count)
                st.session_state['wire_colors'] = colors
                st.session_state['bare_present'] = bool(bare)
                st.success("Johdot tallennettu.")
        with cols[1]:
            if st.button("Jatka mittauksiin", key='wires_next'):
                # ensure values saved
                st.session_state['wire_count'] = int(wire_count)
                st.session_state['wire_colors'] = colors
                st.session_state['bare_present'] = bool(bare)
                st.session_state['interactive_step'] = 5
                st.success("Johdot tallennettu. Siirrytään mittauksiin.")

        # Additional section: allow confirming/defining the same wiring for the bridge pickup
        st.markdown('---')
        st.markdown('#### Talla — vahvista johdotus (erillinen näkymä)')
        bridge_colors = st.session_state.get('bridge_wire_colors', colors.copy()) if 'bridge_wire_colors' in st.session_state else colors.copy()
        for i in range(1, 5):
            row_label = f"Talla Johto {i}"
            used = (i <= wire_count)
            current = bridge_colors[i-1] if i-1 < len(bridge_colors) else defaults[i-1]

            cols_b = st.columns([1, 5])
            with cols_b[0]:
                emoji = COLOR_EMOJI.get(current, '⚪')
                if used:
                    st.markdown(f"<div style=\"font-size:28px; line-height:1\">{emoji}</div>", unsafe_allow_html=True)
                else:
                    st.markdown(f"<div style=\"font-size:22px; color:#999; line-height:1\">{emoji}</div>", unsafe_allow_html=True)
            with cols_b[1]:
                opt_cols = st.columns(len(COLOR_OPTIONS))
                for ci, opt in enumerate(COLOR_OPTIONS):
                    col_key = f'choose_bridge_{i}_{opt}'
                    label = COLOR_EMOJI.get(opt, opt)
                    if used:
                        if opt_cols[ci].button(label, key=col_key):
                            bridge_colors[i-1] = opt
                            # persist only bridge-specific selection so neck colors are not overwritten
                            st.session_state['bridge_wire_colors'] = bridge_colors
                    else:
                        opt_cols[ci].markdown(f"<div style=\"font-size:18px; color:#bbb; text-align:center\">{label}</div>", unsafe_allow_html=True)

        cols_b2 = st.columns([1, 1])
        with cols_b2[0]:
            if st.button('Tallenna tallan johdot', key='save_bridge_wires'):
                st.session_state['bridge_wire_colors'] = bridge_colors
                st.success('Tallan johdot tallennettu.')
        with cols_b2[1]:
            if st.button('Jatka mittauksiin (talla)', key='bridge_wires_next'):
                st.session_state['bridge_wire_colors'] = bridge_colors
                st.session_state['wire_count'] = int(wire_count)
                st.session_state['bare_present'] = bool(bare)
                st.session_state['interactive_step'] = 5
                st.success('Tallan johdot tallennettu. Siirrytään mittauksiin.')

        # Preview wiring: draw both pickups with four wire markers to the right.
        neck_preview_colors = st.session_state.get('wire_colors', colors)
        bridge_preview_colors = st.session_state.get('bridge_wire_colors', neck_preview_colors)
        wc = int(st.session_state.get('wire_count', wire_count))

        # Suggest roles using the default manufacturer mapping (Seymour Duncan)
        manuf_map = MANUFACTURER_COLORS.get('Seymour Duncan')
        def _role_indices_from_colors(color_list, manuf_map):
            role_idxs = {'HOT': [], 'SERIES': [], 'GROUND': []}
            if not manuf_map or not color_list:
                return role_idxs
            # HOT -> north_start
            ns = manuf_map.get('north_start')
            if ns and ns in color_list:
                role_idxs['HOT'].append(color_list.index(ns))
            # SERIES -> north_finish + south_finish
            nf = manuf_map.get('north_finish')
            sf = manuf_map.get('south_finish')
            for r in (nf, sf):
                if r and r in color_list and color_list.index(r) not in role_idxs['SERIES']:
                    role_idxs['SERIES'].append(color_list.index(r))
            # GROUND -> south_start (bare shown as caption only)
            ss = manuf_map.get('south_start')
            if ss and ss in color_list:
                role_idxs['GROUND'].append(color_list.index(ss))
            return role_idxs

        neck_roles = _role_indices_from_colors(neck_preview_colors, manuf_map)
        bridge_roles = _role_indices_from_colors(bridge_preview_colors, manuf_map)

        neck_svg = _build_wiring_svg(neck_preview_colors, wc, title='Kaula (neck)', highlight_indices=neck_roles.get('SERIES', []) + neck_roles.get('HOT', []), role_labels={
            'HOT': neck_roles.get('HOT', []),
            'SERIES': neck_roles.get('SERIES', []),
            'GROUND': neck_roles.get('GROUND', [])
        })
        bridge_svg = _build_wiring_svg(bridge_preview_colors, wc, title='Talla (bridge)', highlight_indices=bridge_roles.get('SERIES', []) + bridge_roles.get('HOT', []), role_labels={
            'HOT': bridge_roles.get('HOT', []),
            'SERIES': bridge_roles.get('SERIES', []),
            'GROUND': bridge_roles.get('GROUND', [])
        })
        components.html(neck_svg, height=180)
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        components.html(bridge_svg, height=180)

    # Step 5: Measurements — collect coil resistances (neck & bridge, upper/lower)
    if step == 5:
        st.header("Interaktiivinen mittausvaihe — vaihe 5")
        st.markdown(
            """
            Aseta yleismittari vastusmittaukseen ja valitse alue ~20 kΩ (20kΩ-asetus).
            Etsi johdotuspareja yhdistämällä mittapihdit kahden johtimen välillä. Kun mittari näyttää
            resistanssia (esim. noin 3.85), olet löytänyt kelaparin.
            Syötä löytyneet resistanssiarvot alla (yksikössä kilo-ohmia, kΩ). Anna desimaaliluku, esim. `3.85`.
            """
        )

        st.subheader("Kaulamikin mittaukset")
        neck_upper = st.number_input("Kaula — yläkela (kΩ)", min_value=0.0, format="%.2f", key='neck_upper_res')
        neck_lower = st.number_input("Kaula — alakela (kΩ)", min_value=0.0, format="%.2f", key='neck_lower_res')

        st.subheader("Tallamikin mittaukset")
        bridge_upper = st.number_input("Talla — yläkela (kΩ)", min_value=0.0, format="%.2f", key='bridge_upper_res')
        bridge_lower = st.number_input("Talla — alakela (kΩ)", min_value=0.0, format="%.2f", key='bridge_lower_res')

        if st.button("Tallenna mittaukset ja analysoi", key='save_measurements'):
            st.session_state['neck_upper_res_kohm'] = float(neck_upper)
            st.session_state['neck_lower_res_kohm'] = float(neck_lower)
            st.session_state['bridge_upper_res_kohm'] = float(bridge_upper)
            st.session_state['bridge_lower_res_kohm'] = float(bridge_lower)
            st.session_state['interactive_step'] = 6
            st.success("Mittaukset tallennettu. Voit jatkaa analyysiin tai siirtyä seuraavaan ohjeistukseen.")

    # Step 6: Analysis — map wires to HOT / series link / ground using phase checks
    if step == 6:
        # Pull needed session values and allow the user to explicitly declare which wire colors belong to each coil
        wire_colors = st.session_state.get('wire_colors', [])
        wire_count = int(st.session_state.get('wire_count', 4))
        bare = bool(st.session_state.get('bare_present', False))

        

        st.markdown('---')
        st.markdown('**Valinnainen: Käytä presettiä** — valitse valmistaja ja wiring-preset, niin ehdotukset ja esikatselu korostavat ehdotettuja johtimia. Presetti ei korvaa probe-mittauksia; varmista napaisuudet mittaamalla.')
        manuf = st.selectbox('Valmistajan värikoodit (preset)', ['(none)'] + list(MANUFACTURER_COLORS.keys()), index=0, key='preset_manufacturer')
        preset_choice = st.selectbox('Wiring preset (esitäytetty ehdotus)', ['(none)'] + list(WIRING_PRESETS.keys()), index=0, key='preset_choice')

        st.subheader('Määritä, mitkä johtimet kuuluvat mihinkin kelaan')
        if not wire_colors:
            st.warning('Et ole vielä määrittänyt johdon värejä vaiheessa 4. Palaa takaisin ja tallenna johdot ennen analyysiä.')

        opts = [c for c in wire_colors if c]
        # Language toggle: show Finnish labels in the multiselects by default.
        show_english = st.checkbox('Näytä värit englanniksi', value=False, key='show_colors_english')

        # Display mapping (English -> Finnish)
        fi_map = {
            'Red': 'Punainen',
            'White': 'Valkoinen',
            'Green': 'Vihreä',
            'Black': 'Musta',
            'Yellow': 'Keltainen',
            'Blue': 'Sininen',
            'Gray': 'Harmaa',
            'Grey': 'Harmaa'
        }
        # padded defaults
        padded = wire_colors + [None] * (4 - len(wire_colors))

        # Preference rule: North (N) -> 'Red', South (S) -> 'White'
        # If those colors exist, prefill the defaults to make the UX easier.
        def _prefill_pair(primary_color, other_opts):
            if primary_color in other_opts:
                # pick a different second color if available
                for c in other_opts:
                    if c != primary_color:
                        return [primary_color, c]
                # only primary exists
                return [primary_color]
            # fallback to padded positions
            if len(padded) >= 2 and (padded[0] or padded[1]):
                return [padded[0], padded[1]]
            return []

        default_north = _prefill_pair('Red', opts)
        # ensure we don't reuse the same color as the north default for south's second candidate
        remaining_opts = [c for c in opts if c not in default_north]
        default_south = _prefill_pair('White', remaining_opts) if remaining_opts else _prefill_pair('White', opts)

        st.markdown('Huom: oletusarvona käytämme pohjoiselle (N) punaista ja etelälle (S) valkoista, jos värit löytyvät johtoluettelosta.')
        # Use format_func to display Finnish names unless the user opts for English
        def _fmt(x):
            return x if show_english else fi_map.get(x, x)

        neck_upper_sel = st.multiselect('Kaula — Yläkela: valitse 2 johtoa', options=opts, default=default_north, key='neck_upper_sel', format_func=_fmt)
        neck_lower_sel = st.multiselect('Kaula — Alakela: valitse 2 johtoa', options=opts, default=default_south, key='neck_lower_sel', format_func=_fmt)

        bridge_upper_sel = st.multiselect('Talla — Yläkela: valitse 2 johtoa', options=opts, default=default_north, key='bridge_upper_sel', format_func=_fmt)
        bridge_lower_sel = st.multiselect('Talla — Alakela: valitse 2 johtoa', options=opts, default=default_south, key='bridge_lower_sel', format_func=_fmt)

        # Mahdollisuus pakottaa musta väri HOTiksi (käyttäjän toiveen mukaan)
        st.markdown("**Valinnainen asetus:**")
        force_black_hot = st.checkbox('Vahvista: Musta on HOT (pakota North START = Musta, jos saatavilla)', value=False, key='force_black_hot')

        # Show plain textual meter-lead mapping (no colored badges)
        def _plain_meter_labels(pair_list):
            if not pair_list:
                return ('tuntematon', 'tuntematon')
            first = pair_list[0] if len(pair_list) > 0 and pair_list[0] else 'tuntematon'
            second = pair_list[1] if len(pair_list) > 1 and pair_list[1] else 'tuntematon'
            return (first, second)

        # Display mapping using the same language as the multiselect labels
        def _display_color(val):
            if st.session_state.get('show_colors_english', False):
                return val or 'tuntematon'
            return fi_map.get(val, val) if val else 'tuntematon'

        n_up_red, n_up_black = _plain_meter_labels(st.session_state.get('neck_upper_sel', []))
        st.write(f"Kaula — Yläkela: AnturiPLUS -> {_display_color(n_up_red)}.    AnturiMIINUS -> {_display_color(n_up_black)}")

        n_lo_red, n_lo_black = _plain_meter_labels(st.session_state.get('neck_lower_sel', []))
        st.write(f"Kaula — Alakela: AnturiPLUS -> {_display_color(n_lo_red)}.    AnturiMIINUS -> {_display_color(n_lo_black)}")

        # Lisätään pieni tyhjä rivi kelojen väliin luettavuuden parantamiseksi
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        b_up_red, b_up_black = _plain_meter_labels(st.session_state.get('bridge_upper_sel', []))
        st.write(f"Talla — Yläkela: AnturiPLUS -> {_display_color(b_up_red)}.    AnturiMIINUS -> {_display_color(b_up_black)}")

        b_lo_red, b_lo_black = _plain_meter_labels(st.session_state.get('bridge_lower_sel', []))
        st.write(f"Talla — Alakela: AnturiPLUS -> {_display_color(b_lo_red)}.   AnturiMIINUS -> {_display_color(b_lo_black)}")

        # Basic validation: ensure each selection has exactly two wires
        def _valid_pair(lst):
            return isinstance(lst, list) and len(lst) == 2 and all(lst)

        if not _valid_pair(st.session_state.get('neck_upper_sel', [])) or not _valid_pair(st.session_state.get('neck_lower_sel', [])) or not _valid_pair(st.session_state.get('bridge_upper_sel', [])) or not _valid_pair(st.session_state.get('bridge_lower_sel', [])):
            st.warning('Valitse jokaiselle kelalle täsmälleen kaksi johtoa (valintajärjestys määrittää oletusparin).')

        # Warn on duplicate usage within the same pickup only (same colors in neck's selections or in bridge's selections)
        neck_selected = (st.session_state.get('neck_upper_sel', []) or []) + (st.session_state.get('neck_lower_sel', []) or [])
        bridge_selected = (st.session_state.get('bridge_upper_sel', []) or []) + (st.session_state.get('bridge_lower_sel', []) or [])
        neck_dupes = [c for c in set(neck_selected) if neck_selected.count(c) > 1]
        bridge_dupes = [c for c in set(bridge_selected) if bridge_selected.count(c) > 1]
        if neck_dupes:
            st.warning(f"Huom (Kaula): sama johto väri esiintyy useassa kaulamikin kelassa: {', '.join(neck_dupes)}. Varmista, että valinnat vastaavat fyysistä johdotusta.")
        if bridge_dupes:
            st.warning(f"Huom (Talla): sama johto väri esiintyy useassa tallamikin kelassa: {', '.join(bridge_dupes)}. Varmista, että valinnat vastaavat fyysistä johdotusta.")

        # Ask user for napaisuus (S/N) based on the visual step, and also run probe test (laskee/nousee)
        st.subheader("Kaulamikin kelat")
        # default polarities from session (visual step)
        def _pol_default(key_opts):
            for k in key_opts:
                v = st.session_state.get(k)
                if v in ('S', 'N'):
                    return v
            return 'S'

        neck_upper_default = _pol_default(['upper_polarity', 'neck_left'])
        neck_lower_default = _pol_default(['lower_polarity', 'neck_right'])

        neck_upper_pol = st.selectbox('Kaula — Yläkela (napaisuus)', ['S', 'N'], index=0 if neck_upper_default == 'S' else 1, key='neck_upper_pol')
        neck_upper_probe = st.radio("Kaula — yläkela: Mitä tapahtuu kun kosketat kelan slugeja?", ["Nousee (normaali)", "Laskee (käänteinen)"], index=0, key='neck_upper_probe')

        neck_lower_pol = st.selectbox('Kaula — Alakela (napaisuus)', ['S', 'N'], index=0 if neck_lower_default == 'S' else 1, key='neck_lower_pol')
        neck_lower_probe = st.radio("Kaula — alakela: Mitä tapahtuu kun kosketat kelan slugeja?", ["Nousee (normaali)", "Laskee (käänteinen)"], index=0, key='neck_lower_probe')

        st.subheader("Tallamikin kelat")
        bridge_upper_default = _pol_default(['bridge_upper_polarity', 'bridge_left'])
        bridge_lower_default = _pol_default(['bridge_lower_polarity', 'bridge_right'])

        bridge_upper_pol = st.selectbox('Talla — Yläkela (napaisuus)', ['S', 'N'], index=0 if bridge_upper_default == 'S' else 1, key='bridge_upper_pol')
        bridge_upper_probe = st.radio("Talla — yläkela: Mitä tapahtuu kun kosketat kelan slugeja?", ["Nousee (normaali)", "Laskee (käänteinen)"], index=0, key='bridge_upper_probe')

        bridge_lower_pol = st.selectbox('Talla — Alakela (napaisuus)', ['S', 'N'], index=0 if bridge_lower_default == 'S' else 1, key='bridge_lower_pol')
        bridge_lower_probe = st.radio("Talla — alakela: Mitä tapahtuu kun kosketat kelan slugeja?", ["Nousee (normaali)", "Laskee (käänteinen)"], index=0, key='bridge_lower_probe')

        # Allow user to explicitly swap probe leads per-coil if they notice the resistance drops when touching slugs
        st.markdown('**Vahvista probe-suunnat**: Jos resistanssi laskee koskettaessa slugeja (pole pieces), probeet ovat todennäköisesti käänteiset. Sovellus ehdottaa vaihtoa automaattisesti; tarkista mittauksesi ja muuta tarvittaessa.')

        def _probe_indicates_reverse(choice: str) -> bool:
            # Return True when the probe/tap result indicates a REVERSED phase
            # i.e. the resistance DECREASES when removing the tool.
            if not choice:
                return False
            c = str(choice).lower()
            return 'laskee' in c or 'reverse' in c or 'decrease' in c or 'inverted' in c

        def _probe_is_normal(choice: str) -> bool:
            # Return True when the probe/tap result indicates NORMAL phase
            # i.e. the resistance INCREASES when removing the tool.
            if not choice:
                return False
            c = str(choice).lower()
            return 'nousee' in c or 'increase' in c or 'normal' in c

        neck_upper_swap_default = _probe_indicates_reverse(neck_upper_probe)
        neck_lower_swap_default = _probe_indicates_reverse(neck_lower_probe)
        bridge_upper_swap_default = _probe_indicates_reverse(bridge_upper_probe)
        bridge_lower_swap_default = _probe_indicates_reverse(bridge_lower_probe)

        neck_upper_swap = st.checkbox('Vaihda kaula — yläkela probe-johdot (swap)', value=neck_upper_swap_default, key='neck_upper_swap')
        if neck_upper_swap_default:
            st.info('Mittauksen perusteella yläkelan probeet voivat olla käänteiset — vaihtoa suositellaan.')
        neck_lower_swap = st.checkbox('Vaihda kaula — alakela probe-johdot (swap)', value=neck_lower_swap_default, key='neck_lower_swap')
        if neck_lower_swap_default:
            st.info('Mittauksen perusteella alakelan probeet voivat olla käänteiset — vaihtoa suositellaan.')
        bridge_upper_swap = st.checkbox('Vaihda talla — yläkela probe-johdot (swap)', value=bridge_upper_swap_default, key='bridge_upper_swap')
        if bridge_upper_swap_default:
            st.info('Mittauksen perusteella tallan yläkelan probeet voivat olla käänteiset — vaihtoa suositellaan.')
        bridge_lower_swap = st.checkbox('Vaihda talla — alakela probe-johdot (swap)', value=bridge_lower_swap_default, key='bridge_lower_swap')
        if bridge_lower_swap_default:
            st.info('Mittauksen perusteella tallan alakelan probeet voivat olla käänteiset — vaihtoa suositellaan.')

        # Helper to choose start/finish from a pair based on phase radio selection
        def choose_pair_roles(pair_colors: list, phase_choice: str):
            # Expect pair_colors length == 2
            if not pair_colors or len(pair_colors) < 2:
                return {'start': None, 'finish': None}
            first, second = pair_colors[0], pair_colors[1]
            # If probe indicates normal (resistance INCREASES on removal),
            # then the first selected color is START and second is FINISH.
            if _probe_is_normal(phase_choice):
                return {'start': first, 'finish': second}
            else:
                # reverse
                return {'start': second, 'finish': first}

        # Map positions -> pairings (assumption: wires ordered as [N_start?, N_finish?, S_start?, S_finish?])
        # We assume the first two wires correspond to the North (upper) coil and the next two to the South (lower) coil.
        # If fewer wires are present, do best-effort mapping and warn the user.
        pairs_ok = True
        if wire_count < 4:
            st.warning("Huom: vähemmän kuin 4 johdinta valittu — analyysi tekee parhaan arvauksen, mutta joissain tapauksissa täydellistä sarjakytkentäohjetta ei voi muodostaa.")

        # Use the explicit selections (fall back to defaults if selections missing)
        north_pair = neck_upper_sel if _valid_pair(neck_upper_sel) else default_north
        south_pair = neck_lower_sel if _valid_pair(neck_lower_sel) else default_south
        bridge_north_pair = bridge_upper_sel if _valid_pair(bridge_upper_sel) else default_north
        bridge_south_pair = bridge_lower_sel if _valid_pair(bridge_lower_sel) else default_south

        # Show observations summary using chosen colors
        st.subheader('Havainnot')
        st.write(f"Kaulamikki — Yläkela: {north_pair[0] or 'tuntematon'} / {north_pair[1] or 'tuntematon'} (napaisuus: {st.session_state.get('neck_upper_pol', 'S')}).")
        st.write(f"Kaulamikki — Alakela: {south_pair[0] or 'tuntematon'} / {south_pair[1] or 'tuntematon'} (napaisuus: {st.session_state.get('neck_lower_pol', 'S')}).")
        st.write(f"Tallamikki — Yläkela: {bridge_north_pair[0] or 'tuntematon'} / {bridge_north_pair[1] or 'tuntematon'} (napaisuus: {st.session_state.get('bridge_upper_pol', 'S')}).")
        st.write(f"Tallamikki — Alakela: {bridge_south_pair[0] or 'tuntematon'} / {bridge_south_pair[1] or 'tuntematon'} (napaisuus: {st.session_state.get('bridge_lower_pol', 'S')}).")

        st.markdown('---')
        st.markdown('Kytke alemman kelan johdinpari yleismittariin vaihe 5:n havaintojen mukaisesti ja tee seuraava testi:')
        st.markdown('1) Kytke ensimmäinen johto punaiseen mittaripäähän ja toinen johto mustaan mittaripäähän.\n2) Kosketa kelaa metallityökalulla ja nosta se pois.\n3) Vastaa, nouseeko vai laskeeko resistanssi koskettaessa (hetkellisesti)?')

        # (probe radios for each coil were collected above as *_probe variables)

        neck_north = choose_pair_roles(north_pair, neck_upper_probe)
        neck_south = choose_pair_roles(south_pair, neck_lower_probe)

        bridge_north = choose_pair_roles(bridge_north_pair, bridge_upper_probe) if wire_count >= 4 else choose_pair_roles(padded[0:2], bridge_upper_probe)
        bridge_south = choose_pair_roles(bridge_south_pair, bridge_lower_probe) if wire_count >= 4 else choose_pair_roles(padded[2:4], bridge_lower_probe)

        # Apply manual probe-swap if user indicated the probes were reversed
        if st.session_state.get('neck_upper_swap'):
            neck_north = {'start': neck_north['finish'], 'finish': neck_north['start']}
        if st.session_state.get('neck_lower_swap'):
            neck_south = {'start': neck_south['finish'], 'finish': neck_south['start']}
        if st.session_state.get('bridge_upper_swap'):
            bridge_north = {'start': bridge_north['finish'], 'finish': bridge_north['start']}
        if st.session_state.get('bridge_lower_swap'):
            bridge_south = {'start': bridge_south['finish'], 'finish': bridge_south['start']}

        # Show small highlighted preview based on selected preset (if any)
        try:
            neck_preview_colors = st.session_state.get('wire_colors', [])
            bridge_preview_colors = st.session_state.get('bridge_wire_colors', neck_preview_colors)
            highlight_idx_neck = []
            highlight_idx_bridge = []
            if preset_choice and preset_choice != '(none)':
                preset = WIRING_PRESETS[preset_choice]
                manuf_map = MANUFACTURER_COLORS.get(manuf) if manuf and manuf != '(none)' else None
                # map preset roles (like 'north_finish') -> color names using manufacturer map if available
                def role_to_colors(role_names):
                    cols = []
                    for rn in role_names:
                        if manuf_map and rn in manuf_map:
                            cols.append(manuf_map[rn])
                    return cols

                # for neck: focus on series link wires if series preset, otherwise hot wires
                if 'SERIES_LINK' in preset:
                    target_roles = preset['SERIES_LINK']
                else:
                    target_roles = preset.get('HOT', [])

                target_colors = role_to_colors(target_roles)
                for c in target_colors:
                    if c in neck_preview_colors:
                        highlight_idx_neck.append(neck_preview_colors.index(c))
                    if c in bridge_preview_colors:
                        highlight_idx_bridge.append(bridge_preview_colors.index(c))

            # render previews
            if neck_preview_colors:
                nsvg = _build_wiring_svg(neck_preview_colors, wire_count, title='Kaula (highlighted)', highlight_indices=highlight_idx_neck)
                components.html(nsvg, height=160)
            if bridge_preview_colors:
                bsvg = _build_wiring_svg(bridge_preview_colors, wire_count, title='Talla (highlighted)', highlight_indices=highlight_idx_bridge)
                components.html(bsvg, height=160)
        except Exception:
            # preview is optional — don't break analysis if it fails
            pass

        # Note: previously there was an option to force Black as HOT here. Per phase-based
        # decision rules we do not override START/FINISH with forced values; START/FINISH
        # are determined from the probe results above.

        # Näytä selkeästi START / FINISH jokaiselle kelalle ja tee napaisuustarkistus
        def _phase_check(pair, probe_choice, roles):
            plus, minus = _plain_meter_labels(pair)
            # If touching causes resistance to rise ('Nousee (normaali)'), AnturiPLUS corresponds to START
            normal = _probe_is_normal(probe_choice)
            expected_start = plus if normal else minus
            ok = (roles.get('start') == expected_start)
            return {
                'plus': plus,
                'minus': minus,
                'start': roles.get('start'),
                'finish': roles.get('finish'),
                'expected_start': expected_start,
                'phase_ok': ok,
                'normal_probe': normal,
            }

        st.subheader('START / FINISH ja napaisuustarkastus')

        # Kaula — yläkela
        n_up_info = _phase_check(north_pair, neck_upper_probe, neck_north)
        st.write(f"Kaula — Yläkela: START -> {_display_color(n_up_info['start'])} ; FINISH -> {_display_color(n_up_info['finish'])}.")
        st.write(f"(AnturiPLUS -> {_display_color(n_up_info['plus'])}, AnturiMIINUS -> {_display_color(n_up_info['minus'])})")
        st.write("Napaisuustesti: " + ("OK (napaisuudet vastaavat mittausta)" if n_up_info['phase_ok'] else "VASTAANOTTAA KÄÄNTEINEN — tarkista napaisuudet"))

        # Kaula — alakela
        n_lo_info = _phase_check(south_pair, neck_lower_probe, neck_south)
        st.write(f"Kaula — Alakela: START -> {_display_color(n_lo_info['start'])} ; FINISH -> {_display_color(n_lo_info['finish'])}.")
        st.write(f"(AnturiPLUS -> {_display_color(n_lo_info['plus'])}, AnturiMIINUS -> {_display_color(n_lo_info['minus'])})")
        st.write("Napaisuustesti: " + ("OK (napaisuudet vastaavat mittausta)" if n_lo_info['phase_ok'] else "VASTAANOTTAA KÄÄNTEINEN — tarkista napaisuudet"))

        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

        # Talla — yläkela
        b_up_info = _phase_check(bridge_north_pair, bridge_upper_probe, bridge_north)
        st.write(f"Talla — Yläkela: START -> {_display_color(b_up_info['start'])} ; FINISH -> {_display_color(b_up_info['finish'])}.")
        st.write(f"(AnturiPLUS -> {_display_color(b_up_info['plus'])}, AnturiMIINUS -> {_display_color(b_up_info['minus'])})")
        st.write("Napaisuustesti: " + ("OK (napaisuudet vastaavat mittausta)" if b_up_info['phase_ok'] else "VASTAANOTTAA KÄÄNTEINEN — tarkista napaisuudet"))

        # Talla — alakela
        b_lo_info = _phase_check(bridge_south_pair, bridge_lower_probe, bridge_south)
        st.write(f"Talla — Alakela: START -> {_display_color(b_lo_info['start'])} ; FINISH -> {_display_color(b_lo_info['finish'])}.")
        st.write(f"(AnturiPLUS -> {_display_color(b_lo_info['plus'])}, AnturiMIINUS -> {_display_color(b_lo_info['minus'])})")
        st.write("Napaisuustesti: " + ("OK (napaisuudet vastaavat mittausta)" if b_lo_info['phase_ok'] else "VASTAANOTTAA KÄÄNTEINEN — tarkista napaisuudet"))

        # Selkeä sarjakytkentäohje: mitä värejä yhdistetään
        st.markdown('---')
        st.subheader('Sarjakytkentä (mitä yhdistetään)')
        st.write('Sarjakytkentä muodostuu yhdistämällä North FINISH (-) ja South START (+).')
        st.write(f"Kaula: yhdistä {_display_color(neck_north.get('finish'))} (North FINISH) + {_display_color(neck_south.get('start'))} (South START)")
        st.write(f"Talla: yhdistä {_display_color(bridge_north.get('finish'))} (North FINISH) + {_display_color(bridge_south.get('start'))} (South START)")
        st.markdown("Huom: 'North START = HOT' — START on yleensä AnturiPLUS kun mittauksessa valinta oli 'Laskee (normaali)'. Varmista, että olet määrittänyt START/FINISH oikein kummallekin kelalle ennen juotoksia.")

        # Mapping rules (derived from measured phase START/FINISH):
        # - North START = HOT (output, typically the AnturiPLUS when probe shows 'Laskee')
        # - Series link must connect North FINISH (-) to South START (+)
        # - Ground is South FINISH (-) combined with bare (if present)

        # For neck pickup
        neck_mapping = {
            'north_start': neck_north.get('start'),
            'north_finish': neck_north.get('finish'),
            'south_start': neck_south.get('start'),
            'south_finish': neck_south.get('finish'),
        }

        neck_result = {
            'HOT': neck_mapping['north_start'],
            'SERIES_LINK': [neck_mapping['north_finish'], neck_mapping['south_start']],
            'GROUND': [neck_mapping['south_finish'], 'bare' if bare else None]
        }

        # For bridge pickup (same mapping logic)
        bridge_mapping = {
            'north_start': bridge_north.get('start'),
            'north_finish': bridge_north.get('finish'),
            'south_start': bridge_south.get('start'),
            'south_finish': bridge_south.get('finish'),
        }
        bridge_result = {
            'HOT': bridge_mapping['north_start'],
            'SERIES_LINK': [bridge_mapping['north_finish'], bridge_mapping['south_start']],
            'GROUND': [bridge_mapping['south_finish'], 'bare' if bare else None]
        }

        st.subheader('Ehdotetut kytkentäohjeet')
        st.markdown('**Kaula (neck)**')
        st.write(f"HOT (North start): {neck_result['HOT']}")
        st.write(f"Series link (NorthFINISH + SouthSTART): {neck_result['SERIES_LINK']}")
        st.write(f"Ground (SouthFINISH + bare): {neck_result['GROUND']}")

        st.markdown('**Talla (bridge)**')
        st.write(f"HOT (North start): {bridge_result['HOT']}")
        st.write(f"Series link (NorthFINISH + SouthSTART): {bridge_result['SERIES_LINK']}")
        st.write(f"Ground (SouthFINISH + bare): {bridge_result['GROUND']}")

        # Selkeä virrankulkukuvaus (esim. white -> black -> series -> red -> green -> ground)
        def _clean_join(items):
            return ' + '.join([_display_color(i) for i in (items or []) if i]) or 'tuntematon'

        st.subheader('Virrankulku (kuvaus)')
        # Neck flow
        hot_n = _display_color(neck_result.get('HOT'))
        series_n = _clean_join(neck_result.get('SERIES_LINK'))
        ground_n = _clean_join(neck_result.get('GROUND'))
        st.write(f"Kaula: Virta lähtee HOTista ({hot_n}) -> kulkee North-kelan läpi -> tulee North FINISHiin ja yhdistyy South STARTiin ({series_n}) -> jatkuu South-kelan läpi -> maadoitus ({ground_n}).")

        # Bridge flow
        hot_b = _display_color(bridge_result.get('HOT'))
        series_b = _clean_join(bridge_result.get('SERIES_LINK'))
        ground_b = _clean_join(bridge_result.get('GROUND'))
        st.write(f"Talla: Virta lähtee HOTista ({hot_b}) -> kulkee North-kelan läpi -> tulee North FINISHiin ja yhdistyy South STARTiin ({series_b}) -> jatkuu South-kelan läpi -> maadoitus ({ground_b}).")

        # Save to session_state for future steps or export
        analysis = {'neck': neck_result, 'bridge': bridge_result, 'wire_colors': wire_colors, 'bare_present': bare}
        st.session_state['analysis_result'] = analysis

        st.markdown('---')
        st.info('Tulokset tallennettu sessioon. Voit kopioida yllä olevat ohjeet tai pyytää LLM:ää selittämään seuraavat juotosaskeleet (valinnainen).')

        if lmm_available():
            if st.button('Pyydä LLM:ltä lyhyt juotosohje (valinnainen)'):
                hot_n = neck_result['HOT'] or 'tuntematon'
                link_n = ' + '.join([c for c in (neck_result['SERIES_LINK'] or []) if c]) or 'tuntematon'
                ground_n = ' + '.join([c for c in (neck_result['GROUND'] or []) if c]) or 'tuntematon'
                prompt = (
                    f"Provide a short soldering instruction in English: For the neck pickup, solder {hot_n} as HOT, join {link_n} as the series link, and connect {ground_n} to ground. Also include safety reminder and one-sentence verification steps."
                    f"Ask user if he tries ohms after soldering series link together and try to measure ohms, check resistance. Should be double. And also check if phase is correct")
                run_llm_guidance(prompt, max_tokens=220)


def next_steps_view():
    st.header("Seuraavat vaiheet")
    pt = st.session_state.get('pickup_type', 'Humbucker')
    wires = st.session_state.get('wires', [])
    current_step = st.session_state.get('interactive_step', 0)

    if wires:
        st.markdown(f"**Johdot:** {', '.join(wires)}")

    # Only recommend a compass when the user is still in the polarity-checking
    # part of the workflow (interactive steps 1-3). Do not show for measurement
    # phase (4) or later.
    pt_norm = str(pt or '').lower()
    is_humbucker = pt_norm.startswith('h') or pt_norm == 'humbucker' or st.session_state.get('hb_layout', '') == 'HH'
    if current_step < 4 and is_humbucker:
        st.markdown("Seuraavassa vaiheessa tarvitset kompassia.")

    st.markdown("---")
    st.info("Voit kopioida valmiin mittauslomakkeen tai käyttää 'Mittaukset' kenttää seuraavassa vaiheessa.")


def main():
    # Initialize session keys
    if 'start_survey' not in st.session_state:
        st.session_state['start_survey'] = False
    if 'interactive' not in st.session_state:
        st.session_state['interactive'] = False
    if 'interactive_step' not in st.session_state:
        st.session_state['interactive_step'] = 0
    if 'auto_ping_on_load' not in st.session_state:
        # Default: do not auto-ping on page load; user can opt in via the UI.
        st.session_state['auto_ping_on_load'] = False

    greet()

    # If interactive flow was started, run interactive survey (one question at a time)
    if st.session_state.get('interactive'):
        interactive_survey()
    elif st.session_state.get('start_survey'):
        survey_form()

    # If survey already submitted, show next steps
    if st.session_state.get('pickup_type'):
        next_steps_view()

    # Show LLM info at the bottom of the page (less prominent)
    show_llm_info()


if __name__ == '__main__':
    main()
