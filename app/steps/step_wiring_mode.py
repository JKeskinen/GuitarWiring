import streamlit as st

def step_wiring_mode(st_module):
    """Step 3: Polarity detection - determine if pickups are North or South up"""
    st.header('Step 3 — Polarity (top of pickup)')
    st.write('Use a compass over the pickup (top of pickup). Slug = North coil; Screw = South coil.')
    
    # Initialize session state keys if not present (only on first run)
    if 'neck_is_north_up' not in st.session_state:
        st.session_state['neck_is_north_up'] = True
    if 'bridge_is_north_up' not in st.session_state:
        st.session_state['bridge_is_north_up'] = True
    
    # Helper callbacks to update derived state when checkbox changes
    def _on_neck_toggle():
        is_north = st.session_state.get('neck_is_north_up', True)
        st.session_state['neck_orientation'] = 'Top = Slug (N) / Bottom = Screw (S)' if is_north else 'Top = Screw (S) / Bottom = Slug (N)'
        st.session_state['neck_img_choice'] = 'north' if is_north else 'south'
    
    def _on_bridge_toggle():
        is_north = st.session_state.get('bridge_is_north_up', True)
        st.session_state['bridge_orientation'] = 'Top = Slug (N) / Bottom = Screw (S)' if is_north else 'Top = Screw (S) / Bottom = Slug (N)'
        st.session_state['bridge_img_choice'] = 'north' if is_north else 'south'
    
    # Render checkboxes with callbacks to update state independently
    st.checkbox('Neck — top is Slug (N)', value=st.session_state.get('neck_is_north_up', True), key='neck_is_north_up', on_change=_on_neck_toggle)
    st.checkbox('Bridge — top is Slug (N)', value=st.session_state.get('bridge_is_north_up', True), key='bridge_is_north_up', on_change=_on_bridge_toggle)
    
    # Compute display strings based on current state (do NOT modify state here, only read it)
    neck_is_north = st.session_state.get('neck_is_north_up', True)
    bridge_is_north = st.session_state.get('bridge_is_north_up', True)
    
    neck_display = f"Neck — Top: {'NORTH' if neck_is_north else 'SOUTH'}, Bottom: {'SOUTH' if neck_is_north else 'NORTH'}"
    bridge_display = f"Bridge — Top: {'NORTH' if bridge_is_north else 'SOUTH'}, Bottom: {'SOUTH' if bridge_is_north else 'NORTH'}"
    
    st.write(neck_display)
    st.write(bridge_display)
    
    # Debug helper: show key orientation/image state when needed
    if st.checkbox('Show debug state', value=False, key='show_debug_state'):
        dbg = {
            'neck_is_north_up': st.session_state.get('neck_is_north_up'),
            'bridge_is_north_up': st.session_state.get('bridge_is_north_up'),
            'neck_img_choice': st.session_state.get('neck_img_choice'),
            'bridge_img_choice': st.session_state.get('bridge_img_choice'),
        }
        st.json(dbg)
