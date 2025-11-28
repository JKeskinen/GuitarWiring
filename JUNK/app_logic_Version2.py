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
        a,b = k.split("-")
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
    # Koska emme tiedä kelan arvoa, etsimme suhteellisia pienimpiä arvoja ja summamalleja.
    cand = []
    uniq_pairs = set()
    for a in wires:
        for b in wires:
            if a==b: continue
            if (a,b) in uniq_pairs: continue
            uniq_pairs.add((a,b))
            key = (a,b)
            if key in pairs:
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
        if 10 <= r <= 20000:
            chosen.append((a,b,r))
            used.add(a); used.add(b)
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
    # etsi johto, joka on yhteinen kelaparissa (esim. A-B ja B-C -> B on yhteinen)
    names = [coil1[0], coil1[1], coil2[0], coil2[1]]
    for w in set(names):
        # tarkista jatkuvuus w->molempiin muihin ja summat
        other_coil1 = coil1[0] if coil1[1]==w else (coil1[1] if coil1[0]==w else None)
        other_coil2 = coil2[0] if coil2[1]==w else (coil2[1] if coil2[0]==w else None)
        # Simpukka: helpompi lasku: tarkista jokaisen vastuksen olemassaolo w-x
        # Jos w on keskitappi, sen pitäisi näyttää resistansseina noin coil_a_part ja coil_b_part.
        # Tässä yksinkertaisessa heuristiikassa etsimme johtoa jolla on jatkuvuus molempiin kelapareihin.
        count = 0
        for x in set(names):
            if x==w: continue
            k = (w,x)
            if k in pairs and not math.isinf(pairs[k]):
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
    explanation_lines.append("Detected coil pairs:")
    for (a,b,r) in pairs:
        explanation_lines.append(f" - {a} <--> {b}  (measured {r:.1f} Ω)")
    if center_tap:
        explanation_lines.append(f"Center tap likely: {center_tap}")
        suggestions.append("Coil‑split/tap: keskimmäinen johto on keskitappi. Katso valmistajan kaavio ennen juotoksia.")
    else:
        explanation_lines.append("No obvious center tap detected.")
    # Phase hint
    explanation_lines.append("Phase check: If two pickups together sound thin, swap hot and ground of one pickup.")
    # Simple ASCII diagram generator (very basic)
    diagram.append("ASCII connection proposal (hot -> tip, ground -> sleeve):")
    # assume pairs[0] = coil A, pairs[1] = coil B
    if len(pairs) >= 2:
        a1,a2,_ = pairs[0]
        b1,b2,_ = pairs[1]
        diagram.append(f" Coil1: ({a1})---[windings]---({a2})")
        diagram.append(f" Coil2: ({b1})---[windings]---({b2})")
        if center_tap:
            diagram.append(f" Center tap: {center_tap} (connect per split wiring)")
    else:
        diagram.append(" Not enough detected coils to draw detailed diagram.")
    return {
        "explanation": "\n".join(explanation_lines),
        "ascii_diagram": "\n".join(diagram),
        "suggestions": "\n".join(suggestions)
    }

if __name__ == "__main__":
    # small local test
    sample = {
        "red-white": 7200.0,
        "white-black": 7200.0,
        "red-black": 14400.0,
        "red-bare": 0.5,
        "black-bare": 0.6,
        "white-bare": 0.55
    }
    pairs = find_coil_pairs(sample)
    center = detect_center_tap(sample, pairs)
    plan = make_connection_plan(pairs, center, ["red","white","black","bare"])
    print(plan["explanation"])
    print(plan["ascii_diagram"])