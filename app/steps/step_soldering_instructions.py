import streamlit as st


def _render_mapping_summary(title: str, north: list, south: list):
    """Show a compact summary of the wires assigned to each coil."""
    st.write(f"**{title}**")
    st.write(f"Upper coil: {', '.join(north) if north else '—'}")
    st.write(f"Lower coil: {', '.join(south) if south else '—'}")


def step_soldering_instructions(st_module):
    """Step 5: Soldering instructions and pre-flight phase checks."""
    st.header('Step 5 — Soldering & Phase Check')

    # Quick recap from Step 4 so the user sees what they are about to solder.
    wire_count = st.session_state.get('wire_count', 4)
    bare_present = st.session_state.get('bare_present', False)
    neck_north = st.session_state.get('neck_north_wires', [])
    neck_south = st.session_state.get('neck_south_wires', [])
    bridge_north = st.session_state.get('bridge_north_wires', [])
    bridge_south = st.session_state.get('bridge_south_wires', [])

    valid_neck = len(neck_north) == 2 and len(neck_south) == 2
    valid_bridge = len(bridge_north) == 2 and len(bridge_south) == 2

    st.subheader('What you decided so far')
    st.write(f"Conductors (excl. bare): {wire_count}")
    st.write(f"Bare/shield present: {'Yes' if bare_present else 'No'}")

    cols = st.columns(2)
    with cols[0]:
        _render_mapping_summary('Neck pickup', neck_north, neck_south)
    with cols[1]:
        _render_mapping_summary('Bridge pickup', bridge_north, bridge_south)

    if not (valid_neck and valid_bridge):
        st.warning('Mappings are incomplete. Go back to Step 4 and select two wires for each coil before soldering.')

    st.markdown('---')

    st.subheader('Phase check before soldering')
    st.markdown(
        "\n".join(
            [
                '- Set multimeter to ~20kΩ; confirm each coil pair shows a stable resistance.',
                '- Tap a pole piece with a small metal object while watching meter or scope: rising reading = probe positive on coil start.',
                '- If two pickups sound thin together after wiring, swap HOT and GROUND on one pickup to correct phase.',
            ]
        )
    )

    with st.expander('Step-by-step soldering checklist', expanded=False):
        st.markdown(
            "\n".join(
                [
                    '- Tin iron tip; keep it clean with brass wool.',
                    '- Pre-tin wire ends and the lugs you will use.',
                    '- Connect bare/shield to ground first (back of pot or common ground).',
                    '- Join the two series-link wires for each pickup; insulate the joint.',
                    '- Solder HOT lead to the selector or volume pot input.',
                    '- Solder ground lead to pot back or star ground; avoid long ground loops.',
                    '- Let joints cool; gently tug wires to ensure they are solid.',
                ]
            )
        )

    with st.expander('Quality checks after soldering', expanded=False):
        st.markdown(
            "\n".join(
                [
                    '- Measure pickup output at the jack: you should see total resistance roughly equal to the two coils in series.',
                    '- Tap-test each coil position on the switch; verify expected pickup selection and hum-cancelling modes.',
                    '- Wiggle-test the harness to ensure no intermittent joints.',
                ]
            )
        )

    st.markdown('---')

    if st.button('Continue to Step 6 (Summary)'):
        st.session_state['step'] = 6
        st.success('Moving to Step 6 — Summary & final output...')
