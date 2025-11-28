"""
Mittausanalyysi ja päätöslogiikka humbucker-tyyppisille pickupille.

Funktiot:
- find_coil_pairs(measurements): tunnistaa jotka johtimet muodostavat kelan (per mittausmatriisi)
- detect_center_tap(measurements, threshold): yrittää tunnistaa keskitapin
- make_connection_plan(pairs, center_tap, wire_names): muodostaa kytkentäehdotuksen ja ASCII-diagrammin
"""

from typing import Dict, Tuple, List, Optional
import math

# measurements: dict with keys like "A-B" -> ohms (float)
# wire_names: list of str, e.g. ["red","white","black","green","bare"]

def pair_key(a: str, b: str) -> str:
    return f"{a}-{b}"

def parse_measurements_table(measurements: Dict[str, float]) -> Tuple[List[str], Dict[Tuple[str,str], float]]:
    """Normalize measurements dict to tuple keys and gather unique wires."""
    pairs = {}
    wires = set()
    for k, v in measurements.items():
        if not isinstance(k, str):
            continue
        parts = k.split("-")
        if len(parts) != 2:
            continue
        a,b = parts
        a=a.strip(); b=b.strip()
        wires.add(a); wires.add(b)
        pairs[(a,b)] = v
        pairs[(b,a)] = v
    return list(wires), pairs

def find_coil_pairs(measurements: Dict[str, float], tolerance: float = 0.25) -> List[Tuple[str,str,float]]:
    """
    Etsi todennäköiset kelaparit: etsi mitkä kaksi johtoa ovat "kelan päät"
    Käytämme heuristiikkaa: kelan vastus on kilo-ohmeissa ja sarja-kytkentä näkyy summana.
    tolerance on suhteellinen sallittu poikkeama (25%).
    """
    wires, pairs = parse_measurements_table(measurements)
    # Etsi kaikki mahdolliset parit ja valitse ne, joiden resistanssi on "kelan luokkaa".
    cand = []
    uniq_pairs = set()
    for a in wires:
        for b in wires:
            if a==b: continue
            key = (a,b)
            if key in uniq_pairs: continue
            uniq_pairs.add(key)
            if key in pairs:
                val = pairs[key]
                try:
                    if math.isnan(val):
                        continue
                except Exception:
                    pass
                cand.append((a,b,pairs[key]))
    # Sort by resistance ascending
    cand_sorted = sorted(cand, key=lambda x: x[2])
    # Heuristisesti: kysele pienimmistä arvoista kelan parit
    chosen = []
    used = set()
    for a,b,r in cand_sorted:
        if a in used or b in used:
            continue
        # Accept if r > 10 and r < 20000 ohm (10Ω - 20kΩ heuristic)
        if r is None:
            continue
        try:
            if 10 <= r <= 20000:
                chosen.append((a,b,r))
                used.add(a); used.add(b)
        except Exception:
            continue
    return chosen

def detect_center_tap(measurements: Dict[str, float], pairs_found: List[Tuple[str,str,float]], tol: float = 0.25) -> Optional[str]:
    """
    Jos löytyy johto, joka on jatkuva molempiin keloihin ja resistanssit summaan suhteutettuna, 
    tulkitaan se center tapiksi.
    """
    wires, pairs = parse_measurements_table(measurements)
    if len(pairs_found) < 2:
        return None
    coil1 = pairs_found[0]
    coil2 = pairs_found[1]
    names = [coil1[0], coil1[1], coil2[0], coil2[1]]
    for w in set(names):
        count = 0
        for x in set(names):
            if x==w: continue
            k = (w,x)
            if k in pairs:
                try:
                    if not math.isinf(pairs[k]):
                        count += 1
                except Exception:
                    count += 1
        if count >= 2:
            return w
    return None

def make_connection_plan(pairs: List[Tuple[str,str,float]], center_tap: Optional[str], wire_names: List[str]) -> Dict[str, str]:
    """
    Luo yksinkertainen kytkentäehdotus tekstimuotoisena.
    Palauttaa dict: keys: explanation, ascii_diagram, suggestions
    """
    explanation_lines = []
    diagram = []
    suggestions = []
    explanation_lines.append("Havaitut kelaparit:")
    for (a,b,r) in pairs:
        explanation_lines.append(f" - {a} <--> {b}  (mitattu {r:.1f} Ω)")
    if center_tap:
        explanation_lines.append(f"Keskitappi todennäköinen: {center_tap}")
        suggestions.append("Kelajako/keskitappi: keskimmäinen johto on keskitappi. Katso valmistajan kaavio ennen juotoksia.")
    else:
        explanation_lines.append("Ei havaittua keskitappia.")
    explanation_lines.append("Vaiheen tarkistus: Jos kahden mikin yhdistelmä kuulostaa kapealta/ohueltä, vaihda yhden mikin hot ja maa -liitännät tai käännä johtojen suunta.")
    diagram.append("ASCII-kytkentäehdotus (hot -> tip, ground -> sleeve):")
    if len(pairs) >= 2:
        a1,a2,_ = pairs[0]
        b1,b2,_ = pairs[1]
        # Show direction with arrows: start --> windings --> finish
        diagram.append(f" Coil1: ({a1})--->[windings]--->({a2})")
        diagram.append(f" Coil2: ({b1})--->[windings]--->({b2})")
        # Annotate HOT and GND directions (convention: hot = coil1 start, ground = coil2 finish)
        hot = a1
        gnd = b2
        diagram.append("")
        diagram.append(f" -> HOT (tuleva signaali)  --> {hot}")
        diagram.append(f" -> GND (maa, potikan runkoon) --> {gnd}")
        if center_tap:
            diagram.append(f" Keskitappi: {center_tap} (käytettävissä split- tai tap-kytkentään)")
    else:
        diagram.append(" Ei tarpeeksi kelapareja yksityiskohtaista diagrammia varten.")
    return {
        "explanation": "\n".join(explanation_lines),
        "ascii_diagram": "\n".join(diagram),
        "suggestions": "\n".join(suggestions)
    }


def compute_coil_resistances(pairs: List[Tuple[str,str,float]]) -> Dict[str, float]:
    """
    Given a list of detected pairs (a,b,resistance), compute basic resistances:
    - r1, r2: coil resistances (first two pairs)
    - series: r1 + r2
    - parallel: (r1*r2)/(r1+r2) if both non-zero

    Returns a dict with keys 'r1','r2','series','parallel'. If insufficient
    data is available, values may be None.
    """
    out = {"r1": None, "r2": None, "series": None, "parallel": None}
    if not pairs:
        return out
    # Use first pair as coil1
    try:
        a1, b1, r1 = pairs[0]
    except Exception:
        try:
            a1, b1 = pairs[0]
            r1 = None
        except Exception:
            return out
    out["r1"] = float(r1) if r1 is not None else None
    if len(pairs) >= 2:
        try:
            a2, b2, r2 = pairs[1]
        except Exception:
            try:
                a2, b2 = pairs[1]
                r2 = None
            except Exception:
                r2 = None
        out["r2"] = float(r2) if r2 is not None else None
    # Compute series and parallel when possible
    if out["r1"] is not None and out["r2"] is not None:
        r1v = out["r1"]
        r2v = out["r2"]
        out["series"] = r1v + r2v
        try:
            out["parallel"] = (r1v * r2v) / (r1v + r2v) if (r1v + r2v) != 0 else None
        except Exception:
            out["parallel"] = None
    return out


def humbucker_hum_cancel_analysis(polarity1: str, polarity2: str, windings_same: bool) -> Dict[str, str]:
    """
    Determine hum cancelling and output strength based on magnetic polarities
    of the two coils and whether their windings are the same or opposite.

    polarity1, polarity2: 'North' or 'South'
    windings_same: True if the coil windings are in the same direction, False if opposite

    Returns dict with keys: 'magnetic_relation', 'windings_relation', 'output_strength', 'hum_cancel' ('Yes'/'No')
    Based on the user's table:
    1) Same / Same -> Strong / No
    2) Opposite / Opposite -> Strong / Yes
    3) Same / Opposite -> Weak / Yes
    4) Opposite / Same -> Weak / No
    """
    mag_relation = 'Same' if polarity1 == polarity2 else 'Opposite'
    wind_relation = 'Same' if windings_same else 'Opposite'
    # Map to results
    if mag_relation == 'Same' and wind_relation == 'Same':
        return {"magnetic_relation": mag_relation, "windings_relation": wind_relation, "output_strength": "Strong", "hum_cancel": "No"}
    if mag_relation == 'Opposite' and wind_relation == 'Opposite':
        return {"magnetic_relation": mag_relation, "windings_relation": wind_relation, "output_strength": "Strong", "hum_cancel": "Yes"}
    if mag_relation == 'Same' and wind_relation == 'Opposite':
        return {"magnetic_relation": mag_relation, "windings_relation": wind_relation, "output_strength": "Weak", "hum_cancel": "Yes"}
    # Opposite / Same
    return {"magnetic_relation": mag_relation, "windings_relation": wind_relation, "output_strength": "Weak", "hum_cancel": "No"}

if __name__ == "__main__":
    # small local test
    sample = {
        "red-white": 7200.0,
        "white-black": 7200.0,
        "red-black": 14400.0,
        "red-bare": 0.5,
        "black-bare": 0.6,
        "white-bare": 0.55,
        "green-bare": 0.58
    }
    pairs = find_coil_pairs(sample)
    center = detect_center_tap(sample, pairs)
    plan = make_connection_plan(pairs, center, ["red","white","black","green","bare"])
    print(plan["explanation"])
    print(plan["ascii_diagram"])
