"""
Streamlit UI for pickup diagnostics.

Run:
  streamlit run app/streamlit_app.py
"""
import streamlit as st
from typing import Dict
from app.logic import find_coil_pairs, detect_center_tap, make_connection_plan
from app.llm_client import SimpleLLM
import os

st.set_page_config(page_title="Pickup Assistant", layout="centered")

st.title("AI-avusteinen kitaramikrofonien asennusopas (Humbucker)")

st.markdown("""
Tervetuloa. Tässä sovelluksessa syötät johtovärien nimet ja multimetrimittaukset (ohmit).
Sovellus ehdottaa kelapareja ja antaa vaihe‑testiohjeet. Voit pyytää myös luonnollisen kielen ohjeen paikalliselta LLM:ltä.
""")

with st.form("pickup_form"):
    pickup_type = st.selectbox("Pickup-tyyppi", ["humbucker", "single-coil", "other"])
    st.markdown("Syötä johtojen nimet/merkinnät (esim. red, white, black, green, bare).")
    wires_input = st.text_input("Johtimet (pilkuilla eroteltuna)", value="red, white, black, bare")
    wires = [w.strip() for w in wires_input.split(",") if w.strip()]
    st.markdown("Lisää mittaukset jokaisen mahdollisen parin välillä muodossa 'a-b: ohm'. Esim. red-white: 7200")
    measurements_text = st.text_area("Mittaukset", value="\n".join([f"{w1}-{w2}: " for i,w1 in enumerate(wires) for w2 in wires[i+1:]]), height=160)
    submitted = st.form_submit_button("Analyze")

if submitted:
    # Parse measurements
    meas = {}
    for line in measurements_text.splitlines():
        if not line.strip(): continue
        if ":" in line:
            left,right = line.split(":",1)
            key = left.strip()
            try:
                val = float(right.strip())
            except:
                val = float("nan")
            meas[key] = val
    st.subheader("Raw measurements")
    st.json(meas)
    st.info("Analyzing...")
    pairs = find_coil_pairs(meas)
    center = detect_center_tap(meas, pairs)
    plan = make_connection_plan(pairs, center, wires)
    st.subheader("Analysis result")
    st.markdown(plan["explanation"])
    st.markdown("### Diagram")
    st.code(plan["ascii_diagram"])
    if plan["suggestions"]:
        st.markdown("### Suggestions")
        st.markdown(plan["suggestions"])

    st.markdown("---")
    st.subheader("Compass & Phase test guidance (manual)")
    st.markdown("""
    - Napaisuuden (polarity) testaaminen kompassilla:
      1. Pidä pieni kompassi lähellä yhtä polepieceä (poista muut magneetit/metallit läheltä).
      2. Jos kompassin north‑neula vetää kohti polepiecea, merkkaa se. Toista kaikille polepiecesille.
      3. Vastakkaiset vetävät eri tavalla; kirjaa havainnot.
    - Vaiheen (phase) testaaminen:
      1. Kytke molemmat mikit vahvistimeen normaalisti.
      2. Soita samanaikaisesti; jos soundi muuttuu ohuemmaksi ja keskitaajuudet vähenevät, mikit ovat vastavaiheessa.
      3. Korjaus: swap hot ja ground yhdestä pickupista (juotos) tai sovita johtoväreihin valmistajan kaavion mukaan.
    """)

    st.markdown("---")
    st.subheader("Generate step-by-step guide from local LLM")
    llm_backend = os.environ.get("LLM_BACKEND", "llama_cpp")
    st.caption(f"Configured LLM backend: {llm_backend}")
    if st.button("Generate guide"):
        prompt = f\"\"\"You are a concise technical assistant. Given these measurements and analysis, generate a step-by-step Finnish guide for identifying coils, testing polarity with a compass, and checking/fixing phase. Measurements: {meas}. Analysis: {plan['explanation']}. Provide clear juotosohjeet and safety reminders.\"\"\"
        client = SimpleLLM()
        with st.spinner("Generating..."):
            out = client.generate(prompt, max_tokens=400)
        st.subheader("LLM-generated guide")
        st.markdown(out)

st.markdown("---")
st.caption("Disclaimer: Tämä työkalu antaa opastusta. Käyttäjä vastaa fyysisestä työstä ja turvallisuudesta.")