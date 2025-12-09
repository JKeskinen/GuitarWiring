import streamlit as st

def step_pole_assignment(st_module):
    """Step 2: Define wire colors for neck and bridge pickups"""
    st.header('Step 2 — Define wire colors')
    st.write('Choose up to 4 conductor colors for each pickup (and check bare if present).')
    COLOR_OPTIONS = ['Red', 'White', 'Green', 'Black', 'Yellow', 'Blue', 'Bare']
    col1 = st.multiselect('Neck wire colors (ordered)', COLOR_OPTIONS,
                          default=st.session_state.get('neck_wire_colors', ['Red', 'White', 'Green', 'Black']),
                          key='neck_wire_colors')
    col2 = st.multiselect('Bridge wire colors (ordered)', COLOR_OPTIONS,
                          default=st.session_state.get('bridge_wire_colors', ['Red', 'White', 'Green', 'Black']),
                          key='bridge_wire_colors')
    bare = st.checkbox('Bare (ground) present', value=st.session_state.get('bare', False), key='bare')
