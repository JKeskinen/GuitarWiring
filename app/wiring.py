"""Helper functions for humbucker wiring analysis and small SVG preview.

This module is intentionally small and dependency-free so it can be imported
from a minimal `main.py` Streamlit app.
"""
from typing import List, Dict, Optional

# Manufacturer / preset color maps (Bare Knuckle + generic 4-conductor fallback)
MANUFACTURER_COLORS = {
    'Bare Knuckle': {
        'north_start': 'Red',
        'north_finish': 'White',
        'south_start': 'Green',
        'south_finish': 'Black',
        'bare': 'Bare'
    },
    'Generic 4-conductor': {
        'north_start': 'Red',
        'north_finish': 'White',
        'south_start': 'Green',
        'south_finish': 'Black',
        'bare': 'Bare'
    }
}

# Wiring presets (names map to role names used in manufacturer maps)
WIRING_PRESETS = {
    'Series Humbucking': {'HOT': ['north_start'], 'SERIES_LINK': ['north_finish', 'south_start'], 'GROUND': ['south_finish']},
    'Parallel Humbucking': {'HOT': ['north_start', 'south_start'], 'SERIES_LINK': [], 'GROUND': ['south_finish']},
    'Slug Coil Only': {'HOT': ['north_start'], 'SERIES_LINK': [], 'GROUND': ['south_finish']},
    'Screw Coil Only': {'HOT': ['south_start'], 'SERIES_LINK': [], 'GROUND': ['south_finish']}
}


def _probe_is_normal(choice: Optional[str]) -> bool:
    """Return True when the probe/tap result indicates NORMAL phase.

    Normal = when touching the pole piece causes a momentary increase in
    displayed resistance ("Nousee (normaali)").
    """
    if not choice:
        return False
    c = str(choice).lower()
    return 'nousee' in c or 'increase' in c or 'normaali' in c or 'normal' in c


def _probe_is_reverse(choice: Optional[str]) -> bool:
    if not choice:
        return False
    c = str(choice).lower()
    return 'laskee' in c or 'decrease' in c or 'käänte' in c or 'reverse' in c


def choose_pair_roles(pair_colors: List[str], phase_choice: Optional[str], swap: bool = False) -> Dict[str, Optional[str]]:
    """Given a pair (2 colors) and the probe observation, return start/finish.

    If probe is normal -> first is start, second is finish.
    If reverse -> swapped.
    `swap` allows manual inversion after measurement.
    """
    if not pair_colors or len(pair_colors) < 2:
        return {'start': None, 'finish': None}
    first, second = pair_colors[0], pair_colors[1]
    if _probe_is_normal(phase_choice):
        start, finish = first, second
    else:
        start, finish = second, first
    if swap:
        start, finish = finish, start
    return {'start': start, 'finish': finish}


def infer_start_finish_from_probes(pair_colors: List[str], red_wire: Optional[str], black_wire: Optional[str],
                                  probe_choice: Optional[str], swap: bool = False) -> Dict[str, Optional[str]]:
    """Infer start/finish for a coil using explicit probe->wire selections.

    Logic:
    - If both `red_wire` and `black_wire` are present and match the pair, use the probe result
      (`_probe_is_normal`) to set the touched wire as START when normal, otherwise as FINISH.
    - If only one probe-wire is provided and it matches the pair, treat the touched wire as START
      when probe indicates normal, otherwise prefer the other wire as START.
    - If no matching probe-wire information is available, fall back to `choose_pair_roles()` which
      uses the pair ordering and the probe choice.

    This function preserves the `swap` manual override.
    """
    if not pair_colors or len(pair_colors) < 2:
        return {'start': None, 'finish': None}

    # normalize strings for comparison (keep original casing in return)
    pair_set = set(pair_colors)

    # helper to pick the other color in the pair
    def other(color: str) -> Optional[str]:
        for c in pair_colors:
            if c != color:
                return c
        return None

    start = None
    finish = None

    # Both probes provided and match the pair
    if red_wire and black_wire and red_wire in pair_set and black_wire in pair_set:
        if _probe_is_normal(probe_choice):
            start = red_wire
            finish = other(start)
        else:
            start = black_wire
            finish = other(start)
    # Only red probe specified and it matches
    elif red_wire and red_wire in pair_set:
        if _probe_is_normal(probe_choice):
            start = red_wire
        else:
            start = other(red_wire)
        finish = other(start)
    # Only black probe specified and it matches
    elif black_wire and black_wire in pair_set:
        if _probe_is_normal(probe_choice):
            start = black_wire
        else:
            start = other(black_wire)
        finish = other(start)
    else:
        # No explicit probe-wire mapping; fall back to existing ordering logic
        return choose_pair_roles(pair_colors, probe_choice, swap)

    if swap:
        start, finish = finish, start

    return {'start': start, 'finish': finish}


def analyze_pickup(north_pair: List[str], south_pair: List[str], north_probe: Optional[str], south_probe: Optional[str],
                   north_swap: bool = False, south_swap: bool = False, bare: bool = False,
                   north_res_kohm: Optional[float] = None, south_res_kohm: Optional[float] = None,
                   north_red_wire: Optional[str] = None, north_black_wire: Optional[str] = None,
                   south_red_wire: Optional[str] = None, south_black_wire: Optional[str] = None) -> Dict:
    """Analyze pickup mapping and compute suggested wiring.

    Returns dict with HOT, SERIES_LINK, GROUND and resistance estimates.
    """
    # Prefer explicit probe->wire mapping when available to determine start/finish
    north = infer_start_finish_from_probes(north_pair, north_red_wire, north_black_wire, north_probe, north_swap)
    south = infer_start_finish_from_probes(south_pair, south_red_wire, south_black_wire, south_probe, south_swap)

    mapping = {
        'north_start': north.get('start'),
        'north_finish': north.get('finish'),
        'south_start': south.get('start'),
        'south_finish': south.get('finish'),
    }

    result = {
        'HOT': mapping['north_start'],
        'SERIES_LINK': [mapping['north_finish'], mapping['south_start']],
        'GROUND': [mapping['south_finish'], 'Bare' if bare else None]
    }

    # Resistances
    r_n = north_res_kohm
    r_s = south_res_kohm
    series = None
    parallel = None
    try:
        if r_n is not None and r_s is not None:
            series = float(r_n) + float(r_s)
            if (r_n + r_s) > 0:
                parallel = float(r_n) * float(r_s) / (float(r_n) + float(r_s))
    except Exception:
        series = None
        parallel = None

    result['resistance_kohm'] = {'north_kohm': r_n, 'south_kohm': r_s, 'series_kohm': series, 'parallel_kohm': parallel}
    return result


def compute_electrical_polarity_from_probe(pair_colors: List[str], red_wire: Optional[str], black_wire: Optional[str],
                                           probe_choice: Optional[str], swap: bool = False) -> Dict[str, Optional[str]]:
    """Compute which wire appears electrically positive ('+') for a coil using probe info.

    Returns a dict: {
        'positive_wire': <color or None>,
        'start': <start color or None>,
        'finish': <finish color or None>,
        'start_sign': '+' or '-' or None,
        'finish_sign': '+' or '-' or None
    }

    Heuristic used:
    - If both `red_wire` and `black_wire` are provided and match the pair:
        - If probe is NORMAL (meter rises when touching) => the wire touched by the RED probe behaves as '+'
        - If probe is REVERSE (meter falls when touching) => the wire touched by the BLACK probe behaves as '+'
    - If only one probe-wire is given, prefer that rule and assign '+' to it when possible.
    - Fall back to `infer_start_finish_from_probes()` for start/finish when mapping is ambiguous.
    - `swap` inverts start/finish after mapping (keeps parity with other helpers).
    """
    if not pair_colors or len(pair_colors) < 2:
        return {'positive_wire': None, 'start': None, 'finish': None, 'start_sign': None, 'finish_sign': None}

    # Use existing inference to obtain start/finish as baseline
    baseline = infer_start_finish_from_probes(pair_colors, red_wire, black_wire, probe_choice, swap)
    start = baseline.get('start')
    finish = baseline.get('finish')

    # Decide which wire is electrically '+' based on probe behavior
    positive = None
    if red_wire and black_wire and red_wire in pair_colors and black_wire in pair_colors and probe_choice:
        if _probe_is_normal(probe_choice):
            positive = red_wire
        else:
            positive = black_wire
    elif red_wire and red_wire in pair_colors and probe_choice:
        positive = red_wire if _probe_is_normal(probe_choice) else None
    elif black_wire and black_wire in pair_colors and probe_choice:
        positive = black_wire if not _probe_is_normal(probe_choice) else None

    # Assign signs relative to start/finish: the wire that equals `positive` is '+'
    start_sign = '+' if positive and start and positive == start else ('-' if start else None)
    finish_sign = '+' if positive and finish and positive == finish else ('-' if finish else None)

    return {'positive_wire': positive, 'start': start, 'finish': finish, 'start_sign': start_sign, 'finish_sign': finish_sign}


def simple_humbucker_svg(colors: List[str], roles: Dict[str, List[int]] = None, title: str = 'Humbucker') -> str:
    """Create a very small inline SVG showing up to 4 colored dots and optional role labels.

    `colors` is a list like ['Red','White','Green','Black']
    `roles` is a dict mapping role name -> list of indices in colors to label (e.g. {'HOT':[0], 'SERIES':[1,2]})
    Returns an HTML string (SVG) suitable for `components.html`.
    """
    # color name -> hex fallback
    COLOR_HEX = {
        'Red': '#d62728',
        'White': '#ffffff',
        'Green': '#2ca02c',
        'Black': '#111111',
        'Yellow': '#ffbf00',
        'Bare': '#888888'
    }
    w = 320
    h = 80
    dot_x_start = 60
    spacing = 50
    svg_parts = [f"<svg width=\"{w}\" height=\"{h}\" viewBox=\"0 0 {w} {h}\" xmlns=\"http://www.w3.org/2000/svg\">"]
    svg_parts.append(f"<text x=\"12\" y=\"18\" font-family=\"sans-serif\" font-size=14>{title}</text>")
    for i in range(min(4, len(colors))):
        cx = dot_x_start + i * spacing
        cy = 44
        col = COLOR_HEX.get(colors[i], '#cccccc')
        svg_parts.append(f"<circle cx=\"{cx}\" cy=\"{cy}\" r=\"12\" fill=\"{col}\" stroke=\"#222\" stroke-width=1 />")
        # Draw a contrasting initial inside the colored ball (white for most colors)
        initial = (colors[i][0] if colors[i] else '?').upper()
        # Choose black text for very light fills
        light_text_colors = {'#ffffff', '#ffbf00'}
        text_fill = '#ffffff' if col.lower() not in light_text_colors else '#111111'
        svg_parts.append(f"<text x=\"{cx}\" y=\"{cy}\" text-anchor=\"middle\" dominant-baseline=\"middle\" font-size=11 font-family=\"sans-serif\" fill=\"{text_fill}\">{initial}</text>")
        svg_parts.append(f"<text x=\"{cx}\" y=\"{cy+28}\" text-anchor=\"middle\" font-size=11 font-family=\"sans-serif\">{colors[i]}</text>")

    # role labels
    if roles:
        label_y = 16
        for role, idxs in (roles.items() if isinstance(roles, dict) else []):
            for idx in idxs:
                if 0 <= idx < len(colors):
                    lx = dot_x_start + idx * spacing
                    svg_parts.append(f"<text x=\"{lx}\" y=\"{label_y}\" text-anchor=\"middle\" font-size=11 font-family=\"sans-serif\" fill=\"#ff7f0e\">{role}</text>")

    svg_parts.append('</svg>')
    return '\n'.join(svg_parts)
