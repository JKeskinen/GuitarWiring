"""
Streamlit UI for pickup diagnostics.

Run:
  streamlit run app/streamlit_app.py
"""
import sys
import pathlib

# Ensure project root is on sys.path so `from app import ...` works when
# Streamlit runs the script from the `app/` folder.
HERE = pathlib.Path(__file__).resolve()
PROJECT_ROOT = HERE.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from typing import Dict
from app.logic import find_coil_pairs, detect_center_tap, make_connection_plan
from app.llm_client import SimpleLLM
import os
from datetime import datetime

st.set_page_config(page_title="Pickup Assistant", layout="centered")

st.title("AI-avusteinen kitaramikrofonien asennusopas (Humbucker)")

st.markdown("""
Tervetuloa. Tässä sovelluksessa syötät johtovärien nimet ja multimetrimittaukset (ohmit).
Sovellus ehdottaa kelapareja ja antaa vaihe‑testiohjeet. Voit pyytää myös luonnollisen kielen ohjeen paikalliselta LLM:ltä.
""")

with st.form("pickup_form"):
    pickup_type = st.selectbox("Pickup-tyyppi", ["humbucker", "single-coil", "other"])
    st.markdown("Syötä johtojen nimet/merkinnät (esim. Punainen, Vihreä, Valkoinen, Musta).")
    wires_input = st.text_input("Johtimet (pilkuilla eroteltuna)", value="Punainen, Vihreä, Valkoinen, Musta")
    wires = [w.strip() for w in wires_input.split(",") if w.strip()]
    # Poista mahdollinen 'bare' (maa) käyttäjän syötteestä — käsitellään aina maadoituksena
    ground_name = None
    for w in wires.copy():
        if w.lower() in ("bare", "maa", "ground"):
            ground_name = w
            wires.remove(w)
    if ground_name:
        st.caption(f"Huom: '{ground_name}' käsitellään automaattisesti maadoituksena (bare) — sitä ei tarvitse lisätä johtolistaan.")
    # If user selected humbucker, ask explicitly for kelaparit (a-b pairs) instead of every combination
    if pickup_type == "humbucker":
        st.markdown("Syötä kelaparit muodossa 'a-b', pilkuilla eroteltuna. Esim. Punainen-Valkoinen, Vihreä-Musta.\n\nSeuraavaksi voit antaa kunkin kelaparin ohm-arvon.")
        # Allow user to indicate HH (two humbuckers) so we can show explicit per-pickup fields
        hb_layout = st.selectbox("Asennus","single-humbucker|HH".split("|"), index=1, format_func=lambda x: "Single humbucker" if x=="single-humbucker" else "HH (2 humbuckeria)", key="hb_layout")
        # Default pair suggestion: first-second and third-fourth if available
        if len(wires) >= 4:
            default_pairs = f"{wires[0]}-{wires[1]}, {wires[2]}-{wires[3]}"
        else:
            # fallback: pair adjacent wires
            default_pairs = ", ".join([f"{wires[i]}-{wires[i+1]}" for i in range(len(wires)-1)]) if len(wires) > 1 else ""
        pairs_input = st.text_input("Kelaparit (pilkuilla eroteltuna, a-b)", value=default_pairs)
        # Create measurements area only for the listed pairs (user fills ohm values)
        pair_list = [p.strip() for p in pairs_input.split(",") if p.strip()]
        # If user selected HH layout, show explicit per-pickup manual resistance inputs for neck and bridge
        if hb_layout == "HH":
            st.markdown("**Syötä kummankin humbuckerin kelaparit, napaisuudet ja resistanssit**")
            # Default suggestions for pairs
            def default_pair(i):
                try:
                    a,b = pair_list[i].split("-")
                    return a.strip(), b.strip()
                except Exception:
                    return (wires[i*2] if i*2 < len(wires) else f"A{i*2+1}", wires[i*2+1] if i*2+1 < len(wires) else f"B{i*2+2}")

            n_a, n_b = default_pair(0) if len(pair_list)>0 else (wires[0] if wires else "A", wires[1] if len(wires)>1 else "B")
            b_a, b_b = default_pair(1) if len(pair_list)>1 else (wires[2] if len(wires)>2 else "C", wires[3] if len(wires)>3 else "D")

            st.markdown("Kaulamikin (Neck)")
            st.text("Syötä ensin ylempi kelapari (upper coil):")
            neck_upper_pair = st.text_input("Neck upper pair (a-b)", value=f"{n_a}-{n_b}", key="form_neck_upper_pair")
            neck_upper_polarity = st.selectbox("Neck upper polarity", options=["Tuntematon","North","South","Start","End"], index=0, key="form_neck_upper_polarity")
            neck_upper_r = st.number_input("Neck upper coil resistance (Ω)", min_value=0.0, value=0.0, key="form_neck_upper_r")

            st.text("Syötä alempi kelapari (lower coil):")
            neck_lower_pair = st.text_input("Neck lower pair (a-b)", value=f"{b_a}-{b_b}", key="form_neck_lower_pair")
            neck_lower_polarity = st.selectbox("Neck lower polarity", options=["Tuntematon","North","South","Start","End"], index=0, key="form_neck_lower_polarity")
            neck_lower_r = st.number_input("Neck lower coil resistance (Ω)", min_value=0.0, value=0.0, key="form_neck_lower_r")

            st.markdown("Tallamikki (Bridge)")
            st.text("Syötä ensin ylempi kelapari (upper coil):")
            bridge_upper_pair = st.text_input("Bridge upper pair (a-b)", value=f"{wires[2] if len(wires)>2 else b_a}-{wires[3] if len(wires)>3 else b_b}", key="form_bridge_upper_pair")
            bridge_upper_polarity = st.selectbox("Bridge upper polarity", options=["Tuntematon","North","South","Start","End"], index=0, key="form_bridge_upper_polarity")
            bridge_upper_r = st.number_input("Bridge upper coil resistance (Ω)", min_value=0.0, value=0.0, key="form_bridge_upper_r")

            st.text("Syötä alempi kelapari (lower coil):")
            bridge_lower_pair = st.text_input("Bridge lower pair (a-b)", value=f"{wires[0] if len(wires)>0 else b_a}-{wires[1] if len(wires)>1 else b_b}", key="form_bridge_lower_pair")
            bridge_lower_polarity = st.selectbox("Bridge lower polarity", options=["Tuntematon","North","South","Start","End"], index=0, key="form_bridge_lower_polarity")
            bridge_lower_r = st.number_input("Bridge lower coil resistance (Ω)", min_value=0.0, value=0.0, key="form_bridge_lower_r")

            # Also keep a measurements text area for raw pairs (optional)
            measurements_text = st.text_area("Kelaparien mittaukset (muodossa a-b: ohm) — vapaaehtoinen", value="\n".join([f"{p}: " for p in pair_list]), height=120)
        else:
            measurements_text = st.text_area("Kelaparien mittaukset (muodossa a-b: ohm)", value="\n".join([f"{p}: " for p in pair_list]), height=160)
    else:
        st.markdown("Lisää mittaukset jokaisen mahdollisen parin välillä muodossa 'a-b: ohm'. Esim. red-white: 7200")
        measurements_text = st.text_area("Mittaukset", value="\n".join([f"{w1}-{w2}: " for i,w1 in enumerate(wires) for w2 in wires[i+1:]]), height=160)
    submitted = st.form_submit_button("Analyze")

if submitted or st.session_state.get("analyzed", False):
    # If freshly submitted, parse and store analysis in session_state.
    if submitted:
        # Parse measurements
        meas = {}
        bad_lines = []
        for idx, line in enumerate(measurements_text.splitlines(), start=1):
            if not line.strip(): continue
            if ":" in line:
                left,right = line.split(":",1)
                key = left.strip()
                try:
                    val = float(right.strip())
                    meas[key] = val
                except Exception:
                    bad_lines.append((idx, line))
            else:
                bad_lines.append((idx, line))
        if bad_lines:
            st.warning("Seuraavat rivit eivät olleet oikeassa muodossa ja jätettiin huomiotta:")
            for idx, line in bad_lines:
                st.text(f"{idx}: {line}")

        st.session_state["meas"] = meas
        st.session_state["wires"] = wires
        st.session_state["ground_name"] = ground_name
        st.session_state["pickup_type"] = pickup_type
        st.session_state["analyzed"] = True
        # If user filled HH manual fields in the form (explicit per-pickup upper/lower), include them in meas
        try:
            if pickup_type == "humbucker" and st.session_state.get("hb_layout", "HH") == "HH":
                # Read explicit per-pickup fields (upper/lower for neck and bridge)
                nu = st.session_state.get("form_neck_upper_pair")
                nl = st.session_state.get("form_neck_lower_pair")
                bu = st.session_state.get("form_bridge_upper_pair")
                bl = st.session_state.get("form_bridge_lower_pair")
                nur = float(st.session_state.get("form_neck_upper_r", 0.0) or 0.0)
                nlr = float(st.session_state.get("form_neck_lower_r", 0.0) or 0.0)
                bur = float(st.session_state.get("form_bridge_upper_r", 0.0) or 0.0)
                blr = float(st.session_state.get("form_bridge_lower_r", 0.0) or 0.0)

                def parse_pair(pair_str):
                    if not pair_str or "-" not in pair_str:
                        return None, None
                    parts = [x.strip() for x in pair_str.split("-", 1)]
                    if len(parts) != 2:
                        return None, None
                    return parts[0], parts[1]

                manual_pairs = []
                # Neck upper
                a,b = parse_pair(nu)
                if a and b and nur:
                    meas[f"{a}-{b}"] = nur
                    manual_pairs.append((a,b,nur))
                # Neck lower
                a,b = parse_pair(nl)
                if a and b and nlr:
                    meas[f"{a}-{b}"] = nlr
                    manual_pairs.append((a,b,nlr))
                # Bridge upper
                a,b = parse_pair(bu)
                if a and b and bur:
                    meas[f"{a}-{b}"] = bur
                    manual_pairs.append((a,b,bur))
                # Bridge lower
                a,b = parse_pair(bl)
                if a and b and blr:
                    meas[f"{a}-{b}"] = blr
                    manual_pairs.append((a,b,blr))

                if manual_pairs:
                    # If user provided explicit HH data, use it directly as detected pairs
                    st.session_state["pairs"] = manual_pairs
                    st.session_state["center"] = detect_center_tap(meas, manual_pairs)
                    st.session_state["plan"] = make_connection_plan(manual_pairs, st.session_state["center"], wires)
                    # store meas back after adding manual items
                    st.session_state["meas"] = meas
                else:
                    # Fallback to automatic detection if explicit manual pairs not provided
                    st.session_state["pairs"] = find_coil_pairs(meas)
                    st.session_state["center"] = detect_center_tap(meas, st.session_state["pairs"])
                    st.session_state["plan"] = make_connection_plan(st.session_state["pairs"], st.session_state["center"], wires)
                # done
                raise SystemExit
        except SystemExit:
            # We've already set pairs/plan above for manual case; continue normally
            pass
        except Exception:
            # On any unexpected error, fall back to automatic detection
            st.session_state["pairs"] = find_coil_pairs(meas)
            st.session_state["center"] = detect_center_tap(meas, st.session_state["pairs"])
            st.session_state["plan"] = make_connection_plan(st.session_state["pairs"], st.session_state["center"], wires)
        else:
            # If not a manual HH or try block didn't set pairs, run default detection
            if "pairs" not in st.session_state:
                st.session_state["pairs"] = find_coil_pairs(meas)
                st.session_state["center"] = detect_center_tap(meas, st.session_state["pairs"])
                st.session_state["plan"] = make_connection_plan(st.session_state["pairs"], st.session_state["center"], wires)

    # Load from session_state for rendering (works both immediately and on subsequent form submits)
    meas = st.session_state.get("meas", {})
    wires = st.session_state.get("wires", wires)
    ground_name = st.session_state.get("ground_name", ground_name)
    pickup_type = st.session_state.get("pickup_type", pickup_type)
    pairs = st.session_state.get("pairs", [])
    center = st.session_state.get("center")
    plan = st.session_state.get("plan", {"explanation":"","ascii_diagram":"","suggestions":""})

    # Pickup layout display (unified with the form's `hb_layout`)
    st.markdown("---")
    is_hh = (pickup_type == "humbucker" and st.session_state.get("hb_layout", "HH") == "HH")
    st.markdown(f"**Kitaran asennus:** {'HH (2 humbuckeria)' if is_hh else 'Single (1 mikki)'}")

    st.subheader("Raakamittaukset")
    st.json(meas)
    st.info("Analysoidaan...")
    st.subheader("Analyysin tulos")
    # Toggle: näytä tai piilota yksityiskohtaiset diagrammit ja ehdotukset
    show_details = st.checkbox("Näytä diagrammi ja ehdotukset", value=False)
    st.markdown(plan["explanation"]) 
    if show_details:
        st.markdown("### Diagrammi")
        st.code(plan["ascii_diagram"])
        if plan.get("suggestions"):
            st.markdown("### Ehdotukset")
            st.markdown(plan["suggestions"])
        # Näytetään tunnistetut johdinparit selkeästi väreillä
        if pairs:
            st.subheader("Johdinparit")
            # Esimerkkivärijärjestys: Punainen, Vihreä, Valkoinen, Musta
            color_names = ["Punainen", "Vihreä", "Valkoinen", "Musta"]
            # Jos enemmän pareja löytyi, laajennetaan nimeämistä numeerisesti
            pair_lines = []
            for i, p in enumerate(pairs):
                # pairs entries are (a, b, resistance)
                try:
                    left, right, _ = p
                except Exception:
                    # Fallback: if pair is a 2-tuple
                    try:
                        left, right = p
                    except Exception:
                        continue
                name_left = color_names[i*2] if i*2 < len(color_names) else f"Johto{ i*2 + 1 }"
                name_right = color_names[i*2+1] if i*2+1 < len(color_names) else f"Johto{ i*2 + 2 }"
                pair_lines.append(f"{name_left} (`{left}`)  <-->  {name_right} (`{right}`)")
            for line in pair_lines:
                st.write(line)

    # If we've detected at least two pairs, compute resistances and support HH mapping
    from app.logic import compute_coil_resistances
    if len(pairs) >= 2:
        st.markdown("---")
        st.subheader("Laskelmat: kelojen resistanssit ja yhdistelmät")
        # Allow the user to map which pairs belong to which pickup when HH selected
        if is_hh:
            st.markdown("Valitse HH-analyysi (neck + bridge). Jos annoit manuaaliset kelaparit, käytetään niitä suoraan.")
            # If user provided explicit per-pickup HH fields, use them directly
            if st.session_state.get("form_neck_upper_pair") or st.session_state.get("form_neck_lower_pair"):
                if len(pairs) >= 4:
                    neck_pairs = [pairs[0], pairs[1]]
                    bridge_pairs = [pairs[2], pairs[3]]
                    neck_res = compute_coil_resistances(neck_pairs)
                    bridge_res = compute_coil_resistances(bridge_pairs)

                    st.markdown("**Kaulamikin resistanssit (upper, lower, series, parallel)**")
                    st.write(neck_res)
                    st.markdown("**Tallamikin resistanssit (upper, lower, series, parallel)**")
                    st.write(bridge_res)
                else:
                    st.warning("Manuaalinen HH-data tunnistettu, mutta pareja ei ole tarpeeksi (tarvitaan 4 kelaparia: neck upper/lower, bridge upper/lower).")
                    st.info("Voit täydentää mittaukset tai käyttää automaattista tunnistusta alla.")
            else:
                # fallback to older mapping UI when no explicit manual HH fields provided
                st.markdown("Valitse, mitkä tunnistetut parit kuuluvat kaula- ja tallamikkiin. Oletus: pari 1 = kaula, pari 2 = talla.")
                pair_options = [f"Pari {i+1}: {p[0]}-{p[1]} ({p[2]:.1f}Ω)" if len(p)>=3 else f"Pari {i+1}: {p[0]}-{p[1]}" for i,p in enumerate(pairs)]
                neck_choice = st.selectbox("Kaulamikin pari", options=pair_options, index=0, key="calc_neck_choice")
                # Build bridge options excluding the neck choice to avoid selecting the same pair twice
                bridge_options = [opt for opt in pair_options if opt != neck_choice]
                if not bridge_options:
                    # Only one unique pair available — allow selecting the same but warn
                    st.warning("Vain yksi tunnistettu pari saatavilla — tarkista mittaukset tai käytä manuaalista syöttöä.")
                    bridge_options = pair_options
                bridge_choice = st.selectbox("Tallamikin pari", options=bridge_options, index=0, key="calc_bridge_choice")

                # resolve indices in original pairs list
                neck_idx = pair_options.index(neck_choice)
                bridge_idx = pair_options.index(bridge_choice)

                # compute resistances for neck and bridge (single-pair each)
                neck_res = compute_coil_resistances([pairs[neck_idx]])
                # if user accidentally chose the same pair for both, show a warning and avoid duplicate computation
                if neck_idx == bridge_idx:
                    st.warning("Valitsit saman parin sekä kaula- että tallamikille — voit syöttää tallamikille mittaukset manuaalisesti alla.")
                    bridge_res = None
                else:
                    bridge_res = compute_coil_resistances([pairs[bridge_idx]])

                st.markdown("**Kaulamikin resistanssit**")
                st.write(neck_res)

                # If bridge_res is missing or incomplete, show manual inputs for bridge coils so user can enter both coil resistances
                st.markdown("**Tallamikin resistanssit**")
                if bridge_res is None or not bridge_res.get("r2"):
                    st.info("Tallamikille ei ole saatavilla erillistä paria automaattisesti — syötä tallamikille kelaparin tiedot manuaalisesti tai valitse toinen pari yllä.")
                    b_wires_manual = st.text_input("Talla - johdinparit (muoto a-b, erota pilkulla useammalle):", value="", key="calc_bridge_manual_wires")
                    b_wire_list = [s.strip() for s in b_wires_manual.replace(',', ' ').split() if s.strip()]
                    b_r1 = st.number_input("Talla - kela 1 vastus (ohm)", min_value=0.0, value=0.0, key="calc_bridge_manual_r1")
                    b_r2 = st.number_input("Talla - kela 2 vastus (ohm)", min_value=0.0, value=0.0, key="calc_bridge_manual_r2")
                    # compute simple series/parallel from manual values if provided
                    if b_r1 and b_r2:
                        b_series = b_r1 + b_r2
                        b_parallel = (b_r1 * b_r2) / (b_r1 + b_r2) if (b_r1 + b_r2) != 0 else None
                    else:
                        b_series = b_parallel = None
                    st.write({"r1": b_r1 or None, "r2": b_r2 or None, "series": b_series, "parallel": b_parallel})
                else:
                    st.write(bridge_res)
        else:
            # Single or simple humbucker case: take first two pairs as the pickup's coils
            res = compute_coil_resistances(pairs)
            st.markdown("**Kelojen resistanssit (r1, r2, sarja, rinnakkais)**")
            st.write(res)

            # Napaisuuden (polarity) varmistus: anna käyttäjälle valinta per kela
            st.markdown("---")
            st.subheader("Napaisuuden varmistus")
            st.markdown("Valitse jokaisen kelan napaisuus (North/South) tai jätä 'Tuntematon' jos et ole varma. Voit pyytää paikallista LLM:ää ehdottamaan arviota mittausten perusteella.")
            polarity_keys = []
            for i, p in enumerate(pairs):
                try:
                    a, b, _ = p
                except Exception:
                    # fallback if pair is 2-tuple
                    try:
                        a, b = p
                    except Exception:
                        continue
                key = f"polarity_{i}"
                polarity_keys.append(key)
                current = st.session_state.get(key, "Tuntematon")
                choice = st.radio(f"Kela {i+1}: {a} <--> {b} — napaisuus", options=["Tuntematon", "North", "South"], index=["Tuntematon", "North", "South"].index(current), key=key)

            # LLM-ehdotus napaisuuksista
            if st.button("Pyydä LLM ehdottamaan napaisuutta"):
                # Build a prompt describing the situation
                pairs_desc = ", ".join([f"{p[0]}-{p[1]} ({p[2]:.1f}Ω)" if len(p) >=3 else f"{p[0]}-{p[1]}" for p in pairs])
                prompt = (
                    f"Arvioi seuraavien kelapareiden napaisuus (North tai South) ja kirjoita selkeät suositukset ja miten varmistat sen kompassilla tai ruuvimeisselitestillä. "
                    f"Mittaukset: {pairs_desc}. Anna vastaus muodossa 'Kela1: North', 'Kela2: South' tai käytä johtojen nimiä.'"
                )
                client = SimpleLLM()
                with st.spinner("Kysytään paikalliselta LLM:ltä..."):
                    llm_out = client.generate(prompt, max_tokens=300)
                st.markdown("**LLM ehdotus napaisuudesta:**")
                st.code(llm_out)

                # Try to parse simple suggestions from LLM output
                lowered = llm_out.lower()
                applied = 0
                for i, p in enumerate(pairs):
                    # identify wires
                    try:
                        a, b, _ = p
                    except Exception:
                        try:
                            a, b = p
                        except Exception:
                            continue
                    a_low = a.lower()
                    b_low = b.lower()
                    # If LLM mentions the wire names and 'north'/'south', apply suggestion
                    if a_low in lowered or b_low in lowered:
                        if 'north' in lowered and (a_low in lowered or b_low in lowered):
                            st.session_state[f"polarity_{i}"] = 'North'
                            applied += 1
                        elif 'south' in lowered and (a_low in lowered or b_low in lowered):
                            st.session_state[f"polarity_{i}"] = 'South'
                            applied += 1
                if applied:
                    st.success(f"Automaattisesti asetettu {applied} napaisuusehdotusta.")
                else:
                    st.info("LLM ehdotus annettiin, mutta automaattinen asetus ei löytänyt sopivia merkintöjä. Valitse napaisuus manuaalisesti.")

    # Wiring / sarjakytkentäohjeet, perustuu tunnistettuihin kelapareihin
    # Use unified layout choice
    pickup_layout = "HH (neck + bridge)" if is_hh else "Single humbucker"

    # Single humbucker flow (vain yksi humbucker): vaatii vähintään 2 kelaparia
    if pickup_layout == "Single humbucker" and len(pairs) >= 2:
        # Näytä ehdotetut kelaparit ja pyydä käyttäjältä vahvistus start/finish -merkinnöille
        c1a, c1b, _ = pairs[0]
        c2a, c2b, _ = pairs[1]
        st.markdown("---")
        st.subheader("Vahvista kelojen start/finish -sijoitus")
        st.markdown("Valitse kumpi johto on kelan start ja kumpi finish. Jos olet mittaamalla varmistanut start/finish -suhteen, valitse ne täällä.")
        with st.form("start_finish_form"):
            start1 = st.radio(f"Kela 1: valitse start", options=[c1a, c1b], index=0, key="sf1")
            start2 = st.radio(f"Kela 2: valitse start", options=[c2a, c2b], index=0, key="sf2")
            confirm = st.form_submit_button("Vahvista start/finish ja piirrä diagrammi")

        if 'confirm' in locals() and confirm:
            # Määritä start/finish sen perusteella mitä käyttäjä valitsi
            s1 = start1
            f1 = c1b if start1 == c1a else c1a
            s2 = start2
            f2 = c2b if start2 == c2a else c2a

            wiring_lines = []
            wiring_lines.append("Suositellut kytkentävaiheet sarjaankytkentää varten:")
            wiring_lines.append(f" - Liitä {f1} -> {s2} (finish ensimmäisestä -> start toisen).")
            hot = s1
            ground = ground_name if ground_name else f2
            wiring_lines.append(f" - Hot (signaali) = {hot}")
            wiring_lines.append(f" - Ground (maa) = {ground}")
            if center:
                wiring_lines.append(f" - Keskitappi: {center} (voi olla käytössä split- tai tap-kytkennässä).")
            wiring_text = "\n".join(wiring_lines)
            st.markdown("---")
            st.subheader("Wiring-ohje")
            st.code(wiring_text)
            st.markdown("Varmista vaihe ruuvimeisselitestillä ennen lopullista juotosta ja merkitse start/finish selkeästi.")

            # Näytä myös päivitetty ASCII-diagrammi selvennyksellä HOT/GND
            st.markdown("### Päivitetty ASCII-diagrammi (vahvistettu start/finish)")
            ascii_lines = []
            ascii_lines.append(f" Coil1: ({s1})--->[windings]--->({f1})")
            ascii_lines.append(f" Coil2: ({s2})--->[windings]--->({f2})")
            ascii_lines.append("")
            ascii_lines.append(f" -> HOT (tuleva signaali)  --> {hot}")
            ascii_lines.append(f" -> GND (maa, potikan runkoon) --> {ground}")
            if center:
                ascii_lines.append(f" Keskitappi: {center} (käytettävissä split- tai tap-kytkentään)")
            st.code("\n".join(ascii_lines))

        st.markdown("---")
        st.subheader("Compass & Vaihe (phase) -testaus (manuaalinen)")
        st.markdown("""
        - Napaisuuden (polarity) testaaminen kompassilla:
            1. Pidä pieni kompassi kelan lähellä (poista muut magneetit/metallit läheltä).
            2. Jos kompassin north‑neula vetää kohti kelaa, merkkaa se North. Toista toiselle kelalle.
            3. Kirjaa, mitkä polepiecet vetävät pohjoiseen ja mitkä etelään — näistä näkee napaisuuden suuntauksen.

        - Vaiheen (phase) testaaminen — ruuvimeisselitesti (nopea käytännön testi):
            1. Kiinnitä pieni metallinen työkalu (esim. ruuvimeisseli) varovasti yhden polepiecen päälle siten, että se koskettaa metallipintaa.
            2. Aseta yleismittarin mittakärjet haluttuihin johtoihin (esimerkiksi musta mittakärki = miinus, punainen = plus).
            3. Nosta ruuvimeisseliä hieman irti polepiecesta ja seuraa ohm-mittauksen muutosta:
                 - Jos ohm ARVON NOUSEE, mittausjohdot ovat samasuuntaiset ("miinus‑miinus, plus‑plus") → vaihe oikea.
                 - Jos ohm ARVON LASKEE, mittausjohdot ovat vastakkaiset ("miinus‑plus, plus‑miinus") → vaihe väärinpäin; käännä yhden parin mittausjohtojen suunta (tai juotosvaihe / hot-ground).

        Esimerkki käytännöstä:
            - Oletetaan, että punainen ja vihreä muodostavat kelaparin.
            - Mittaat punaisen mittakärjen olevan miinus (-) ja vihreän plus (+).
            - Jos ruuvimeisselitesti antaa LASKEVAN ohmin, pari on väärässä vaiheessa: vaihda punainen -> + ja vihreä -> - (eli swap hot/ground tai korjaa johtoliitännät).
            - Kun vaihe on oikein, löydät myös "start" ja "finish" -merkkauksen: tässä esimerkissä punainen = start, vihreä = finish.

        Turvallisuus: käytä pieniä metalliesineitä varoen äläkä kosketa voimakkaita magneetteja tai jännitteellisiä osia. Irrota laitteet virtalähteestä ennen juotostöitä.
        """)

        # Visual guide (ASCII) for the screwdriver polarity/phase test
        st.markdown("### Visual guide — ruuvimeisselitesti")
        st.code("""
         Polepiece (metal)
             |
            [*]  <- metal tool (screwdriver)
             |
        red (-)  ----[windings]----  green (+)
           |                          |
           +--------[multimeter]------+

        Probes: black probe -> red (miinus), red probe -> green (plus)

        - Jos OHM NOUSEE: mittausjohdot ovat samasuuntaiset ("miinus‑miinus, plus‑plus") -> vaihe OK.
        - Jos OHM LASKEE: mittausjohdot ovat vastakkaiset ("miinus‑plus, plus‑miinus") -> vaihe väärinpäin; vaihda yhden parin johdot tai swap hot/ground.

        Esimerkki: punainen = start, vihreä = finish. Jos ruuvimeisselitesti antaa LASKEVAN ohmin, käännä punainen -> + ja vihreä -> -.
        """)

    # HH (kaksi humbuckeria) flow
    elif pickup_layout.startswith("HH"):
        st.markdown("---")
        st.subheader("HH-asennus (kaula + talla) — täytä kentät järjestyksessä")

        # Step 1: show mic style
        st.markdown("**1) Kitaran mikitystyyli:** HH (kaksi humbuckeria)")

        # Helper: use detected pairs if any
        detected_pairs = st.session_state.get("pairs", pairs)

        # --- Kaula (Neck) ---
        st.markdown("---")
        st.header("Kaulamikki (Neck)")

        # Step 2: Kaulamikin napaisuudet (yläkela, alakela)
        st.markdown("**2) Kaulamikin napaisuudet**")
        neck_polarity_upper = st.selectbox("Yläkela (North/South/Tuntematon)", options=["Tuntematon","North","South"], index=0, key="neck_polarity_upper")
        neck_polarity_lower = st.selectbox("Alakela (North/South/Tuntematon)", options=["Tuntematon","North","South"], index=0, key="neck_polarity_lower")

        # Step 3 & 4: ylä- ja alakelan johdinparit ja phase (start/finish)
        st.markdown("**3) Yläkelan johdinpari ja phase**")
        # Offer choices from detected pairs or allow manual entry
        neck_pair_options = [f"{i+1}: {p[0]}-{p[1]} ({p[2]:.1f}Ω)" if len(p)>=3 else f"{i+1}: {p[0]}-{p[1]}" for i,p in enumerate(detected_pairs)]
        neck_upper_choice = st.selectbox("Valitse yläkelan pari (tai valitse manuaali)", options=["Manuaali"] + neck_pair_options, index=1 if neck_pair_options else 0, key="neck_upper_choice")
        # Sijainti-valinta: missä tämä pari sijaitsee (voi olla kaula tai talla)
        neck_upper_location = st.selectbox("Sijainti (yläkela)", options=["Kaula","Talla"], index=0, key="neck_upper_location")
        # Napaisuusjärjestys: miten ylä/ala määritellään napaisuuksiltaan
        neck_polarity_pattern = st.selectbox("Napaisuus (ylä/ala)", options=["Ylä=North / Ala=South","Ylä=South / Ala=North","Tuntematon"], key="neck_polarity_pattern")
        if neck_upper_choice == "Manuaali":
            nu_manual = st.text_input("Yläkelan pari (muoto a-b)", key="neck_upper_manual")
            nu_wires = [s.strip() for s in (nu_manual or "").split("-") if s.strip()]
            nu_phase = st.selectbox("Yläkelan phase (valitse start-johto)", options=["start","finish"], index=0, key="neck_upper_phase")
        else:
            # parse selection
            idx = int(neck_upper_choice.split(":")[0]) - 1
            try:
                nu_a, nu_b, nu_r = detected_pairs[idx]
            except Exception:
                nu_a, nu_b = detected_pairs[idx][0], detected_pairs[idx][1]
                nu_r = detected_pairs[idx][2] if len(detected_pairs[idx])>=3 else 0.0
            nu_wires = [nu_a, nu_b]
            nu_phase = st.selectbox("Yläkelan phase (valitse start-johto)", options=[nu_a, nu_b], index=0, key="neck_upper_phase")

        st.markdown("**4) Alakelan johdinpari ja phase**")
        # Option to auto-fill alakelan pari: choose first other pair that isn't the upper
        auto_fill_lower = st.checkbox("Automaattinen alakelan valinta yläkelan perusteella", value=True, key="neck_auto_lower")
        neck_lower_choice = None
        nl_wires = []
        nl_r = 0.0
        if auto_fill_lower and neck_upper_choice != "Manuaali":
            try:
                upper_idx = int(neck_upper_choice.split(":")[0]) - 1
                # pick first different pair as lower
                lower_idx = next(i for i in range(len(detected_pairs)) if i != upper_idx)
                nl_pair = detected_pairs[lower_idx]
                nl_a = nl_pair[0]; nl_b = nl_pair[1]; nl_r = nl_pair[2] if len(nl_pair)>=3 else 0.0
                nl_wires = [nl_a, nl_b]
                st.info(f"Alakelan pari valittu automaattisesti: {nl_a}-{nl_b}")
                neck_lower_choice = f"{lower_idx+1}: {nl_a}-{nl_b}"
                nl_phase = st.selectbox("Alakelan phase (valitse start-johto)", options=[nl_a, nl_b], index=0, key="neck_lower_phase")
            except StopIteration:
                st.warning("Ei löydy toista paria automaattisesti; määritä alakelan pari manuaalisesti.")
            except Exception:
                st.warning("Alakelan automaattinen valinta epäonnistui; valitse manuaalisesti.")
        else:
            neck_lower_choice = st.selectbox("Valitse alakelan pari (tai Manuaali)", options=["Manuaali"] + neck_pair_options, index=2 if len(neck_pair_options)>1 else 0, key="neck_lower_choice")
            if neck_lower_choice == "Manuaali":
                nl_manual = st.text_input("Alakelan pari (muoto a-b)", key="neck_lower_manual")
                nl_wires = [s.strip() for s in (nl_manual or "").split("-") if s.strip()]
                nl_phase = st.selectbox("Alakelan phase (valitse start-johto)", options=["start","finish"], index=0, key="neck_lower_phase")
            else:
                idx2 = int(neck_lower_choice.split(":")[0]) - 1
                try:
                    nl_a, nl_b, nl_r = detected_pairs[idx2]
                except Exception:
                    nl_a, nl_b = detected_pairs[idx2][0], detected_pairs[idx2][1]
                    nl_r = detected_pairs[idx2][2] if len(detected_pairs[idx2])>=3 else 0.0
                nl_wires = [nl_a, nl_b]
                nl_phase = st.selectbox("Alakelan phase (valitse start-johto)", options=[nl_a, nl_b], index=0, key="neck_lower_phase")

        # Step 5: Ohm määrät johdinpareille
        st.markdown("**5) Syötä ohm-arvot johdinpareille**")
        n_r_upper = st.number_input("Yläkela - pari ohm", value=float(nu_r) if 'nu_r' in locals() and nu_r is not None else 0.0, min_value=0.0, key="neck_r_upper")
        n_r_lower = st.number_input("Alakela - pari ohm", value=float(nl_r) if 'nl_r' in locals() and nl_r is not None else 0.0, min_value=0.0, key="neck_r_lower")

        # Step 6: LLM tutkii humbuckerin johdot ja kertoo sarjakytkentäehdotuksen
        st.markdown("**6) LLM ehdotus: miten yhdistää kelat sarjaan (neck)**")
        if st.button("Pyydä LLM:ltä ehdotus (kaula)", key="llm_neck_btn"):
            prompt = f"Anna selkeä suositus, miten yhdistetään humbuckerin kaulan ylä- ja alakelan johdot sarjakytkentää varten.\nYläkela pari: {nu_wires} phase: {nu_phase} ohm: {n_r_upper}.\nAlakela pari: {nl_wires} phase: {nl_phase} ohm: {n_r_lower}.\nKerro mitä liittää yhteen (finish->start) ja mikä on hot/ground."
            client = SimpleLLM()
            with st.spinner("Kysytään paikalliselta LLM:ltä..."):
                neck_llm = client.generate(prompt, max_tokens=300)
            st.code(neck_llm)

        # --- Bridge (Talla) ---
        st.markdown("---")
        st.header("Tallamikki (Bridge)")

        st.markdown("**7) Täytä Tallamikin tiedot: napaisuudet, ylä/ala kelat, parit, phase ja ohmit**")
        bridge_polarity_upper = st.selectbox("Talla Yläkela (North/South/Tuntematon)", options=["Tuntematon","North","South"], index=0, key="bridge_polarity_upper")
        bridge_polarity_lower = st.selectbox("Talla Alakela (North/South/Tuntematon)", options=["Tuntematon","North","South"], index=0, key="bridge_polarity_lower")

        bridge_pair_options = [f"{i+1}: {p[0]}-{p[1]} ({p[2]:.1f}Ω)" if len(p)>=3 else f"{i+1}: {p[0]}-{p[1]}" for i,p in enumerate(detected_pairs)]
        bridge_upper_choice = st.selectbox("Talla yläkelan pari (tai Manuaali)", options=["Manuaali"] + bridge_pair_options, index=3 if len(bridge_pair_options)>2 else 0, key="bridge_upper_choice")
        bridge_polarity_pattern = st.selectbox("Napaisuus (ylä/ala)", options=["Ylä=North / Ala=South","Ylä=South / Ala=North","Tuntematon"], key="bridge_polarity_pattern")

        # Ensure bu_* variables exist for later use
        bu_wires = []
        bu_r = 0.0
        bu_phase = None
        if bridge_upper_choice == "Manuaali":
            bu_manual = st.text_input("Talla yläkelan pari (muoto a-b)", key="bridge_upper_manual")
            bu_wires = [s.strip() for s in (bu_manual or "").split("-") if s.strip()]
            bu_phase = st.selectbox("Talla yläkelan phase (valitse start-johto)", options=["start","finish"], index=0, key="bridge_upper_phase")
        else:
            bi = int(bridge_upper_choice.split(":")[0]) - 1
            try:
                bu_a, bu_b, bu_r = detected_pairs[bi]
            except Exception:
                bu_a, bu_b = detected_pairs[bi][0], detected_pairs[bi][1]
                bu_r = detected_pairs[bi][2] if len(detected_pairs[bi])>=3 else 0.0
            bu_wires = [bu_a, bu_b]
            bu_phase = st.selectbox("Talla yläkelan phase (valitse start-johto)", options=[bu_a, bu_b], index=0, key="bridge_upper_phase")

        auto_fill_lower_b = st.checkbox("Automaattinen alakelan valinta yläkelan perusteella", value=True, key="bridge_auto_lower")
        bl_wires = []
        bl_r = 0.0
        if auto_fill_lower_b and bridge_upper_choice != "Manuaali":
            try:
                upper_bi = int(bridge_upper_choice.split(":")[0]) - 1
                lower_bi = next(i for i in range(len(detected_pairs)) if i != upper_bi)
                bl_pair = detected_pairs[lower_bi]
                bl_a = bl_pair[0]; bl_b = bl_pair[1]; bl_r = bl_pair[2] if len(bl_pair)>=3 else 0.0
                bl_wires = [bl_a, bl_b]
                st.info(f"Tallan alakelan pari valittu automaattisesti: {bl_a}-{bl_b}")
                bl_phase = st.selectbox("Talla alakelan phase (valitse start-johto)", options=[bl_a, bl_b], index=0, key="bridge_lower_phase")
            except StopIteration:
                st.warning("Ei löydy toista paria automaattisesti; määritä alakelan pari manuaalisesti.")
            except Exception:
                st.warning("Alakelan automaattinen valinta epäonnistui; valitse manuaalisesti.")
        else:
            bridge_lower_choice = st.selectbox("Talla alakelan pari (tai Manuaali)", options=["Manuaali"] + bridge_pair_options, index=4 if len(bridge_pair_options)>3 else 0, key="bridge_lower_choice")
            if bridge_lower_choice == "Manuaali":
                bl_manual = st.text_input("Talla alakelan pari (muoto a-b)", key="bridge_lower_manual")
                bl_wires = [s.strip() for s in (bl_manual or "").split("-") if s.strip()]
                bl_phase = st.selectbox("Talla alakelan phase (valitse start-johto)", options=["start","finish"], index=0, key="bridge_lower_phase")
            else:
                bj = int(bridge_lower_choice.split(":")[0]) - 1
                try:
                    bl_a, bl_b, bl_r = detected_pairs[bj]
                except Exception:
                    bl_a, bl_b = detected_pairs[bj][0], detected_pairs[bj][1]
                    bl_r = detected_pairs[bj][2] if len(detected_pairs[bj])>=3 else 0.0
                bl_wires = [bl_a, bl_b]
                bl_phase = st.selectbox("Talla alakelan phase (valitse start-johto)", options=[bl_a, bl_b], index=0, key="bridge_lower_phase")

        b_r_upper = st.number_input("Talla yläkela - pari ohm", value=float(bu_r) if 'bu_r' in locals() and bu_r is not None else 0.0, min_value=0.0, key="bridge_r_upper")
        b_r_lower = st.number_input("Talla alakela - pari ohm", value=float(bl_r) if 'bl_r' in locals() and bl_r is not None else 0.0, min_value=0.0, key="bridge_r_lower")

        if st.button("Pyydä LLM ehdottamaan sarjakytkentää (talla)", key="llm_bridge_btn"):
            prompt_b = f"Anna suositus, miten yhdistetään humbuckerin talla ylä- ja alakelan johdot sarjaan.\nYlä: {bu_wires} phase: {bu_phase} ohm: {b_r_upper}.\nAla: {bl_wires} phase: {bl_phase} ohm: {b_r_lower}."
            client = SimpleLLM()
            with st.spinner("Kysytään paikalliselta LLM:ltä..."):
                bridge_llm = client.generate(prompt_b, max_tokens=300)
            st.code(bridge_llm)

        # Finally: compute series/parallel ohms for both humbuckers
        st.markdown("---")
        st.subheader("Lasketaan sarja- ja rinnankytkentäresistanssit")
        from app.logic import compute_coil_resistances
        neck_res = {"r1": n_r_upper, "r2": n_r_lower}
        try:
            neck_series = neck_res["r1"] + neck_res["r2"] if neck_res["r1"] and neck_res["r2"] else None
            neck_parallel = (neck_res["r1"] * neck_res["r2"]) / (neck_res["r1"] + neck_res["r2"]) if neck_res["r1"] and neck_res["r2"] and (neck_res["r1"] + neck_res["r2"]) != 0 else None
        except Exception:
            neck_series = neck_parallel = None

        bridge_res = {"r1": b_r_upper, "r2": b_r_lower}
        try:
            bridge_series = bridge_res["r1"] + bridge_res["r2"] if bridge_res["r1"] and bridge_res["r2"] else None
            bridge_parallel = (bridge_res["r1"] * bridge_res["r2"]) / (bridge_res["r1"] + bridge_res["r2"]) if bridge_res["r1"] and bridge_res["r2"] and (bridge_res["r1"] + bridge_res["r2"]) != 0 else None
        except Exception:
            bridge_series = bridge_parallel = None

        st.markdown("**Kaula (Neck)**")
        st.write({"r1": neck_res.get("r1"), "r2": neck_res.get("r2"), "series": neck_series, "parallel": neck_parallel})
        st.markdown("**Talla (Bridge)**")
        st.write({"r1": bridge_res.get("r1"), "r2": bridge_res.get("r2"), "series": bridge_series, "parallel": bridge_parallel})

        st.markdown("---")
        st.subheader("Compass & Vaihe (phase) -testaus (manuaalinen)")
        st.markdown("Katso edellinen single-kappaleen ohjeistus — toista testit kummallekin humbuckerille erikseen.")

    st.markdown("---")
    st.subheader("Luo vaiheittainen ohje paikalliselta LLM:ltä")
    llm_backend = os.environ.get("LLM_BACKEND", "ollama")
    st.caption(f"Konfiguroitu LLM-backend: {llm_backend}")

    # Full guide generation (existing behavior)
    if st.button("Luo ohje"):
        prompt = f"""You are a concise technical assistant. Given these measurements and analysis, generate a step-by-step Finnish guide for identifying coils, testing polarity with a compass, and checking/fixing phase. Measurements: {meas}. Analysis: {plan['explanation']}. Provide clear juotosohjeet and safety reminders."""
        client = SimpleLLM()
        with st.spinner("Luodaan ohjetta..."):
            out = client.generate(prompt, max_tokens=400)
        st.subheader("LLM:n luoma ohje")
        st.markdown(out)

    # Quick test: ask Ollama to write a short observation and show it in an editable text area
    st.markdown("### Nopeampi testi: pyydä LLM kirjaamaan lyhyt havainto")
    if st.button("Kirjoita havainto LLM:ltä"):
        quick_prompt = (
            f"Kirjoita lyhyt suomenkielinen havainto seuraavista mittaustuloksista ja analyysista."
            f" Mittaukset: {meas}. Analyysi: {plan['explanation']}"
        )
        client = SimpleLLM()
        with st.spinner("Kysytään paikalliselta LLM:ltä..."):
            obs = client.generate(quick_prompt, max_tokens=200)
        # If the client returns an error-like message, surface it
        if isinstance(obs, str) and (obs.startswith("Error connecting") or obs.startswith("Ollama server returned") or obs.startswith("LLM backend not configured")):
            st.error(obs)
        else:
            st.session_state["llm_test_observation"] = obs
            st.session_state["llm_test_observation_time"] = datetime.utcnow().isoformat(timespec="seconds") + "Z"

    # Show editable observation populated from session state (if present)
    obs_val = st.session_state.get("llm_test_observation", "")
    st.text_area("LLM:n havainto (voit muokata)", value=obs_val, height=200, key="llm_obs_area")
    # Näytetään selkeä merkintä, kun teksti on luotu LLM:llä
    obs_time = st.session_state.get("llm_test_observation_time")
    if obs_val:
        badge = f"**Luotu paikallisella LLM:llä**"
        if obs_time:
            badge += f" — {obs_time}"
        st.markdown(badge)

st.markdown("---")
st.caption("Disclaimer: Tämä työkalu antaa opastusta. Käyttäjä vastaa fyysisestä työstä ja turvallisuudesta.")
