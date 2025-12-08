import streamlit as st
import streamlit.components.v1 as components

# Color emoji mapping for UI
COLOR_EMOJI = {
    'Red': '🔴',
    'White': '⚪',
    'Green': '🟢',
    'Black': '⚫',
    'Yellow': '🟡',
    'Blue': '🔵',
    'Bare': '⚫'
}

def step_measurements(st_module):
    """Step 4: Wire definition, measurements, and coil mapping."""
    st.header('Step 4 — Wire Definition & Measurements')
    
    # Section 1: Wire count and bare wire
    st.subheader('1️⃣ Conductor Count')
    col1, col2 = st.columns([2, 1])
    with col1:
        wire_count = st.slider('Number of conductors (excluding bare)', 1, 4, 
                               value=st.session_state.get('wire_count', 4), 
                               key='wire_count')
    with col2:
        bare_present = st.checkbox('Bare wire present', 
                                   value=st.session_state.get('bare_present', False), 
                                   key='bare_present')
    
    st.markdown('---')
    
    # Section 2: Wire color selection for both pickups
    st.subheader('2️⃣ Assign Wire Colors')
    COLOR_OPTIONS = ['Red', 'White', 'Green', 'Black', 'Yellow', 'Blue']
    defaults = ['Red', 'White', 'Green', 'Black']
    
    # Initialize wire colors in session state if not present
    if 'wire_colors_neck' not in st.session_state:
        st.session_state['wire_colors_neck'] = defaults[:wire_count]
    if 'wire_colors_bridge' not in st.session_state:
        st.session_state['wire_colors_bridge'] = defaults[:wire_count]
    
    neck_colors = st.session_state.get('wire_colors_neck', defaults[:wire_count])
    bridge_colors = st.session_state.get('wire_colors_bridge', defaults[:wire_count])
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write('**Neck Pickup**')
        new_neck = []
        for i in range(wire_count):
            default_color = defaults[i] if i < len(defaults) else 'Black'
            current = neck_colors[i] if i < len(neck_colors) else default_color
            idx = COLOR_OPTIONS.index(current) if current in COLOR_OPTIONS else 0
            color = st.selectbox(
                f'Wire {i+1}',
                COLOR_OPTIONS,
                index=idx,
                key=f'neck_wire_color_{i}',
                label_visibility='collapsed'
            )
            new_neck.append(color)
        st.session_state['wire_colors_neck'] = new_neck
    
    with col2:
        st.write('**Bridge Pickup**')
        new_bridge = []
        for i in range(wire_count):
            default_color = defaults[i] if i < len(defaults) else 'Black'
            current = bridge_colors[i] if i < len(bridge_colors) else default_color
            idx = COLOR_OPTIONS.index(current) if current in COLOR_OPTIONS else 0
            color = st.selectbox(
                f'Wire {i+1}',
                COLOR_OPTIONS,
                index=idx,
                key=f'bridge_wire_color_{i}',
                label_visibility='collapsed'
            )
            new_bridge.append(color)
        st.session_state['wire_colors_bridge'] = new_bridge
    
    st.markdown('---')
    
    # Section 3: Coil resistance measurements
    st.subheader('3️⃣ Measure Coil Resistances')
    st.info('💡 Set multimeter to ~20kΩ range. Connect probes between two wires. Record the resistance in kΩ (e.g., 3.85).')
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write('**Neck Pickup**')
        n_up = st.number_input('Upper coil (kΩ)', 
                               min_value=0.0, format='%.2f',
                               value=st.session_state.get('n_up', 0.0),
                               key='n_up')
        n_lo = st.number_input('Lower coil (kΩ)',
                               min_value=0.0, format='%.2f',
                               value=st.session_state.get('n_lo', 0.0),
                               key='n_lo')
    
    with col2:
        st.write('**Bridge Pickup**')
        b_up = st.number_input('Upper coil (kΩ)',
                               min_value=0.0, format='%.2f',
                               value=st.session_state.get('b_up', 0.0),
                               key='b_up')
        b_lo = st.number_input('Lower coil (kΩ)',
                               min_value=0.0, format='%.2f',
                               value=st.session_state.get('b_lo', 0.0),
                               key='b_lo')
    
    st.markdown('---')
    
    # Section 4: Map wires to coils
    st.subheader('4️⃣ Map Wires to Coils')
    st.write('Select which wire colors belong to the Upper (North) and Lower (South) coils.')
    
    neck_colors_current = st.session_state.get('wire_colors_neck', defaults[:wire_count])
    bridge_colors_current = st.session_state.get('wire_colors_bridge', defaults[:wire_count])
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.write('**Neck Pickup**')
        st.multiselect(
            'Upper Coil wires',
            neck_colors_current,
            default=st.session_state.get('neck_north_wires', neck_colors_current[:2] if len(neck_colors_current) >= 2 else neck_colors_current),
            max_selections=2,
            key='neck_north_wires',
            label_visibility='collapsed'
        )
        st.multiselect(
            'Lower Coil wires',
            neck_colors_current,
            default=st.session_state.get('neck_south_wires', neck_colors_current[2:] if len(neck_colors_current) > 2 else []),
            max_selections=2,
            key='neck_south_wires',
            label_visibility='collapsed'
        )
    
    with col2:
        st.write('**Bridge Pickup**')
        st.multiselect(
            'Upper Coil wires',
            bridge_colors_current,
            default=st.session_state.get('bridge_north_wires', bridge_colors_current[:2] if len(bridge_colors_current) >= 2 else bridge_colors_current),
            max_selections=2,
            key='bridge_north_wires',
            label_visibility='collapsed'
        )
        st.multiselect(
            'Lower Coil wires',
            bridge_colors_current,
            default=st.session_state.get('bridge_south_wires', bridge_colors_current[2:] if len(bridge_colors_current) > 2 else []),
            max_selections=2,
            key='bridge_south_wires',
            label_visibility='collapsed'
        )
    
    # Validate selections before proceeding
    st.markdown('---')
    valid_neck = len(st.session_state.get('neck_north_wires', [])) == 2 and len(st.session_state.get('neck_south_wires', [])) == 2
    valid_bridge = len(st.session_state.get('bridge_north_wires', [])) == 2 and len(st.session_state.get('bridge_south_wires', [])) == 2
    if valid_neck and valid_bridge:
        st.success('Wires assigned ✔ — you can continue to the next step.')
    else:
        st.warning('Select exactly two wires for each coil (Upper and Lower) on both pickups.')

    # Allow saving and advancing to Step 5
    cols_save = st.columns([1,1])
    with cols_save[0]:
        if st.button('Save wiring selections'):
            st.session_state['wire_colors_neck'] = neck_colors_current
            st.session_state['wire_colors_bridge'] = bridge_colors_current
            st.success('Saved wire selections.')
    with cols_save[1]:
        if st.button('Save & continue to Step 5'):
            st.session_state['wire_colors_neck'] = neck_colors_current
            st.session_state['wire_colors_bridge'] = bridge_colors_current
            if valid_neck and valid_bridge:
                st.session_state['step'] = 5
                st.success('Saved and moving to Step 5...')
            else:
                st.error('Please select two wires per coil for neck and bridge before continuing.')

    st.markdown('---')

    # Section 5: Visual wire diagram
    st.subheader('5️⃣ Wire Diagram')
    
    def _build_simple_wire_diagram(colors, pickup_name='Pickup'):
        """Build a simple SVG showing wires connected to upper/lower coils."""
        svg_parts = [
            f'<svg width="300" height="200" viewBox="0 0 300 200" xmlns="http://www.w3.org/2000/svg">',
            f'<text x="150" y="20" text-anchor="middle" font-size="16" font-weight="bold" fill="white">{pickup_name}</text>',
        ]
        
        # Draw coil boxes
        svg_parts.append('<rect x="20" y="40" width="80" height="40" rx="4" fill="none" stroke="#ccc" stroke-width="2"/>')
        svg_parts.append('<text x="60" y="65" text-anchor="middle" font-size="12" fill="white">Upper</text>')
        svg_parts.append('<rect x="20" y="100" width="80" height="40" rx="4" fill="none" stroke="#ccc" stroke-width="2"/>')
        svg_parts.append('<text x="60" y="125" text-anchor="middle" font-size="12" fill="white">Lower</text>')
        
        # Draw wires on the right
        color_map = {
            'Red': '#d62728',
            'White': '#ffffff',
            'Green': '#2ca02c',
            'Black': '#111111',
            'Yellow': '#ffbf00',
            'Blue': '#1f77b4'
        }
        
        y_positions = [60, 80, 120, 140]
        for i, color in enumerate(colors[:4]):
            hex_color = color_map.get(color, '#888888')
            y = y_positions[i]
            # Draw line from coil to wire
            if i < 2:
                svg_parts.append(f'<line x1="100" y1="60" x2="200" y2="{y}" stroke="{hex_color}" stroke-width="2"/>')
            else:
                svg_parts.append(f'<line x1="100" y1="120" x2="200" y2="{y}" stroke="{hex_color}" stroke-width="2"/>')
            # Draw wire circle
            svg_parts.append(f'<circle cx="240" cy="{y}" r="8" fill="{hex_color}" stroke="#222" stroke-width="1"/>')
            # Wire label
            svg_parts.append(f'<text x="260" y="{y+4}" font-size="11" fill="white">{color}</text>')
        
        svg_parts.append('</svg>')
        return ''.join(svg_parts)
    
    col1, col2 = st.columns(2)
    with col1:
        neck_svg = _build_simple_wire_diagram(st.session_state.get('wire_colors_neck', defaults[:wire_count]), 'Neck')
        components.html(neck_svg, height=220)
    
    with col2:
        bridge_svg = _build_simple_wire_diagram(st.session_state.get('wire_colors_bridge', defaults[:wire_count]), 'Bridge')
        components.html(bridge_svg, height=220)
    
    st.success('✅ Step 4 complete! Your wire configuration is saved.')
